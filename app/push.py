"""Powiadomienia Web Push: klucze VAPID, szyfrowanie treści i wysyłka.

Powiadomienie o końcu fazy Pomodoro musi dotrzeć także wtedy, gdy karta jest
zamknięta albo telefon leży zablokowany — przeglądarka nie wykona wtedy
żadnego kodu strony. Dlatego koniec fazy planuje serwer (``ScheduledPush``),
a w umówionej chwili wysyła wiadomość przez usługę push przeglądarki
(Google, Mozilla, Apple). Tak działa to również na iPhonie z MTQuiz dodanym
do ekranu początkowego (iOS 16.4+).

Implementacja trzyma się standardów bez dodatkowych bibliotek:
- RFC 8291 — szyfrowanie treści (ECDH P-256 + HKDF + AES-128-GCM, ``aes128gcm``),
- RFC 8292 — uwierzytelnienie serwera tokenem VAPID (JWT ES256),
- RFC 8030 — sam protokół (nagłówki ``TTL`` i ``Urgency``).
"""
from __future__ import annotations

import asyncio
import base64
import json
import logging
import os
import struct
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from datetime import timedelta
from functools import lru_cache
from urllib.parse import urlsplit

import jwt
from cryptography.hazmat.primitives import hashes, hmac, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from sqlalchemy import delete, select, update

from .config import settings
from .database import session_scope
from .models import PushSubscription, ScheduledPush, utcnow

logger = logging.getLogger("mtquiz")

VAPID_KEY_FILE = ".vapid_private.pem"
RECORD_SIZE = 4096
# Powiadomienie spóźnione o więcej (np. po restarcie serwera) nie ma już sensu.
MAX_DELAY = timedelta(minutes=5)
DISPATCH_INTERVAL = 2.0


def b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def b64url_decode(value: str) -> bytes:
    value = value.strip()
    return base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))


@dataclass(frozen=True)
class VapidKeys:
    private_key: ec.EllipticCurvePrivateKey
    # Klucz publiczny w postaci przyjmowanej przez ``pushManager.subscribe``.
    public_key: str


def _public_bytes(key: ec.EllipticCurvePrivateKey) -> bytes:
    return key.public_key().public_bytes(serialization.Encoding.X962, serialization.PublicFormat.UncompressedPoint)


@lru_cache(maxsize=4)
def _load_vapid(path: str) -> VapidKeys:
    key_file = settings.data_dir / VAPID_KEY_FILE
    if key_file.exists():
        private_key = serialization.load_pem_private_key(key_file.read_bytes(), password=None)
    else:
        # Klucz powstaje raz i zostaje w wolumenie danych — jego zmiana unieważniłaby
        # subskrypcje wszystkich przeglądarek.
        private_key = ec.generate_private_key(ec.SECP256R1())
        settings.ensure_directories()
        key_file.write_bytes(
            private_key.private_bytes(
                serialization.Encoding.PEM,
                serialization.PrivateFormat.PKCS8,
                serialization.NoEncryption(),
            )
        )
        try:
            key_file.chmod(0o600)
        except OSError:  # pragma: no cover - zależne od systemu plików
            pass
    return VapidKeys(private_key=private_key, public_key=b64url(_public_bytes(private_key)))


def vapid_keys() -> VapidKeys:
    return _load_vapid(str(settings.data_dir))


def _hmac_sha256(key: bytes, data: bytes) -> bytes:
    digest = hmac.HMAC(key, hashes.SHA256())
    digest.update(data)
    return digest.finalize()


def encrypt_payload(
    payload: bytes,
    p256dh: str,
    auth: str,
    *,
    salt: bytes | None = None,
    server_key: ec.EllipticCurvePrivateKey | None = None,
) -> bytes:
    """Szyfruje treść wiadomości dla jednej subskrypcji (RFC 8291, kodowanie ``aes128gcm``).

    ``salt`` i ``server_key`` są parametrami wyłącznie na potrzeby testów
    z wektorami z RFC — w normalnej pracy każda wiadomość dostaje nowe.
    """
    ua_public = b64url_decode(p256dh)
    auth_secret = b64url_decode(auth)
    ua_key = ec.EllipticCurvePublicKey.from_encoded_point(ec.SECP256R1(), ua_public)

    server_key = server_key or ec.generate_private_key(ec.SECP256R1())
    as_public = _public_bytes(server_key)
    shared_secret = server_key.exchange(ec.ECDH(), ua_key)

    # HKDF w dwóch krokach: najpierw sekret wspólny wiązany z sekretem subskrypcji…
    prk_key = _hmac_sha256(auth_secret, shared_secret)
    ikm = _hmac_sha256(prk_key, b"WebPush: info\x00" + ua_public + as_public + b"\x01")
    # …potem klucz treści i nonce z losowej soli.
    salt = salt or os.urandom(16)
    prk = _hmac_sha256(salt, ikm)
    cek = _hmac_sha256(prk, b"Content-Encoding: aes128gcm\x00\x01")[:16]
    nonce = _hmac_sha256(prk, b"Content-Encoding: nonce\x00\x01")[:12]

    # Jeden rekord: treść + ogranicznik 0x02 oznaczający rekord ostatni.
    ciphertext = AESGCM(cek).encrypt(nonce, payload + b"\x02", None)
    header = salt + struct.pack("!I", RECORD_SIZE) + bytes([len(as_public)]) + as_public
    return header + ciphertext


def vapid_authorization(endpoint: str, keys: VapidKeys | None = None) -> str:
    """Nagłówek ``Authorization`` z tokenem VAPID dla usługi push danego adresu."""
    keys = keys or vapid_keys()
    parts = urlsplit(endpoint)
    claims = {
        "aud": f"{parts.scheme}://{parts.netloc}",
        "exp": int(time.time()) + 12 * 3600,
        "sub": settings.push_contact,
    }
    token = jwt.encode(claims, keys.private_key, algorithm="ES256")
    return f"vapid t={token}, k={keys.public_key}"


def send_push(subscription: PushSubscription, message: dict, *, ttl: int = 600) -> int:
    """Wysyła jedną wiadomość. Zwraca kod HTTP usługi push (0 — brak połączenia)."""
    body = encrypt_payload(
        json.dumps(message, ensure_ascii=False).encode("utf-8"), subscription.p256dh, subscription.auth
    )
    request = urllib.request.Request(
        subscription.endpoint,
        data=body,
        method="POST",
        headers={
            "Authorization": vapid_authorization(subscription.endpoint),
            "Content-Encoding": "aes128gcm",
            "Content-Type": "application/octet-stream",
            "TTL": str(ttl),
            "Urgency": "high",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=10) as response:
            return response.status
    except urllib.error.HTTPError as exc:
        detail = exc.read()[:200].decode("utf-8", "replace")
        logger.info("Usługa push odrzuciła wiadomość (%s): %s", exc.code, detail)
        return exc.code
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        logger.warning("Brak połączenia z usługą push: %s", exc)
        return 0


def deliver_to_user(user_id: int, message: dict) -> int:
    """Wysyła wiadomość na wszystkie urządzenia konta; zwraca liczbę doręczeń.

    Subskrypcje odrzucone przez usługę jako wygasłe (404, 410) są usuwane.
    """
    with session_scope() as db:
        subscriptions = list(db.scalars(select(PushSubscription).where(PushSubscription.user_id == user_id)))
        db.expunge_all()

    delivered = 0
    for subscription in subscriptions:
        status = send_push(subscription, message)
        with session_scope() as db:
            if status in (404, 410):
                db.execute(delete(PushSubscription).where(PushSubscription.id == subscription.id))
            elif 200 <= status < 300:
                delivered += 1
                db.execute(
                    update(PushSubscription)
                    .where(PushSubscription.id == subscription.id)
                    .values(last_success_at=utcnow())
                )
    return delivered


def dispatch_due(now=None) -> int:
    """Wysyła powiadomienia, których czas nadszedł. Zwraca liczbę obsłużonych pozycji."""
    now = now or utcnow()
    with session_scope() as db:
        due = list(
            db.scalars(
                select(ScheduledPush)
                .where(ScheduledPush.sent_at.is_(None), ScheduledPush.fire_at <= now)
                .order_by(ScheduledPush.fire_at)
                .limit(50)
            )
        )
        claimed = []
        for item in due:
            # Oznaczenie przed wysyłką: przy dwóch procesach wiadomość nie pójdzie dwa razy.
            result = db.execute(
                update(ScheduledPush)
                .where(ScheduledPush.id == item.id, ScheduledPush.sent_at.is_(None))
                .values(sent_at=now)
            )
            fire_at = item.fire_at if item.fire_at.tzinfo else item.fire_at.replace(tzinfo=now.tzinfo)
            if result.rowcount and now - fire_at <= MAX_DELAY:
                claimed.append(
                    (item.user_id, {"title": item.title, "body": item.body, "url": item.url, "tag": "mtquiz-pomodoro"})
                )
        # Wysłane dawniej niż dobę temu nie są już potrzebne.
        db.execute(delete(ScheduledPush).where(ScheduledPush.sent_at < now - timedelta(days=1)))

    for user_id, message in claimed:
        deliver_to_user(user_id, message)
    return len(due)


async def run_dispatcher() -> None:
    """Pętla w tle procesu aplikacji — co kilka sekund sprawdza zaplanowane powiadomienia."""
    while True:
        try:
            await asyncio.to_thread(dispatch_due)
        except asyncio.CancelledError:  # pragma: no cover - zamykanie aplikacji
            raise
        except Exception:  # noqa: BLE001 - błąd jednej rundy nie może zatrzymać pętli
            logger.exception("Błąd wysyłki powiadomień push.")
        await asyncio.sleep(DISPATCH_INTERVAL)

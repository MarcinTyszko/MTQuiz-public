#!/usr/bin/env bash
# Instaluje proces transkrybujący jako usługę systemd użytkownika.
#
# Po instalacji transkrypcja działa sama: usługa startuje przy uruchomieniu
# maszyny, wstaje po awarii i nie wymaga otwartego terminala.
#
#   ./scripts/zainstaluj-usluge.sh              # instalacja i start
#   ./scripts/zainstaluj-usluge.sh --usun       # usunięcie usługi
#
# Nie wymaga uprawnień administratora. Jedynym krokiem, który może o nie
# poprosić, jest włączenie trybu „linger” — dzięki niemu usługa działa także
# wtedy, gdy nikt nie jest zalogowany graficznie.
set -euo pipefail

KATALOG="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
NAZWA="mtquiz-transkrypcja.service"
KATALOG_USLUG="$HOME/.config/systemd/user"
PLIK_USLUGI="$KATALOG_USLUG/$NAZWA"

if ! systemctl --user is-system-running >/dev/null 2>&1; then
  echo "Błąd: systemd użytkownika nie działa w tej sesji." >&2
  echo "Uruchom proces ręcznie: ./scripts/transkrypcja-worker.sh" >&2
  exit 1
fi

if [ "${1:-}" = "--usun" ]; then
  systemctl --user disable --now "$NAZWA" 2>/dev/null || true
  rm -f "$PLIK_USLUGI"
  systemctl --user daemon-reload
  echo "Usługa $NAZWA została usunięta."
  exit 0
fi

mkdir -p "$KATALOG_USLUG"

cat > "$PLIK_USLUGI" <<UNIT
[Unit]
Description=MTQuiz — proces transkrybujący nagrania
Documentation=file://$KATALOG/README.md
After=default.target

[Service]
Type=simple
WorkingDirectory=$KATALOG
ExecStart=$KATALOG/scripts/transkrypcja-worker.sh
Restart=always
RestartSec=10
# Model Whispera zajmuje kilka GB pamięci — nie zabijamy procesu zbyt wcześnie.
TimeoutStopSec=30
StandardOutput=journal
StandardError=journal
SyslogIdentifier=mtquiz-transkrypcja

[Install]
WantedBy=default.target
UNIT

systemctl --user daemon-reload
systemctl --user enable --now "$NAZWA"

echo "Usługa $NAZWA jest zainstalowana i uruchomiona."
echo

# Bez trybu „linger” usługa kończy się przy wylogowaniu użytkownika.
if [ "$(loginctl show-user "$USER" --property=Linger --value 2>/dev/null || echo no)" = "yes" ]; then
  echo "Tryb linger: włączony — usługa działa także bez zalogowania."
else
  if loginctl enable-linger "$USER" >/dev/null 2>&1; then
    echo "Tryb linger: właśnie włączony — usługa działa także bez zalogowania."
  else
    echo "Tryb linger: wyłączony. Usługa zatrzyma się przy wylogowaniu."
    echo "Aby działała niezależnie od sesji, wykonaj jednorazowo:"
    echo
    echo "    sudo loginctl enable-linger $USER"
  fi
fi

echo
echo "Przydatne polecenia:"
echo "    systemctl --user status mtquiz-transkrypcja     # stan usługi"
echo "    systemctl --user restart mtquiz-transkrypcja    # ponowne uruchomienie"
echo "    journalctl --user -u mtquiz-transkrypcja -f     # podgląd dziennika"

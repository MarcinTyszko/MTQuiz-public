#!/usr/bin/env bash
# Uruchamia proces transkrybujący MTQuiz na maszynie z kartą graficzną.
#
#   ./scripts/transkrypcja-worker.sh              # nasłuchuje w pętli
#   ./scripts/transkrypcja-worker.sh --raz        # przetwarza kolejkę i kończy
#   ./scripts/transkrypcja-worker.sh --cpu        # wymusza procesor
#
# Szuka interpretera z zainstalowanym faster-whisper w kolejności:
#   1. zmienna PYTHON_TRANSKRYPCJI
#   2. ./.venv-transkrypcja/bin/python
#   3. ./.venv/bin/python
#   4. ../Transkrypcja AI z dziadkami/.venv/bin/python   (środowisko z sąsiedniego projektu)
#   5. python3 z systemu
set -euo pipefail

KATALOG="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DANE="${QUIZAPP_DANE:-$KATALOG/data}"

znajdz_pythona() {
  local kandydaci=(
    "${PYTHON_TRANSKRYPCJI:-}"
    "$KATALOG/.venv-transkrypcja/bin/python"
    "$KATALOG/.venv/bin/python"
    "$KATALOG/../Transkrypcja AI z dziadkami/.venv/bin/python"
    "$(command -v python3 || true)"
  )
  for kandydat in "${kandydaci[@]}"; do
    [ -n "$kandydat" ] && [ -x "$kandydat" ] || continue
    if "$kandydat" -c "import faster_whisper" >/dev/null 2>&1; then
      echo "$kandydat"
      return 0
    fi
  done
  return 1
}

if ! PYTHON="$(znajdz_pythona)"; then
  cat >&2 <<'POMOC'
Nie znalazłem interpretera Pythona z pakietem faster-whisper.

Przygotuj środowisko jednorazowo:

    pip --python ./.venv-transkrypcja/bin/python install faster-whisper
    # albo wskaż istniejące środowisko:
    export PYTHON_TRANSKRYPCJI=/sciezka/do/.venv/bin/python

Na karcie NVIDIA potrzebne są też biblioteki CUDA:

    pip --python ./.venv-transkrypcja/bin/python install nvidia-cublas-cu12 nvidia-cudnn-cu12
POMOC
  exit 1
fi

# Biblioteki CUDA z pakietów pip muszą trafić na LD_LIBRARY_PATH PRZED startem
# Pythona — dynamiczny linker czyta tę zmienną przy uruchamianiu procesu, więc
# ustawienie jej z wnętrza skryptu jest już za późno.
CUDA_LIBS="$("$PYTHON" - <<'PYTHON'
import glob, os
try:
    import nvidia
except ImportError:
    print("")
else:
    sciezki = {p for baza in nvidia.__path__ for p in glob.glob(os.path.join(baza, "*", "lib"))}
    print(":".join(sorted(sciezki)))
PYTHON
)"

if [ -n "$CUDA_LIBS" ]; then
  export LD_LIBRARY_PATH="${CUDA_LIBS}${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}"
fi

echo "Interpreter: $PYTHON"
echo "Katalog danych: $DANE"
[ -n "$CUDA_LIBS" ] && echo "Biblioteki CUDA: znalezione" || echo "Biblioteki CUDA: brak (praca na procesorze)"
exec "$PYTHON" "$KATALOG/scripts/worker_transkrypcji.py" --dane "$DANE" "$@"

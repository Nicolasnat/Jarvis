#!/usr/bin/env bash
# Ajusta o ganho de captura do microfone.
#
# Em notebooks com DMIC (sofhdadsp) o controle 'Capture' vem de fabrica no
# maximo e o sinal chega estourado. Audio com clipping nao serve: nem o
# openwakeword reconhece a wakeword nem o whisper transcreve direito. O
# controle que manda no mic digital e o 'Dmic0', entao ajustamos os dois.
set -euo pipefail

NIVEL_CAPTURE="${1:-21}"   # 0-63  (63 = +30 dB)
NIVEL_DMIC="${2:-35}"      # 0-70  (70 = +20 dB)

command -v amixer >/dev/null 2>&1 || { echo "[mic] amixer nao encontrado."; exit 0; }

CARD=""
for card in $(seq 0 5); do
    amixer -c "$card" scontents 2>/dev/null | grep -q "Simple mixer control 'Capture'" || continue
    CARD="$card"
    break
done

if [ -z "$CARD" ]; then
    echo "[mic] Nenhum controle 'Capture' encontrado."
    exit 0
fi

ajustar() {
    local controle="$1" nivel="$2"
    amixer -c "$CARD" scontents 2>/dev/null | grep -q "Simple mixer control '$controle'" || return 0
    # Sem isto, o 'set -e' faz o script sair com erro quando a placa ainda nao
    # voltou no boot. Como este script roda em ExecStartPre, uma falha aqui
    # impede o Jarvis de comecar. Ajuste de ganho e nice-to-have, nunca motivo
    # para o assistente nao subir.
    amixer -c "$CARD" set "$controle" "$nivel" silent || echo "[mic] nao deu para ajustar '$controle'." >&2
    echo "[mic] '$controle' do card $CARD -> $nivel"
}

ajustar 'Dmic0' "$NIVEL_DMIC"
ajustar 'Capture' "$NIVEL_CAPTURE"

amixer -c "$CARD" get 'Capture' 2>/dev/null | sed 's/^/[mic] /'
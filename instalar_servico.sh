#!/usr/bin/env bash
# Instala e ativa o Jarvis como servico de usuario (systemd --user), para ele
# ficar rodando em segundo plano sem precisar abrir terminal.
set -euo pipefail

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DEST="$HOME/.config/systemd/user/jarvis.service"

mkdir -p "$(dirname "$DEST")"
sed "s|@PROJETO@|$DIR|g" "$DIR/jarvis.service" > "$DEST"

systemctl --user daemon-reload
systemctl --user enable --now jarvis.service

echo "Jarvis instalado e ativo."
echo "  status:  systemctl --user status jarvis"
echo "  logs:    journalctl --user -u jarvis -f"
echo "  parar:   systemctl --user stop jarvis"
echo "  remover: systemctl --user disable --now jarvis && rm $DEST"

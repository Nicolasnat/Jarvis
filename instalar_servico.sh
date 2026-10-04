#!/usr/bin/env bash
# Instala e ativa o Nexus como servico de usuario (systemd --user), para ele
# ficar rodando em segundo plano sem precisar abrir terminal.
set -euo pipefail

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DEST="$HOME/.config/systemd/user/nexus.service"

mkdir -p "$(dirname "$DEST")"
sed "s|@PROJETO@|$DIR|g" "$DIR/nexus.service" > "$DEST"

systemctl --user daemon-reload
# 'reenable' troca o alvo de instalacao antigo (default.target) pelo novo
# (graphical-session.target) sem deixar symlink duplicado.
systemctl --user reenable nexus.service
systemctl --user restart nexus.service

echo "Nexus instalado e ativo."
echo "  status:  systemctl --user status nexus"
echo "  logs:    journalctl --user -u nexus -f"
echo "  parar:   systemctl --user stop nexus"
echo "  remover: systemctl --user disable --now nexus && rm $DEST"

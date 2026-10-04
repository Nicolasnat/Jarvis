#!/usr/bin/env bash
# Script de vigia pos-auto-aprimoramento.
# Reinicia o servico Nexus, espera, checa saude (systemd active + dados/saude.ok).
# Se nao saudavel: rollback para tag nexus-antes-<id>, reinicia, confirma, registra falha.
set -euo pipefail

TAG_ANTES="${1:-}"
PROJETO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DADOS="$PROJETO/dados"
SAUDE_OK="$DADOS/saude.ok"
TEMPO_ESPERA="${NEXUS_VIGIA_TEMPO:-60}"  # segundos, configuravel via env

log() { echo "[vigia] $*"; }
erro() { echo "[vigia] ERRO: $*" >&2; }

if [ -z "$TAG_ANTES" ]; then
    erro "Uso: $0 <tag-antes>"
    exit 1
fi

log "Iniciando vigia pos-auto-aprimoramento (tag antes: $TAG_ANTES)"
log "Projeto: $PROJETO"
log "Tempo de espera: ${TEMPO_ESPERA}s"

# 1. Reinicia servico
log "Reiniciando servico nexus..."
systemctl --user restart nexus.service

# 2. Espera o servico subir
log "Aguardando ${TEMPO_ESPERA}s para o servico estabilizar..."
sleep "$TEMPO_ESPERA"

# 3. Checa saude
SAUDE=0

# 3a. Servico ativo?
if systemctl --user is-active nexus.service >/dev/null 2>&1; then
    log "Servico systemd: ACTIVE"
else
    erro "Servico systemd NAO esta active"
    SAUDE=1
fi

# 3b. Arquivo saude.ok existe e e recente?
if [ -f "$SAUDE_OK" ]; then
    # Verifica se foi modificado nos ultimos 2 minutos (120s)
    if [ "$(find "$SAUDE_OK" -mmin -2 2>/dev/null)" ]; then
        log "Arquivo saude.ok: RECENTE (wakeword detectada e processada)"
    else
        erro "Arquivo saude.ok existe mas e antigo (>2min)"
        SAUDE=1
    fi
else
    erro "Arquivo saude.ok NAO encontrado"
    SAUDE=1
fi

if [ "$SAUDE" -eq 0 ]; then
    log "SUCESSO: Nexus saudavel apos auto-aprimoramento"
    # Registra sucesso no historico (ja feito pelo plugin, so loga)
    exit 0
fi

# 4. FALHA - ROLLBACK
erro "FALHA NA SAUDE - Iniciando rollback para $TAG_ANTES"

log "Fazendo git reset --hard $TAG_ANTES..."
cd "$PROJETO"
git reset --hard "$TAG_ANTES" || { erro "git reset falhou"; exit 1; }

log "Reiniciando servico apos rollback..."
systemctl --user restart nexus.service

# Espera um pouco e checa de novo
sleep 10
if systemctl --user is-active nexus.service >/dev/null 2>&1; then
    log "Rollback OK: servico ativo novamente"
else
    erro "Rollback falhou: servico ainda nao sobe"
fi

# Notifica via desktop (se disponivel)
if command -v notify-send >/dev/null 2>&1; then
    notify-send -u critical "Nexus Auto-Aprimoramento" "Falha na vigia. Rollback para $TAG_ANTES executado." 2>/dev/null || true
fi

log "Vigia concluido (com rollback)"
exit 0
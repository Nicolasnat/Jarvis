# PLANO: Auto-Aperfeiçoamento Supervisionado do Nexus

## Visão Geral
Implementar a capacidade do Nexus de modificar seu próprio código de forma segura e supervisionada:
- Usuário pede: "corrige esse bug no seu código" ou "adicione tal função em você"
- Nexus cria cópia isolada (git worktree), faz mudanças, testa, pede aprovação, aplica
- Se algo quebrar, rollback automático via tag git e systemd restart + health check

---

## ETAPA 0 - Verificações Pré-Requisitos (JÁ FEITO)
- [x] `venv/` não está versionado ✓
- [x] `.gitignore` tem `venv/` e `dados/` ✓
- [x] Árvore git limpa (exceto minhas mudanças recentes em `interface/`) - **precisa commit ou stash**
- [x] `opencode-permissoes.json` gerado automaticamente pelo `nexus.py` ✓
- [x] Entendido: `PASTA_TRABALHO = ~/projetos`, `TEMPO_CODIGO = 900`, `PERMISSOES_AUTOMATICAS = True`

---

## ETAPA 1 - Módulo de Segurança (`seguranca.py`) - PROTEGIDO
**Arquivo novo:** `seguranca.py` (movido do `nexus.py` para ficar protegido)
**Objetivo:** Centralizar listas de segurança (BLOQUEIOS, CREDENCIAIS, CONFIRMACOES, CAMINHOS_PROIBIDOS) e funções `detectar_graves`, `confirmar_risco`, `para_regex`, `dentro_do_projeto`, `gerar_config_permissoes`, `aplicar_config_permissoes`

**Por que:** Item A dos protegidos diz "as listas de segurança (se estiverem no nexus.py, mover para um módulo seguranca.py protegido)"

**Arquivos alterados:**
- `nexus.py` - importa de `seguranca` em vez de definir localmente
- `config/protegidos.json` - lista este arquivo como protegido

---

## ETAPA 2 - Configuração de Protegidos (`config/protegidos.json`)
**Arquivo novo:** `config/protegidos.json`
**Conteúdo:** Lista de arquivos/pastas que o auto-aprimoramento NÃO pode tocar:
```
- opencode-permissoes.json e código que o gera (seguranca.py)
- nexus.service, instalar_servico.sh, ajustar_microfone.sh
- seguranca.py, config/protegidos.json
- scripts/aplicar_e_vigiar.sh
- ferramentas/_spotify.py, config/ (credenciais)
- .git/, .gitignore, venv/, dados/
```

**Validação:** Após o OpenCode terminar na worktree, `git diff --name-only` contra esta lista. Se tocou → REJEITA tudo.

---

## ETAPA 3 - Plugin de Auto-Aprimoramento (`ferramentas/auto_aprimoramento.py`)
**Arquivo novo:** `ferramentas/auto_aprimoramento.py`
**Ferramenta:** `auto_aprimoramento` (exposta no catálogo)

**Função principal:** `funcao(pedido: str, descricao: str = "")`
- `pedido`: o que o usuário quer (ex: "corrigir bug no abrir_programa")
- `descricao`: descrição opcional para o commit/tag

**Fluxo implementado AQUI (chamado pelo `pedir_ao_opencode` quando detecta auto-aprimoramento):**
1. **PRÉ-CHECAGEM:** repo git? árvore limpa? lock em `dados/auto_aprimoramento.lock`
2. **TAG RESTAURAÇÃO:** `nexus-antes-<timestamp>`
3. **WORKTREE:** `~/projetos/.nexus-dev/<id>` branch `auto/<id>-<slug>`
4. **CHAMA OPENCODE** na worktree com a tarefa + regras de segurança
5. **VERIFICAÇÃO PROTEGIDOS:** `git diff --name-only` vs `config/protegidos.json`
6. **VALIDAÇÃO:** `python nexus.py --autoteste` na worktree (usa venv principal)
7. **APRESENTAÇÃO:** diff stat, arquivos, resultado testes, riscos (marca "NÚCLEO" se nexus.py, voz.py, comum.py, interface/)
8. **APROVAÇÃO:** `confirmar_risco` (terminal) ou popup (interface)
9. **APLICAÇÃO:** merge fast-forward, tag `nexus-depois-<id>`, roda `scripts/aplicar_e_vigiar.sh`
10. **REGISTRO:** `dados/auto_aprimoramentos.json`

---

## ETAPA 4 - Modificação no `pedir_ao_opencode` (gancho principal)
**Arquivo alterado:** `nexus.py` - função `pedir_ao_opencode`

**Lógica de detecção:** Se `pasta_destino` for a raiz do Nexus (BASE_PROJETO) OU o `tarefa` contiver palavras-chave:
- "seu código", "você mesmo", "no nexus", "nesse código", "nesse bug", "auto-aprimoramento", "melhore você"

**Ação:** Em vez de chamar OpenCode direto, delega para `auto_aprimoramento.funcao(tarefa, pasta_destino)`

---

## ETAPA 5 - Autoteste (`--autoteste`)
**Arquivo alterado:** `nexus.py` - adicionar flag `--autoteste` no `main()`

**O que testa (sem Ollama, sem microfone, sem dados/):**
- `py_compile` em todos .py (nexus.py, voz.py, comum.py, ferramentas/*.py, interface/*.py, interface/popups/*.py)
- Importar nexus.py, voz.py, todos plugins
- Carregador carrega todas ferramentas com schema válido
- Testes de roteamento de intenção (`precisa_de_codigo`, `quer_plano`)
- Testes de política de segurança (bloqueados continuam bloqueados, confirmações exigem confirmação, caminhos proibidos recusados)
- Nenhum arquivo protegido alterado (lê `config/protegidos.json`)

**Retorno:** exit code 0 se tudo passar, != 0 se falhar

---

## ETAPA 6 - Script de Vigia (`scripts/aplicar_e_vigiar.sh`)
**Arquivo novo:** `scripts/aplicar_e_vigiar.sh` (shell independente do Python)

**Fluxo:**
1. Salva commit atual (HEAD)
2. `systemctl --user restart nexus`
3. Espera N segundos (configurável, padrão ~60s)
4. Verifica saúde:
   - Serviço `active`
   - Arquivo `dados/saude.ok` existe (escrito pelo Nexus ao subir wakeword)
5. Se saudável: registra sucesso, notifica desktop
6. Se NÃO saudável: `git reset --hard` para tag `nexus-antes-<id>`, restart, confirma, registra falha, notifica

---

## ETAPA 7 - Saúde do Nexus (`dados/saude.ok`)
**Arquivo alterado:** `nexus.py` - no loop principal (modo voz/serviço), ao detectar wakeword e iniciar com sucesso, escreve `dados/saude.ok` (timestamp)

---

## ETAPA 8 - Histórico e Desfazer (no mesmo plugin)
**Funções adicionais em `auto_aprimoramento.py`:**
- `historico_aprimoramentos()` - lê `dados/auto_aprimoramentos.json`, retorna lista legível
- `desfazer_ultimo()` - pega último registro, faz `git reset --hard` para tag `nexus-antes-<id>`, roda vigia, registra desfazimento

**Frases de ativação (no nexus.py REGRAS):**
- "o que você mudou em si mesmo?" → chama `historico_aprimoramentos`
- "desfaz a última mudança" → chama `desfazer_ultimo` (com confirmação)

---

## ETAPA 9 - Interface Gráfica (Popup de Aprovação)
**Arquivo alterado:** `interface/popups/confirmacao.py` ou novo popup
- Popup "AUTO-APRIMORAMENTO // N.E.X.U.S." com: resumo, diff, botões Aprovar/Rejeitar/Desfazer
- Usa mesmo mecanismo `ponte.pedir_confirmacao_bloqueante` com timeout

---

## ETAPA 10 - Documentação
**Arquivos alterados:**
- `README.md` - corrigir `git clone` (aponta para Jarvis.git), adicionar seção auto-aprimoramento
- `AGENTS.md` - adicionar regras do auto-aprimoramento
- `INSTALACAO.md` - adicionar dependências se houver

---

## CONSTANTES CONFIGURÁVEIS (topo do nexus.py ou config/)
- `AUTO_APRIMORAMENTO_MAX_LINHAS_DIFF = 500` - aviso extra se passar
- `AUTO_APRIMORAMENTO_TEMPO_VIGIA = 60` - segundos para health check
- `AUTO_APRIMORAMENTO_MAX_TENTATIVAS_TESTE = 2` - retentativas do autoteste

---

## RESUMO DE ARQUIVOS

### Novos:
1. `seguranca.py` (módulo protegido)
2. `config/protegidos.json`
3. `ferramentas/auto_aprimoramento.py`
4. `scripts/aplicar_e_vigiar.sh`
5. `PLANO_AUTO_APRIMORAMENTO.md` (este arquivo)

### Alterados:
1. `nexus.py` - import seguranca, gancho em pedir_ao_opencode, --autoteste, saúde.ok, frases histórico/desfazer
2. `interface/popups/confirmacao.py` - popup especial auto-aprimoramento (opcional)
3. `README.md`, `AGENTS.md`, `INSTALACAO.md`

---

## COMO O VIGIA DETECTA NEXUS SAUDÁVEL

O `scripts/aplicar_e_vigiar.sh` faz:
```bash
# 1. Restarta serviço
systemctl --user restart nexus

# 2. Espera (ex: 60s)
sleep 60

# 3. Verifica saúde DUPLA:
#    a) systemctl --user is-active nexus == "active"
#    b) [ -f "$PROJETO/dados/saude.ok" ] E timestamp recente (< 2 min)
#       (o Nexus escreve este arquivo ao acordar com wakeword e processar 1 comando)
```

Se ambos OK → sucesso. Se falhar → rollback para tag `nexus-antes-<id>`.

---

## GANCHO NO `pedir_ao_opencode`

```python
def pedir_ao_opencode(tarefa: str, pasta_destino: str = ".") -> str:
    pasta = resolver(pasta_destino)
    
    # DETECÇÃO DE AUTO-APRIMORAMENTO
    if _eh_auto_aprimoramento(tarefa, pasta):
        from ferramentas.auto_aprimoramento import funcao as auto_aprimorar
        return auto_aprimorar(tarefa, pasta_destino)
    
    # ... fluxo normal existente
```

`_eh_auto_aprimoramento` verifica:
- `pasta == BASE_PROJETO` (raiz do Nexus)
- OU palavras-chave na tarefa: "seu código", "você mesmo", "no nexus", "nesse bug", "auto-aprimoramento"
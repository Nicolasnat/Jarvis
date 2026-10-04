# AGENTS.md — Nexus

Regras compartilhadas para os agentes que trabalham neste repositório
(OpenCode como executor de código, Antigravity/Gemini como arquiteto e
revisor). Válido para todo o projeto e subpastas.

## O que é

Assistente de voz local em português do Brasil. O "cérebro" é um modelo da
Ollama; o trabalho pesado é delegado: OpenCode escreve e executa código,
Antigravity planeja e revisa. Tudo roda offline no terminal ou como serviço
`systemd --user`.

## Estrutura

- `nexus.py` — aplicação principal: loop de conversa, roteamento de intenção,
  segurança, delegação e modo voz.
- `voz.py` — wakeword, transcrição (faster-whisper), fala (Piper) e barge-in.
- `interface/` — interface gráfica PySide6: `app.py` (instância única + Qt),
  `janela_principal.py`, `ponte.py` (sinais Qt, inclui confirmação bloqueante)
  e `popups/` (um popup por ferramenta). Ativa com `--interface`.
- `comum.py` — constantes e helpers compartilhados.
- `ferramentas/` — plugins carregados automaticamente.
- `config/` — configuração editável (`apps.json`, `voz.json`, `spotify.json`).
- `dados/` — estado em tempo de execução (memória, RAG, vozes). Não versionado.
- `AGENTS.md` / `README.md` / `INSTALACAO.md` — documentação.

## Convenções

- Python 3.12, sem `pyproject.toml`/`Makefile`. O ambiente é `./venv`.
- **Comentários e docstrings no código são ASCII** (sem acento); textos de
  documentação (`.md`) usam acentuação normal em português.
- Prefira a biblioteca padrão; só adicione dependência se necessário e registre
  em `requirements.txt`.
- Plugins em `ferramentas/` expõem `NOME`, `DESCRICAO`, `PARAMETROS` e `funcao`.
  Arquivos iniciados por `_` não viram ferramenta (são módulos de apoio).
- Nome do assistente: **Nexus**. A wakeword é por palavras-chave (Vosk): valem
  "Nexus", "nexo", "Nexus iniciar", "oi nexus" e "hey nexus" (`wake_frases` em
  `config/voz.json`; ver `voz.py`). O modelo fica em `dados/vosk/` (não
  versionado).

## Comandos
 
```bash
./venv/bin/python nexus.py               # modo texto
./venv/bin/python nexus.py --voz         # modo voz
./venv/bin/python nexus.py --interface   # interface gráfica (voz + texto)
./venv/bin/python nexus.py --escrever    # entrada por texto, resposta em voz
./venv/bin/python nexus.py --modo-privado    # forca cerebro local
./venv/bin/python nexus.py --modo-nuvem      # reabilita cadeia nuvem
./venv/bin/python nexus.py --configurar-cerebro  # wizard chave Gemini
./venv/bin/python nexus.py --teste-cerebro     # testes simulados
./venv/bin/python nexus.py --autoteste         # testes automatizados
./venv/bin/python -m py_compile nexus.py voz.py comum.py ferramentas/*.py interface/*.py interface/popups/*.py
./instalar_servico.sh                    # instala/reinicia o serviço nexus.service
systemctl --user restart nexus.service
journalctl --user -u nexus.service -f
```

## Colaboração entre agentes

- OpenCode é o **executor**: cria/altera arquivos e roda comandos de verdade.
- Antigravity é o **arquiteto** (`--mode plan`) e o **revisor** (confere o que
  foi construído contra o plano). Nenhum dos dois escreve credenciais ou mexe
  fora da pasta de trabalho.
- Preserve os gates de segurança de `nexus.py` (`detectar_graves`,
  `confirmar_risco`, `CAMINHOS_PROIBIDOS`). Com `--interface`, `confirmar_risco`
  usa o popup de confirmação via `_ponte.pedir_confirmacao_bloqueante` (com
  timeout); sem interface, continua pedindo `sim` no terminal.

## Estilo de código

- Siga o padrão dos arquivos vizinhos; mudanças pequenas e focadas.
- Não deixe código morto, backups (`.bak`) nem arquivos temporários no repo.
- Ao terminar, valide com `py_compile` e, se possível, reinicie o serviço e
  confira o `journalctl`.

### Cápsula de ação rápida (interface/acoes_rapidas.py)

- Regra única `deve_usar_capsula(nome)` decide entre cápsula (ações somente-execução) e popup (ações com conteúdo / confirmação). Consultada ANTES de abrir qualquer popup. Veja `interface/acoes_rapidas.py`.

## Cadeia de Cérebros (cerebro.py)
 
- **Provedores**: `nuvem_gratis` (Gemini gratuito) -> `local` (Ollama). Configuravel em `config/cerebro.json` e `dados/cerebro.json`.
- **Failover**: 429/quota/billing/5xx/timeout -> proximo provedor. 401/403 -> erro claro + fallback. Circuit breaker (3 erros -> descanso 5min -> teste recuperação).
- **Contadores**: `dados/uso_cerebro.json` (tokens/dia/mes por provedor). Aviso 80%, limite configuravel.
- **Troca mid-turn**: histórico neutro (`dados/historico_neutro.json`) + brute Gemini separado. Ferramentas ja executadas nao repetem.
- **Modo privado** (`--modo-privado`): força local. `--modo-nuvem` reabilita cadeia.
- **Flags**: `max_passos` por provedor (nuvem=6, local=4). `rede_seguranca_palavra_chave` só no local.
 
## Memória Ativa (ferramentas/memoria_ativa.py)
 
- Embeddings locais `nomic-embed-text` (Ollama). Cache vetores em `dados/memoria_vetores.json`.
- A cada pedido: busca 5 fatos mais relevantes por similaridade de cosseno. Fallback palavra-chave se Ollama/embedding falhar.
- Modo privado: só busca local. Nuvem: filtra fatos que parecem credenciais (`CREDENCIAIS_REGEX`).
- Atualiza/remove vetores ao salvar/apagar fatos (`lembrar_fato`, `esquecer_fato`).
 
## Resumo de Contexto (ferramentas/resumo_contexto.py)
 
- Mantém últimas 10 msgs integrais + resumo contínuo do antigo em `dados/contexto_resumo.json`.
- Trigger: >30 msgs ou >6k tokens estimados. Falha no resumo -> descarte antigo (`podar`).
- `limpar_resumo()` limpa cache nova sessao.
 
## Auto-Aprimoramento Supervisionado
 
- **Gatilho**: `pedir_ao_opencode` detecta auto-aprimoramento se `pasta_destino` for a raiz do Nexus (`BASE_PROJETO`) OU o pedido contiver: "seu código", "você mesmo", "no nexus", "nesse bug", "auto-aprimoramento", "melhore o nexus", "corrija você", "em si mesmo".
- **Fluxo**: worktree isolada em `~/projetos/.nexus-dev/<id>` -> OpenCode -> `python nexus.py --autoteste` -> verifica `config/protegidos.json` -> apresenta diff -> `confirmar_risco` -> merge + `scripts/aplicar_e_vigiar.sh` -> vigia systemd (60s, checa `active` + `dados/saude.ok`) -> rollback automatico se falhar.
- **Protegidos** (`config/protegidos.json`): `seguranca.py`, `config/protegidos.json`, `opencode-permissoes.json`, `nexus.service`, `instalar_servico.sh`, `ajustar_microfone.sh`, `scripts/aplicar_e_vigiar.sh`, `ferramentas/_spotify.py`, `config/spotify.json`, `.git/`, `.gitignore`, `venv/`, `dados/`, `config/gemini.json`, `config/cerebro.json`, `dados/uso_cerebro.json`.
- **Historico/Desfazer**: "o que voce mudou em si mesmo?" -> `historico_aprimoramentos()`; "desfaz a ultima mudança" -> `desfazer_ultimo()` (com confirmacao e vigia).
- **Interface**: popup "AUTO-APRIMORAMENTO // N.E.X.U.S." com diff e botoes Aprovar/Rejeitar/Desfazer (usa `confirmar_risco` bloqueante).
- **Autoteste** (`--autoteste`): py_compile, imports, schemas, roteamento, politica de seguranca, protegidos. Retorna 0 se tudo passar.

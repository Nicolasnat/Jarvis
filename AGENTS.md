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
./venv/bin/python nexus.py            # modo texto
./venv/bin/python nexus.py --voz      # modo voz
./venv/bin/python -m py_compile nexus.py voz.py comum.py ferramentas/*.py
./instalar_servico.sh                 # instala/reinicia o serviço nexus.service
systemctl --user restart nexus.service
journalctl --user -u nexus.service -f
```

## Colaboração entre agentes

- OpenCode é o **executor**: cria/altera arquivos e roda comandos de verdade.
- Antigravity é o **arquiteto** (`--mode plan`) e o **revisor** (confere o que
  foi construído contra o plano). Nenhum dos dois escreve credenciais ou mexe
  fora da pasta de trabalho.
- Preserve os gates de segurança de `nexus.py` (`detectar_graves`,
  `confirmar_risco`, `CAMINHOS_PROIBIDOS`).

## Estilo de código

- Siga o padrão dos arquivos vizinhos; mudanças pequenas e focadas.
- Não deixe código morto, backups (`.bak`) nem arquivos temporários no repo.
- Ao terminar, valide com `py_compile` e, se possível, reinicie o serviço e
  confira o `journalctl`.

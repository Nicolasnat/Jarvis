# PLANO.md

> Gerado pelo Antigravity (modo plano, `gemini-3.1-pro-high`) em 2026-10-03 00:16.

Aqui está o plano de implementação detalhado, respeitando a regra de não criar arquivos e não rodar comandos durante o planejamento:

### ETAPA 1 - Arquitetura de plugins
*   **Arquivos a criar:** `ferramentas/carregador.py`. Modificar `nexus.py` para usar os plugins.
*   **Funções e assinaturas:** `carregar_plugins(pasta: str) -> tuple[list, dict]` (retorna CATALOGO e funções).
*   **Dependências:** Nenhuma adicional (built-ins de Python).
*   **Integração:** `carregar_plugins` inspeciona a pasta, exige dicionários NOME, DESCRICAO, PARAMETROS e funcao. Valida BINARIO via `shutil.which`.
*   **Segurança:** Nenhum comando shell injetado (`shell=False`).
*   **Validação:** Rodar Nexus e verificar log confirmando carregamento. Adicionar plugin sem binário e constatar que é ignorado.

### ETAPA 2 - Memória, tarefas e lembretes
*   **Arquivos a criar:** `ferramentas/memoria.py`, `ferramentas/tarefas.py`, `ferramentas/lembretes.py`.
*   **Funções e assinaturas:** `lembrar_fato(fato: str)`, `buscar_memoria(busca: str)`, `agendar_lembrete(msg: str, minutos: int)`.
*   **Dependências:** apt: `libnotify-bin` (para `notify-send`).
*   **Integração:** Importados como plugins. Injeção de memória no prompt no loop principal. Lembretes usam `threading.Timer`.
*   **Segurança:** Restringir manipulação de arquivos estritamente à pasta `dados/`.
*   **Validação:** Salvar uma nota, reiniciar e verificar se o sistema carrega os dados no prompt.

### ETAPA 3 - Sistema e programas
*   **Arquivos a criar:** `ferramentas/sistema.py`, `config/apps.json`.
*   **Funções e assinaturas:** `status_sistema() -> dict`, `abrir_programa(app: str)`, `fechar_programa(app: str)`.
*   **Dependências:** pip: `psutil`. apt: `xclip` (ou `wl-clipboard`), `pulseaudio-utils`, `brightnessctl`.
*   **Integração:** Plugins com validação em listas brancas na hora da chamada.
*   **Segurança:** `fechar_programa` sempre aciona `confirmar_risco` no fluxo de segurança do `nexus.py`. Sem execução arbitrária.
*   **Validação:** Tentar abrir um programa fora do `apps.json` e receber bloqueio local.

### ETAPA 4 - Voz
*   **Arquivos a criar:** `voz.py` (ou integrado condicionalmente no `nexus.py`).
*   **Funções e assinaturas:** `escutar_wakeword() -> bool`, `transcrever() -> str`, `falar(texto: str)`.
*   **Dependências:** pip: `faster-whisper`, `vosk`. apt: `espeak-ng`.
*   **Integração:** Flag de inicialização `--voz` muda a interface de `input()`/`print()` para loops de áudio local.
*   **Segurança:** Execução 100% offline; áudio não trafega para a nuvem.
*   **Validação:** Inicializar com `--voz`, falar "Nexus", pedir a hora e ouvir a resposta em áudio.

### ETAPA 5 - Documentos e estudo (RAG local)
*   **Arquivos a criar:** `ferramentas/rag.py`.
*   **Funções e assinaturas:** `indexar_pasta(caminho: str)`, `perguntar_documentos(pergunta: str)`.
*   **Dependências:** pip: `chromadb`, `PyPDF2`, `python-docx`, módulo `ollama`.
*   **Integração:** Ferramentas adicionais no CATALOGO. Resumo usa prompt + contexto recuperado via embeddings.
*   **Segurança:** Path traversal bloqueado rigorosamente em `detectar_graves` para caminhos de documentos.
*   **Validação:** Indexar um `.md` qualquer e realizar perguntas cujas respostas só existam naquele documento.

### Ordem de Implementação e Pontos de Checagem
1.  **Fundação:** Configurar `.gitignore` e implementar `carregador.py` (Etapa 1). **Checagem:** Plugins antigos convertidos e funcionando.
2.  **Estado Local:** Implementar Memória, Tarefas e controle do Sistema (Etapas 2 e 3). **Checagem:** Verificar persistência de notas e proteção ao encerrar processos.
3.  **Conhecimento (RAG):** Implementar base ChromaDB/Ollama (Etapa 5). **Checagem:** Fazer o modelo responder com contexto dos PDFs/TXTs locais.
4.  **Interface Acessível:** Implementar Wakeword, transcrição e TTS (Etapa 4). **Checagem:** Comunicação apenas por voz em tempo real funcionando fluidamente sem crashs.

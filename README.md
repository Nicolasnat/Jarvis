# 🤖 Nexus

Assistente de IA **local** em português do Brasil, que roda no terminal e **delega o trabalho pesado** para outras ferramentas: o cérebro conversa e decide, o [OpenCode](https://opencode.ai) escreve e executa o código de verdade, e o Antigravity (Gemini) faz o papel de arquiteto em projetos grandes.

> O Nexus nunca escreve código por conta própria. Ele entende o pedido, escolhe a ferramenta certa e relata o que realmente aconteceu no disco.

---

## ✨ O que ele faz

- 💬 **Conversa no terminal** usando modelos locais via [Ollama](https://ollama.com)
- 🛠️ **Cria e modifica projetos** (apps, sites, scripts, APIs...) delegando ao OpenCode, que executa comandos reais (`npm`, `pip`, build, testes)
- 🏗️ **Planeja antes de construir**: em projetos grandes, o Antigravity gera um plano de arquitetura que é anexado à tarefa do OpenCode
- 🔎 **Pesquisa na web** (DuckDuckGo) para fatos atuais e documentação
- 🧠 **Consulta um modelo especialista** (`qwen2.5:7b`) para perguntas de conhecimento e raciocínio
- 🧩 **Arquitetura de plugins**: cada ferramenta é um arquivo em `ferramentas/`, carregado automaticamente
- 🗒️ **Memória, tarefas, lembretes e anotações** persistentes em `dados/`
- 🖥️ **Controla o sistema**: status de CPU/RAM/disco, abre e fecha programas, volume, brilho e área de transferência
- 🎙️ **Modo voz** (`--voz`): escuta a wakeword "Nexus" ou "Hey Nexus" (ver nota abaixo), transcreve e responde falando (100% offline, voz neural Piper pt-BR)
- 🛎️ **Serviço em segundo plano** (`--servico`): roda sozinho no login, sem terminal; modelos pesados são descarregados quando ociosos
- 📚 **RAG local**: indexe documentos (txt, md, pdf, docx) e faça perguntas com base neles
- 📂 **Organiza arquivos**: lista projetos, cria pastas, abre o VS Code e o gerenciador de arquivos
- ✅ **Verifica o disco**: depois de cada tarefa de código, confere se o projeto foi realmente criado (e não confia só na resposta da IA)

---

## 🧩 Como funciona

```
Você ──► Nexus (llama3.1:8b via Ollama)
              │
              ├── código / projeto ──► OpenCode  ──► executa no disco
              │        ▲
              │        └── plano de arquitetura ◄── Antigravity (Gemini)
              │
              ├── conhecimento geral ─► qwen2.5:7b (Ollama)
              ├── fatos atuais ───────► busca na web (DDGS)
              ├── memória / tarefas / lembretes ─► dados/*.json
              ├── sistema ────────────► psutil, pactl, xclip, apps.json
              ├── voz ────────────────► arecord + vosk + faster-whisper
              └── documentos ─────────► ChromaDB + nomic-embed-text
```

### Divisão de trabalho

| Papel | Ferramenta | Responsabilidade |
|---|---|---|
| Cérebro | `llama3.1:8b` (Ollama) | Conversa, interpreta o pedido, escolhe ferramentas |
| Especialista | `qwen2.5:7b` (Ollama) | Perguntas de conhecimento e raciocínio |
| Executor de código | OpenCode | Cria/altera projetos e roda comandos de verdade |
| Arquiteto | Antigravity (`agy`) | Gera o plano de implementação (sem criar arquivos) |
| Segunda opinião | Claude Code (opcional) | Revisa código quando o usuário pede |
| Embeddings | `nomic-embed-text` (Ollama) | Vetoriza documentos para o RAG local |

### Garantias contra "alucinação"

- **Roteamento de intenção**: se o pedido parece ser de código e o modelo não acionou o OpenCode, o Nexus **força a delegação**.
- **Anti-duplicação**: o OpenCode é chamado uma única vez por turno.
- **Normalização de argumentos**: modelos pequenos às vezes trocam o nome dos parâmetros; o Nexus remapeia em vez de falhar.
- **Relato fiel**: o prompt do sistema obriga o assistente a relatar apenas o que a ferramenta retornou.

---

## 🛡️ Segurança

O Nexus tem três camadas de proteção para o que é enviado ao OpenCode e ao Antigravity:

1. **Bloqueio total** — comandos que destroem o sistema ou vazam credenciais (`rm -rf /`, `mkfs*`, `dd of=/dev/*`, fork bomb, `cat ~/.ssh*`...). Nem chegam a ser enviados.
2. **Confirmação** — operações sensíveis mas legítimas (`sudo`, `git push`, `apt`, `chmod`, `kill -9`, `drop table`...). O Nexus pergunta e só executa se você digitar `sim`.
3. **Permissões do OpenCode** — o arquivo `opencode-permissoes.json` é gerado automaticamente e aplicado via `OPENCODE_CONFIG`. Ele nega leitura e escrita em `~/.ssh`, `~/.aws`, `/etc`, `/usr` etc., bloqueia `.env` e permite `rm -rf` apenas dentro da pasta de projetos.

Ferramentas que executam comandos ou fecham processos passam por uma verificação central (`detectar_graves` + `confirmar_risco`). Ao fechar um programa, a confirmação é **sempre** pedida. O plugin `indexar_documentos` só aceita caminhos dentro da sua pasta pessoal e recusa pastas de credenciais e arquivos `.env`.

> ⚠️ **Atenção:** por padrão o Antigravity roda com `--dangerously-skip-permissions` (o modo headless `-p` não consegue pedir aprovação). As regras para ele são injetadas num bloco gerenciado do `~/.gemini/GEMINI.md` (o conteúdo existente é preservado), mas isso é uma instrução ao modelo, não um bloqueio técnico. Use com cuidado. Alternativa mais segura: ligar `ANTIGRAVITY_SANDBOX = True` no `nexus.py` e cadastrar as permissões necessárias em `permissions.allow` do `~/.gemini/antigravity-cli/settings.json` — sem essas regras, o sandbox **auto-recusa** as ferramentas em `-p`.

---

## 📋 Pré-requisitos

- **Linux** (usa `xdg-open`, `arecord` e notificações do desktop)
- **Python 3.10+**
- **[Ollama](https://ollama.com)** instalado e rodando
- **[OpenCode](https://opencode.ai)** instalado (comando `opencode` no PATH)
- Opcionais:
  - **Antigravity** (`agy`) — habilita planejamento e a ferramenta `pedir_ao_antigravity`
  - **Claude Code** (`claude`) — habilita a segunda opinião
  - **VS Code** (`code`) — para a ferramenta de abrir editor
  - `brightnessctl` — para a ferramenta de brilho

Ferramentas opcionais só aparecem se o binário estiver instalado.

---

## 🚀 Instalação

```bash
# 1. Clone o repositório
git clone https://github.com/Nicolasnat/Jarvis.git
cd Jarvis

# 2. Crie e ative um ambiente virtual
python3 -m venv venv
source venv/bin/activate

# 3. Instale as dependências Python
pip install -r requirements.txt

# 4. Baixe os modelos
ollama pull llama3.1:8b
ollama pull qwen2.5:7b
ollama pull nomic-embed-text
```

Pacotes de sistema (opcionais) estão listados em [`INSTALACAO.md`](INSTALACAO.md).

## ▶️ Uso

Há três jeitos de conversar com o Nexus: **digitando** (modo texto), **falando**
(modo voz) ou **digitando e ouvindo a resposta** (modo escrita). Em todos, o
Ollama precisa estar rodando (`ollama serve`).

### Digitando (modo texto)

```bash
./venv/bin/python nexus.py
```

Digite o pedido e tecle Enter; `sair` (ou Ctrl+D) encerra. Neste modo não há
microfone nem fala.

### Falando (modo voz)

```bash
./venv/bin/python nexus.py --voz
```

Diga **"Nexus"** (valem também "Hey Nexus", "Oi Nexus" e "Nexus iniciar") e
espere o "Ouvindo.". Depois é só dizer o comando — não precisa repetir "Nexus".
Fale por cima a qualquer momento para interromper; um "para" cancela o que
estiver rolando.

> A wakeword é reconhecida por palavras-chave (Vosk), então não precisa de
> treino. As frases aceitas ficam em `config/voz.json` (`wake_frases`) e o modelo
> é baixado uma vez conforme [`INSTALACAO.md`](INSTALACAO.md). Para calibrar o
> microfone, veja `config/voz.json` e `ajustar_microfone.sh`.

> A voz usa o Piper (modelo `pt_BR-faber-medium`, baixado uma vez conforme [`INSTALACAO.md`](INSTALACAO.md)). Se o modelo não estiver presente, cai para `espeak-ng`/`spd-say`.

### Digitando e ouvindo a resposta

```bash
./venv/bin/python nexus.py --escrever
```

Você **digita** (mais preciso que a transcrição de voz) e o Nexus **responde em
voz** pelo Piper — bom com fones de ouvido ou quando o teclado está longe do
microfone. `--texto-voz` é um apelido para o mesmo modo.

### Rodando em segundo plano (sem terminal)

Para o Nexus ficar sempre disponível (é só dizer "Nexus"), instale-o como
serviço de usuário do systemd:

```bash
./instalar_servico.sh
```

Ele passa a iniciar sozinho no login e fica ouvindo em segundo plano. Controle:

```bash
systemctl --user status nexus     # ver estado
journalctl --user -u nexus -f     # acompanhar logs
systemctl --user stop nexus       # parar agora
systemctl --user start nexus      # iniciar de novo
systemctl --user disable --now nexus   # remover do login
```

> O serviço roda **só no modo voz**: não há terminal para digitar. Para usar o
> modo texto, pare o serviço (`systemctl --user stop nexus`) e rode
> `./venv/bin/python nexus.py`. Em segundo plano, para ver o que ele ouviu e
> respondeu, acompanhe o `journalctl` acima.

> **Memória sob controle**: em repouso, só o detector de wakeword fica carregado
> (~230 MB). Os modelos pesados (Whisper, ~570 MB, e Piper) são carregados sob
> demanda e **descarregados logo após o uso**, devolvendo a RAM ao sistema. Assim o
> consumo acompanha apenas a função que está rodando.
>
> Para iniciar sem precisar fazer login (após reboot), rode uma vez:
> `sudo loginctl enable-linger $USER`.

Exemplos de pedidos:

```text
Você: crie um projeto React com Vite chamado minha-loja
Você: planeje a arquitetura de uma API de tarefas em Node e depois construa
Você: lembre que meu café é sem açúcar
Você: me lembra de beber água em 20 minutos
Você: adicione "revisar o PR" às minhas tarefas
Você: como está o sistema?
Você: abra o navegador
Você: deixe o volume em 40
Você: indexe a pasta ~/Documentos/faculdade e me explique o capítulo 3
```

Para encerrar, digite `sair`.

### Controlando o planejamento

- Para **forçar** o plano: use palavras como *planeje*, *arquitetura*, *plano*.
- Para **pular** o plano: diga *sem plano*, *direto* ou *só executa*.
- Em projetos grandes (app, site, API, sistema...) o plano é pedido automaticamente quando o Antigravity está disponível.

---

## ⚙️ Configuração

As constantes ficam no topo do `nexus.py`:

| Constante | Padrão | Descrição |
|---|---|---|
| `MODELO` | `llama3.1:8b` | Modelo principal (cérebro) |
| `MODELO_ESPECIALISTA` | `qwen2.5:7b` | Modelo para conhecimento e raciocínio |
| `PASTA_TRABALHO` | `~/projetos` | Onde todos os projetos são criados |
| `TEMPO_CODIGO` | `900` | Timeout (s) para tarefas de código |
| `TEMPO_PLANO` | `360` | Timeout (s) para o planejamento |
| `PERMISSOES_AUTOMATICAS` | `True` | Roda o OpenCode com `--auto` |
| `LIMITE_HISTORICO` | `14` | Mensagens mantidas no contexto |
| `MODELO_ARQUITETO` | `gemini-3.1-pro-high` | Modelo do Antigravity para planejar |
| `MODELO_EXECUTOR` | `gemini-3.8-flash-high` | Modelo do Antigravity para executar |
| `ANTIGRAVITY_SANDBOX` | `False` | Roda o Antigravity em `--sandbox` (exige allow-rules; ver nota) |
| `ANTIGRAVITY_PLANEJA` | `True` | Liga/desliga o planejamento automático |

As listas `BLOQUEIOS`, `CREDENCIAIS`, `CONFIRMACOES` e `CAMINHOS_PROIBIDOS` definem a política de segurança.

A lista de programas que o Nexus pode abrir/fechar fica em [`config/apps.json`](config/apps.json).

### 📦 Descobrir aplicativos

O `apps.json` é gerado a partir dos arquivos `.desktop` do sistema. Diga
**"Nexus, lê meus aplicativos"** (ou rode `descobrir_apps`) e ele registra
tudo que estiver instalado, com apelidos em português — "Visual Studio Code"
também responde a `vscode` e `code`. A busca ignora acentos, maiúsculas e
artigos, então "abre o gerenciador de arquivos" acha o `nautilus`.

Cada varredura é idempotente: nomes que saíram do sistema são descartados e os
que você adicionou à mão são preservados. Para conferir a lista, pergunte
**"quais aplicativos você abre?"**.

O scanner cobre pacotes nativos, Snap e Flatpak — o Google Chrome, por exemplo,
é Flatpak e só aparece se as pastas `flatpak/exports/share/applications`
estiverem na varredura. Nomes cadastrados à mão não são sobrescritos: seu
`navegador` continua apontando para o Firefox mesmo com o Chrome instalado.

---

## 🗂️ Estrutura

```
Nexus/
├── nexus.py                  # Aplicação principal (loop, intenção, segurança, pipeline)
├── comum.py                   # Helpers compartilhados (caminhos, JSON, memória no prompt)
├── voz.py                     # Wakeword, transcrição e fala (usado com --voz)
├── nexus.service             # Modelo do serviço systemd (usado pelo instalador)
├── instalar_servico.sh        # Instala/ativa o Nexus como serviço de usuário
├── ferramentas/
│   ├── carregador.py          # Carrega os plugins automaticamente
│   ├── _agenda.py             # Motor de lembretes em segundo plano
│   ├── _rag.py                # Motor do RAG (ChromaDB + nomic-embed-text)
│   ├── _spotify.py            # Cliente do Spotify Web API (PKCE, sem dependências)
│   └── *.py                   # Um arquivo por ferramenta
├── config/
│   ├── apps.json              # Programas que podem ser abertos/fechados
│   └── spotify.json           # Client ID do Spotify (não versionado)
├── dados/                     # Memória, tarefas, lembretes e índice vetorial (não versionado)
├── requirements.txt
├── INSTALACAO.md
├── PLANO.md                   # Plano de arquitetura gerado pelo Antigravity
└── README.md
```

## 🧰 Ferramentas disponíveis

| Ferramenta | Função |
|---|---|
| `pedir_ao_opencode` | Cria/modifica código e projetos (obrigatória para qualquer código) |
| `planejar_com_antigravity` | Gera apenas o plano de arquitetura *(opcional)* |
| `pedir_ao_antigravity` | Executa tarefas com o Antigravity/Gemini *(opcional)* |
| `pedir_ao_claude` | Segunda opinião do Claude Code *(opcional)* |
| `perguntar_qwen` | Consulta o modelo especialista local |
| `pesquisar_na_web` | Busca na web com títulos, resumos e links |
| `criar_pasta` | Cria diretórios vazios |
| `listar_projetos` | Lista os projetos da pasta de trabalho |
| `abrir_pasta` | Abre no gerenciador de arquivos |
| `abrir_vscode` | Abre no VS Code *(opcional)* |
| `lembrar_fato` / `buscar_memoria` / `esquecer_fato` | Memória de fatos sobre o usuário |
| `adicionar_tarefa` / `listar_tarefas` / `concluir_tarefa` | Lista de tarefas |
| `agendar_lembrete` / `listar_lembretes` / `cancelar_lembrete` | Lembretes com notificação |
| `anotar` | Anotações rápidas por dia |
| `status_sistema` | CPU, RAM, disco, uptime e bateria |
| `abrir_programa` / `fechar_programa` | Abre/fecha programas da lista permitida |
| `descobrir_apps` / `listar_apps` | Escaneia os apps instalados e lista os disponíveis |
| `spotify` | Toca música ou playlist pelo nome (casa a playlist mais parecida), pausar, próxima, volume *(exige Spotify Premium)* |
| `definir_volume` | Volume do sistema (0–100) |
| `definir_brilho` | Brilho da tela (requer `brightnessctl`) *(opcional)* |
| `ler_clipboard` / `copiar_clipboard` | Área de transferência |
| `indexar_documentos` / `perguntar_documentos` | RAG local sobre seus arquivos |

---

## 🗺️ Ideias para o futuro

- [x] Entrada e saída por voz
- [x] Memória persistente entre sessões
- [ ] Suporte a Windows e macOS
- [ ] Testes automatizados para o roteamento de intenção e a política de segurança

## 📄 Licença

Defina a licença do projeto (ex.: MIT).

## 👤 Autor

Feito por [Nicolasnat](https://github.com/Nicolasnat).

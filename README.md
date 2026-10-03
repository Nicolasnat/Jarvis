# 🤖 Jarvis

Assistente de IA **local** em português do Brasil, que roda no terminal e **delega o trabalho pesado** para outras ferramentas: o cérebro conversa e decide, o [OpenCode](https://opencode.ai) escreve e executa o código de verdade, e o Antigravity (Gemini) faz o papel de arquiteto em projetos grandes.

> O Jarvis nunca escreve código por conta própria. Ele entende o pedido, escolhe a ferramenta certa e relata o que realmente aconteceu no disco.

---

## ✨ O que ele faz

- 💬 **Conversa no terminal** usando modelos locais via [Ollama](https://ollama.com)
- 🛠️ **Cria e modifica projetos** (apps, sites, scripts, APIs...) delegando ao OpenCode, que executa comandos reais (`npm`, `pip`, build, testes)
- 🏗️ **Planeja antes de construir**: em projetos grandes, o Antigravity gera um plano de arquitetura que é anexado à tarefa do OpenCode
- 🔎 **Pesquisa na web** (DuckDuckGo) para fatos atuais e documentação
- 🧠 **Consulta um modelo especialista** (`qwen2.5:7b`) para perguntas de conhecimento e raciocínio
- 📂 **Organiza arquivos**: lista projetos, cria pastas, abre o VS Code e o gerenciador de arquivos
- ✅ **Verifica o disco**: depois de cada tarefa de código, confere se o projeto foi realmente criado (e não confia só na resposta da IA)

---

## 🧩 Como funciona

```
Você ──► Jarvis (llama3.1:8b via Ollama)
              │
              ├── código / projeto ──► OpenCode  ──► executa no disco
              │        ▲
              │        └── plano de arquitetura ◄── Antigravity (Gemini)
              │
              ├── conhecimento geral ─► qwen2.5:7b (Ollama)
              ├── fatos atuais ───────► busca na web (DDGS)
              └── organização ────────► criar pasta, listar, abrir VS Code / Nautilus
```

### Divisão de trabalho

| Papel | Ferramenta | Responsabilidade |
|---|---|---|
| Cérebro | `llama3.1:8b` (Ollama) | Conversa, interpreta o pedido, escolhe ferramentas |
| Especialista | `qwen2.5:7b` (Ollama) | Perguntas de conhecimento e raciocínio |
| Executor de código | OpenCode | Cria/altera projetos e roda comandos de verdade |
| Arquiteto | Antigravity (`agy`) | Gera o plano de implementação (sem criar arquivos) |
| Segunda opinião | Claude Code (opcional) | Revisa código quando o usuário pede |

### Garantias contra "alucinação"

- **Roteamento de intenção**: se o pedido parece ser de código e o modelo não acionou o OpenCode, o Jarvis **força a delegação**.
- **Anti-duplicação**: o OpenCode é chamado uma única vez por turno.
- **Normalização de argumentos**: modelos pequenos às vezes trocam o nome dos parâmetros; o Jarvis remapeia em vez de falhar.
- **Relato fiel**: o prompt do sistema obriga o assistente a relatar apenas o que a ferramenta retornou.

---

## 🛡️ Segurança

O Jarvis tem três camadas de proteção para o que é enviado ao OpenCode e ao Antigravity:

1. **Bloqueio total** — comandos que destroem o sistema ou vazam credenciais (`rm -rf /`, `mkfs*`, `dd of=/dev/*`, fork bomb, `cat ~/.ssh*`...). Nem chegam a ser enviados.
2. **Confirmação** — operações sensíveis mas legítimas (`sudo`, `git push`, `apt`, `chmod`, `kill -9`, `drop table`...). O Jarvis pergunta e só executa se você digitar `sim`.
3. **Permissões do OpenCode** — o arquivo `opencode-permissoes.json` é gerado automaticamente e aplicado via `OPENCODE_CONFIG`. Ele nega leitura e escrita em `~/.ssh`, `~/.aws`, `/etc`, `/usr` etc., bloqueia `.env` e permite `rm -rf` apenas dentro da pasta de projetos.

> ⚠️ **Atenção:** o Antigravity roda com `--dangerously-skip-permissions`. As regras para ele são injetadas num bloco gerenciado do `~/.gemini/GEMINI.md` (o conteúdo existente é preservado), mas isso é uma instrução ao modelo, não um bloqueio técnico. Use com cuidado.

---

## 📋 Pré-requisitos

- **Linux** (usa `xdg-open` para abrir pastas)
- **Python 3.10+**
- **[Ollama](https://ollama.com)** instalado e rodando
- **[OpenCode](https://opencode.ai)** instalado (comando `opencode` no PATH)
- Opcionais:
  - **Antigravity** (`agy`) — habilita planejamento e a ferramenta `pedir_ao_antigravity`
  - **Claude Code** (`claude`) — habilita a segunda opinião
  - **VS Code** (`code`) — para a ferramenta de abrir editor

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

# 3. Instale as dependências
pip install ollama ddgs

# 4. Baixe os modelos
ollama pull llama3.1:8b
ollama pull qwen2.5:7b
```

## ▶️ Uso

Com o Ollama rodando (`ollama serve`):

```bash
python jarvis.py
```

Exemplos de pedidos:

```text
Você: crie um projeto React com Vite chamado minha-loja
Você: planeje a arquitetura de uma API de tarefas em Node e depois construa
Você: liste meus projetos
Você: abre a pasta minha-loja no VS Code
Você: pesquise as novidades do Python 3.14
Você: explique o que é recursão
```

Para encerrar, digite `sair`.

### Controlando o planejamento

- Para **forçar** o plano: use palavras como *planeje*, *arquitetura*, *plano*.
- Para **pular** o plano: diga *sem plano*, *direto* ou *só executa*.
- Em projetos grandes (app, site, API, sistema...) o plano é pedido automaticamente quando o Antigravity está disponível.

---

## ⚙️ Configuração

As constantes ficam no topo do `jarvis.py`:

| Constante | Padrão | Descrição |
|---|---|---|
| `MODELO` | `llama3.1:8b` | Modelo principal (cérebro) |
| `MODELO_ESPECIALISTA` | `qwen2.5:7b` | Modelo para conhecimento e raciocínio |
| `PASTA_TRABALHO` | `~/projetos` | Onde todos os projetos são criados |
| `TEMPO_CODIGO` | `900` | Timeout (s) para tarefas de código |
| `TEMPO_PLANO` | `360` | Timeout (s) para o planejamento |
| `PERMISSOES_AUTOMATICAS` | `True` | Roda o OpenCode com `--auto` |
| `LIMITE_HISTORICO` | `14` | Mensagens mantidas no contexto |
| `MODELO_ANTIGRAVITY` | `gemini-3.1-pro-high` | Modelo usado pelo Antigravity |
| `ANTIGRAVITY_PLANEJA` | `True` | Liga/desliga o planejamento automático |

As listas `BLOQUEIOS`, `CREDENCIAIS`, `CONFIRMACOES` e `CAMINHOS_PROIBIDOS` definem a política de segurança.

---

## 🗂️ Estrutura

```
Jarvis/
├── jarvis.py                 # Aplicação principal (loop de conversa, ferramentas, segurança)
├── opencode-permissoes.json  # Gerado automaticamente com as permissões do OpenCode
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
| `abrir_vscode` | Abre no VS Code |

---

## 🗺️ Ideias para o futuro

- [ ] Entrada e saída por voz
- [ ] Memória persistente entre sessões
- [ ] Suporte a Windows e macOS
- [ ] Testes automatizados para o roteamento de intenção e a política de segurança

## 📄 Licença

Defina a licença do projeto (ex.: MIT).

## 👤 Autor

Feito por [Nicolasnat](https://github.com/Nicolasnat).

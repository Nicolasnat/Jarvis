import subprocess
from pathlib import Path
import ollama
from duckduckgo_search import DDGS

MODELO = "llama3.1:8b"
PASTA_TRABALHO = Path.home() / "jarvis-projetos"
PASTA_TRABALHO.mkdir(parents=True, exist_ok=True)


# ---------- AJUDANTES E FERRAMENTAS ----------

def rodar(comando, tempo, pasta=None):
    local = Path(pasta).expanduser() if pasta else PASTA_TRABALHO
    if not local.is_absolute():
        local = PASTA_TRABALHO / local
    local.mkdir(parents=True, exist_ok=True)
    
    try:
        r = subprocess.run(
            comando, 
            cwd=str(local),
            capture_output=True, 
            text=True, 
            timeout=tempo
        )
        return r.stdout or r.stderr or "Comando executado com sucesso."
    except FileNotFoundError:
        return f"O programa '{comando[0]}' não está instalado."
    except subprocess.TimeoutExpired:
        return "A execução demorou demais e foi interrompida."


def pesquisar_na_web(busca: str) -> str:
    try:
        resultados = list(DDGS().text(busca, max_results=3))
        if not resultados:
            return f"Nenhum resultado encontrado para '{busca}'."
        
        conteudos = [
            f"Título: {r.get('title')}\nResumo: {r.get('body')}\nLink: {r.get('href')}"
            for r in resultados
        ]
        return "Informações encontradas na web:\n\n" + "\n\n".join(conteudos)
    except Exception as e:
        return f"Erro ao realizar a busca na web: {e}"


def criar_pasta(caminho: str):
    """Cria uma pasta física no sistema."""
    pasta = Path(caminho).expanduser()
    if not pasta.is_absolute():
        pasta = PASTA_TRABALHO / pasta
        
    pasta.mkdir(parents=True, exist_ok=True)
    return f"Pasta criada com sucesso em: {pasta}"


def abrir_pasta(caminho: str):
    pasta = Path(caminho).expanduser()
    if not pasta.is_absolute():
        pasta = PASTA_TRABALHO / pasta
        
    if not pasta.is_dir():
        return f"A pasta '{pasta}' não existe."
    subprocess.Popen(["xdg-open", str(pasta)])
    return f"Abri a pasta {pasta}."


def abrir_vscode(caminho="."):
    pasta = Path(caminho).expanduser()
    if not pasta.is_absolute():
        pasta = PASTA_TRABALHO / pasta
        
    if not pasta.exists():
        pasta.mkdir(parents=True, exist_ok=True)

    subprocess.Popen(["code", str(pasta)])
    return f"VS Code aberto no caminho: {pasta}"


def perguntar_qwen(pergunta: str):
    r = ollama.chat(model="qwen2.5:7b", messages=[{"role": "user", "content": pergunta}])
    return r["message"]["content"]


def pedir_ao_opencode(tarefa: str, pasta_destino: str = "."):
    """Executa o OpenCode para criar, programar ou alterar arquivos no projeto."""
    return rodar(["opencode", "run", tarefa], 300, pasta=pasta_destino)


def pedir_ao_antigravity(pergunta: str):
    return rodar(["agy", "-p", pergunta], 120)


# ---------- MAPEAMENTO DE FERRAMENTAS ----------

FERRAMENTAS = {
    "pesquisar_na_web": pesquisar_na_web,
    "criar_pasta": criar_pasta,
    "abrir_pasta": abrir_pasta,
    "abrir_vscode": abrir_vscode,
    "perguntar_qwen": perguntar_qwen,
    "pedir_ao_opencode": pedir_ao_opencode,
    "pedir_ao_antigravity": pedir_ao_antigravity,
}


# ---------- ESQUEMA DAS FERRAMENTAS ----------

MANUAL = [
    {
        "type": "function",
        "function": {
            "name": "pesquisar_na_web",
            "description": "Pesquisa na web e retorna o resumo dos resultados",
            "parameters": {
                "type": "object",
                "properties": {"busca": {"type": "string", "description": "Termo de pesquisa"}},
                "required": ["busca"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "criar_pasta",
            "description": "Cria um novo diretório/pasta no computador",
            "parameters": {
                "type": "object",
                "properties": {"caminho": {"type": "string", "description": "Nome ou caminho da pasta a ser criada"}},
                "required": ["caminho"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "abrir_pasta",
            "description": "Abre uma pasta no gerenciador de arquivos do sistema",
            "parameters": {
                "type": "object",
                "properties": {"caminho": {"type": "string", "description": "Caminho ou nome da pasta"}},
                "required": ["caminho"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "abrir_vscode",
            "description": "Abre a janela do Visual Studio Code em uma pasta específica.",
            "parameters": {
                "type": "object",
                "properties": {"caminho": {"type": "string", "description": "Nome da pasta ou caminho para abrir no VS Code"}},
                "required": ["caminho"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "pedir_ao_opencode",
            "description": "Executa o OpenCode para programar, criar scripts, códigos e arquivos de projetos.",
            "parameters": {
                "type": "object",
                "properties": {
                    "tarefa": {
                        "type": "string", 
                        "description": "Instrução detalhada do que o OpenCode deve programar."
                    },
                    "pasta_destino": {
                        "type": "string", 
                        "description": "Nome da pasta onde o OpenCode deve trabalhar."
                    }
                },
                "required": ["tarefa"],
            },
        },
    },
]

# Prompt que força a chamada da ferramenta do VS Code caso o usuário peça
conversa = [{
    "role": "system",
    "content": (
        "Você é o Jarvis, assistente em português do Brasil curto e objetivo. "
        "Se o usuário pedir para abrir o VS Code, você DEVE obrigatoriamente chamar a ferramenta 'abrir_vscode'. "
        "NUNCA diga no texto que abriu o VS Code sem antes ter chamado a ferramenta 'abrir_vscode'."
    )
}]

print("Jarvis online. Digite 'sair' para encerrar.")

while True:
    try:
        texto = input("\nVocê: ").strip()
    except (KeyboardInterrupt, EOFError):
        break

    if not texto:
        continue

    if texto.lower() == "sair":
        break

    conversa.append({"role": "user", "content": texto})

    while True:
        resposta = ollama.chat(model=MODELO, messages=conversa, tools=MANUAL)
        mensagem = resposta["message"]
        conversa.append(mensagem)

        if mensagem.get("tool_calls"):
            for pedido in mensagem["tool_calls"]:
                nome = pedido["function"]["name"]
                argumentos = pedido["function"]["arguments"]

                # Executa a ferramenta sem imprimir logs de debug no terminal
                try:
                    resultado = FERRAMENTAS[nome](**argumentos)
                except Exception as erro:
                    resultado = f"Erro na execução da ferramenta {nome}: {erro}"

                conversa.append({
                    "role": "tool",
                    "content": str(resultado)
                })
        else:
            if mensagem.get("content"):
                print(f"Jarvis: {mensagem['content']}")
            break
"""Plugin: abre uma pasta no Visual Studio Code."""
import subprocess

from comum import resolver, esquema

NOME = "abrir_vscode"
DESCRICAO = "Abre uma pasta no Visual Studio Code. Use DEPOIS que o OpenCode terminar de criar o projeto."
PARAMETROS = esquema(
    {"caminho": {"type": "string", "description": "Pasta a abrir. Use '.' para a pasta raiz."}},
    ["caminho"],
)
BINARIO = "code"


def funcao(caminho: str = "."):
    pasta = resolver(caminho)
    if not pasta.exists():
        pasta.mkdir(parents=True, exist_ok=True)
    try:
        subprocess.Popen(
            ["code", str(pasta)],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            stdin=subprocess.DEVNULL, start_new_session=True,
        )
    except FileNotFoundError:
        return "Falha: o VS Code (comando 'code') nao esta instalado."
    return f"VS Code aberto em: {pasta}"

"""Plugin: abre uma pasta no gerenciador de arquivos do sistema."""
import subprocess

from comum import resolver, esquema

NOME = "abrir_pasta"
DESCRICAO = "Abre UMA PASTA EXISTENTE no gerenciador de arquivos do sistema (Nautilus). NAO CRIA pasta nova - use 'criar_pasta' para isso."
PARAMETROS = esquema(
    {"caminho": {"type": "string", "description": "Pasta a abrir"}},
    ["caminho"],
)


def funcao(caminho: str):
    pasta = resolver(caminho)
    if not pasta.is_dir():
        return f"A pasta '{pasta}' nao existe."
    subprocess.Popen(
        ["xdg-open", str(pasta)],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        stdin=subprocess.DEVNULL, start_new_session=True,
    )
    return f"Gerenciador de arquivos aberto em: {pasta}"

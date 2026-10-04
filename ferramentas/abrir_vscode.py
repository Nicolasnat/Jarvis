"""Plugin: abre uma pasta no Visual Studio Code."""
import subprocess
from pathlib import Path

from comum import resolver, esquema

NOME = "abrir_vscode"
DESCRICAO = (
    "Abre UMA PASTA ESPECIFICA EXISTENTE no Visual Studio Code. "
    "Use SEMPRE que o usuario pedir para abrir o VS Code, o editor, ou o code "
    "EM UMA PASTA JA EXISTENTE (ex.: 'abre o vscode na pasta meu-projeto', 'abrir vscode aqui', "
    "'abrir pasta X no vscode', 'code na pasta Y', 'abrir projeto integrador origem'). "
    "NAO use 'abrir_programa' para isso - essa ferramenta so abre o app sem pasta. "
    "NAO use 'criar_pasta' - essa CRIA pasta nova, nao abre existente."
)
PARAMETROS = esquema(
    {"caminho": {"type": "string", "description": "Nome ou caminho da pasta a abrir (ex.: 'meu-projeto', 'sistema interno', '.')."}},
    ["caminho"],
)
BINARIO = "code"


def _tentar_variacoes(pasta: Path) -> Path | None:
    """Tenta encontrar pasta existente com underscore/hifen no lugar de espaco."""
    nome = pasta.name
    if " " not in nome:
        return None
    pai = pasta.parent
    if not pai.exists():
        return None
    alvos = {nome.replace(" ", "_").lower(), nome.replace(" ", "-").lower()}
    for item in pai.iterdir():
        if item.is_dir() and item.name.lower() in alvos:
            return item
    return None


def _buscar_por_nome_parcial(pasta: Path) -> Path | None:
    """Busca pasta por correspondencia parcial do nome (ultimas palavras)."""
    nome = pasta.name.lower()
    pai = pasta.parent
    if not pai.exists():
        return None
    # Divide o nome em palavras e tenta achar pasta que contenha as palavras-chave
    palavras = [p for p in nome.split() if len(p) > 2]
    if not palavras:
        return None
    for item in pai.iterdir():
        if not item.is_dir():
            continue
        item_lower = item.name.lower()
        # Verifica se a maioria das palavras-chave esta no nome da pasta
        matches = sum(1 for p in palavras if p in item_lower)
        if matches >= max(1, len(palavras) - 1):
            return item
    return None


def funcao(caminho: str = "."):
    pasta = resolver(caminho)
    if not pasta.exists():
        existente = _tentar_variacoes(pasta)
        if existente is None:
            existente = _buscar_por_nome_parcial(pasta)
        if existente is not None:
            pasta = existente
        else:
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

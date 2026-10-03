"""Plugin: lista os projetos existentes na pasta de trabalho."""
from datetime import datetime

from comum import resolver, esquema, TEXTO

NOME = "listar_projetos"
DESCRICAO = "Lista os projetos existentes na pasta de trabalho."
PARAMETROS = esquema({"caminho": TEXTO}, [])


def funcao(caminho="."):
    base = resolver(caminho)
    if not base.is_dir():
        return f"A pasta '{base}' nao existe."

    linhas = [f"Projetos em {base}:"]
    for item in sorted(base.iterdir()):
        if not item.is_dir() or item.name.startswith("."):
            continue
        arquivos = [a for a in item.iterdir() if a.name != "node_modules"]
        modificado = datetime.fromtimestamp(item.stat().st_mtime)
        linhas.append(f"- {item.name} ({len(arquivos)} itens, modificado em {modificado:%d/%m/%Y})")
    return "\n".join(linhas) if len(linhas) > 1 else f"Nenhum projeto em {base}."

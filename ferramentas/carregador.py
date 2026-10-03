"""Importa automaticamente os plugins de ferramentas/ e monta o catalogo."""
import importlib
import shutil
from pathlib import Path

PASTA = Path(__file__).resolve().parent
IGNORADOS = {"__init__.py", "carregador.py"}
OBRIGATORIOS = ("NOME", "DESCRICAO", "PARAMETROS", "funcao")


def carregar_plugins():
    """Retorna (catalogo, funcoes, indisponiveis).

    - catalogo: lista de dicts no formato usado pelo Jarvis.
    - funcoes: dicionario nome -> funcao.
    - indisponiveis: lista de (nome, motivo) para avisar o usuario.
    """
    catalogo, funcoes, indisponiveis = [], {}, []

    for arquivo in sorted(PASTA.glob("*.py")):
        if arquivo.name in IGNORADOS or arquivo.name.startswith("_"):
            continue

        nome_modulo = f"{__package__}.{arquivo.stem}"
        try:
            modulo = importlib.import_module(nome_modulo)
        except Exception as erro:
            indisponiveis.append((arquivo.stem, f"erro ao importar: {erro}"))
            continue

        faltando = [atributo for atributo in OBRIGATORIOS if not hasattr(modulo, atributo)]
        if faltando:
            indisponiveis.append((arquivo.stem, f"faltam: {', '.join(faltando)}"))
            continue

        binario = getattr(modulo, "BINARIO", None)
        if binario and not shutil.which(binario):
            indisponiveis.append((modulo.NOME, f"programa '{binario}' nao instalado"))
            continue

        item = {
            "nome": modulo.NOME,
            "descricao": modulo.DESCRICAO,
            "parametros": modulo.PARAMETROS,
            "fn": modulo.funcao,
            "seguranca": getattr(modulo, "SEGURANCA", None),
        }
        catalogo.append(item)
        funcoes[modulo.NOME] = modulo.funcao

    return catalogo, funcoes, indisponiveis

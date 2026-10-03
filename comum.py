"""Funcoes e constantes compartilhadas entre o Jarvis e os plugins.

Fica num modulo separado para que os plugins possam importar helpers sem
criar import circular com o jarvis.py (que roda como __main__).
"""
import re
from pathlib import Path

BASE_PROJETO = Path(__file__).resolve().parent
PASTA_TRABALHO = Path.home() / "projetos"
PASTA_TRABALHO.mkdir(parents=True, exist_ok=True)
PASTA_DADOS = BASE_PROJETO / "dados"
PASTA_CONFIG = BASE_PROJETO / "config"

MODELO_ESPECIALISTA = "qwen2.5:7b"

REDUNDANTES = {"projetos", "projects", "projeto", "project"}


def resolver(caminho) -> Path:
    """Normaliza um caminho para dentro de PASTA_TRABALHO (ou mantem absolutos)."""
    pasta = Path(str(caminho).strip().strip("\"'")).expanduser()

    if not pasta.is_absolute():
        partes = pasta.parts
        if partes and partes[0].lower() in REDUNDANTES:
            partes = partes[1:]
        return PASTA_TRABALHO.joinpath(*partes) if partes else PASTA_TRABALHO

    try:
        relativo = pasta.relative_to(PASTA_TRABALHO)
    except ValueError:
        return pasta

    partes = list(relativo.parts)
    while partes and partes[0].lower() in REDUNDANTES:
        partes.pop(0)
    return PASTA_TRABALHO.joinpath(*partes) if partes else PASTA_TRABALHO


def permitido_para_escrita(pasta) -> bool:
    """So permite criar/escrever dentro da pasta de projetos ou do proprio Jarvis."""
    alvo = Path(pasta).resolve()
    for base in (PASTA_TRABALHO.resolve(), BASE_PROJETO.resolve()):
        try:
            alvo.relative_to(base)
            return True
        except ValueError:
            continue
    return False


def esquema(propriedades, obrigatorias):
    return {"type": "object", "properties": propriedades, "required": obrigatorias}


TEXTO = {"type": "string"}


def limpar_ansi(texto: str) -> str:
    return re.sub(r"\x1b\[[0-9;?]*[a-zA-Z]|\x1b\][^\x07]*\x07", "", texto)


def resumir_busca(web: str, limite=1800) -> str:
    if len(web) <= limite:
        return web
    return web[:limite] + "\n...[conteudo truncado]"


def garantir_pasta_dados() -> Path:
    PASTA_DADOS.mkdir(parents=True, exist_ok=True)
    return PASTA_DADOS

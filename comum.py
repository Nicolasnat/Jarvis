"""Funcoes e constantes compartilhadas entre o Nexus e os plugins.

Fica num modulo separado para que os plugins possam importar helpers sem
criar import circular com o nexus.py (que roda como __main__).
"""
import json
import re
import unicodedata
from pathlib import Path

BASE_PROJETO = Path(__file__).resolve().parent
PASTA_TRABALHO = Path.home() / "projetos"
PASTA_TRABALHO.mkdir(parents=True, exist_ok=True)
PASTA_DADOS = BASE_PROJETO / "dados"
PASTA_CONFIG = BASE_PROJETO / "config"
PASTA_NOTAS = PASTA_DADOS / "notas"

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
    """So permite criar/escrever dentro da pasta de projetos ou do proprio Nexus."""
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


ARTIGOS = {"o", "a", "os", "as", "um", "uma"}


def sem_acentos(texto: str) -> str:
    """'Acentuação' vira 'Acentuacao', para comparar o que foi falado com o nome do app."""
    normalizado = unicodedata.normalize("NFKD", str(texto or ""))
    return "".join(c for c in normalizado if not unicodedata.combining(c))


def chave_nome(texto: str) -> str:
    """Normaliza um nome falado para comparar: minusculo, sem acento e sem artigos.

    'o Visual Studio Code' e 'visual studio code' viram a mesma chave, que e o
    que o Whisper devolve depois de listening do usuario. Preposicoes sao
    mantidas de proposito: em portugues boa parte dos apps se chama
    'gerenciador de arquivos', 'mesa de som'.
    """
    limpo = sem_acentos(texto).lower()
    limpo = re.sub(r"[^a-z0-9]+", " ", limpo)
    palavras = [p for p in limpo.split() if p and p not in ARTIGOS]
    return " ".join(palavras)


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


def ler_json(caminho, padrao):
    """Le um JSON local; devolve o padrao se o arquivo nao existir ou estiver corrompido."""
    try:
        return json.loads(Path(caminho).read_text())
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return padrao


def salvar_json(caminho, dados):
    caminho = Path(caminho)
    caminho.parent.mkdir(parents=True, exist_ok=True)
    caminho.write_text(json.dumps(dados, indent=2, ensure_ascii=False))
    return caminho


ARQUIVO_MEMORIA = PASTA_DADOS / "memoria.json"
ARQUIVO_TAREFAS = PASTA_DADOS / "tarefas.json"
ARQUIVO_LEMBRETES = PASTA_DADOS / "lembretes.json"
ARQUIVO_APPS = PASTA_CONFIG / "apps.json"


def memoria_para_prompt(limite=8) -> str:
    """Devolve um resumo curto da memoria para injetar no prompt do sistema."""
    fatos = ler_json(ARQUIVO_MEMORIA, [])
    if not fatos:
        return ""
    recentes = fatos[-limite:]
    linhas = [f"- {item.get('fato', '')}" for item in recentes if item.get("fato")]
    if not linhas:
        return ""
    return "\n\nO que voce ja sabe sobre o usuario (memoria):\n" + "\n".join(linhas)


def apps_para_prompt(limite=120) -> str:
    """Lista os aplicativos que o Nexus pode abrir, para o modelo escolher o nome certo."""
    apps = ler_json(ARQUIVO_APPS, {})
    if not apps:
        return ""
    nomes = [nome.replace("_", " ") for nome in sorted(apps)[:limite]]
    if not nomes:
        return ""
    return (
        "\n\nAplicativos que voce pode abrir com abrir_programa "
        "(use o nome como aparece aqui):\n" + ", ".join(nomes)
    )

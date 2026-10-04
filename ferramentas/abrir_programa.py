"""Plugin: abre um programa instalado ou site no navegador.

A lista de apps vem de config/apps.json (pode ser gerada pelo descobrir_apps).
A lista de sites vem de config/sites.json (editavel pelo usuario).
Como o usuario fala ("abre o code", "abrir o claude", "abrir whatsapp"),
a busca ignora acento, maiusculas, artigos e espacamentos.
"""
import difflib
import os
import shutil
import subprocess
import urllib.parse
import urllib.request
import re
from pathlib import Path

from comum import ARQUIVO_APPS, BASE_PROJETO, chave_nome, ler_json, esquema

NOME = "abrir_programa"
DESCRICAO = (
    "Abre um aplicativo instalado ou site no navegador pelo nome. "
    "Use para 'abrir o X' (apps) ou 'abrir site Y' (sites em config/sites.json). "
    "Se o site nao estiver cadastrado, tenta buscar na web (fallback). "
    "Se a lista estiver desatualizada, use antes o descobrir_apps."
)
PARAMETROS = esquema(
    {"app": {"type": "string", "description": "Nome do programa ou site (ex.: vscode, claude, whatsapp, https://site.com)"}},
    ["app"],
)
SEGURANCA = "detectar"

APELIDOS = {
    "vscode": "code",
    "vs code": "code",
    "visual studio code": "code",
    "visual studio": "code",
    "navegador": "chrome",
    "google chrome": "chrome",
}

ARQUIVO_SITES = BASE_PROJETO / "config" / "sites.json"


def _carregar_sites() -> dict:
    """Carrega sites do config/sites.json."""
    return ler_json(ARQUIVO_SITES, {})


def _catalogo():
    apps = ler_json(ARQUIVO_APPS, {})
    if not isinstance(apps, dict):
        return {}
    # Indexa tambem pela chave normalizada, para os nomes antigos com "_".
    indice = {}
    for nome, comando in apps.items():
        indice.setdefault(chave_nome(nome), comando)
    return indice


def _comando_para(app: str):
    indice = _catalogo()
    if not indice:
        return None, (
            "A lista de aplicativos esta vazia. Rode o descobrir_apps para ler os "
            "programas instalados."
        )

    # Verifica URL no original (antes de normalizar)
    app_strip = (app or "").strip()
    if app_strip.startswith(("http://", "https://", "www.")):
        return ["xdg-open", app_strip], None

    pedido = chave_nome(app_strip)
    if not pedido:
        return None, "Nao entendi qual programa abrir. Diga o nome, ex.: 'abre o vscode'."

    # Verifica se e um site conhecido (config/sites.json)
    sites = _carregar_sites()
    if pedido in sites:
        url = sites[pedido]
        return ["xdg-open", url], None

    # Verifica se e um app instalado
    if pedido in indice:
        return indice[pedido], None

    alias = {chave_nome(k): chave_nome(v) for k, v in APELIDOS.items()}.get(pedido)
    if alias in indice:
        return indice[alias], None

    # Prefere quem comeca com o que foi falado, para "spot" achar "spotify".
    prefixos = [chave for chave in indice if chave.startswith(pedido)]
    if prefixos:
        return indice[min(prefixos, key=len)], None

    contendo = [chave for chave in indice if pedido in chave]
    if contendo:
        return indice[min(contendo, key=len)], None

    # Aproximacao so como ultimo recurso, e mais rigida em nomes curtos.
    if len(pedido) >= 4:
        corte = 0.85 if len(pedido) <= 6 else 0.72
        parecidos = difflib.get_close_matches(pedido, indice.keys(), n=1, cutoff=corte)
        if parecidos:
            return indice[parecidos[0]], None

    for chave in sorted(indice, key=len, reverse=True):
        if len(chave) >= 4 and pedido.endswith(chave):
            return indice[chave], None

    # FALLBACK: tenta buscar o site na web se nao achou em apps nem em sites.json
    # Isso evita ter que cadastrar todos os sites manualmente.
    return _buscar_e_abrir_site(app_strip), None


def _buscar_e_abrir_site(nome: str):
    """Busca o site na web e retorna comando para abrir o primeiro resultado.
    Usa DuckDuckGo HTML scraping simples (sem API key)."""
    try:
        query = urllib.parse.quote_plus(f"{nome} site oficial")
        url = f"https://html.duckduckgo.com/html/?q={query}"
        headers = {"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36"}
        req = urllib.request.Request(url, headers=headers)
        with urllib.request.urlopen(req, timeout=10) as resp:
            html = resp.read().decode("utf-8", errors="ignore")

        # Extrai primeiro link de resultado (classe result__url ou similar)
        # DuckDuckGo HTML tem links em <a class="result__url" href="...">
        matches = re.findall(r'class="result__url"[^>]*href="([^"]+)"', html)
        if not matches:
            matches = re.findall(r'<a[^>]+class="[^"]*result[^"]*"[^>]+href="([^"]+)"', html)
        if not matches:
            # Fallback generico: primeiro link http(s) que nao seja duckduckgo
            matches = re.findall(r'href="(https?://[^"]+)"', html)
            matches = [m for m in matches if "duckduckgo" not in m and "bing.com" not in m]

        if matches:
            primeiro = matches[0]
            # Limpa parametros de tracking do DDG
            if primeiro.startswith("//duckduckgo.com/l/?"):
                parsed = urllib.parse.urlparse(primeiro)
                params = urllib.parse.parse_qs(parsed.query)
                if "uddg" in params:
                    primeiro = params["uddg"][0]
            return ["xdg-open", primeiro]

    except Exception:
        pass

    # Se tudo falhou, tenta abrir busca no Google
    return ["xdg-open", f"https://www.google.com/search?q={urllib.parse.quote_plus(nome)}"]


def funcao(app: str):
    comando, erro = _comando_para(app)
    if erro:
        return erro
    if not isinstance(comando, list) or not comando:
        return f"A configuracao de '{app}' no apps.json esta invalida."
    if not shutil.which(comando[0]) and not os.path.isabs(comando[0]):
        return f"O programa '{comando[0]}' nao esta instalado no sistema."
    subprocess.Popen(
        comando,
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        stdin=subprocess.DEVNULL, start_new_session=True,
    )
    return f"Abrindo {app}."
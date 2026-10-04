"""Plugin: abre um programa instalado.

A lista vem de config/apps.json, que pode ser gerada em tempo de execucao pelo
plugin 'descobrir_apps' (le os .desktop do sistema). Como o usuario fala
("abre o code", "abrir o gerenciador de arquivos"), a busca ignora acento,
maiusculas, artigos e espaamentos antes de casar com o nome cadastrado.
"""
import difflib
import os
import shutil
import subprocess

from comum import ARQUIVO_APPS, chave_nome, ler_json, esquema

NOME = "abrir_programa"
DESCRICAO = (
    "Abre um aplicativo instalado no computador pelo nome. Use para 'abrir o X'. "
    "Se a lista estiver desatualizada, use antes o descobrir_apps."
)
PARAMETROS = esquema(
    {"app": {"type": "string", "description": "Nome do programa (ex.: vscode, spotify, terminal)"}},
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

SITES_CONHECIDOS = {
    "claude": "https://claude.ai",
    "chatgpt": "https://chat.openai.com",
    "chat gpt": "https://chat.openai.com",
    "whatsapp": "https://web.whatsapp.com",
    "web whatsapp": "https://web.whatsapp.com",
    "gmail": "https://mail.google.com",
    "google": "https://www.google.com",
    "youtube": "https://www.youtube.com",
    "github": "https://github.com",
    "gitlab": "https://gitlab.com",
    "linkedin": "https://www.linkedin.com",
    "twitter": "https://twitter.com",
    "x twitter": "https://twitter.com",
    "facebook": "https://www.facebook.com",
    "instagram": "https://www.instagram.com",
    "reddit": "https://www.reddit.com",
    "stackoverflow": "https://stackoverflow.com",
    "google drive": "https://drive.google.com",
    "drive": "https://drive.google.com",
    "google maps": "https://maps.google.com",
    "maps": "https://maps.google.com",
    "google tradutor": "https://translate.google.com",
    "tradutor": "https://translate.google.com",
    "notion": "https://www.notion.so",
    "figma": "https://www.figma.com",
    "canva": "https://www.canva.com",
    "spotify web": "https://open.spotify.com",
    "netflix": "https://www.netflix.com",
    "prime video": "https://www.primevideo.com",
    "disney": "https://www.disneyplus.com",
    "globoplay": "https://globoplay.globo.com",
    "twitch": "https://www.twitch.tv",
    "discord": "https://discord.com/app",
    "telegram web": "https://web.telegram.org",
    "teams": "https://teams.microsoft.com",
    "meet": "https://meet.google.com",
    "zoom": "https://zoom.us",
}


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

    # Verifica se e um site conhecido
    if pedido in SITES_CONHECIDOS:
        url = SITES_CONHECIDOS[pedido]
        # Tenta abrir no navegador padrao (xdg-open) que ja abre o browser se fechado
        return ["xdg-open", url], None

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

    # Aproximacao so como ultimo recurso, e mais rigida em nomes curtos: e o
    # que impede 'discord' (nao instalado) de casar com 'code'.
    if len(pedido) >= 4:
        corte = 0.85 if len(pedido) <= 6 else 0.72
        parecidos = difflib.get_close_matches(pedido, indice.keys(), n=1, cutoff=corte)
        if parecidos:
            return indice[parecidos[0]], None

    for chave in sorted(indice, key=len, reverse=True):
        if len(chave) >= 4 and pedido.endswith(chave):
            return indice[chave], None

    return None, (
        f"Nao achei '{app}' na lista de aplicativos. "
        f"Para incluir um programa novo, rode o descobrir_apps. "
        f"Ja tem {len(indice)} disponiveis, por exemplo: {', '.join(sorted(indice)[:10])}."
    )


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
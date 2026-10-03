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

    pedido = chave_nome(app)
    if not pedido:
        return None, "Nao entendi qual programa abrir. Diga o nome, ex.: 'abre o vscode'."

    if pedido in indice:
        return indice[pedido], None

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
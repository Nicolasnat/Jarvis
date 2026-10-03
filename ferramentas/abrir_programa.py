"""Plugin: abre um programa da lista permitida em config/apps.json."""
import shutil
import subprocess

from comum import ARQUIVO_APPS, ler_json, esquema

NOME = "abrir_programa"
DESCRICAO = "Abre um programa instalado. So aceita os programas da lista permitida (config/apps.json)."
PARAMETROS = esquema(
    {"app": {"type": "string", "description": "Nome do programa (ex.: navegador, vscode, spotify)"}},
    ["app"],
)
SEGURANCA = "detectar"


def _comando_para(app: str):
    apps = ler_json(ARQUIVO_APPS, {})
    nome = (app or "").strip().lower()
    comando = apps.get(nome)
    if comando is None:
        return None, f"O programa '{app}' nao esta na lista permitida. Disponiveis: {', '.join(sorted(apps))}."
    if not isinstance(comando, list) or not comando:
        return None, f"A configuracao de '{nome}' em apps.json esta invalida."
    if not shutil.which(comando[0]):
        return None, f"O programa '{comando[0]}' nao esta instalado no sistema."
    return comando, None


def funcao(app: str):
    comando, erro = _comando_para(app)
    if erro:
        return erro
    subprocess.Popen(
        comando,
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        stdin=subprocess.DEVNULL, start_new_session=True,
    )
    return f"Abrindo {app}."

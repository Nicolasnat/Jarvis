"""Plugin: fecha um programa da lista permitida em config/apps.json."""
from pathlib import Path

import psutil

from comum import ARQUIVO_APPS, ler_json, esquema

NOME = "fechar_programa"
DESCRICAO = "Fecha um programa em execucao. So aceita programas da lista permitida e sempre pede confirmacao."
PARAMETROS = esquema(
    {"app": {"type": "string", "description": "Nome do programa a fechar (ex.: navegador, spotify)"}},
    ["app"],
)
SEGURANCA = "sempre"


def _nomes_de_processo(app: str):
    apps = ler_json(ARQUIVO_APPS, {})
    nome = (app or "").strip().lower()
    comando = apps.get(nome)
    if comando is None:
        return None, f"O programa '{app}' nao esta na lista permitida. Disponiveis: {', '.join(sorted(apps))}."
    alvo = Path(comando[0]).name
    raiz = alvo.split(".")[0]
    return (alvo, raiz), None


def funcao(app: str):
    alvos, erro = _nomes_de_processo(app)
    if erro:
        return erro

    fechados = 0
    for processo in psutil.process_iter(["name"]):
        nome_proc = (processo.info.get("name") or "").lower()
        if nome_proc in alvos or nome_proc.startswith(alvos[1]):
            try:
                processo.terminate()
                fechados += 1
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                continue

    if fechados:
        psutil.wait_procs(
            [p for p in psutil.process_iter(["name"])
             if (p.info.get("name") or "").lower().startswith(alvos[1])],
            timeout=3,
        )
        return f"Fechando {app} ({fechados} processo(s))."
    return f"Nenhum processo de '{app}' estava em execucao."

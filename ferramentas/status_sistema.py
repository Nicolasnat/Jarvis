"""Plugin: mostra o status atual do sistema (CPU, RAM, disco, uptime)."""
from datetime import datetime

import psutil

from comum import esquema

NOME = "status_sistema"
DESCRICAO = "Mostra CPU, memoria RAM, uso do disco e tempo ligado."
PARAMETROS = esquema({}, [])


def _gb(bytes_):
    return f"{bytes_ / 1024 ** 3:.1f} GB"


def funcao():
    cpu = psutil.cpu_percent(interval=0.3)
    mem = psutil.virtual_memory()
    disco = psutil.disk_usage("/")
    ligado = datetime.now() - datetime.fromtimestamp(psutil.boot_time())

    linhas = [
        f"CPU: {cpu:.0f}%",
        f"RAM: {mem.percent:.0f}% ({_gb(mem.used)} de {_gb(mem.total)})",
        f"Disco /: {disco.percent:.0f}% ({_gb(disco.used)} de {_gb(disco.total)})",
        f"Ligado ha: {str(ligado).split('.')[0]}",
    ]

    bateria = psutil.sensors_battery() if hasattr(psutil, "sensors_battery") else None
    if bateria is not None:
        estado = "carregando" if bateria.power_plugged else "na bateria"
        linhas.append(f"Bateria: {bateria.percent:.0f}% ({estado})")

    return "\n".join(linhas)

"""Plugin: define o volume do sistema (0 a 100)."""
import re
import subprocess

from comum import esquema

NOME = "definir_volume"
DESCRICAO = "Define o volume do sistema em uma porcentagem de 0 a 100."
PARAMETROS = esquema(
    {"nivel": {"type": "integer", "description": "Volume de 0 a 100"}},
    ["nivel"],
)
BINARIO = "pactl"
SEGURANCA = "detectar"


def volume_atual():
    """Volume atual do sink padrao (0-100), ou None se nao der para ler."""
    try:
        resultado = subprocess.run(
            ["pactl", "get-sink-volume", "@DEFAULT_SINK@"],
            capture_output=True, text=True, timeout=10,
        )
    except Exception:  # noqa: BLE001 - sem pactl/audio, so nao ha leitura
        return None
    if resultado.returncode != 0:
        return None
    achado = re.search(r"(\d+)%", resultado.stdout)
    return int(achado.group(1)) if achado else None


def funcao(nivel: int):
    try:
        valor = max(0, min(100, int(nivel)))
    except (TypeError, ValueError):
        return "Informe o volume como um numero de 0 a 100."

    resultado = subprocess.run(
        ["pactl", "set-sink-volume", "@DEFAULT_SINK@", f"{valor}%"],
        capture_output=True, text=True, timeout=10,
    )
    if resultado.returncode != 0:
        return f"Nao consegui ajustar o volume: {resultado.stderr.strip()}"
    return f"Volume ajustado para {valor}%."

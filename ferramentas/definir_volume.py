"""Plugin: define o volume do sistema (0 a 100)."""
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

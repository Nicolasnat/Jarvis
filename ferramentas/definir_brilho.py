"""Plugin: define o brilho da tela (0 a 100). Requer brightnessctl."""
import subprocess

from comum import esquema

NOME = "definir_brilho"
DESCRICAO = "Define o brilho da tela em uma porcentagem de 0 a 100."
PARAMETROS = esquema(
    {"nivel": {"type": "integer", "description": "Brilho de 0 a 100"}},
    ["nivel"],
)
BINARIO = "brightnessctl"
SEGURANCA = "detectar"


def funcao(nivel: int):
    try:
        valor = max(0, min(100, int(nivel)))
    except (TypeError, ValueError):
        return "Informe o brilho como um numero de 0 a 100."

    resultado = subprocess.run(
        ["brightnessctl", "set", f"{valor}%"],
        capture_output=True, text=True, timeout=10,
    )
    if resultado.returncode != 0:
        return f"Nao consegui ajustar o brilho: {resultado.stderr.strip()}"
    return f"Brilho ajustado para {valor}%."

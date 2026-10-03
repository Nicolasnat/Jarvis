"""Plugin: le o texto da area de transferencia."""
import os
import shutil
import subprocess

from comum import esquema

NOME = "ler_clipboard"
DESCRICAO = "Le o texto que esta na area de transferencia."
PARAMETROS = esquema({}, [])


def _colar():
    if os.environ.get("WAYLAND_DISPLAY") and shutil.which("wl-paste"):
        comando = ["wl-paste", "--no-newline"]
    elif shutil.which("xclip"):
        comando = ["xclip", "-selection", "clipboard", "-o"]
    else:
        return None
    try:
        resultado = subprocess.run(comando, capture_output=True, text=True, timeout=10)
    except (OSError, subprocess.SubprocessError):
        return None
    if resultado.returncode != 0:
        return None
    return resultado.stdout


def funcao():
    texto = _colar()
    if texto is None:
        return "Nao consegui ler a area de transferencia (instale xclip ou wl-clipboard)."
    texto = texto.strip()
    return f"Area de transferencia:\n{texto}" if texto else "A area de transferencia esta vazia."

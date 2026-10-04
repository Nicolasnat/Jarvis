"""Plugin: copia um texto para a area de transferencia."""
import os
import shutil
import subprocess

from comum import esquema

NOME = "copiar_clipboard"
DESCRICAO = (
    "COPIA TEXTO para a area de transferencia (ctrl+C). "
    "Use para 'copia isso', 'copiar texto', 'coloca no clipboard'. "
    "NAO ABRE apps - para abrir whatsapp/spotify/code use 'abrir_programa'."
)
PARAMETROS = esquema(
    {"texto": {"type": "string", "description": "Texto a copiar"}},
    ["texto"],
)
SEGURANCA = "detectar"


def funcao(texto: str):
    texto = texto if texto is not None else ""
    if os.environ.get("WAYLAND_DISPLAY") and shutil.which("wl-copy"):
        comando = ["wl-copy"]
    elif shutil.which("xclip"):
        comando = ["xclip", "-selection", "clipboard"]
    else:
        return "Nao consegui acessar a area de transferencia (instale xclip ou wl-clipboard)."
    try:
        subprocess.run(
            comando, input=texto, text=True, timeout=10, check=True,
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        )
    except (OSError, subprocess.SubprocessError) as erro:
        return f"Falha ao copiar: {erro}"
    return "Texto copiado para a area de transferencia."

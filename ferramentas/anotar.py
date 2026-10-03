"""Plugin: salva uma anotacao rapida em dados/notas/AAAA-MM-DD.md."""
from datetime import datetime

from comum import PASTA_NOTAS, esquema

NOME = "anotar"
DESCRICAO = "Salva uma anotacao rapida no arquivo de notas do dia."
PARAMETROS = esquema(
    {"texto": {"type": "string", "description": "O que anotar"}},
    ["texto"],
)


def funcao(texto: str):
    texto = (texto or "").strip()
    if not texto:
        return "Nada para anotar."
    agora = datetime.now()
    PASTA_NOTAS.mkdir(parents=True, exist_ok=True)
    arquivo = PASTA_NOTAS / f"{agora:%Y-%m-%d}.md"
    with arquivo.open("a", encoding="utf-8") as f:
        f.write(f"- {agora:%H:%M} {texto}\n")
    return f"Anotado em {arquivo}: {texto}"

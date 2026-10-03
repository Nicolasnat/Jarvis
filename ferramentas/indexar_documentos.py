"""Plugin: indexa documentos locais na base de conhecimento (RAG)."""
from comum import esquema
from ferramentas._rag import indexar

NOME = "indexar_documentos"
DESCRICAO = (
    "Indexa uma pasta ou arquivo (txt, md, pdf, docx) para consulta posterior. "
    "So aceita caminhos dentro da sua pasta pessoal."
)
PARAMETROS = esquema(
    {"caminho": {"type": "string", "description": "Pasta ou arquivo a indexar"}},
    ["caminho"],
)
SEGURANCA = "detectar"


def funcao(caminho: str):
    return indexar(caminho)

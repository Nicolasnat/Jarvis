"""Plugin: responde perguntas com base nos documentos indexados (RAG)."""
from comum import esquema
from ferramentas._rag import perguntar

NOME = "perguntar_documentos"
DESCRICAO = (
    "Responde uma pergunta usando apenas os documentos que ja foram indexados. "
    "Use 'indexar_documentos' antes."
)
PARAMETROS = esquema(
    {"pergunta": {"type": "string", "description": "Pergunta sobre os documentos"}},
    ["pergunta"],
)


def funcao(pergunta: str):
    return perguntar(pergunta)

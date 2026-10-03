"""Plugin: lista os lembretes agendados."""
from comum import esquema
from ferramentas._agenda import listar

NOME = "listar_lembretes"
DESCRICAO = "Lista os lembretes agendados e seus horarios."
PARAMETROS = esquema({}, [])


def funcao():
    return listar()

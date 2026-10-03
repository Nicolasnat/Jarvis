"""Plugin: cancela um lembrete agendado (por numero ou texto)."""
from comum import esquema
from ferramentas._agenda import cancelar

NOME = "cancelar_lembrete"
DESCRICAO = "Cancela um lembrete pelo numero (#) ou por um trecho da mensagem."
PARAMETROS = esquema(
    {"identificador": {"type": "string", "description": "Numero do lembrete (#2) ou trecho da mensagem"}},
    ["identificador"],
)


def funcao(identificador: str):
    return cancelar(identificador)

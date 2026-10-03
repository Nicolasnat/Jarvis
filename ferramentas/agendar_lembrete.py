"""Plugin: agenda um lembrete (ex.: 'em 20 minutos', 'amanha as 8h')."""
from comum import esquema
from ferramentas._agenda import agendar

NOME = "agendar_lembrete"
DESCRICAO = (
    "Agenda um lembrete que dispara uma notificacao no horario. "
    "Em 'quando' use algo como 'em 20 minutos', 'em 2 horas', 'amanha as 8h' ou '18:30'."
)
PARAMETROS = esquema(
    {
        "mensagem": {"type": "string", "description": "O que avisar quando chegar a hora"},
        "quando": {"type": "string", "description": "Em quanto tempo ou o horario do lembrete"},
    },
    ["mensagem", "quando"],
)


def funcao(mensagem: str, quando: str):
    return agendar(mensagem, quando)

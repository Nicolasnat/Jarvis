"""Plugin: agenda um lembrete (ex.: 'em 20 minutos', 'amanha as 8h')."""
from comum import esquema
from ferramentas._agenda import agendar

NOME = "agendar_lembrete"
DESCRICAO = (
    "CRIA LEMBRETE COM DATA/HORA ESPECIFICA (notificacao futura). "
    "Use para: 'me lembra DA FESTA DIA 10 AS 14H', 'avisa AMANHA AS 8H', "
    "'lembrete PARA DIA 15/10 AS 20H', 'me lembra EM 30 MINUTOS'. "
    "O parametro 'quando' ACEITA: 'em 30 minutos', 'amanha as 8h', 'dia 10 as 14h', "
    "'15/10 as 20h', '10 de outubro as 14 horas'. "
    "NAO use 'adicionar_tarefa' - essa e lista sem horario."
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

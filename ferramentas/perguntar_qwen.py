"""Plugin: consulta o modelo especialista local via Ollama."""
import ollama

from comum import MODELO_ESPECIALISTA, esquema

NOME = "perguntar_qwen"
DESCRICAO = (
    f"Consulta o modelo local {MODELO_ESPECIALISTA} para perguntas de conhecimento, "
    "raciocinio, matematica, programacao, historia, ciencia, biografia. "
    "QUANDO USAR: fatos estaveis, explicacoes conceituais, resolucao de problemas, "
    "definicoes, traducao, resumo de textos, geracao de ideias. "
    "QUANDO NAO USAR: fatos atuais (noticias, clima, cotacao) - use 'pesquisar_na_web'; "
    "para criar arquivos/codigo (use 'pedir_ao_opencode'); "
    "para buscar em documentos locais (use 'perguntar_documentos'). "
    "Exemplos: pergunta='o que e recursao em programacao', "
    "pergunta='capital da franca', pergunta='explique derivadas', "
    "pergunta='traduzir para ingles: boa noite'."
)
PARAMETROS = esquema(
    {"pergunta": {"type": "string", "description": "A pergunta a enviar ao especialista (ex.: o que e recursao, capital da franca)"}},
    ["pergunta"],
)


def funcao(pergunta: str):
    try:
        resposta = ollama.chat(
            model=MODELO_ESPECIALISTA,
            messages=[{"role": "user", "content": pergunta}],
        )
        return resposta["message"]["content"]
    except Exception as erro:
        return f"Falha ao consultar o {MODELO_ESPECIALISTA}: {erro}"

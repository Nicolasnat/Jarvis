"""Plugin: consulta o modelo especialista local via Ollama."""
import ollama

from comum import MODELO_ESPECIALISTA, esquema

NOME = "perguntar_qwen"
DESCRICAO = (
    f"Consulta o modelo local {MODELO_ESPECIALISTA} para perguntas de conhecimento, "
    "raciocinio ou texto. NAO serve para criar arquivos."
)
PARAMETROS = esquema(
    {"pergunta": {"type": "string", "description": "A pergunta a enviar ao especialista"}},
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

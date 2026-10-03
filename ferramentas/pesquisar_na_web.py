"""Plugin: pesquisa na web via DuckDuckGo (ddgs)."""
from ddgs import DDGS

from comum import resumir_busca, esquema

NOME = "pesquisar_na_web"
DESCRICAO = "Pesquisa na web e retorna titulos, resumos e links."
PARAMETROS = esquema(
    {"busca": {"type": "string", "description": "Termo de pesquisa"}},
    ["busca"],
)


def funcao(busca: str):
    try:
        resultados = list(DDGS().text(busca, max_results=5))
        if not resultados:
            return f"Nenhum resultado encontrado para '{busca}'."

        conteudos = [
            f"Titulo: {r.get('title')}\nResumo: {r.get('body')}\nLink: {r.get('href')}"
            for r in resultados
        ]
        return resumir_busca("Informacoes encontradas na web:\n\n" + "\n\n".join(conteudos))
    except Exception as erro:
        return f"Erro ao realizar a busca na web: {erro}"

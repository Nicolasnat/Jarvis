"""Plugin: pesquisa na web via DuckDuckGo (ddgs)."""
from ddgs import DDGS

from comum import resumir_busca, esquema

NOME = "pesquisar_na_web"
DESCRICAO = (
    "Pesquisa na web via DuckDuckGo e retorna titulos, resumos e links. "
    "QUANDO USAR: fatos atuais (noticias, clima, cotacao), documentacao oficial, "
    "versoes recentes de software, preco de produtos, biografias recentes. "
    "QUANDO NAO USAR: conhecimento geral estavel (historia, ciencia, matematica, programacao) - use 'perguntar_qwen'; "
    "para buscar em documentos locais (use 'perguntar_documentos'); "
    "para abrir site direto (use 'abrir_programa'). "
    "Exemplos: busca='clima sao paulo hoje', busca='python 3.12 novidades', "
    "busca='documentacao react hooks', busca='cotacao dolar hoje'."
)
PARAMETROS = esquema(
    {"busca": {"type": "string", "description": "Termo de pesquisa (ex.: clima sao paulo hoje, python 3.12 novidades)"}},
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

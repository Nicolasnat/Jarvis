"""Plugin: busca fatos na memoria local."""
from comum import ARQUIVO_MEMORIA, ler_json, esquema

NOME = "buscar_memoria"
DESCRICAO = "Busca fatos guardados na memoria local. Use antes de perguntar algo que talvez ja saiba."
PARAMETROS = esquema(
    {"busca": {"type": "string", "description": "Termo a procurar (vazio traz tudo)"}},
    [],
)


def funcao(busca: str = ""):
    fatos = ler_json(ARQUIVO_MEMORIA, [])
    termo = (busca or "").lower().strip()
    achados = [item for item in fatos if termo in item.get("fato", "").lower()] if termo else fatos
    if not achados:
        return f"Nada encontrado na memoria para '{busca}'."
    return "Memoria:\n" + "\n".join(f"- {item.get('fato', '')}" for item in achados)

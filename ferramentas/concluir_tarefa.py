"""Plugin: marca uma tarefa local como concluida (por numero ou texto)."""
from comum import ARQUIVO_TAREFAS, ler_json, salvar_json, esquema

NOME = "concluir_tarefa"
DESCRICAO = (
    "MARCA TAREFA EXISTENTE COMO FEITA (pelo #numero ou texto). "
    "Use para 'conclui tarefa 1', 'marca como feito', 'terminei X'. "
    "NAO CRIA tarefa nem lembrete - so finaliza o que ja existe."
)
PARAMETROS = esquema(
    {"identificador": {"type": "string", "description": "Numero da tarefa (#3) ou trecho do texto"}},
    ["identificador"],
)


def funcao(identificador: str):
    alvo = (identificador or "").strip()
    try:
        alvo_id = int(alvo.lstrip("#"))
    except ValueError:
        alvo_id = None

    tarefas = ler_json(ARQUIVO_TAREFAS, [])
    concluidas, nomes = 0, []
    for item in tarefas:
        casa = item.get("id") == alvo_id if alvo_id is not None else alvo.lower() in item.get("texto", "").lower()
        if casa and not item.get("feita"):
            item["feita"] = True
            concluidas += 1
            nomes.append(item.get("texto", ""))
    salvar_json(ARQUIVO_TAREFAS, tarefas)
    if concluidas:
        return f"Concluidas: {', '.join(nomes)}"
    return "Nenhuma tarefa pendente correspondente encontrada."

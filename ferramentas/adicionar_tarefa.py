"""Plugin: adiciona uma tarefa na lista local."""
from datetime import datetime

from comum import ARQUIVO_TAREFAS, ler_json, salvar_json, esquema

NOME = "adicionar_tarefa"
DESCRICAO = "Adiciona uma tarefa a lista de tarefas local."
PARAMETROS = esquema(
    {"descricao": {"type": "string", "description": "O que precisa ser feito"}},
    ["descricao"],
)


def funcao(descricao: str):
    descricao = (descricao or "").strip()
    if not descricao:
        return "A tarefa veio vazia."
    tarefas = ler_json(ARQUIVO_TAREFAS, [])
    novo_id = max([item.get("id", 0) for item in tarefas], default=0) + 1
    tarefas.append({
        "id": novo_id,
        "texto": descricao,
        "feita": False,
        "criada": datetime.now().isoformat(timespec="seconds"),
    })
    salvar_json(ARQUIVO_TAREFAS, tarefas)
    return f"Tarefa #{novo_id} adicionada: {descricao}"

"""Plugin: lista as tarefas locais."""
from comum import ARQUIVO_TAREFAS, ler_json, esquema

NOME = "listar_tarefas"
DESCRICAO = "Lista as tarefas locais, separando pendentes e concluidas."
PARAMETROS = esquema({}, [])


def funcao():
    tarefas = ler_json(ARQUIVO_TAREFAS, [])
    if not tarefas:
        return "Nenhuma tarefa cadastrada."
    pendentes = [t for t in tarefas if not t.get("feita")]
    feitas = [t for t in tarefas if t.get("feita")]
    linhas = []
    if pendentes:
        linhas.append("Pendentes:")
        linhas += [f"- #{t.get('id')} {t.get('texto', '')}" for t in pendentes]
    if feitas:
        linhas.append("Concluidas:")
        linhas += [f"- #{t.get('id')} {t.get('texto', '')}" for t in feitas]
    return "\n".join(linhas)

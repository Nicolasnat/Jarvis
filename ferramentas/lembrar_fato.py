"""Plugin: guarda um fato sobre o usuario na memoria local."""
from datetime import datetime

from comum import ARQUIVO_MEMORIA, ler_json, salvar_json, esquema
from ferramentas.memoria_ativa import atualizar_vetor_fato

NOME = "lembrar_fato"
DESCRICAO = "Guarda um fato sobre o usuario na memoria local, para lembrar nas proximas conversas."
PARAMETROS = esquema(
    {"fato": {"type": "string", "description": "O fato que deve ser lembrado"}},
    ["fato"],
)


def funcao(fato: str):
    fato = (fato or "").strip()
    if not fato:
        return "Nada para lembrar: o fato veio vazio."
    fatos = ler_json(ARQUIVO_MEMORIA, [])
    if any(item.get("fato", "").lower() == fato.lower() for item in fatos):
        return f"Ja estava na memoria: {fato}"
    quando = datetime.now().isoformat(timespec="seconds")
    fato_id = quando
    fatos.append({"fato": fato, "quando": quando, "id": fato_id})
    salvar_json(ARQUIVO_MEMORIA, fatos)
    # Cacheia o vetor do novo fato
    atualizar_vetor_fato(fato_id, fato)
    return f"Anotado na memoria: {fato}"

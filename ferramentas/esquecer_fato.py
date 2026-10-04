"""Plugin: apaga fatos da memoria local."""
from comum import ARQUIVO_MEMORIA, ler_json, salvar_json, esquema
from ferramentas.memoria_ativa import remover_vetor_fato

NOME = "esquecer_fato"
DESCRICAO = "Apaga da memoria local os fatos que contenham o termo informado."
PARAMETROS = esquema(
    {"termo": {"type": "string", "description": "Trecho do fato a esquecer"}},
    ["termo"],
)


def funcao(termo: str):
    termo = (termo or "").lower().strip()
    if not termo:
        return "Informe o termo do fato a esquecer."
    fatos = ler_json(ARQUIVO_MEMORIA, [])
    restantes = []
    for item in fatos:
        if termo in item.get("fato", "").lower():
            # Remove vetor cacheado
            fato_id = item.get("id") or item.get("quando")
            if fato_id:
                remover_vetor_fato(fato_id)
        else:
            restantes.append(item)
    removidos = len(fatos) - len(restantes)
    salvar_json(ARQUIVO_MEMORIA, restantes)
    return f"Esqueci {removidos} fato(s) que continham '{termo}'."

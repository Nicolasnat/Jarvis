"""Plugin: lista quais aplicativos o Nexus sabe abrir."""
from comum import ARQUIVO_APPS, ler_json, esquema

NOME = "listar_apps"
DESCRICAO = (
    "Lista todos os aplicativos que o Nexus consegue abrir pelo nome. "
    "Use quando o usuario perguntar quais programas ele tem, ou 'o que voce abre'."
)
PARAMETROS = esquema(
    {"filtro": {"type": "string", "description": "Parte do nome para filtrar (ex.: 'code', 'jogo'). Opcional."}},
    [],
)


def funcao(filtro: str = ""):
    apps = ler_json(ARQUIVO_APPS, {})
    if not isinstance(apps, dict) or not apps:
        return (
            "A lista de aplicativos esta vazia. Use o descobrir_apps para ler os "
            "programas instalados no sistema."
        )

    termos = [t for t in (filtro or "").lower().split() if t]
    if termos:
        escolhidos = [n for n in apps if any(t in n.lower() for t in termos)]
    else:
        escolhidos = sorted(apps)

    if not escolhidos:
        return f"Nenhum aplicativo casa com '{filtro}'. Tenho {len(apps)} cadastrados."

    nomes = ", ".join(sorted(escolhidos))
    return f"{len(escolhidos)} de {len(apps)} aplicativos ({ARQUIVO_APPS}): {nomes}"
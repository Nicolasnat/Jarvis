"""Plugin: cria um diretorio vazio dentro da pasta de projetos."""
from comum import resolver, esquema, permitido_para_escrita

NOME = "criar_pasta"
DESCRICAO = (
    "Cria apenas um diretorio vazio. NAO use para criar projetos: "
    "isso e responsabilidade do pedir_ao_opencode."
)
PARAMETROS = esquema(
    {"caminho": {"type": "string", "description": "Nome ou caminho da pasta"}},
    ["caminho"],
)
SEGURANCA = "detectar"


def funcao(caminho: str):
    pasta = resolver(caminho)
    if not permitido_para_escrita(pasta):
        return f"Bloqueado: o Jarvis so cria pastas dentro de {resolver('.')}."
    if pasta.exists() and any(pasta.iterdir()):
        return f"A pasta '{pasta}' ja existe e nao esta vazia."
    pasta.mkdir(parents=True, exist_ok=True)
    return f"Pasta criada em: {pasta}"

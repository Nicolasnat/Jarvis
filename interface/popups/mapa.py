"""Mapeamento de titulos amigaveis e fabrica de popups especializados do N.E.X.U.S.

Roteia cada ferramenta para sua classe de popup especializada correspondente
ou para o PopupGenerico com titulo correto.
Todos os comentarios e docstrings neste modulo usam exclusivamente ASCII.
"""
from interface.popup_base import PopupBase
from interface.popups.controles import PopupControles
from interface.popups.documentos import PopupDocumentos
from interface.popups.generico import PopupGenerico
from interface.popups.listas import PopupLista
from interface.popups.pesquisa import PopupPesquisaGlobal
from interface.popups.projetos_programas import (
    PopupClipboard,
    PopupProgramas,
    PopupProjetos,
)
from interface.popups.sistema import PopupStatusSistema
from interface.popups.spotify import PopupSpotify

MAPA_TITULOS: dict[str, str] = {
    # Sistema e Controles
    "status_sistema": "STATUS DO SISTEMA",
    "definir_volume": "CONTROLES DO SISTEMA",
    "definir_brilho": "CONTROLES DO SISTEMA",

    # Midia
    "spotify": "SPOTIFY",

    # Listas: Tarefas, Lembretes, Memoria, Notas
    "listar_tarefas": "TAREFAS",
    "adicionar_tarefa": "TAREFAS",
    "concluir_tarefa": "TAREFAS",
    "listar_lembretes": "LEMBRETES",
    "agendar_lembrete": "LEMBRETES",
    "cancelar_lembrete": "LEMBRETES",
    "lembrar_fato": "MEMORIA",
    "buscar_memoria": "MEMORIA",
    "esquecer_fato": "MEMORIA",
    "anotar": "ANOTACOES",

    # Area de transferencia
    "ler_clipboard": "AREA DE TRANSFERENCIA",
    "copiar_clipboard": "AREA DE TRANSFERENCIA",

    # Projetos
    "listar_projetos": "PROJETOS",
    "criar_pasta": "PROJETOS",
    "abrir_pasta": "PROJETOS",
    "abrir_vscode": "PROJETOS",

    # Programas
    "abrir_programa": "PROGRAMAS",
    "fechar_programa": "PROGRAMAS",
    "descobrir_apps": "PROGRAMAS",
    "listar_apps": "PROGRAMAS",

    # Documentos
    "indexar_documentos": "DOCUMENTOS (RAG)",
    "perguntar_documentos": "DOCUMENTOS (RAG)",

    # Pesquisa
    "pesquisar_na_web": "PESQUISA GLOBAL",

    # Consultas e Delegacao
    "perguntar_qwen": "CONSULTA ESPECIALISTA",
    "pedir_ao_claude": "CONSULTA ESPECIALISTA",
    "pedir_ao_opencode": "EXECUCAO DE CODIGO",
    "pedir_ao_antigravity": "EXECUCAO DE CODIGO",
    "planejar_com_antigravity": "PLANO DE ARQUITETURA",
}


def criar_popup(
    nome: str,
    resultado: str,
    duracao: float = 0.0,
    termo_busca: str = "",
    parent=None,
) -> PopupBase:
    """Devolve a instancia do popup apropriado para a ferramenta informada."""
    ferramenta = str(nome or "").strip().lower()

    if ferramenta == "pesquisar_na_web":
        return PopupPesquisaGlobal(
            resultado=resultado,
            duracao=duracao,
            termo_busca=termo_busca,
            parent=parent,
        )

    if ferramenta == "status_sistema":
        return PopupStatusSistema(
            resultado=resultado,
            duracao=duracao,
            parent=parent,
        )

    if ferramenta in ("definir_volume", "definir_brilho"):
        return PopupControles(
            nome_ferramenta=nome,
            resultado=resultado,
            duracao=duracao,
            parent=parent,
        )

    if ferramenta == "spotify":
        return PopupSpotify(
            resultado=resultado,
            duracao=duracao,
            parent=parent,
        )

    if ferramenta in (
        "listar_tarefas",
        "adicionar_tarefa",
        "concluir_tarefa",
        "listar_lembretes",
        "agendar_lembrete",
        "cancelar_lembrete",
        "lembrar_fato",
        "buscar_memoria",
        "esquecer_fato",
        "anotar",
    ):
        return PopupLista(
            nome_ferramenta=nome,
            resultado=resultado,
            duracao=duracao,
            parent=parent,
        )

    if ferramenta in ("indexar_documentos", "perguntar_documentos"):
        return PopupDocumentos(
            nome_ferramenta=nome,
            resultado=resultado,
            duracao=duracao,
            parent=parent,
        )

    if ferramenta in ("listar_projetos", "criar_pasta", "abrir_pasta", "abrir_vscode"):
        return PopupProjetos(
            nome_ferramenta=nome,
            resultado=resultado,
            duracao=duracao,
            parent=parent,
        )

    if ferramenta in ("abrir_programa", "fechar_programa", "descobrir_apps", "listar_apps"):
        return PopupProgramas(
            nome_ferramenta=nome,
            resultado=resultado,
            duracao=duracao,
            parent=parent,
        )

    if ferramenta in ("ler_clipboard", "copiar_clipboard"):
        return PopupClipboard(
            nome_ferramenta=nome,
            resultado=resultado,
            duracao=duracao,
            parent=parent,
        )

    # Fallback com titulo amigavel para ferramentas genericas
    titulo = MAPA_TITULOS.get(ferramenta, ferramenta.replace("_", " ").upper())
    return PopupGenerico(
        nome_ferramenta=nome,
        resultado=resultado,
        duracao=duracao,
        titulo=titulo,
        parent=parent,
    )

"""Pacote de popups e modais do N.E.X.U.S.

Exporta as classes especializadas de popup, gerenciador e funcoes utilitarias.
Todos os comentarios e docstrings neste modulo usam exclusivamente ASCII.
"""
from interface.popup_base import PopupBase
from interface.popups.confirmacao import PopupConfirmacao
from interface.popups.controles import PopupControles
from interface.popups.documentos import PopupDocumentos
from interface.popups.generico import PopupGenerico
from interface.popups.gerenciador import (
    GerenciadorPopups,
    abrir_popup,
    obter_gerenciador,
)
from interface.popups.listas import PopupLista
from interface.popups.mapa import (
    MAPA_TITULOS,
    criar_popup,
)
from interface.popups.pesquisa import (
    PopupPesquisaGlobal,
    extrair_dominio,
    extrair_etiqueta_fonte,
    extrair_marcos_temporais,
    parse_pesquisa,
)
from interface.popups.projetos_programas import (
    PopupClipboard,
    PopupProgramas,
    PopupProjetos,
)
from interface.popups.sistema import PopupStatusSistema
from interface.popups.spotify import PopupSpotify

__all__ = [
    "PopupBase",
    "PopupConfirmacao",
    "PopupPesquisaGlobal",
    "PopupStatusSistema",
    "PopupControles",
    "PopupSpotify",
    "PopupLista",
    "PopupDocumentos",
    "PopupProjetos",
    "PopupProgramas",
    "PopupClipboard",
    "PopupGenerico",
    "GerenciadorPopups",
    "abrir_popup",
    "obter_gerenciador",
    "criar_popup",
    "MAPA_TITULOS",
    "parse_pesquisa",
    "extrair_dominio",
    "extrair_etiqueta_fonte",
    "extrair_marcos_temporais",
]

"""Gerenciador de exibicao e ciclo de vida de popups modais do N.E.X.U.S.

Roteia a abertura de popups especializados (pesquisar_na_web -> PopupPesquisaGlobal)
ou fallback generico (PopupGenerico) com overlay escurecido sobre a JanelaPrincipal.
Todos os comentarios e docstrings neste modulo usam exclusivamente ASCII.
"""
from typing import Optional

from PySide6.QtCore import QObject
from PySide6.QtWidgets import QWidget

from interface.popup_base import PopupBase
from interface.popups.generico import PopupGenerico
from interface.popups.mapa import criar_popup
from interface.popups.pesquisa import PopupPesquisaGlobal


class GerenciadorPopups(QObject):
    """Gerencia a instancia ativa e a transicao de popups sobre a interface."""

    def __init__(self, janela_principal: Optional[QWidget] = None):
        super().__init__(janela_principal)
        self.janela = janela_principal
        self._popup_ativo: Optional[PopupBase] = None

    def vincular_janela(self, janela: QWidget) -> None:
        """Associa a janela principal para overlay e posicionamento relativo."""
        self.janela = janela

    def abrir_popup(
        self,
        nome: str,
        resultado: str,
        duracao: float = 0.0,
        termo_busca: str = "",
    ) -> PopupBase:
        """Instancia, posiciona e exibe o popup apropriado para a ferramenta."""
        self.fechar_popup_ativo()

        popup = criar_popup(
            nome=nome,
            resultado=resultado,
            duracao=duracao,
            termo_busca=termo_busca,
            parent=self.janela,
        )

        self._popup_ativo = popup
        popup.fechado.connect(self._ao_fechar_popup)

        if self.janela is not None:
            if not self.janela.isVisible():
                self.janela.show()
            popup.resize(self.janela.size())
            popup.move(0, 0)
        else:
            popup.resize(500, 480)

        popup.abrir()
        return popup

    def fechar_popup_ativo(self) -> None:
        """Fecha e desvincula qualquer popup ativo no momento."""
        if self._popup_ativo is not None:
            try:
                self._popup_ativo.fechar()
            except Exception:
                pass
            self._popup_ativo = None

    def _ao_fechar_popup(self) -> None:
        """Callback acionado ao fechar o popup."""
        self._popup_ativo = None

    def popup_ativo(self) -> Optional[PopupBase]:
        """Devolve a referencia do popup atualmente em exibicao, se houver."""
        return self._popup_ativo


_instancia_global: Optional[GerenciadorPopups] = None


def obter_gerenciador(janela: Optional[QWidget] = None) -> GerenciadorPopups:
    """Devolve a instancia singleton do gerenciador de popups."""
    global _instancia_global
    if _instancia_global is None:
        _instancia_global = GerenciadorPopups(janela)
    elif janela is not None and _instancia_global.janela is None:
        _instancia_global.vincular_janela(janela)
    return _instancia_global


def abrir_popup(
    nome: str,
    resultado: str,
    duracao: float = 0.0,
    termo_busca: str = "",
    parent: Optional[QWidget] = None,
) -> PopupBase:
    """Funcao utilitaria para abrir popups diretamente pelo modulo."""
    gerenciador = obter_gerenciador(parent)
    if parent is not None and gerenciador.janela != parent:
        gerenciador.vincular_janela(parent)
    return gerenciador.abrir_popup(
        nome=nome,
        resultado=resultado,
        duracao=duracao,
        termo_busca=termo_busca,
    )

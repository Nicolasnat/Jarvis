"""Popup generico e reutilizavel para ferramentas do N.E.X.U.S.

Serve de fallback para exibir os resultados textuais de qualquer ferramenta
que nao possua um popup especializado dedicado.
Todos os comentarios e docstrings neste modulo usam exclusivamente ASCII.
"""
from datetime import datetime
from pathlib import Path

from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import (
    QWidget,
    QFrame,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QScrollArea,
)

from comum import garantir_pasta_dados
from interface.estilo import (
    COR_FUNDO_SECUNDARIO,
    COR_FUNDO_SUPERFICIE,
    COR_CIANO,
    COR_CIANO_BRILHO,
    COR_BORDA,
    COR_BORDA_SUAVE,
    COR_TEXTO,
    COR_TEXTO_MUTED,
    COR_TEXTO_BRANCO,
    COR_SUCESSO,
    FONTE_MONO,
)
from interface.popup_base import PopupBase


class PopupGenerico(PopupBase):
    """Popup de visualizacao padrao para saidas de ferramentas do sistema."""

    def __init__(
        self,
        nome_ferramenta: str = "FERRAMENTA",
        resultado: str = "",
        duracao: float = 0.0,
        titulo: str | None = None,
        parent=None,
    ):
        self._nome_ferramenta = str(nome_ferramenta or "ferramenta").strip()
        titulo_formatado = (titulo or self._nome_ferramenta.replace("_", " ")).upper()
        super().__init__(titulo=titulo_formatado, parent=parent)

        self._resultado = str(resultado or "")
        self._duracao = float(duracao) if isinstance(duracao, (int, float)) else 0.0

        linhas = self._resultado.strip().splitlines() if self._resultado.strip() else []
        self.definir_contagem(f"{len(linhas)} LINHAS" if linhas else "0 ITENS")

        self._montar_ui()
        self.exportar_telemetria_solicitado.connect(self._ao_exportar_telemetria)

    def _montar_ui(self) -> None:
        """Configura a aba unica de exibicao de resultado textual."""
        conteudo = QWidget()
        layout_raiz = QVBoxLayout(conteudo)
        layout_raiz.setContentsMargins(4, 4, 4, 4)
        layout_raiz.setSpacing(10)

        # Barra superior com metadados de execucao
        barra_status = QFrame()
        barra_status.setStyleSheet(f"""
            QFrame {{
                background-color: {COR_FUNDO_SUPERFICIE};
                border: 1px solid {COR_BORDA_SUAVE};
                border-left: 3px solid {COR_CIANO};
                border-radius: 6px;
            }}
        """)
        layout_status = QHBoxLayout(barra_status)
        layout_status.setContentsMargins(10, 6, 10, 6)

        selo = QLabel("STATUS: CONCLUIDO" if self._resultado.strip() else "STATUS: OCIOSO / VAZIO")
        selo.setStyleSheet(f"""
            color: {COR_SUCESSO if self._resultado.strip() else COR_TEXTO_MUTED};
            font-family: {FONTE_MONO};
            font-size: 10px;
            font-weight: bold;
            letter-spacing: 1px;
        """)
        layout_status.addWidget(selo)
        layout_status.addStretch(1)

        tempo_str = f"LATENCIA: {self._duracao:.2f}s"
        lbl_tempo = QLabel(tempo_str)
        lbl_tempo.setStyleSheet(f"""
            color: {COR_CIANO};
            font-family: {FONTE_MONO};
            font-size: 10px;
            font-weight: bold;
        """)
        layout_status.addWidget(lbl_tempo)
        layout_raiz.addWidget(barra_status)

        # Area com resultado real ou estado vazio
        if self._resultado.strip():
            area_scroll = QScrollArea()
            area_scroll.setWidgetResizable(True)
            area_scroll.setFrameShape(QFrame.Shape.NoFrame)
            area_scroll.setStyleSheet("background: transparent; border: none;")

            cartao_texto = QFrame()
            cartao_texto.setStyleSheet(f"""
                QFrame {{
                    background-color: rgba(7, 27, 38, 0.7);
                    border: 1px solid {COR_BORDA_SUAVE};
                    border-radius: 8px;
                }}
            """)
            layout_texto = QVBoxLayout(cartao_texto)
            layout_texto.setContentsMargins(12, 10, 12, 10)

            lbl_conteudo = QLabel(self._resultado.strip())
            lbl_conteudo.setWordWrap(True)
            lbl_conteudo.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
            lbl_conteudo.setStyleSheet(f"""
                color: {COR_TEXTO};
                font-family: {FONTE_MONO};
                font-size: 11px;
                line-height: 1.4;
            """)
            layout_texto.addWidget(lbl_conteudo)
            area_scroll.setWidget(cartao_texto)
            layout_raiz.addWidget(area_scroll, 1)
        else:
            layout_raiz.addWidget(self._criar_widget_vazio(), 1)

        self.adicionar_aba("Resultado", conteudo)

    def _criar_widget_vazio(self) -> QWidget:
        """Gera um estado vazio quando a ferramenta nao devolve dados."""
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(12, 40, 12, 40)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.setSpacing(8)

        icone = QLabel("◈")
        icone.setStyleSheet(f"color: {COR_TEXTO_MUTED}; font-size: 24px;")
        icone.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(icone)

        texto = QLabel("SEM RETORNO DE DADOS")
        texto.setStyleSheet(f"""
            color: {COR_TEXTO_MUTED};
            font-family: {FONTE_MONO};
            font-size: 11px;
            font-weight: bold;
            letter-spacing: 1px;
        """)
        texto.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(texto)

        subtexto = QLabel("A ferramenta foi executada, mas nao gerou conteudo textual.")
        subtexto.setStyleSheet(f"""
            color: {COR_TEXTO_MUTED};
            font-size: 10px;
        """)
        subtexto.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(subtexto)

        return widget

    def _ao_exportar_telemetria(self) -> Path:
        """Salva a saida da ferramenta em arquivo Markdown em dados/."""
        pasta = garantir_pasta_dados()
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        arquivo_md = pasta / f"execucao_{self._nome_ferramenta}_{ts}.md"

        linhas = [
            f"# Execucao de Ferramenta // {self._nome_ferramenta.upper()}",
            "",
            f"- **Data/Hora:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
            f"- **Ferramenta:** {self._nome_ferramenta}",
            f"- **Duracao:** {self._duracao:.2f}s",
            "",
            "## Saida Textual",
            "```",
            self._resultado if self._resultado.strip() else "[Sem retorno de dados]",
            "```",
            "",
        ]

        arquivo_md.write_text("\n".join(linhas), encoding="utf-8")

        self.btn_exportar.setText("✓ Telemetria Salva!")
        self.btn_exportar.setStyleSheet(f"""
            QPushButton {{
                background-color: rgba(0, 230, 118, 0.2);
                border: 1px solid {COR_SUCESSO};
                border-radius: 12px;
                color: {COR_SUCESSO};
                font-family: {FONTE_MONO};
                font-size: 11px;
                font-weight: bold;
                padding: 5px 14px;
            }}
        """)
        QTimer.singleShot(3000, self._restaurar_botao_exportar)
        return arquivo_md

    def _restaurar_botao_exportar(self) -> None:
        """Restaura o estilo padrao do botao de exportar."""
        self.btn_exportar.setText("Exportar Telemetria")
        self.btn_exportar.setStyleSheet(f"""
            QPushButton {{
                background-color: rgba(0, 229, 255, 0.15);
                border: 1px solid {COR_CIANO};
                border-radius: 12px;
                color: {COR_CIANO};
                font-family: {FONTE_MONO};
                font-size: 11px;
                font-weight: bold;
                padding: 5px 14px;
            }}
            QPushButton:hover {{
                background-color: {COR_CIANO};
                color: {COR_FUNDO_SECUNDARIO};
            }}
        """)

"""Componente base de modal e popup reutilizavel para o N.E.X.U.S.

Fornece o cartao central com cantos arredondados, borda ciano, cabecalho,
sistema de abas, rodape criptografado, animacao de entrada e fechamento via ESC.
Todos os comentarios e docstrings neste modulo usam exclusivamente ASCII.
"""
from PySide6.QtCore import Qt, Signal, QPropertyAnimation, QEasingCurve, QRect
from PySide6.QtGui import QColor, QFont, QPainter
from PySide6.QtWidgets import (
    QWidget,
    QFrame,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QStackedWidget,
    QGraphicsOpacityEffect,
    QSizePolicy,
)

from interface.estilo import (
    COR_FUNDO_SECUNDARIO,
    COR_CIANO,
    COR_CIANO_BRILHO,
    COR_BORDA,
    COR_TEXTO,
    COR_TEXTO_MUTED,
    COR_TEXTO_BRANCO,
    FONTE_MONO,
)


class PopupBase(QWidget):
    """Widget de dialogo/popup com estilo cibernetico e comportamento modal."""

    fechado = Signal()
    exportar_telemetria_solicitado = Signal()
    aba_mudou = Signal(int)

    def __init__(self, titulo: str = "SISTEMA", parent=None):
        if parent is not None:
            super().__init__(parent)
        else:
            super().__init__(None, Qt.WindowType.FramelessWindowHint | Qt.WindowType.Dialog)
            self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)

        self._titulo_base = titulo
        self._botoes_abas = []
        self._animacao_em_andamento = False

        self._construir_ui()

    def _construir_ui(self) -> None:
        """Monta a estrutura visual do popup."""
        layout_fundo = QVBoxLayout(self)
        layout_fundo.setContentsMargins(12, 12, 12, 12)
        layout_fundo.setAlignment(Qt.AlignmentFlag.AlignCenter)

        # Cartao central
        self.cartao = QFrame(self)
        self.cartao.setObjectName("cartao_central")
        self.cartao.setMinimumSize(360, 360)
        self.cartao.setMaximumSize(720, 560)
        self.cartao.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.cartao.setStyleSheet(f"""
            QFrame#cartao_central {{
                background-color: {COR_FUNDO_SECUNDARIO};
                border: 1px solid {COR_BORDA};
                border-radius: 14px;
            }}
        """)

        layout_cartao = QVBoxLayout(self.cartao)
        layout_cartao.setContentsMargins(18, 16, 18, 16)
        layout_cartao.setSpacing(12)

        # --- Cabecalho ---
        layout_cabecalho = QHBoxLayout()
        layout_cabecalho.setSpacing(10)

        icone = QLabel("◈")
        icone.setStyleSheet(f"color: {COR_CIANO}; font-size: 16px; font-weight: bold;")
        layout_cabecalho.addWidget(icone)

        self.rotulo_titulo = QLabel(f"{self._titulo_base.upper()} // N.E.X.U.S.")
        self.rotulo_titulo.setStyleSheet(f"""
            color: {COR_TEXTO_BRANCO};
            font-family: {FONTE_MONO};
            font-size: 13px;
            font-weight: bold;
            letter-spacing: 1px;
        """)
        layout_cabecalho.addWidget(self.rotulo_titulo)

        layout_cabecalho.addStretch(1)

        # Etiqueta de contagem / telemetria
        self.etiqueta_contagem = QLabel("ITENS: 0")
        self.etiqueta_contagem.setStyleSheet(f"""
            color: {COR_CIANO};
            background-color: rgba(0, 229, 255, 0.1);
            border: 1px solid {COR_BORDA};
            border-radius: 10px;
            padding: 2px 8px;
            font-family: {FONTE_MONO};
            font-size: 10px;
            font-weight: bold;
        """)
        layout_cabecalho.addWidget(self.etiqueta_contagem)

        # Botao Fechar (X)
        self.btn_fechar_x = QPushButton("✕")
        self.btn_fechar_x.setFixedSize(24, 24)
        self.btn_fechar_x.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_fechar_x.setStyleSheet(f"""
            QPushButton {{
                background-color: transparent;
                border: none;
                color: {COR_TEXTO_MUTED};
                font-size: 14px;
                font-weight: bold;
                padding: 0px;
            }}
            QPushButton:hover {{
                color: {COR_CIANO_BRILHO};
            }}
        """)
        self.btn_fechar_x.clicked.connect(self.fechar)
        layout_cabecalho.addWidget(self.btn_fechar_x)

        layout_cartao.addLayout(layout_cabecalho)

        # Linha divisoria do cabecalho
        linha_cabecalho = QFrame()
        linha_cabecalho.setFrameShape(QFrame.Shape.HLine)
        linha_cabecalho.setStyleSheet(f"border-top: 1px solid {COR_BORDA}; background: none;")
        layout_cartao.addWidget(linha_cabecalho)

        # --- Barra de abas ---
        self.layout_abas = QHBoxLayout()
        self.layout_abas.setSpacing(8)
        layout_cartao.addLayout(self.layout_abas)

        # --- Area de conteudo ---
        self.pilha_conteudo = QStackedWidget(self.cartao)
        self.pilha_conteudo.setStyleSheet("background: transparent;")
        layout_cartao.addWidget(self.pilha_conteudo, 1)

        # Linha divisoria do rodape
        linha_rodape = QFrame()
        linha_rodape.setFrameShape(QFrame.Shape.HLine)
        linha_rodape.setStyleSheet(f"border-top: 1px solid {COR_BORDA}; background: none;")
        layout_cartao.addWidget(linha_rodape)

        # --- Rodape ---
        layout_rodape = QHBoxLayout()
        layout_rodape.setSpacing(12)

        rotulo_seguranca = QLabel("SESSAO CRIPTOGRAFADA // KERNEL")
        rotulo_seguranca.setStyleSheet(f"""
            color: {COR_TEXTO_MUTED};
            font-family: {FONTE_MONO};
            font-size: 9px;
            letter-spacing: 1px;
        """)
        layout_rodape.addWidget(rotulo_seguranca)

        layout_rodape.addStretch(1)

        self.btn_fechar = QPushButton("Fechar [ESC]")
        self.btn_fechar.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_fechar.setStyleSheet(f"""
            QPushButton {{
                background-color: transparent;
                border: 1px solid {COR_TEXTO_MUTED};
                border-radius: 12px;
                color: {COR_TEXTO_MUTED};
                font-family: {FONTE_MONO};
                font-size: 11px;
                padding: 5px 12px;
            }}
            QPushButton:hover {{
                border-color: {COR_TEXTO};
                color: {COR_TEXTO};
            }}
        """)
        self.btn_fechar.clicked.connect(self.fechar)
        layout_rodape.addWidget(self.btn_fechar)

        self.btn_exportar = QPushButton("Exportar Telemetria")
        self.btn_exportar.setCursor(Qt.CursorShape.PointingHandCursor)
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
        self.btn_exportar.clicked.connect(self.exportar_telemetria_solicitado.emit)
        layout_rodape.addWidget(self.btn_exportar)

        layout_cartao.addLayout(layout_rodape)
        layout_fundo.addWidget(self.cartao)

        # Configura efeito para animacao de entrada
        self._efeito_opacidade = QGraphicsOpacityEffect(self.cartao)
        self.cartao.setGraphicsEffect(self._efeito_opacidade)

    def adicionar_aba(self, titulo: str, widget: QWidget) -> int:
        """Adiciona uma nova aba com botao e conteudo correspondente."""
        indice = self.pilha_conteudo.addWidget(widget)

        btn_aba = QPushButton(titulo)
        btn_aba.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_aba.setProperty("indice_aba", indice)
        btn_aba.clicked.connect(lambda: self.definir_aba_ativa(indice))
        self.layout_abas.addWidget(btn_aba)
        self._botoes_abas.append(btn_aba)

        if indice == 0:
            self.definir_aba_ativa(0)

        return indice

    def definir_aba_ativa(self, indice: int) -> None:
        """Altera a aba ativa e atualiza os estilos visuais."""
        if 0 <= indice < self.pilha_conteudo.count():
            self.pilha_conteudo.setCurrentIndex(indice)
            for i, btn in enumerate(self._botoes_abas):
                if i == indice:
                    btn.setStyleSheet(f"""
                        QPushButton {{
                            background-color: transparent;
                            border: none;
                            border-bottom: 2px solid {COR_CIANO};
                            color: {COR_CIANO};
                            font-family: {FONTE_MONO};
                            font-weight: bold;
                            padding: 6px 12px;
                            border-radius: 0px;
                        }}
                    """)
                else:
                    btn.setStyleSheet(f"""
                        QPushButton {{
                            background-color: transparent;
                            border: none;
                            border-bottom: 2px solid transparent;
                            color: {COR_TEXTO_MUTED};
                            font-family: {FONTE_MONO};
                            padding: 6px 12px;
                            border-radius: 0px;
                        }}
                        QPushButton:hover {{
                            color: {COR_TEXTO};
                        }}
                    """)
            self.aba_mudou.emit(indice)

    def definir_contagem(self, texto: str) -> None:
        """Atualiza o texto da etiqueta de contagem."""
        self.etiqueta_contagem.setText(str(texto))

    def abrir(self) -> None:
        """Exibe o popup e dispara a animacao de fade e escala."""
        if self.parent() is not None:
            self.resize(self.parent().size())
        self.show()
        self.raise_()
        self.activateWindow()

        # Animacao de fade in (opacidade)
        self._anim_fade = QPropertyAnimation(self._efeito_opacidade, b"opacity")
        self._anim_fade.setDuration(200)
        self._anim_fade.setStartValue(0.0)
        self._anim_fade.setEndValue(1.0)
        self._anim_fade.setEasingCurve(QEasingCurve.Type.OutCubic)
        self._anim_fade.start()

        # Animacao sutil de escala/posicao (deslize de baixo para o centro)
        geometria_alvo = self.cartao.geometry()
        geometria_inicio = QRect(
            geometria_alvo.x(),
            geometria_alvo.y() + 15,
            geometria_alvo.width(),
            geometria_alvo.height(),
        )
        self._anim_pos = QPropertyAnimation(self.cartao, b"geometry")
        self._anim_pos.setDuration(200)
        self._anim_pos.setStartValue(geometria_inicio)
        self._anim_pos.setEndValue(geometria_alvo)
        self._anim_pos.setEasingCurve(QEasingCurve.Type.OutCubic)
        self._anim_pos.start()

    def fechar(self) -> None:
        """Fecha o popup e notifica via sinal."""
        self.fechado.emit()
        self.hide()

    def paintEvent(self, event) -> None:
        """Desenha a camada escura e semi-transparente de fundo."""
        painter = QPainter(self)
        painter.fillRect(self.rect(), QColor(2, 8, 14, 185))

    def keyPressEvent(self, event) -> None:
        """Fecha o popup ao teclar ESC."""
        if event.key() == Qt.Key.Key_Escape:
            self.fechar()
            event.accept()
        else:
            super().keyPressEvent(event)

    def mousePressEvent(self, event) -> None:
        """Fecha o popup se houver clique fora do cartao central."""
        pos = event.position().toPoint() if hasattr(event, "position") else event.pos()
        if not self.cartao.geometry().contains(pos):
            self.fechar()
            event.accept()
        else:
            super().mousePressEvent(event)

"""Janela principal do N.E.X.U.S.

Janela sem bordas nativas (frameless), fundo translucido, orbe animado,
pilula de status em tempo real e barra de comando para texto e voz.
Todos os comentarios e docstrings neste modulo usam exclusivamente ASCII.
"""
from PySide6.QtCore import Qt, Signal, QPoint
from PySide6.QtWidgets import (
    QWidget,
    QFrame,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QSizePolicy,
)

from interface.estilo import (
    COR_FUNDO,
    COR_FUNDO_SECUNDARIO,
    COR_FUNDO_SUPERFICIE,
    COR_CIANO,
    COR_CIANO_BRILHO,
    COR_CIANO_ESCURO,
    COR_BORDA,
    COR_TEXTO,
    COR_TEXTO_MUTED,
    COR_TEXTO_BRANCO,
    COR_SUCESSO,
    COR_ALERTA,
    FONTE_MONO,
)
from interface.orbe import Orbe
from interface.acoes_rapidas import CapsulaAcoesRapidas


class PilulaStatus(QFrame):
    """Pilula de status tripla que exibe o estado operacional do N.E.X.U.S."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("pilula_status")
        self.setStyleSheet(f"""
            QFrame#pilula_status {{
                background-color: {COR_FUNDO_SECUNDARIO};
                border: 1px solid {COR_BORDA};
                border-radius: 16px;
                padding: 3px 12px;
            }}
        """)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(10, 4, 10, 4)
        layout.setSpacing(10)

        # Item 1: Estado global do sistema
        self.item1 = QLabel("SISTEMA ATIVO")
        self.item1.setStyleSheet(f"""
            color: {COR_CIANO};
            font-family: {FONTE_MONO};
            font-size: 10px;
            font-weight: bold;
        """)
        layout.addWidget(self.item1)

        # Divisor 1
        div1 = QLabel("│")
        div1.setStyleSheet(f"color: {COR_CIANO_ESCURO}; font-size: 10px;")
        layout.addWidget(div1)

        # Item 2: Estado dinamico (escutando, pensando, etc.)
        self.item2 = QLabel("AGUARDANDO WAKEWORD")
        self.item2.setStyleSheet(f"""
            color: {COR_TEXTO_MUTED};
            font-family: {FONTE_MONO};
            font-size: 10px;
            font-weight: bold;
        """)
        layout.addWidget(self.item2)

        # Divisor 2
        div2 = QLabel("│")
        div2.setStyleSheet(f"color: {COR_CIANO_ESCURO}; font-size: 10px;")
        layout.addWidget(div2)

        # Item 3: Conexao neural / modelo
        self.item3 = QLabel("NEURAL LINK: ON")
        self.item3.setStyleSheet(f"""
            color: {COR_SUCESSO};
            font-family: {FONTE_MONO};
            font-size: 10px;
            font-weight: bold;
        """)
        layout.addWidget(self.item3)


class JanelaPrincipal(QWidget):
    """Janela principal do assistente com orbe animado e comandos."""

    comando_digitado = Signal(str)
    mic_pressionado = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.Window)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)

        self._posicao_arrasto = None
        self.setFixedSize(440, 580)

        self._construir_ui()

    def _construir_ui(self) -> None:
        """Monta o leiaute completo da janela principal."""
        layout_raiz = QVBoxLayout(self)
        layout_raiz.setContentsMargins(12, 12, 12, 12)

        # Container principal com cantos arredondados e borda ciano
        self.container = QFrame(self)
        self.container.setObjectName("container_principal")
        self.container.setStyleSheet(f"""
            QFrame#container_principal {{
                background-color: {COR_FUNDO};
                border: 1px solid {COR_BORDA};
                border-radius: 20px;
            }}
        """)

        layout_conteudo = QVBoxLayout(self.container)
        layout_conteudo.setContentsMargins(16, 12, 16, 16)
        layout_conteudo.setSpacing(10)

        # --- Topo / Barra de titulo discreta ---
        layout_topo = QHBoxLayout()
        layout_topo.setSpacing(8)

        icone_topo = QLabel("◈")
        icone_topo.setStyleSheet(f"color: {COR_CIANO}; font-size: 13px; font-weight: bold;")
        layout_topo.addWidget(icone_topo)

        rotulo_topo = QLabel("N.E.X.U.S. // CORE INTERFACE")
        rotulo_topo.setStyleSheet(f"""
            color: {COR_TEXTO_MUTED};
            font-family: {FONTE_MONO};
            font-size: 10px;
            font-weight: bold;
            letter-spacing: 1px;
        """)
        layout_topo.addWidget(rotulo_topo)

        layout_topo.addStretch(1)

        # Botao minimizar
        btn_minimizar = QPushButton("—")
        btn_minimizar.setFixedSize(22, 22)
        btn_minimizar.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_minimizar.setStyleSheet(f"""
            QPushButton {{
                background-color: transparent;
                border: none;
                color: {COR_TEXTO_MUTED};
                font-size: 11px;
                font-weight: bold;
                padding: 0px;
            }}
            QPushButton:hover {{
                color: {COR_CIANO};
            }}
        """)
        btn_minimizar.clicked.connect(self.showMinimized)
        layout_topo.addWidget(btn_minimizar)

        # Botao fechar/ocultar
        btn_fechar = QPushButton("✕")
        btn_fechar.setFixedSize(22, 22)
        btn_fechar.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_fechar.setStyleSheet(f"""
            QPushButton {{
                background-color: transparent;
                border: none;
                color: {COR_TEXTO_MUTED};
                font-size: 13px;
                font-weight: bold;
                padding: 0px;
            }}
            QPushButton:hover {{
                color: {COR_CIANO_BRILHO};
            }}
        """)
        btn_fechar.clicked.connect(self.hide)
        layout_topo.addWidget(btn_fechar)

        layout_conteudo.addLayout(layout_topo)

        # --- Area Central com o Orbe ---
        self.orbe = Orbe(self.container)
        layout_conteudo.addWidget(self.orbe, 1, Qt.AlignmentFlag.AlignCenter)

        # --- Pilula de Status ---
        self.pilula = PilulaStatus(self.container)
        layout_conteudo.addWidget(self.pilula, 0, Qt.AlignmentFlag.AlignCenter)

        # Capsula de acoes rapidas (acima da barra de comando)
        self.capsula_acoes = CapsulaAcoesRapidas(self.container)
        layout_conteudo.addWidget(self.capsula_acoes, 0, Qt.AlignmentFlag.AlignCenter)

        layout_conteudo.addSpacing(6)

        # --- Rodape / Barra de Comando ---
        self.barra_comando = QFrame(self.container)
        self.barra_comando.setObjectName("barra_comando")
        self.barra_comando.setStyleSheet(f"""
            QFrame#barra_comando {{
                background-color: {COR_FUNDO_SUPERFICIE};
                border: 1px solid {COR_BORDA};
                border-radius: 22px;
            }}
            QFrame#barra_comando:focus-within {{
                border: 1px solid {COR_CIANO};
            }}
        """)

        layout_barra = QHBoxLayout(self.barra_comando)
        layout_barra.setContentsMargins(6, 4, 6, 4)
        layout_barra.setSpacing(6)

        # Botao microfone
        self.btn_mic = QPushButton("🎙")
        self.btn_mic.setFixedSize(34, 34)
        self.btn_mic.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_mic.setToolTip("Ativar escuta por voz")
        self.btn_mic.setStyleSheet(f"""
            QPushButton {{
                background-color: rgba(0, 229, 255, 0.12);
                border: 1px solid {COR_BORDA};
                border-radius: 17px;
                color: {COR_CIANO};
                font-size: 15px;
                padding: 0px;
            }}
            QPushButton:hover {{
                background-color: {COR_CIANO};
                color: {COR_FUNDO};
            }}
            QPushButton:pressed {{
                background-color: {COR_CIANO_ESCURO};
            }}
        """)
        self.btn_mic.clicked.connect(self.mic_pressionado.emit)
        layout_barra.addWidget(self.btn_mic)

        # Campo de texto para comando quantico
        self.campo_comando = QLineEdit(self.barra_comando)
        self.campo_comando.setPlaceholderText("Fale ou digite comando quantico...")
        self.campo_comando.setStyleSheet(f"""
            QLineEdit {{
                background: transparent;
                border: none;
                color: {COR_TEXTO_BRANCO};
                font-family: {FONTE_MONO};
                font-size: 12px;
                padding: 4px 6px;
            }}
            QLineEdit::placeholder {{
                color: {COR_TEXTO_MUTED};
            }}
        """)
        self.campo_comando.returnPressed.connect(self._ao_enviar)
        layout_barra.addWidget(self.campo_comando, 1)

        # Botao enviar
        self.btn_enviar = QPushButton("➤")
        self.btn_enviar.setFixedSize(34, 34)
        self.btn_enviar.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_enviar.setToolTip("Enviar comando [Enter]")
        self.btn_enviar.setStyleSheet(f"""
            QPushButton {{
                background-color: {COR_CIANO};
                border: none;
                border-radius: 17px;
                color: {COR_FUNDO};
                font-size: 14px;
                font-weight: bold;
                padding: 0px;
            }}
            QPushButton:hover {{
                background-color: {COR_CIANO_BRILHO};
            }}
            QPushButton:pressed {{
                background-color: {COR_CIANO_ESCURO};
            }}
        """)
        self.btn_enviar.clicked.connect(self._ao_enviar)
        layout_barra.addWidget(self.btn_enviar)

        layout_conteudo.addWidget(self.barra_comando)
        layout_raiz.addWidget(self.container)

    def _ao_enviar(self) -> None:
        """Processa e emite o comando textual submetido."""
        texto = self.campo_comando.text().strip()
        if texto:
            self.campo_comando.clear()
            self.comando_digitado.emit(texto)

    def definir_estado(self, estado: str, acao: str = "") -> None:
        """Atualiza a pilula e o orbe conforme o estado operacional do assistente."""
        chave = (estado or "").strip().lower()

        if chave in ("ocioso", "pronto", "aguardando"):
            self.pilula.item1.setText("SISTEMA ATIVO")
            self.pilula.item1.setStyleSheet(f"color: {COR_CIANO}; font-family: {FONTE_MONO}; font-size: 10px; font-weight: bold;")
            self.pilula.item2.setText("AGUARDANDO WAKEWORD")
            self.pilula.item2.setStyleSheet(f"color: {COR_TEXTO_MUTED}; font-family: {FONTE_MONO}; font-size: 10px; font-weight: bold;")
            self.pilula.item3.setText("NEURAL LINK: ON")
            self.pilula.item3.setStyleSheet(f"color: {COR_SUCESSO}; font-family: {FONTE_MONO}; font-size: 10px; font-weight: bold;")
            self.orbe.set_nivel(0.0)

        elif chave in ("ouvindo", "escutando"):
            self.pilula.item1.setText("SISTEMA ATIVO")
            self.pilula.item1.setStyleSheet(f"color: {COR_CIANO}; font-family: {FONTE_MONO}; font-size: 10px; font-weight: bold;")
            self.pilula.item2.setText("ESCUTANDO COMANDO")
            self.pilula.item2.setStyleSheet(f"color: {COR_CIANO_BRILHO}; font-family: {FONTE_MONO}; font-size: 10px; font-weight: bold;")
            self.pilula.item3.setText("CAPTURA: 16kHz")
            self.pilula.item3.setStyleSheet(f"color: {COR_CIANO}; font-family: {FONTE_MONO}; font-size: 10px; font-weight: bold;")
            self.orbe.set_nivel(0.40)

        elif chave in ("pensando", "processando"):
            self.pilula.item1.setText("SISTEMA OCUPADO")
            self.pilula.item1.setStyleSheet(f"color: {COR_ALERTA}; font-family: {FONTE_MONO}; font-size: 10px; font-weight: bold;")
            self.pilula.item2.setText("PROCESSANDO NEURAL...")
            self.pilula.item2.setStyleSheet(f"color: {COR_ALERTA}; font-family: {FONTE_MONO}; font-size: 10px; font-weight: bold;")
            self.pilula.item3.setText("OLLAMA: ATIVO")
            self.pilula.item3.setStyleSheet(f"color: {COR_ALERTA}; font-family: {FONTE_MONO}; font-size: 10px; font-weight: bold;")
            self.orbe.set_nivel(0.20)

        elif chave in ("falando", "respondendo"):
            self.pilula.item1.setText("SISTEMA FALANDO")
            self.pilula.item1.setStyleSheet(f"color: {COR_CIANO_BRILHO}; font-family: {FONTE_MONO}; font-size: 10px; font-weight: bold;")
            self.pilula.item2.setText("SINTESE PIPER")
            self.pilula.item2.setStyleSheet(f"color: {COR_CIANO}; font-family: {FONTE_MONO}; font-size: 10px; font-weight: bold;")
            self.pilula.item3.setText("AUDIO OUT: ON")
            self.pilula.item3.setStyleSheet(f"color: {COR_CIANO_BRILHO}; font-family: {FONTE_MONO}; font-size: 10px; font-weight: bold;")
            self.orbe.set_nivel(0.65)

        elif chave in ("executando", "ferramenta", "tarefa"):
            self.pilula.item1.setText("TAREFA ATIVA")
            self.pilula.item1.setStyleSheet(f"color: #ff80ab; font-family: {FONTE_MONO}; font-size: 10px; font-weight: bold;")
            if acao:
                self.pilula.item2.setText(acao)
            else:
                self.pilula.item2.setText("EXECUTANDO FERRAMENTA")
            self.pilula.item2.setStyleSheet(f"color: #ff4081; font-family: {FONTE_MONO}; font-size: 10px; font-weight: bold;")
            self.pilula.item3.setText("KERNEL: ATIVO")
            self.pilula.item3.setStyleSheet(f"color: #ff80ab; font-family: {FONTE_MONO}; font-size: 10px; font-weight: bold;")
            self.orbe.set_nivel(0.30)

        else:
            self.pilula.item2.setText(estado.upper())

    def mostrar_ou_trazer(self) -> None:
        """Exibe a janela ou traz para a frente se estiver minimizada/oculta."""
        if not self.isVisible():
            self.show()
        if self.isMinimized():
            self.showNormal()
        self.raise_()
        self.activateWindow()

    def keyPressEvent(self, event) -> None:
        """Oculta a janela ao teclar ESC."""
        if event.key() == Qt.Key.Key_Escape:
            self.hide()
            event.accept()
        else:
            super().keyPressEvent(event)

    def mousePressEvent(self, event) -> None:
        """Captura posicao inicial para permitir arrastar a janela."""
        if event.button() == Qt.MouseButton.LeftButton:
            self._posicao_arrasto = (
                event.globalPosition().toPoint() - self.frameGeometry().topLeft()
            )
            event.accept()
        else:
            super().mousePressEvent(event)

    def mouseMoveEvent(self, event) -> None:
        """Move a janela conforme o arraste do mouse."""
        if (
            event.buttons() == Qt.MouseButton.LeftButton
            and self._posicao_arrasto is not None
        ):
            self.move(event.globalPosition().toPoint() - self._posicao_arrasto)
            event.accept()
        else:
            super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event) -> None:
        """Finaliza o arraste da janela."""
        self._posicao_arrasto = None
        super().mouseReleaseEvent(event)

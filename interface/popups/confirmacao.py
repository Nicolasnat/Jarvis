"""Popup de confirmacao de seguranca para operacoes sensiveis do N.E.X.U.S.

Substitui o prompt de confirmacao textual do terminal ('digite sim') quando
a interface grafica estiver ativa.
Todos os comentarios e docstrings neste modulo usam exclusivamente ASCII.
"""
import threading
import time
from typing import Sequence

from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from interface.estilo import (
    COR_ALERTA,
    COR_BORDA_SUAVE,
    COR_FUNDO_SECUNDARIO,
    COR_FUNDO_SUPERFICIE,
    COR_PERIGO,
    COR_TEXTO,
    COR_TEXTO_BRANCO,
    COR_TEXTO_MUTED,
    FONTE_MONO,
)
from interface.popup_base import PopupBase


class PopupConfirmacao(PopupBase):
    """Popup modal que exige autorizacao explicita para acoes sensiveis."""

    respondida = Signal(bool)

    def __init__(
        self,
        comandos: Sequence[str] | str | None = None,
        timeout: float | None = None,
        parent=None,
    ):
        if parent is None and not isinstance(timeout, (int, float)) and timeout is not None:
            parent = timeout
            timeout = None

        super().__init__(titulo="CONFIRMACAO DE SEGURANCA", parent=parent)

        if isinstance(comandos, str):
            self._comandos = [comandos]
        elif comandos:
            self._comandos = [str(c) for c in comandos]
        else:
            self._comandos = ["(nenhum comando especificado)"]

        try:
            self._timeout_total = float(timeout) if timeout is not None else 0.0
        except (ValueError, TypeError):
            self._timeout_total = 0.0

        self._tempo_restante = max(0.0, self._timeout_total)
        self._instante_inicio = time.time()
        self._ja_respondeu = False
        self._trava = threading.Lock()
        self._timer_countdown = None

        qtd = len(self._comandos)
        self.definir_contagem(f"{qtd} COMANDO{'S' if qtd != 1 else ''}")

        self._montar_conteudo()
        self._configurar_rodape()

        if self._timeout_total > 0.0:
            self._timer_countdown = QTimer(self)
            self._timer_countdown.setInterval(100)
            self._timer_countdown.timeout.connect(self._ao_tick_timeout)

    def _montar_conteudo(self) -> None:
        """Cria o painel de alerta e a listagem com caixas para cada comando."""
        conteudo = QWidget()
        layout_conteudo = QVBoxLayout(conteudo)
        layout_conteudo.setContentsMargins(0, 4, 0, 4)
        layout_conteudo.setSpacing(10)

        # Faixa de alerta em destaque ambar/vermelho
        faixa_alerta = QFrame()
        faixa_alerta.setObjectName("faixa_alerta")
        faixa_alerta.setStyleSheet(f"""
            QFrame#faixa_alerta {{
                background-color: rgba(255, 82, 82, 0.12);
                border: 1px solid rgba(255, 82, 82, 0.40);
                border-left: 4px solid {COR_PERIGO};
                border-radius: 8px;
            }}
        """)
        layout_alerta = QVBoxLayout(faixa_alerta)
        layout_alerta.setContentsMargins(12, 10, 12, 10)
        layout_alerta.setSpacing(4)

        linha_topo = QHBoxLayout()
        linha_topo.setSpacing(8)

        icone_alerta = QLabel("▲")
        icone_alerta.setStyleSheet(f"""
            color: {COR_PERIGO};
            font-size: 13px;
            font-weight: bold;
            background: transparent;
        """)
        linha_topo.addWidget(icone_alerta)

        titulo_alerta = QLabel("A tarefa envolve operacoes sensiveis.")
        titulo_alerta.setStyleSheet(f"""
            color: {COR_TEXTO_BRANCO};
            font-family: {FONTE_MONO};
            font-size: 12px;
            font-weight: bold;
            background: transparent;
        """)
        linha_topo.addWidget(titulo_alerta)
        linha_topo.addStretch(1)
        layout_alerta.addLayout(linha_topo)

        subtitulo_alerta = QLabel(
            "Aprovacao expressa do operador e obrigatoria para prosseguir com a execucao."
        )
        subtitulo_alerta.setWordWrap(True)
        subtitulo_alerta.setStyleSheet(f"""
            color: {COR_TEXTO};
            font-size: 11px;
            background: transparent;
        """)
        layout_alerta.addWidget(subtitulo_alerta)

        layout_conteudo.addWidget(faixa_alerta)

        # Scroll area para listar comandos sensiveis
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setStyleSheet("background: transparent; border: none;")

        container_comandos = QWidget()
        container_comandos.setStyleSheet("background: transparent;")
        layout_comandos = QVBoxLayout(container_comandos)
        layout_comandos.setContentsMargins(0, 0, 0, 0)
        layout_comandos.setSpacing(8)

        for cmd in self._comandos:
            caixa_cmd = QFrame()
            caixa_cmd.setStyleSheet(f"""
                QFrame {{
                    background-color: {COR_FUNDO_SUPERFICIE};
                    border: 1px solid {COR_BORDA_SUAVE};
                    border-left: 3px solid {COR_ALERTA};
                    border-radius: 6px;
                }}
            """)
            layout_cmd = QVBoxLayout(caixa_cmd)
            layout_cmd.setContentsMargins(10, 8, 10, 8)

            lbl_cmd = QLabel(cmd)
            lbl_cmd.setWordWrap(True)
            lbl_cmd.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
            lbl_cmd.setStyleSheet(f"""
                color: {COR_TEXTO_BRANCO};
                font-family: {FONTE_MONO};
                font-size: 11px;
                background: transparent;
                border: none;
            """)
            layout_cmd.addWidget(lbl_cmd)
            layout_comandos.addWidget(caixa_cmd)

        layout_comandos.addStretch(1)
        scroll.setWidget(container_comandos)

        layout_conteudo.addWidget(scroll, 1)

        self.pilha_conteudo.addWidget(conteudo)
        self.pilha_conteudo.setCurrentWidget(conteudo)

    def _configurar_rodape(self) -> None:
        """Reconfigura a barra inferior para acomodar botoes e contagem regressiva."""
        self.btn_fechar.hide()
        self.btn_exportar.hide()

        layout_cartao = self.cartao.layout()
        layout_rodape = layout_cartao.itemAt(layout_cartao.count() - 1).layout()

        self.rotulo_timeout = layout_rodape.itemAt(0).widget()
        if self._timeout_total > 0.0:
            self.rotulo_timeout.setText(f"EXPIRA EM: {int(self._timeout_total)}s")
            self.rotulo_timeout.setStyleSheet(f"""
                color: {COR_ALERTA};
                font-family: {FONTE_MONO};
                font-size: 10px;
                font-weight: bold;
                letter-spacing: 1px;
            """)
        else:
            self.rotulo_timeout.setText("CONFIRMACAO MANUAL")
            self.rotulo_timeout.setStyleSheet(f"""
                color: {COR_TEXTO_MUTED};
                font-family: {FONTE_MONO};
                font-size: 10px;
                letter-spacing: 1px;
            """)

        self.btn_cancelar = QPushButton("CANCELAR [ESC]")
        self.btn_cancelar.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_cancelar.setStyleSheet(f"""
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
                border-color: {COR_PERIGO};
                color: {COR_PERIGO};
            }}
        """)
        self.btn_cancelar.clicked.connect(lambda: self.responder(False))
        layout_rodape.addWidget(self.btn_cancelar)

        self.btn_autorizar = QPushButton("AUTORIZAR [Enter]")
        self.btn_autorizar.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_autorizar.setDefault(True)
        self.btn_autorizar.setAutoDefault(True)
        self.btn_autorizar.setStyleSheet(f"""
            QPushButton {{
                background-color: rgba(255, 171, 0, 0.22);
                border: 1px solid {COR_ALERTA};
                border-radius: 12px;
                color: {COR_ALERTA};
                font-family: {FONTE_MONO};
                font-size: 11px;
                font-weight: bold;
                padding: 5px 14px;
            }}
            QPushButton:hover {{
                background-color: {COR_ALERTA};
                color: {COR_FUNDO_SECUNDARIO};
            }}
        """)
        self.btn_autorizar.clicked.connect(lambda: self.responder(True))
        layout_rodape.addWidget(self.btn_autorizar)

    def _ao_tick_timeout(self) -> None:
        """Atualiza o rotulo de contagem e cancela se o tempo expirar."""
        decorrido = time.time() - self._instante_inicio
        restante = max(0.0, self._timeout_total - decorrido)
        self._tempo_restante = restante

        if self.rotulo_timeout is not None:
            self.rotulo_timeout.setText(f"EXPIRA EM: {int(restante + 0.9)}s")

        if restante <= 0.0:
            if self._timer_countdown is not None:
                try:
                    self._timer_countdown.stop()
                except Exception:
                    pass
            self.responder(False)

    def responder(self, aprovado: bool) -> None:
        """Emite a resposta garantindo execucao unica e fecha a janela."""
        with self._trava:
            if self._ja_respondeu:
                return
            self._ja_respondeu = True

        if self._timer_countdown is not None:
            try:
                self._timer_countdown.stop()
            except Exception:
                pass

        try:
            self.respondida.emit(bool(aprovado))
        except Exception:
            pass

        super().fechar()

    def fechar(self) -> None:
        """Garante que fechar manualmente ou via ESC/X equivale a recusar."""
        with self._trava:
            if not self._ja_respondeu:
                self._ja_respondeu = True
                deve_emitir = True
            else:
                deve_emitir = False

        if deve_emitir:
            if self._timer_countdown is not None:
                try:
                    self._timer_countdown.stop()
                except Exception:
                    pass
            try:
                self.respondida.emit(False)
            except Exception:
                pass

        super().fechar()

    def abrir(self) -> None:
        """Abre o popup e inicia o temporizador se configurado."""
        self._instante_inicio = time.time()
        if self._timer_countdown is not None and not self._timer_countdown.isActive():
            self._timer_countdown.start()
        super().abrir()

    def showEvent(self, event) -> None:
        """Inicia contagem regressiva ao se tornar visivel se necessario."""
        super().showEvent(event)
        if self._timer_countdown is not None and not self._timer_countdown.isActive():
            self._instante_inicio = time.time()
            self._timer_countdown.start()

    def keyPressEvent(self, event) -> None:
        """Interpreta as teclas Enter e ESC como atalhos para os botoes."""
        tecla = event.key()
        if tecla in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            self.responder(True)
            event.accept()
        elif tecla == Qt.Key.Key_Escape:
            self.responder(False)
            event.accept()
        else:
            super().keyPressEvent(event)

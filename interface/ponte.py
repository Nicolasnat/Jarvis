"""Ponte de comunicacao assincrona baseada em sinais Qt (PySide6).

Permite conectar os eventos e estados do N.E.X.U.S. (modo texto, voz, plugins)
a interface grafica de forma desacoplada e segura entre threads.
Todos os comentarios e docstrings neste modulo usam exclusivamente ASCII.
"""
import threading

from PySide6.QtCore import QObject, Signal


class Ponte(QObject):
    """Ponte de sinais Qt para desacoplar o nucleo da interface de desktop."""

    estado_mudou = Signal(str)
    cerebro_mudou = Signal(str)
    fala_nivel = Signal(float)
    ferramenta_iniciada = Signal(str, dict)
    ferramenta_concluida = Signal(str, str)
    pedir_confirmacao = Signal(list)
    confirmacao_respondida = Signal(bool)
    resposta_final = Signal(str)
    comando_digitado = Signal(str)
    mic_clicado = Signal()
    wakeword = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._evento_confirmacao = threading.Event()
        self._resultado_confirmacao = False
        self._trava_confirmacao = threading.Lock()
        self.confirmacao_respondida.connect(self.responder_confirmacao)

    def emitir_estado(self, estado: str) -> None:
        """Emite sinal de atualizacao de estado (ocioso, ouvindo, etc.)."""
        try:
            self.estado_mudou.emit(str(estado))
        except Exception:
            pass

    def emitir_cerebro(self, cerebro: str) -> None:
        """Emite qual cerebro esta ativo no momento."""
        try:
            self.cerebro_mudou.emit(str(cerebro))
        except Exception:
            pass

    def emitir_fala_nivel(self, nivel: float) -> None:
        """Emite sinal com amplitude de fala (0.0 a 1.0)."""
        try:
            self.fala_nivel.emit(float(nivel))
        except Exception:
            pass

    def emitir_ferramenta_iniciada(self, nome: str, argumentos: dict) -> None:
        """Emite sinal antes da execucao de uma ferramenta do catalogo."""
        try:
            self.ferramenta_iniciada.emit(str(nome), dict(argumentos or {}))
        except Exception:
            pass

    def emitir_ferramenta_concluida(self, nome: str, resultado: str) -> None:
        """Emite sinal apos a execucao de uma ferramenta do catalogo."""
        try:
            self.ferramenta_concluida.emit(str(nome), str(resultado or ""))
        except Exception:
            pass

    def emitir_pedir_confirmacao(self, comandos) -> None:
        """Emite sinal solicitando aprovacao de uma lista de acoes criticas."""
        try:
            if isinstance(comandos, str):
                comandos = [comandos]
            self.pedir_confirmacao.emit([str(c) for c in (comandos or [])])
        except Exception:
            pass

    def pedir_confirmacao_bloqueante(self, comandos, timeout: float = 120.0) -> bool:
        """Pede confirmacao na interface e bloqueia ate a resposta ou timeout.

        Seguro para chamar de uma thread de trabalho: a leitura acontece via
        threading.Event, independente do loop de eventos do Qt.
        """
        if isinstance(comandos, str):
            comandos = [comandos]
        comandos = [str(c) for c in (comandos or [])]

        with self._trava_confirmacao:
            self._evento_confirmacao.clear()
            self._resultado_confirmacao = False
            self.pedir_confirmacao.emit(comandos)
            if not self._evento_confirmacao.wait(timeout):
                self.confirmacao_respondida.emit(False)
                return False
            return bool(self._resultado_confirmacao)

    def responder_confirmacao(self, aprovado: bool) -> None:
        """Registra a resposta do usuario e libera a thread que aguardava."""
        self._resultado_confirmacao = bool(aprovado)
        self._evento_confirmacao.set()

    def emitir_resposta_final(self, resposta: str) -> None:
        """Emite sinal com a resposta final gerada pelo assistente."""
        try:
            self.resposta_final.emit(str(resposta or ""))
        except Exception:
            pass

    def emitir_comando(self, comando: str) -> None:
        """Emite comando textual submetido pelo usuario."""
        try:
            self.comando_digitado.emit(str(comando or ""))
        except Exception:
            pass

    def emitir_wakeword(self) -> None:
        """Emite sinal quando a wakeword e detectada (abre/traz a janela)."""
        try:
            self.wakeword.emit()
        except Exception:
            pass

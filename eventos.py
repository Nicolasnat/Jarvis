"""Registro de eventos do N.E.X.U.S.

Centraliza o buffer de eventos e emite sinais para a interface.
Todos os comentarios e docstrings neste modulo usam exclusivamente ASCII.
"""
import threading
import time
from datetime import datetime
from typing import Any, Dict, List, Optional

from PySide6.QtCore import QObject, Signal


class RegistroEventos(QObject):
    """Registro thread-safe de eventos do sistema com sinal para a GUI."""

    evento_novo = Signal(dict)

    _instancia: Optional["RegistroEventos"] = None
    _trava_instancia = threading.Lock()

    def __new__(cls) -> "RegistroEventos":
        with cls._trava_instancia:
            if cls._instancia is None:
                cls._instancia = super().__new__(cls)
                cls._instancia._inicializado = False
            return cls._instancia

    def __init__(self) -> None:
        if self._inicializado:
            return
        super().__init__()
        self._buffer: List[Dict[str, Any]] = []
        self._trava = threading.Lock()
        self._max_buffer = 5000
        self._inicializado = True

    @classmethod
    def instanciar(cls) -> "RegistroEventos":
        """Retorna a instancia unica (singleton)."""
        return cls()

    def registrar_evento(
        self,
        tipo: str,
        titulo: str,
        detalhe: str = "",
        ok: Optional[bool] = None,
        duracao_ms: int = 0,
        exec_id: str = "",
    ) -> Dict[str, Any]:
        """Adiciona um evento ao buffer e emite sinal para a GUI.

        Args:
            tipo: Categoria do evento (ex: "estado", "voz", "cerebro", "ferramenta",
                  "comando", "seguranca", "erro").
            titulo: Resumo curto do evento.
            detalhe: Texto completo/longo do evento.
            ok: True=sucesso, False=falha, None=informativo.
            duracao_ms: Duracao em milissegundos (se aplicavel).
            exec_id: Identificador de execucao correlacionado.

        Returns:
            O dicionario do evento criado.
        """
        evento = {
            "ts": datetime.now().isoformat(timespec="milliseconds"),
            "tipo": tipo,
            "titulo": titulo,
            "detalhe": detalhe,
            "ok": ok,
            "duracao_ms": duracao_ms,
            "exec_id": exec_id,
        }

        with self._trava:
            self._buffer.append(evento)
            if len(self._buffer) > self._max_buffer:
                self._buffer = self._buffer[-self._max_buffer:]

        try:
            self.evento_novo.emit(evento)
        except Exception:
            pass

        return evento

    def obter_registro(self) -> List[Dict[str, Any]]:
        """Retorna uma copia do buffer atual (thread-safe)."""
        with self._trava:
            return list(self._buffer)

    def limpar(self) -> None:
        """Limpa o buffer de eventos."""
        with self._trava:
            self._buffer.clear()


def registrar_evento(
    tipo: str,
    titulo: str,
    detalhe: str = "",
    ok: Optional[bool] = None,
    duracao_ms: int = 0,
    exec_id: str = "",
) -> Dict[str, Any]:
    """Funcao de conveniencia para registrar evento via singleton."""
    return RegistroEventos.instanciar().registrar_evento(
        tipo, titulo, detalhe, ok, duracao_ms, exec_id
    )


def obter_registro() -> List[Dict[str, Any]]:
    """Funcao de conveniencia para obter buffer via singleton."""
    return RegistroEventos.instanciar().obter_registro()


def limpar_registro() -> None:
    """Funcao de conveniencia para limpar buffer via singleton."""
    RegistroEventos.instanciar().limpar()
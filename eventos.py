"""Registro de eventos do Nexus: buffer circular, arquivo JSONL, mascaramento e rotação.

Este modulo e independente da interface (funciona sem Qt) e thread-safe.
"""
import json
import os
import re
import threading
import time
from collections import deque
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Deque, Dict, List, Optional

from comum import PASTA_DADOS


# Tipos de evento validos
TIPOS_EVENTO = (
    "estado",
    "voz",
    "cerebro",
    "ferramenta",
    "comando",
    "seguranca",
    "erro",
    "sistema",
)


# Configuracoes
MAX_BUFFER = 2000           # eventos em memoria
MAX_ARQUIVO_MB = 5          # rotação a cada 5 MB
MAX_ARQUIVOS_ROTACAO = 3    # manter 3 arquivos
MAX_DETALHE_CHARS = 300     # truncamento de detalhes longos
MAX_DETALHE_EXPANDIDO = 2000  # limite maximo ao expandir
PERMISSAO_ARQUIVO = 0o600   # permissao do arquivo de log


# Padrões para mascarar segredos (reutiliza logica de seguranca)
_PADRAO_AIza = re.compile(r"\bAIza[0-9A-Za-z\-_]{35}\b")
_PADRAO_SK = re.compile(r"\bsk-[0-9A-Za-z]{48}\b")
_PADRAO_GHP = re.compile(r"\bghp_[0-9A-Za-z]{36}\b")
_PADRAO_AUTH = re.compile(r"(?i)(authorization|bearer)\s*[:=]\s*[\"']?([^\"'\s]{10,})")
_PADRAO_APIKEY = re.compile(r"(?i)(api[_-]?key|token|secret|password)\s*[:=]\s*[\"']?([^\"'\s]{8,})")
_PADRAO_ENV = re.compile(r"(?i)^\s*([A-Z_]+(?:KEY|SECRET|TOKEN|PASS))\s*=\s*([^\s#]+)")

PADROES_SEGREDOS = [
    (_PADRAO_AIza, "AIza***"),
    (_PADRAO_SK, "sk-***"),
    (_PADRAO_GHP, "ghp_**"),
    (_PADRAO_AUTH, r"\1: ***"),
    (_PADRAO_APIKEY, r"\1=***"),
    (_PADRAO_ENV, r"\1=***"),
]


def mascarar_segredos(texto: str) -> str:
    """Mascara segredos conhecidos no texto."""
    if not texto:
        return ""
    resultado = str(texto)
    for padrao, substituto in PADROES_SEGREDOS:
        resultado = padrao.sub(substituto, resultado)
    return resultado


def truncar(texto: str, max_chars: int = MAX_DETALHE_CHARS) -> str:
    """Trunca texto longo adicionando '...' no final."""
    if not texto:
        return ""
    s = str(texto)
    if len(s) <= max_chars:
        return s
    return s[:max_chars - 1] + "…"


def truncar_expandido(texto: str, max_chars: int = MAX_DETALHE_EXPANDIDO) -> str:
    """Trunca para o limite expandido maximo."""
    if not texto:
        return ""
    s = str(texto)
    if len(s) <= max_chars:
        return s
    return s[:max_chars - 1] + "…"


class RegistroEventos:
    """Gerenciador thread-safe de eventos com buffer circular e persistencia JSONL."""

    def __init__(
        self,
        max_buffer: int = MAX_BUFFER,
        arquivo_log: Optional[Path] = None,
        max_arquivo_mb: int = MAX_ARQUIVO_MB,
        max_arquivos: int = MAX_ARQUIVOS_ROTACAO,
    ):
        self._max_buffer = max_buffer
        self._buffer: Deque[Dict[str, Any]] = deque(maxlen=max_buffer)
        self._lock = threading.RLock()
        self._ouvintes: List[Callable[[Dict[str, Any]], None]] = []

        # Arquivo de log
        if arquivo_log is None:
            PASTA_DADOS.mkdir(parents=True, exist_ok=True)
            self._arquivo_log = PASTA_DADOS / "log_nexus.jsonl"
        else:
            self._arquivo_log = arquivo_log
        self._max_arquivo_bytes = max_arquivo_mb * 1024 * 1024
        self._max_arquivos = max_arquivos

        # Garante que o arquivo existe
        self._arquivo_log.parent.mkdir(parents=True, exist_ok=True)
        if not self._arquivo_log.exists():
            self._arquivo_log.touch(mode=PERMISSAO_ARQUIVO)

        # Carrega eventos existentes do arquivo (ultimos max_buffer)
        self._carregar_do_arquivo()

    def _carregar_do_arquivo(self) -> None:
        """Carrega eventos do arquivo JSONL para o buffer (ultimos max_buffer)."""
        if not self._arquivo_log.exists():
            return
        try:
            with open(self._arquivo_log, "r", encoding="utf-8") as f:
                linhas = f.readlines()
            # Pega apenas as ultimas max_buffer linhas
            for linha in linhas[-self._max_buffer:]:
                linha = linha.strip()
                if not linha:
                    continue
                try:
                    evento = json.loads(linha)
                    self._buffer.append(evento)
                except json.JSONDecodeError:
                    continue
        except Exception:
            pass  # Falha silenciosa

    def _verificar_rotacao(self) -> None:
        """Verifica se o arquivo excedeu o tamanho maximo e rotaciona se necessario."""
        try:
            if self._arquivo_log.stat().st_size >= self._max_arquivo_bytes:
                self._rotacionar_arquivo()
        except Exception:
            pass

    def _rotacionar_arquivo(self) -> None:
        """Rotaciona arquivos de log: .jsonl -> .1.jsonl -> .2.jsonl -> remove."""
        # Remove o mais antigo
        mais_antigo = self._arquivo_log.with_suffix(f".{self._max_arquivos}.jsonl")
        if mais_antigo.exists():
            try:
                mais_antigo.unlink()
            except Exception:
                pass

        # Renomeia os existentes
        for i in range(self._max_arquivos - 1, 0, -1):
            atual = self._arquivo_log.with_suffix(f".{i}.jsonl")
            prox = self._arquivo_log.with_suffix(f".{i + 1}.jsonl")
            if atual.exists():
                try:
                    atual.rename(prox)
                except Exception:
                    pass

    def registrar(
        self,
        tipo: str,
        titulo: str,
        detalhe: Optional[str] = None,
        ok: Optional[bool] = None,
        duracao_ms: Optional[int] = None,
        exec_id: Optional[int] = None,
        metadados: Optional[Dict[str, Any]] = None,
    ) -> None:
        """Registra um evento no buffer e no arquivo."""
        if tipo not in TIPOS_EVENTO:
            tipo = "sistema"

        # Prepara o evento
        agora = datetime.now()
        evento = {
            "ts": agora.isoformat(timespec="milliseconds"),
            "tipo": tipo,
            "titulo": str(titulo or ""),
            "detalhe": mascarar_segredos(truncar(detalhe or "")),
            "ok": ok,
            "duracao_ms": duracao_ms,
            "exec_id": exec_id,
        }
        if metadados:
            # Mascara metadados tambem
            metadados_limpos = {}
            for k, v in metadados.items():
                if isinstance(v, str):
                    metadados_limpos[k] = mascarar_segredos(truncar(v))
                else:
                    metadados_limpos[k] = v
            evento["metadados"] = metadados_limpos

        # Adiciona ao buffer (thread-safe)
        with self._lock:
            self._buffer.append(evento)

        # Notifica ouvintes (fora do lock para evitar deadlock)
        for ouvinte in self._ouvintes:
            try:
                ouvinte(evento)
            except Exception:
                pass

        # Escreve no arquivo (append) e verifica rotação
        try:
            with open(self._arquivo_log, "a", encoding="utf-8") as f:
                f.write(json.dumps(evento, ensure_ascii=False) + "\n")
            self._verificar_rotacao()
        except Exception:
            pass  # Falha silenciosa - nao derruba o Nexus

    def obter_todos(self, limite: Optional[int] = None) -> List[Dict[str, Any]]:
        """Retorna copia dos eventos do buffer (mais recentes primeiro)."""
        with self._lock:
            eventos = list(self._buffer)
        if limite and limite > 0:
            return eventos[-limite:]
        return eventos

    def obter_por_tipo(self, tipo: str, limite: Optional[int] = None) -> List[Dict[str, Any]]:
        """Filtra eventos por tipo."""
        with self._lock:
            eventos = [e for e in self._buffer if e.get("tipo") == tipo]
        if limite and limite > 0:
            return eventos[-limite:]
        return eventos

    def limpar_buffer(self) -> None:
        """Limpa apenas o buffer em memoria (nao apaga o arquivo)."""
        with self._lock:
            self._buffer.clear()

    def registrar_ouvinte(self, callback: Callable[[Dict[str, Any]], None]) -> None:
        """Registra um callback para receber eventos em tempo real."""
        self._ouvintes.append(callback)

    def remover_ouvinte(self, callback: Callable[[Dict[str, Any]], None]) -> None:
        """Remove um callback registrado."""
        try:
            self._ouvintes.remove(callback)
        except ValueError:
            pass

    def obter_estatisticas(self) -> Dict[str, Any]:
        """Retorna estatisticas do buffer."""
        with self._lock:
            total = len(self._buffer)
            por_tipo: Dict[str, int] = {}
            for e in self._buffer:
                t = e.get("tipo", "sistema")
                por_tipo[t] = por_tipo.get(t, 0) + 1
        return {
            "total_buffer": total,
            "max_buffer": self._max_buffer,
            "por_tipo": por_tipo,
            "arquivo_log": str(self._arquivo_log),
            "tamanho_arquivo_bytes": self._arquivo_log.stat().st_size if self._arquivo_log.exists() else 0,
        }


# Instancia global (singleton)
_registro_global: Optional[RegistroEventos] = None
_lock_global = threading.Lock()


def obter_registro() -> RegistroEventos:
    """Retorna a instancia global do registro de eventos."""
    global _registro_global
    with _lock_global:
        if _registro_global is None:
            _registro_global = RegistroEventos()
        return _registro_global


def registrar_evento(
    tipo: str,
    titulo: str,
    detalhe: Optional[str] = None,
    ok: Optional[bool] = None,
    duracao_ms: Optional[int] = None,
    exec_id: Optional[int] = None,
    metadados: Optional[Dict[str, Any]] = None,
) -> None:
    """Funcao de conveniencia para registrar evento no registro global."""
    obter_registro().registrar(tipo, titulo, detalhe, ok, duracao_ms, exec_id)


def registrar_ouvinte_global(callback: Callable[[Dict[str, Any]], None]) -> None:
    """Registra ouvinte no registro global."""
    obter_registro().registrar_ouvinte(callback)


# Funcoes de conveniencia para tipos comuns
def log_estado(titulo: str, detalhe: str = "", exec_id: Optional[int] = None) -> None:
    registrar_evento("estado", titulo, detalhe, exec_id=exec_id)


def log_voz(titulo: str, detalhe: str = "", ok: Optional[bool] = None, exec_id: Optional[int] = None) -> None:
    registrar_evento("voz", titulo, detalhe, ok, exec_id=exec_id)


def log_cerebro(titulo: str, detalhe: str = "", ok: Optional[bool] = None, duracao_ms: Optional[int] = None, exec_id: Optional[int] = None) -> None:
    registrar_evento("cerebro", titulo, detalhe, ok, duracao_ms, exec_id)


def log_ferramenta(titulo: str, detalhe: str = "", ok: Optional[bool] = None, duracao_ms: Optional[int] = None, exec_id: Optional[int] = None, metadados: Optional[Dict] = None) -> None:
    registrar_evento("ferramenta", titulo, detalhe, ok, duracao_ms, exec_id, metadados)


def log_comando(titulo: str, detalhe: str = "", ok: Optional[bool] = None, duracao_ms: Optional[int] = None, exec_id: Optional[int] = None) -> None:
    registrar_evento("comando", titulo, detalhe, ok, duracao_ms, exec_id)


def log_seguranca(titulo: str, detalhe: str = "", ok: Optional[bool] = None, exec_id: Optional[int] = None) -> None:
    registrar_evento("seguranca", titulo, detalhe, ok, exec_id=exec_id)


def log_erro(titulo: str, detalhe: str = "", exec_id: Optional[int] = None) -> None:
    registrar_evento("erro", titulo, detalhe, False, exec_id=exec_id)


def log_sistema(titulo: str, detalhe: str = "", ok: Optional[bool] = None, exec_id: Optional[int] = None) -> None:
    registrar_evento("sistema", titulo, detalhe, ok, exec_id=exec_id)


# Teste rapido se executado diretamente
if __name__ == "__main__":
    print("Testando eventos.py...")
    reg = RegistroEventos(max_buffer=100)

    # Testa registro basico
    reg.registrar("estado", "Teste iniciado", "Iniciando testes")
    reg.registrar("ferramenta", "abrir_programa", "Abrindo vscode", True, 150, 1)
    reg.registrar("comando", "$ xdg-open /home/user", "Executado com sucesso", True, 200, 1)
    reg.registrar("seguranca", "Comando bloqueado", "rm -rf /", False, None, 2)
    reg.registrar("erro", "Falha ao abrir", "Arquivo nao encontrado", False, None, 3)

    # Testa mascaramento
    reg.registrar("sistema", "Chave detectada", "Minha chave e AIzaSyB12345678901234567890123456789012345")
    reg.registrar("sistema", "Token", "Bearer sk-abcdefghijklmnopqrstuvwxyz1234567890123456")

    # Testa truncamento
    texto_longo = "x" * 500
    reg.registrar("sistema", "Texto longo", texto_longo)

    # Verifica buffer
    todos = reg.obter_todos()
    print(f"Eventos no buffer: {len(todos)}")

    # Verifica mascaramento no ultimo evento
    ultimo = todos[-1]
    print(f"Ultimo detalhe: {ultimo.get('detalhe', '')[:100]}")

    # Verifica arquivo
    print("Teste concluido com sucesso!")
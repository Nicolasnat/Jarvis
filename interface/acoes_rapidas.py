"""Capsula de acoes rapidas para a interface grafica do N.E.X.U.S.

Substitui popups para acoes que apenas executam algo (uma linha), mantendo
popups apenas para acoes que retornam conteudo para leitura, confirmacoes
de seguranca ou casos especiais.
Todos os comentarios e docstrings usam exclusivamente ASCII.
"""
import math
import time
from typing import Any, Dict, Optional, Tuple

from PySide6.QtCore import (
    Qt,
    QTimer,
    QPropertyAnimation,
    QEasingCurve,
    QPoint,
    QRect,
    QParallelAnimationGroup,
    QObject,
)
from PySide6.QtGui import QColor, QFont, QPainter, QPen
from PySide6.QtWidgets import (
    QFrame,
    QGraphicsOpacityEffect,
    QHBoxLayout,
    QLabel,
    QVBoxLayout,
    QWidget,
)

from interface.estilo import COR_CIANO, COR_CIANO_BRILHO, FONTE_MONO


# Cores por estado
COR_EXECUTANDO = COR_CIANO
COR_CONCLUIDO = "#00e676"  # mesmo tom de sucesso
COR_FALHA = "#ff5252"  # vermelho/ambar forte

COR_TEXTO_PRINCIPAL = "#ffffff"
COR_TEXTO_SECUNDARIO = COR_CIANO_BRILHO
COR_TEXTO_SECUNDARIO_APAGADO = "rgba(128, 243, 255, 180)"
COR_FUNDO_CAPSULA = "rgba(7, 27, 38, 0.92)"
COR_BORDA_CAPSULA = COR_CIANO


# Constantes visuais e temporais
ALTURA_CAPSULA = 56
LARGURA_MIN = 260
LARGURA_MAX_FRACAO = 0.85  # 85% da janela
DURACAO_ANIM_ENTRADA = 250  # ms
DURACAO_ANIM_SAIDA = 250  # ms
TEMPO_CONCLUIDO_VISIVEL = 2500  # ms
TEMPO_FALHA_VISIVEL = 5000  # ms
INTERVALO_ANIM_ICONE = 40  # ms (25 FPS)
INTERVALO_PROGRESSO = 16  # ms (~60 FPS)

LETRAS_ESPACAMENTO = 2.0  # px


# Listas de decisao: capsula ou popup
ACOES_SOMENTE_CAPSULA = {
    "abrir_programa",
    "fechar_programa",
    "spotify",
    "definir_volume",
    "definir_brilho",
    "abrir_pasta",
    "abrir_vscode",
    "criar_pasta",
    "anotar",
    "adicionar_tarefa",
    "concluir_tarefa",
    "agendar_lembrete",
    "cancelar_lembrete",
    "copiar_clipboard",
    "esquecer_fato",
    "lembrar_fato",
}

ACOES_COM_CONTEUDO_POPUP = {
    "pesquisar_na_web",
    "perguntar_qwen",
    "status_sistema",
    "listar_tarefas",
    "listar_lembretes",
    "listar_apps",
    "listar_projetos",
    "buscar_memoria",
    "ler_clipboard",
    "perguntar_documentos",
    "indexar_documentos",
    "pedir_ao_opencode",
    "pedir_ao_antigravity",
    "planejar_com_antigravity",
    "pedir_ao_claude",
}


def deve_usar_capsula(nome_ferramenta: str) -> bool:
    """Retorna True se a acao deve usar capsula, False se deve abrir popup."""
    nome = str(nome_ferramenta or "").strip().lower()
    if not nome:
        return True  # generico

    if nome == "confirmar_risco":
        return False  # sempre popup

    if nome in ACOES_SOMENTE_CAPSULA:
        return True

    if nome in ACOES_COM_CONTEUDO_POPUP:
        return False

    # Ferramenta rapida nao listada: capsula generica
    return True


def truncar_meio(texto: str, max_chars: int = 40) -> str:
    """Trunca texto no meio com '...' se maior que max_chars."""
    s = str(texto or "")
    if len(s) <= max_chars:
        return s
    if max_chars < 5:
        return s[:max_chars]
    meio = max_chars // 2 - 1
    return s[:meio] + "..." + s[-(max_chars - meio - 3):] if (max_chars - meio - 3) > 0 else s[:meio] + "..."


def _extrair_args_chave(args: Dict[str, Any], *chaves: str) -> str:
    if not isinstance(args, dict):
        return ""
    for c in chaves:
        if c in args and args[c] not in (None, ""):
            v = args[c]
            if isinstance(v, (list, tuple)) and v:
                return str(v[0])
            return str(v)
    return ""


def _texto_executando(nome: str, args: Dict[str, Any]) -> str:
    n = str(nome or "").lower()
    if n == "abrir_programa":
        app = _extrair_args_chave(args, "programa", "app", "aplicativo", "nome")
        return f"ABRINDO {app.upper() or 'APLICATIVO'}..."
    if n == "fechar_programa":
        app = _extrair_args_chave(args, "programa", "app", "aplicativo", "nome")
        return f"ENCERRANDO {app.upper() or 'APLICATIVO'}..."
    if n == "spotify":
        acao = _extrair_args_chave(args, "acao", "comando", "acao_spotify").lower()
        if acao in ("tocar", "play", "iniciar"):
            alvo = _extrair_args_chave(args, "playlist", "musica", "faixa", "album", "busca", "q")
            return f"TOCANDO {alvo.upper() or 'SPOTIFY'}..."
        if acao in ("pausar", "pause", "parar", "stop"):
            return "PAUSANDO SPOTIFY..."
        if acao in ("proxima", "next", "avancar", "skip"):
            return "PROXIMA FAIXA..."
        if acao in ("anterior", "previous", "voltar"):
            return "FAIXA ANTERIOR..."
        if acao in ("volume", "set_volume", "ajustar_volume"):
            vol = _extrair_args_chave(args, "volume", "nivel", "valor")
            return f"AJUSTANDO VOLUME SPOTIFY {vol}"
        return "CONECTANDO AO SPOTIFY..."
    if n == "definir_volume":
        vol = _extrair_args_chave(args, "volume", "nivel", "valor", "porcentagem")
        return f"AJUSTANDO VOLUME {vol}..." if vol else "AJUSTANDO VOLUME..."
    if n == "definir_brilho":
        br = _extrair_args_chave(args, "brilho", "nivel", "valor", "porcentagem")
        return f"AJUSTANDO BRILHO {br}..." if br else "AJUSTANDO BRILHO..."
    if n == "abrir_pasta":
        d = _extrair_args_chave(args, "pasta", "diretorio", "caminho", "path")
        return f"ABRINDO {d.upper() or 'PASTA'}..."
    if n == "abrir_vscode":
        d = _extrair_args_chave(args, "pasta", "diretorio", "projeto", "path")
        return f"ABRINDO {d.upper() or 'PROJETO'} NO VSCODE..."
    if n == "criar_pasta":
        d = _extrair_args_chave(args, "nome", "pasta", "diretorio")
        return f"CRIANDO PASTA {d.upper()}..." if d else "CRIANDO PASTA..."
    if n == "anotar":
        return "SALVANDO ANOTACAO..."
    if n == "adicionar_tarefa":
        return "ADICIONANDO TAREFA..."
    if n == "concluir_tarefa":
        return "CONCLUINDO TAREFA..."
    if n == "agendar_lembrete":
        return "AGENDANDO LEMBRETE..."
    if n == "cancelar_lembrete":
        return "CANCELANDO LEMBRETE..."
    if n == "copiar_clipboard":
        return "COPIANDO PARA AREA DE TRANSFERENCIA..."
    if n == "esquecer_fato":
        return "ESQUECENDO FATO..."
    if n == "lembrar_fato":
        return "SALVANDO FATO..."
    return f"EXECUTANDO {n.replace('_', ' ').upper()}..."


def _texto_concluido(nome: str, args: Dict[str, Any], resultado: str) -> str:
    n = str(nome or "").lower()
    res = str(resultado or "")
    res_low = res.lower()

    if n == "abrir_programa":
        app = _extrair_args_chave(args, "programa", "app", "aplicativo", "nome")
        return f"{app.upper() or 'APLICATIVO'} ABERTO"
    if n == "fechar_programa":
        app = _extrair_args_chave(args, "programa", "app", "aplicativo", "nome")
        return f"{app.upper() or 'APLICATIVO'} ENCERRADO"
    if n == "spotify":
        acao = _extrair_args_chave(args, "acao", "comando", "acao_spotify").lower()
        if acao in ("tocar", "play"):
            # tenta extrair faixa/playlist do resultado
            # resultado costuma conter nome
            if res and res_low not in ("ok", "feito", "executado", "concluido"):
                return f"TOCANDO: {res.strip().upper()[:60]}"
            alvo = _extrair_args_chave(args, "playlist", "musica", "faixa", "album", "busca")
            return f"TOCANDO: {alvo.upper() or 'SPOTIFY'}"
        if acao in ("pausar", "pause"):
            return "SPOTIFY PAUSADO"
        if acao in ("proxima", "next", "skip"):
            return "PROXIMA FAIXA TOCANDO"
        if acao in ("anterior", "previous"):
            return "FAIXA ANTERIOR TOCANDO"
        if acao in ("volume", "set_volume"):
            vol = _extrair_args_chave(args, "volume", "nivel", "valor")
            if vol:
                return f"VOLUME: {vol}%".replace("%%", "%")
            return "VOLUME AJUSTADO"
        if res and res_low not in ("ok", "feito"):
            return res.strip().upper()[:60]
        return "SPOTIFY ATUALIZADO"
    if n == "definir_volume":
        vol = _extrair_args_chave(args, "volume", "nivel", "valor", "porcentagem")
        if vol:
            v = str(vol).rstrip("%")
            return f"VOLUME: {v}%"
        return "VOLUME AJUSTADO"
    if n == "definir_brilho":
        br = _extrair_args_chave(args, "brilho", "nivel", "valor", "porcentagem")
        if br:
            b = str(br).rstrip("%")
            return f"BRILHO: {b}%"
        return "BRILHO AJUSTADO"
    if n == "abrir_pasta":
        d = _extrair_args_chave(args, "pasta", "diretorio", "caminho", "path")
        return f"{d.upper() or 'PASTA'} ABERTA"
    if n == "abrir_vscode":
        d = _extrair_args_chave(args, "pasta", "diretorio", "projeto", "path")
        return f"{d.upper() or 'PROJETO'} ABERTO"
    if n == "criar_pasta":
        d = _extrair_args_chave(args, "nome", "pasta", "diretorio")
        return f"PASTA {d.upper()} CRIADA" if d else "PASTA CRIADA"
    if n == "anotar":
        return "ANOTACAO SALVA"
    if n == "adicionar_tarefa":
        return "TAREFA ADICIONADA"
    if n == "concluir_tarefa":
        return "TAREFA CONCLUIDA"
    if n == "agendar_lembrete":
        return "LEMBRETE AGENDADO"
    if n == "cancelar_lembrete":
        return "LEMBRETE CANCELADO"
    if n == "copiar_clipboard":
        return "COPIADO PARA AREA DE TRANSFERENCIA"
    if n == "esquecer_fato":
        return "FATO ESQUECIDO"
    if n == "lembrar_fato":
        return "FATO LEMBRADO"
    if res and res_low not in ("ok", "feito", "executado", "concluido", "sucesso"):
        return res.strip().upper()[:60]
    return "CONCLUIDO"


def _texto_falha(nome: str, args: Dict[str, Any], resultado: str) -> str:
    res = str(resultado or "")
    if res:
        # manter curto e real
        return f"FALHA: {res.strip().upper()[:80]}"
    return "FALHA NA EXECUCAO"


class CapsulaAcoesRapidas(QFrame):
    """Capsula elegante reutilizada para exibir acoes rapidas em execucao."""

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.setObjectName("capsula_acoes_rapidas")
        self.setFixedHeight(ALTURA_CAPSULA)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.setVisible(False)

        # Estado
        self._nome_atual = ""
        self._args_atual: Dict[str, Any] = {}
        self._exec_contador = 0
        self._estado = "oculto"  # oculto | executando | concluido | falha
        self._tempo_inicio_exec: Optional[float] = None
        self._tempo_conclusao: Optional[float] = None
        self._falha = False

        # Animacao icone (equalizador/arco)
        self._angulo_arco = 0.0
        self._fase_eq = 0.0
        self._timer_icone = QTimer(self)
        self._timer_icone.setInterval(INTERVALO_ANIM_ICONE)
        self._timer_icone.timeout.connect(self._atualizar_icone)

        # Animacao saida/timeout
        self._timer_saida = QTimer(self)
        self._timer_saida.setSingleShot(True)
        self._timer_saida.timeout.connect(self._iniciar_saida)

        # Efeito e animacoes
        self._efeito_opacidade = QGraphicsOpacityEffect(self)
        self._efeito_opacidade.setOpacity(0.0)
        self.setGraphicsEffect(self._efeito_opacidade)

        self._anim_fade: Optional[QPropertyAnimation] = None
        self._anim_pos: Optional[QPropertyAnimation] = None
        self._grupo_anim: Optional[QParallelAnimationGroup] = None

        # UI
        self._construir_ui()

        # Estilo base
        self._aplicar_estilo()

    def _construir_ui(self) -> None:
        layout_raiz = QHBoxLayout(self)
        layout_raiz.setContentsMargins(12, 6, 12, 6)
        layout_raiz.setSpacing(10)

        # Icone animado
        self._icone = QLabel(self)
        self._icone.setFixedSize(22, 22)
        self._icone.setAlignment(Qt.AlignmentFlag.AlignCenter)
        font_icone = QFont("Consolas", 10, QFont.Weight.Bold)
        font_icone.setStyleHint(QFont.StyleHint.Monospace)
        self._icone.setFont(font_icone)
        layout_raiz.addWidget(self._icone)

        # Texto (principal + secundario)
        layout_txt = QVBoxLayout()
        layout_txt.setSpacing(2)
        layout_txt.setContentsMargins(0, 2, 0, 2)

        self._lbl_principal = QLabel("", self)
        self._lbl_principal.setStyleSheet(
            f"color: {COR_TEXTO_PRINCIPAL}; font-family: {FONTE_MONO}; font-size: 11px; font-weight: bold; letter-spacing: {LETRAS_ESPACAMENTO}px;"
        )
        self._lbl_principal.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)

        self._lbl_secundario = QLabel("", self)
        self._lbl_secundario.setStyleSheet(
            f"color: {COR_TEXTO_SECUNDARIO_APAGADO}; font-family: {FONTE_MONO}; font-size: 9px; font-weight: bold; letter-spacing: {LETRAS_ESPACAMENTO}px;"
        )
        self._lbl_secundario.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)

        layout_txt.addWidget(self._lbl_principal)
        layout_txt.addWidget(self._lbl_secundario)
        layout_raiz.addLayout(layout_txt, 1)

        # Fio de progresso na base (simulado com linha)
        self._progress = QFrame(self)
        self._progress.setFixedHeight(2)
        self._progress.setStyleSheet(f"background-color: {COR_EXECUTANDO}; border: none;")
        self._progress.setGeometry(0, self.height() - 2, 0, 2)
        self._progress.setVisible(False)

    def _aplicar_estilo(self) -> None:
        self.setStyleSheet(
            f"""
            QFrame#capsula_acoes_rapidas {{
                background-color: {COR_FUNDO_CAPSULA};
                border: 1px solid {COR_BORDA_CAPSULA};
                border-radius: 28px;
            }}
            """
        )

    def _atualizar_icone(self) -> None:
        if self._estado != "executando":
            self._timer_icone.stop()
            return
        self._angulo_arco = (self._angulo_arco + 12.0) % 360.0
        self._fase_eq = (self._fase_eq + 0.4) % (2.0 * math.pi)
        self.update()

    def paintEvent(self, event) -> None:
        super().paintEvent(event)
        if self._estado != "executando":
            return
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        # desenha mini arco animado no icone
        rect = QRect(6, (self.height() - 16) // 2, 16, 16)
        painter.setPen(QPen(QColor(COR_EXECUTANDO), 1.6))
        start = int(self._angulo_arco * 16)
        span = int(60 * 16)
        painter.drawArc(rect, start, span)

    def _ajustar_tamanho_ao_texto(self) -> None:
        if not self.parent():
            return
        txt = self._lbl_principal.text() + " " + self._lbl_secundario.text()
        fm = self.fontMetrics()
        w = fm.horizontalAdvance(txt) + 80  # espaco p/ icone + padding
        w = max(LARGURA_MIN, min(int(self.parent().width() * LARGURA_MAX_FRACAO), w))
        self.setFixedWidth(w)
        # reposiciona progresso
        self._progress.setGeometry(8, self.height() - 2, w - 16, 2)

    def _posicao_alvo(self) -> QPoint:
        if not self.parent():
            return QPoint(0, 0)
        pw = self.parent().width()
        ph = self.parent().height()
        x = (pw - self.width()) // 2
        y_alvo = ph - 90
        # tenta usar barra de comando da janela pai
        try:
            janela = self.parent().window()
            barra = getattr(janela, "barra_comando", None)
            if barra is not None and barra.isVisible():
                g = barra.geometry()
                # acima da barra: y = topo barra - altura capsula - 4
                y_alvo = g.top() - self.height() - 4
            else:
                pilula = getattr(janela, "pilula", None)
                if pilula is not None and pilula.isVisible():
                    g = pilula.geometry()
                    y_alvo = g.bottom() + 4
        except Exception:
            pass
        return QPoint(x, y_alvo)

    def _posicao_inicial(self) -> QPoint:
        p = self._posicao_alvo()
        return QPoint(p.x(), p.y() + 20)

    def iniciar_execucao(self, nome: str, args: Dict[str, Any], exec_id: int) -> None:
        self._nome_atual = str(nome or "")
        self._args_atual = dict(args or {})
        self._exec_contador = exec_id
        self._estado = "executando"
        self._falha = False
        self._tempo_inicio_exec = time.time()
        self._tempo_conclusao = None

        txt_exec = _texto_executando(self._nome_atual, self._args_atual)
        txt_sec = f"EXEC #{exec_id:04d} · {self._nome_atual.upper()} · 0.0S"
        self._lbl_principal.setText(truncar_meio(txt_exec, 60))
        self._lbl_secundario.setText(txt_sec)

        # icone animado
        self._icone.setText("◎")
        self._timer_icone.start()

        # progresso
        self._progress.setStyleSheet(f"background-color: {COR_EXECUTANDO}; border: none;")
        self._progress.setGeometry(8, self.height() - 2, 0, 2)
        self._progress.setVisible(True)
        self._animar_progresso_exec()

        self._aplicar_estilo_estado(COR_EXECUTANDO)

        self._ajustar_tamanho_ao_texto()
        self._mostrar_com_animacao()

    def _aplicar_estilo_estado(self, cor: str) -> None:
        self.setStyleSheet(
            f"""
            QFrame#capsula_acoes_rapidas {{
                background-color: {COR_FUNDO_CAPSULA};
                border: 1px solid {cor};
                border-radius: 28px;
            }}
            """
        )

    def _animar_progresso_exec(self) -> None:
        # anima largura de 0 a width-16 durante ~1.2s e repete suavemente? simples: cresce
        alvo_w = self.width() - 16 if self.width() > 16 else 200 - 16
        anim = QPropertyAnimation(self._progress, b"geometry")
        anim.setDuration(1200)
        anim.setStartValue(QRect(8, self.height() - 2, 0, 2))
        anim.setEndValue(QRect(8, self.height() - 2, alvo_w, 2))
        anim.setEasingCurve(QEasingCurve.Type.InOutCubic)
        anim.start()
        self._anim_prog_exec = anim

    def concluir(self, nome: str, resultado: str) -> None:
        if self._estado != "executando" and self._estado != "falha":
            # ainda assim mostra se visivel? mas regra normal
            pass
        self._estado = "concluido"
        self._falha = False
        self._tempo_conclusao = time.time()
        dur = 0.0
        if self._tempo_inicio_exec:
            dur = max(0.0, self._tempo_conclusao - self._tempo_inicio_exec)

        txt_conc = _texto_concluido(self._nome_atual or nome, self._args_atual, resultado)
        txt_sec = f"EXEC #{self._exec_contador:04d} · {(self._nome_atual or nome).upper()} · {dur:.1f}S"
        self._lbl_principal.setText(truncar_meio(txt_conc, 60))
        self._lbl_secundario.setText(txt_sec)

        self._icone.setText("✓")
        self._timer_icone.stop()

        self._progress.setStyleSheet(f"background-color: {COR_CONCLUIDO}; border: none;")
        alvo_w = self.width() - 16
        self._progress.setGeometry(8, self.height() - 2, alvo_w, 2)
        self._progress.setVisible(True)

        self._aplicar_estilo_estado(COR_CONCLUIDO)
        self._ajustar_tamanho_ao_texto()

        if not self.isVisible():
            self._mostrar_com_animacao()

        self._timer_saida.start(TEMPO_CONCLUIDO_VISIVEL)

    def falhar(self, nome: str, resultado: str) -> None:
        self._estado = "falha"
        self._falha = True
        self._tempo_conclusao = time.time()
        dur = 0.0
        if self._tempo_inicio_exec:
            dur = max(0.0, self._tempo_conclusao - self._tempo_inicio_exec)

        txt_falha = _texto_falha(self._nome_atual or nome, self._args_atual, resultado)
        txt_sec = f"EXEC #{self._exec_contador:04d} · {(self._nome_atual or nome).upper()} · {dur:.1f}S"
        self._lbl_principal.setText(truncar_meio(txt_falha, 60))
        self._lbl_secundario.setText(txt_sec)

        self._icone.setText("!")
        self._timer_icone.stop()

        self._progress.setStyleSheet(f"background-color: {COR_FALHA}; border: none;")
        alvo_w = self.width() - 16
        self._progress.setGeometry(8, self.height() - 2, alvo_w, 2)
        self._progress.setVisible(True)

        self._aplicar_estilo_estado(COR_FALHA)
        self._ajustar_tamanho_ao_texto()

        if not self.isVisible():
            self._mostrar_com_animacao()

        self._timer_saida.start(TEMPO_FALHA_VISIVEL)

    def _mostrar_com_animacao(self) -> None:
        if self._anim_fade is not None:
            try:
                self._anim_fade.stop()
            except Exception:
                pass
        if self._anim_pos is not None:
            try:
                self._anim_pos.stop()
            except Exception:
                pass
        if self._grupo_anim is not None:
            try:
                self._grupo_anim.stop()
            except Exception:
                pass

        alvo = self._posicao_alvo()
        ini = self._posicao_inicial()
        self.move(ini)
        self.setVisible(True)
        self.raise_()

        self._efeito_opacidade.setOpacity(0.0)

        self._anim_fade = QPropertyAnimation(self._efeito_opacidade, b"opacity")
        self._anim_fade.setDuration(DURACAO_ANIM_ENTRADA)
        self._anim_fade.setStartValue(0.0)
        self._anim_fade.setEndValue(1.0)
        self._anim_fade.setEasingCurve(QEasingCurve.Type.OutCubic)

        self._anim_pos = QPropertyAnimation(self, b"pos")
        self._anim_pos.setDuration(DURACAO_ANIM_ENTRADA)
        self._anim_pos.setStartValue(ini)
        self._anim_pos.setEndValue(alvo)
        self._anim_pos.setEasingCurve(QEasingCurve.Type.OutCubic)

        self._grupo_anim = QParallelAnimationGroup(self)
        self._grupo_anim.addAnimation(self._anim_fade)
        self._grupo_anim.addAnimation(self._anim_pos)
        self._grupo_anim.start()

    def _iniciar_saida(self) -> None:
        if self._anim_fade is not None:
            try:
                self._anim_fade.stop()
            except Exception:
                pass
        if self._anim_pos is not None:
            try:
                self._anim_pos.stop()
            except Exception:
                pass
        if self._grupo_anim is not None:
            try:
                self._grupo_anim.stop()
            except Exception:
                pass

        alvo = self._posicao_alvo()
        fim = QPoint(alvo.x(), alvo.y() + 12)

        self._anim_fade = QPropertyAnimation(self._efeito_opacidade, b"opacity")
        self._anim_fade.setDuration(DURACAO_ANIM_SAIDA)
        self._anim_fade.setStartValue(1.0)
        self._anim_fade.setEndValue(0.0)
        self._anim_fade.setEasingCurve(QEasingCurve.Type.InCubic)

        self._anim_pos = QPropertyAnimation(self, b"pos")
        self._anim_pos.setDuration(DURACAO_ANIM_SAIDA)
        self._anim_pos.setStartValue(alvo)
        self._anim_pos.setEndValue(fim)
        self._anim_pos.setEasingCurve(QEasingCurve.Type.InCubic)

        self._grupo_anim = QParallelAnimationGroup(self)
        self._grupo_anim.addAnimation(self._anim_fade)
        self._grupo_anim.addAnimation(self._anim_pos)
        self._grupo_anim.finished.connect(self._ao_saida_finalizada)
        self._grupo_anim.start()

    def _ao_saida_finalizada(self) -> None:
        self.setVisible(False)
        self._estado = "oculto"


class GerenciadorCapsula(QObject):
    """Gerencia exibicao da capsula de acoes rapidas."""

    def __init__(self, janela=None, ponte=None, parent=None):
        super().__init__(parent)
        self.janela = janela
        self.ponte = ponte
        self._capsula: Optional[CapsulaAcoesRapidas] = None
        self._exec_id = 0
        self._fila: list[tuple[str, Dict[str, Any]]] = []  # execucoes pendentes rapidas (nao usado intensivamente)
        self._ultima_nome = ""

        if janela is not None:
            # Reaproveita a capsula que a janela ja montou no leiaute: criar outra
            # aqui deixaria duas empilhadas no mesmo espaco.
            self._capsula = getattr(janela, "capsula_acoes", None)
            if not isinstance(self._capsula, CapsulaAcoesRapidas):
                self._capsula = CapsulaAcoesRapidas(janela)
                try:
                    janela.capsula_acoes = self._capsula
                except Exception:
                    pass

        if ponte is not None:
            try:
                ponte.ferramenta_iniciada.connect(self._ao_iniciada)
            except Exception:
                pass
            try:
                ponte.ferramenta_concluida.connect(self._ao_concluida)
            except Exception:
                pass

    def _garantir_capsula(self) -> Optional[CapsulaAcoesRapidas]:
        if self._capsula is not None:
            return self._capsula
        if self.janela is not None:
            self._capsula = getattr(self.janela, "capsula_acoes", None)
        if not isinstance(self._capsula, CapsulaAcoesRapidas):
            self._capsula = None
        if self._capsula is None and self.janela is not None:
            self._capsula = CapsulaAcoesRapidas(self.janela)
            try:
                self.janela.capsula_acoes = self._capsula
            except Exception:
                pass
        return self._capsula

    def _ao_iniciada(self, nome: str, argumentos: dict) -> None:
        if not deve_usar_capsula(nome):
            return  # deixa popup cuidar
        caps = self._garantir_capsula()
        if caps is None:
            return
        # se janela fechada/minimizada? nao abrir janela so por isso; ainda mostra capsula se visivel
        self._exec_id += 1
        caps.iniciar_execucao(nome, argumentos or {}, self._exec_id)
        self._ultima_nome = nome

    def _ao_concluida(self, nome: str, resultado: str) -> None:
        if not deve_usar_capsula(nome):
            return  # popup
        caps = self._garantir_capsula()
        if caps is None:
            return
        # detecta falha no resultado? heuristica simples
        res_low = str(resultado or "").lower()
        if "falha" in res_low or "erro" in res_low or "não encontrado" in res_low or "nao encontrado" in res_low or res_low.strip().startswith("erro:"):
            caps.falhar(nome, resultado)
        else:
            caps.concluir(nome, resultado)


def criar_gerenciador_capsula(janela=None, ponte=None, parent=None) -> GerenciadorCapsula:
    return GerenciadorCapsula(janela=janela, ponte=ponte, parent=parent)

"""Painel de Log do Sistema N.E.X.U.S.

Painel estilo terminal que exibe eventos do sistema em tempo real.
Mesma identidade visual dos popups (popup_base.py).
"""
from collections import deque
from datetime import datetime
from typing import Deque, List, Optional

from PySide6.QtCore import (
    Qt,
    QTimer,
    QRect,
    QPoint,
    QEasingCurve,
    QPropertyAnimation,
    QParallelAnimationGroup,
    Signal,
    Slot,
    QAbstractListModel,
    QModelIndex,
)
from PySide6.QtGui import QFont, QColor, QPainter, QPen
from PySide6.QtWidgets import (
    QFrame,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QListView,
    QAbstractItemView,
    QStyledItemDelegate,
    QStyleOptionViewItem,
    QWidget,
    QGraphicsOpacityEffect,
    QSizePolicy,
)

from interface.estilo import (
    COR_FUNDO,
    COR_FUNDO_SECUNDARIO,
    COR_FUNDO_SUPERFICIE,
    COR_CIANO,
    COR_CIANO_BRILHO,
    COR_CIANO_ESCURO,
    COR_CIANO_TRANSPARENTE,
    COR_CIANO_SUAVE,
    COR_BORDA,
    COR_BORDA_SUAVE,
    COR_SUCESSO,
    COR_ALERTA,
    COR_PERIGO,
    COR_TEXTO,
    COR_TEXTO_MUTED,
    COR_TEXTO_BRANCO,
    FONTE_MONO,
)


# Cores por tipo de evento
COR_TIPO = {
    "estado": COR_CIANO,
    "voz": COR_CIANO_BRILHO,
    "cerebro": "#9b59b6",      # roxo
    "ferramenta": "#3498db",    # azul
    "comando": "#2ecc71",       # verde
    "seguranca": COR_PERIGO,    # vermelho
    "erro": COR_PERIGO,         # vermelho
    "sistema": COR_CIANO_ESCURO,
}

# Icones por tipo
ICONE_TIPO = {
    "estado": "●",
    "voz": "🎙",
    "cerebro": "🧠",
    "ferramenta": "⚙",
    "comando": "$",
    "seguranca": "⚠",
    "erro": "✗",
    "sistema": "ℹ",
}

# Filtros disponiveis
FILTROS = [
    ("TUDO", None),
    ("COMANDOS", "comando"),
    ("FERRAMENTAS", "ferramenta"),
    ("CÉREBRO", "cerebro"),
    ("SEGURANÇA", "seguranca"),
    ("ERROS", "erro"),
]


class ModeloLog(QAbstractListModel):
    """Modelo de dados para a lista de eventos."""
    
    def __init__(self, max_itens: int = 500):
        super().__init__()
        self._max_itens = max_itens
        self._eventos: List[dict] = []
        self._filtro_tipo: Optional[str] = None
        self._busca: str = ""
    
    def rowCount(self, parent: QModelIndex = QModelIndex()) -> int:
        return len(self.obter_filtrados())
    
    def data(self, index: QModelIndex, role: int = Qt.ItemDataRole.DisplayRole):
        if not index.isValid():
            return None
        eventos_filtrados = self.obter_filtrados()
        if index.row() >= len(eventos_filtrados):
            return None
        evento = eventos_filtrados[index.row()]
        
        if role == Qt.ItemDataRole.DisplayRole:
            return f"[{evento.get('timestamp', '')}] {evento.get('tipo', '')}  {evento.get('titulo', '')}  EXEC #{evento.get('exec_id', '')}  {evento.get('duracao', '')}"
        elif role == Qt.ItemDataRole.ToolTipRole:
            return f"Args: {evento.get('args', '')}\nResultado: {evento.get('resultado', '')}\nSaida: {evento.get('saida', '')}"
        return None
    
    def adicionar(self, evento: dict):
        self.beginInsertRows(QModelIndex(), len(self._eventos), len(self._eventos))
        self._eventos.append(evento)
        if len(self._eventos) > self._max_itens:
            self._eventos = self._eventos[-self._max_itens:]
        self.endInsertRows()
    
    def obter_filtrados(self) -> List[dict]:
        if self._filtro_tipo is None and not self._busca:
            return self._eventos
        resultado = []
        for e in self._eventos:
            if self._filtro_tipo and e.get("tipo") != self._filtro_tipo:
                continue
            if self._busca:
                texto = f"{e.get('titulo','')} {e.get('detalhe','')}".lower()
                if self._busca.lower() not in texto.lower():
                    continue
            resultado.append(e)
        return resultado
    
    def set_filtro(self, tipo: Optional[str]):
        self._filtro_tipo = tipo
        self.layoutChanged.emit()
    
    def set_busca(self, texto: str):
        self._busca = texto
        self.layoutChanged.emit()
    
    def limpar(self):
        self.beginResetModel()
        self._eventos.clear()
        self.endResetModel()
    
    def __len__(self):
        return len(self._eventos)


class DelegadoItemLog(QStyledItemDelegate):
    """Delegate personalizado para renderizar itens do log."""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self._font_mono = QFont("Consolas", 9, QFont.Weight.Normal)
        self._font_mono.setStyleHint(QFont.StyleHint.Monospace)
    
    def paint(self, painter: QPainter, option: QStyleOptionViewItem, index):
        if not index.isValid():
            return
        
        evento = index.data(Qt.ItemDataRole.UserRole)
        if not evento:
            return
        
        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        
        rect = option.rect
        tipo = evento.get("tipo", "sistema")
        cor_tipo = COR_TIPO.get(tipo, COR_CIANO)
        icone = ICONE_TIPO.get(tipo, "●")
        
        # Fundo alternado
        if option.state & QStyleOptionViewItem.State.Selected:
            painter.fillRect(rect, QColor("#00e5ff33"))
        elif index.row() % 2 == 0:
            painter.fillRect(rect, QColor("#071b26"))
        else:
            painter.fillRect(rect, QColor("#04121a"))
        
        # Linha vertical colorida na esquerda
        painter.fillRect(rect.x(), rect.y(), 3, rect.height(), QColor(cor_tipo))
        
        # Texto principal
        ts = evento.get("ts", "")[11:23]  # HH:MM:SS.mmm
        titulo = evento.get("titulo", "")
        detalhe = evento.get("detalhe", "")
        exec_id = evento.get("exec_id")
        duracao = evento.get("duracao_ms")
        
        painter.setFont(self._font_mono)
        painter.setPen(QColor("#e0f7fa"))
        
        # Timestamp
        x = rect.x() + 10
        y = rect.y() + 4
        painter.drawText(x, y, ts)
        
        # Tipo + titulo
        tag = f"{icone} {evento.get('tipo','').upper()}  {titulo}"
        if exec_id is not None:
            tag += f"  EXEC #{exec_id:04d}"
        painter.drawText(x + 80, y, truncar_texto(tag, 55))
        
        # Detalhe
        if detalhe:
            painter.setPen(QColor("#546e7a"))
            painter.drawText(x, y + 16, truncar_texto(detalhe, 70))
        
        # Duracao
        if isinstance(duracao, int) and duracao > 0:
            painter.setPen(QColor("#546e7a"))
            dur_str = f"{duracao}ms" if duracao < 1000 else f"{duracao/1000:.1f}s"
            painter.drawText(rect.right() - 70, y, dur_str)
        
        # Indicador OK/Falha
        ok = evento.get("ok")
        if ok is not None:
            if ok:
                painter.setPen(QColor("#00e676"))
                painter.drawText(rect.right() - 90, y, "✓ OK")
            else:
                painter.setPen(QColor("#ff5252"))
                painter.drawText(rect.right() - 90, y, "✗ FALHA")
        
        painter.restore()
    
    def sizeHint(self, option, index):
        return option.rect.size()


def truncar_texto(texto: str, max_chars: int = 60) -> str:
    if not texto:
        return ""
    s = str(texto)
    if len(s) <= max_chars:
        return s
    return s[:max_chars - 1] + "…"


class PainelLog(QFrame):
    """Painel de log do sistema N.E.X.U.S. desliza de baixo para cima."""
    
    # Sinais
    fechar_painel = Signal()
    
    def __init__(self, parent: Optional[object] = None):
        super().__init__(parent)
        self.setObjectName("painel_log")
        self.setWindowFlags(Qt.WindowType.Window | Qt.WindowType.FramelessWindowHint | Qt.WindowType.Tool)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setFixedHeight(0)  # Inicia fechado
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        
        self._modelo = ModeloLog(max_itens=500)
        self._filtro_atual = None
        self._busca_texto = ""
        self._rolagem_automatica = True
        self._ultimo_scroll = 0
        
        # Contador de eventos novos (nao vistos)
        self._novos_eventos = 0
        self._ultimo_visto_idx = 0
        
        # Animacoes
        self._anim_fade = None
        self._anim_pos = None
        self._anim_grupo = None
        self._animando = False
        
        self._construir_ui()
        self._aplicar_estilo()
        
        # Timer para limitar atualizacoes visuais
        self._timer_atualizar = QTimer(self)
        self._timer_atualizar.setInterval(100)  # 10 FPS max
        self._timer_atualizar.timeout.connect(self._atualizar_visual)
        self._timer_atualizar.start()
        
        # Buffer de eventos pendentes para renderizacao em lote
        self._pendentes: Deque[dict] = deque()
        self._timer_flush = QTimer(self)
        self._timer_flush.setInterval(50)
        self._timer_flush.timeout.connect(self._flush_pendentes)
        self._timer_flush.start()
    
    def _construir_ui(self):
        layout_raiz = QVBoxLayout(self)
        layout_raiz.setContentsMargins(0, 0, 0, 0)
        layout_raiz.setSpacing(0)
        
        # --- Cabeçalho ---
        self._cabecalho = QFrame()
        self._cabecalho.setFixedHeight(36)
        self._cabecalho.setStyleSheet(f"""
            QFrame {{
                background-color: {COR_FUNDO_SECUNDARIO};
                border-top-left-radius: 16px;
                border-top-right-radius: 16px;
                border: 1px solid {COR_BORDA};
                border-bottom: 1px solid {COR_BORDA};
            }}
        """)
        layout_cab = QHBoxLayout(self._cabecalho)
        layout_cab.setContentsMargins(12, 4, 12, 4)
        layout_cab.setSpacing(8)
        
        # Titulo
        lbl_titulo = QLabel("LOG DO SISTEMA // N.E.X.U.S.")
        lbl_titulo.setStyleSheet(f"""
            color: {COR_CIANO};
            font-family: {FONTE_MONO};
            font-size: 10px;
            font-weight: bold;
            letter-spacing: 1px;
        """)
        layout_cab.addWidget(lbl_titulo)
        
        # Contador de eventos
        self._lbl_contador = QLabel("0 eventos")
        self._lbl_contador.setStyleSheet(f"""
            color: {COR_TEXTO_MUTED};
            font-family: {FONTE_MONO};
            font-size: 9px;
            font-weight: bold;
        """)
        layout_cab.addWidget(self._lbl_contador)
        layout_cab.addStretch(1)
        
        # Filtros (chips)
        self._botoes_filtro = {}
        for nome, tipo in FILTROS:
            btn = QPushButton(nome)
            btn.setCheckable(True)
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.setFixedHeight(24)
            btn.setStyleSheet(f"""
                QPushButton {{
                    background-color: transparent;
                    border: 1px solid {COR_BORDA};
                    border-radius: 10px;
                    color: {COR_TEXTO_MUTED};
                    font-family: {FONTE_MONO};
                    font-size: 8px;
                    font-weight: bold;
                    padding: 0px 8px;
                }}
                QPushButton:checked {{
                    background-color: {COR_CIANO};
                    color: {COR_FUNDO};
                    border: 1px solid {COR_CIANO};
                }}
                QPushButton:hover {{
                    border: 1px solid {COR_CIANO};
                    color: {COR_CIANO};
                }}
            """)
            if tipo is None:
                btn.setChecked(True)
            btn.clicked.connect(lambda checked, t=tipo: self._ao_filtro_clicado(t))
            self._botoes_filtro[tipo] = btn
            layout_cab.addWidget(btn)
        
        layout_cab.addStretch(1)
        
        # Campo de busca
        self._campo_busca = QLineEdit()
        self._campo_busca.setPlaceholderText("Filtrar...")
        self._campo_busca.setFixedWidth(140)
        self._campo_busca.setStyleSheet(f"""
            QLineEdit {{
                background-color: {COR_FUNDO};
                border: 1px solid {COR_BORDA};
                border-radius: 10px;
                padding: 2px 8px;
                color: {COR_TEXTO_BRANCO};
                font-family: {FONTE_MONO};
                font-size: 9px;
            }}
            QLineEdit:focus {{
                border: 1px solid {COR_CIANO};
            }}
        """)
        self._campo_busca.setPlaceholderText("Filtrar...")
        self._campo_busca.textChanged.connect(self._ao_busca_alterada)
        layout_cab.addWidget(self._campo_busca)
        
        # Botao limpar tela
        btn_limpar = QPushButton("Limpar tela")
        btn_limpar.setFixedHeight(24)
        btn_limpar.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_limpar.setStyleSheet(f"""
            QPushButton {{
                background-color: transparent;
                border: 1px solid {COR_BORDA};
                border-radius: 10px;
                color: {COR_TEXTO_MUTED};
                font-family: {FONTE_MONO};
                font-size: 8px;
                font-weight: bold;
                padding: 0px 8px;
            }}
            QPushButton:hover {{
                color: {COR_CIANO};
                border: 1px solid {COR_CIANO};
            }}
        """)
        btn_limpar.clicked.connect(self._limpar_visual)
        layout_cab.addWidget(btn_limpar)
        
        # Botao exportar
        btn_exportar = QPushButton("Exportar")
        btn_exportar.setFixedHeight(24)
        btn_exportar.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_exportar.setStyleSheet(f"""
            QPushButton {{
                background-color: {COR_CIANO};
                border: none;
                border-radius: 10px;
                color: {COR_FUNDO};
                font-family: {FONTE_MONO};
                font-size: 8px;
                font-weight: bold;
                padding: 0px 10px;
            }}
            QPushButton:hover {{
                background-color: {COR_CIANO_BRILHO};
            }}
        """)
        btn_exportar.clicked.connect(self._exportar)
        layout_cab.addWidget(btn_exportar)
        
        # Botao fechar
        btn_fechar = QPushButton("✕")
        btn_fechar.setFixedSize(22, 22)
        btn_fechar.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_fechar.setStyleSheet(f"""
            QPushButton {{
                background-color: transparent;
                border: none;
                color: {COR_TEXTO_MUTED};
                font-size: 11px;
                font-weight: bold;
            }}
            QPushButton:hover {{
                color: {COR_PERIGO};
            }}
        """)
        btn_fechar.clicked.connect(self._fechar_painel)
        layout_cab.addWidget(btn_fechar)
        
        # --- Lista de eventos ---
        self._lista = QListView()
        self._lista.setModel(self._modelo)
        self._lista.setItemDelegate(DelegadoItemLog())
        self._lista.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self._lista.setVerticalScrollMode(QListView.ScrollMode.ScrollPerPixel)
        self._lista.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._lista.setStyleSheet(f"""
            QListView {{
                background-color: {COR_FUNDO};
                border: none;
                outline: none;
            }}
            QScrollBar:vertical {{
                border: none;
                background: {COR_FUNDO};
                width: 6px;
                margin: 0px;
            }}
            QScrollBar::handle:vertical {{
                background: {COR_CIANO_ESCURO};
                min-height: 30px;
                border-radius: 3px;
            }}
            QScrollBar::handle:vertical:hover {{
                background: {COR_CIANO};
            }}
        """)
        self._lista.verticalScrollBar().valueChanged.connect(self._ao_scroll)
        
        # Rodape
        self._rodape = QFrame()
        self._rodape.setFixedHeight(28)
        self._rodape.setStyleSheet(f"""
            QFrame {{
                background-color: {COR_FUNDO_SECUNDARIO};
                border-bottom-left-radius: 16px;
                border-bottom-right-radius: 16px;
                border: 1px solid {COR_BORDA};
                border-top: 1px solid {COR_BORDA};
            }}
        """)
        layout_rod = QHBoxLayout(self._rodape)
        layout_rod.setContentsMargins(12, 2, 12, 2)
        layout_rod.setSpacing(8)
        
        self._lbl_status = QLabel("SESSÃO CRIPTOGRAFADA: N.E.X.U.S. KERNEL")
        self._lbl_status.setStyleSheet(f"""
            color: {COR_TEXTO_MUTED};
            font-family: {FONTE_MONO};
            font-size: 8px;
            font-weight: bold;
        """)
        layout_rod.addWidget(self._lbl_status)
        layout_rod.addStretch(1)
        
        # Botao limpar tela (visual)
        btn_limpar_visual = QPushButton("Limpar tela")
        btn_limpar_visual.setFixedHeight(20)
        btn_limpar_visual.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_limpar_visual.setStyleSheet(f"""
            QPushButton {{
                background-color: transparent;
                border: 1px solid {COR_BORDA};
                border-radius: 8px;
                color: {COR_TEXTO_MUTED};
                font-family: {FONTE_MONO};
                font-size: 8px;
                font-weight: bold;
                padding: 0px 8px;
            }}
            QPushButton:hover {{
                color: {COR_CIANO};
                border: 1px solid {COR_CIANO};
            }}
        """)
        btn_limpar_visual.clicked.connect(self._limpar_visual)
        layout_rod.addWidget(btn_limpar_visual)
        
        # Botao exportar
        btn_exportar = QPushButton("Exportar Telemetria")
        btn_exportar.setFixedHeight(20)
        btn_exportar.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_exportar.setStyleSheet(f"""
            QPushButton {{
                background-color: {COR_CIANO};
                border: none;
                border-radius: 8px;
                color: {COR_FUNDO};
                font-family: {FONTE_MONO};
                font-size: 8px;
                font-weight: bold;
                padding: 0px 10px;
            }}
            QPushButton:hover {{
                background-color: {COR_CIANO_BRILHO};
            }}
        """)
        btn_exportar.clicked.connect(self._exportar)
        layout_rod.addWidget(btn_exportar)
        
        # Botao fechar painel
        btn_fechar = QPushButton("Fechar [ESC]")
        btn_fechar.setFixedHeight(20)
        btn_fechar.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_fechar.setStyleSheet(f"""
            QPushButton {{
                background-color: transparent;
                border: 1px solid {COR_BORDA};
                border-radius: 8px;
                color: {COR_TEXTO_MUTED};
                font-family: {FONTE_MONO};
                font-size: 8px;
                font-weight: bold;
                padding: 0px 8px;
            }}
            QPushButton:hover {{
                color: {COR_CIANO};
                border: 1px solid {COR_CIANO};
            }}
        """)
        btn_fechar.clicked.connect(self._fechar_painel)
        layout_rod.addWidget(btn_fechar)
        
        # Adiciona widgets ao layout raiz
        layout_raiz.addWidget(self._cabecalho)
        layout_raiz.addWidget(self._lista, 1)
        layout_raiz.addWidget(self._rodape)
        
        # Efeito de opacidade para animacao
        self._efeito_opacidade = QGraphicsOpacityEffect(self)
        self._efeito_opacidade.setOpacity(0.0)
        self.setGraphicsEffect(self._efeito_opacidade)
    
    def _aplicar_estilo(self):
        self.setStyleSheet(f"""
            QFrame#painel_log {{
                background-color: {COR_FUNDO};
                border: 1px solid {COR_BORDA};
                border-radius: 16px;
            }}
        """)
    
    def _ao_filtro_clicado(self, tipo):
        # Desmarcar outros
        for t, btn in self._botoes_filtro.items():
            if t != tipo:
                btn.setChecked(False)
        self._filtro_atual = tipo
        self._atualizar_visual()
    
    def _ao_busca_alterada(self, texto: str):
        self._busca_texto = texto
        self._atualizar_visual()
    
    def _atualizar_visual(self):
        # Atualiza contador
        total = len(self._modelo._eventos)
        filtrados = len(self._modelo.obter_filtrados())
        self._lbl_contador.setText(f"{filtrados}/{total} eventos")
        
        # Notifica o modelo personalizado que os dados mudaram
        self._modelo.layoutChanged.emit()
    
    def _limpar_visual(self):
        """Limpa apenas a visualizacao (nao apaga o arquivo)."""
        self._modelo.limpar()
        self._atualizar_visual()
        self._novos_eventos = 0
        self._atualizar_botao_log()
    
    def _exportar(self):
        """Exporta a visao filtrada atual para arquivo .md."""
        from pathlib import Path
        from datetime import datetime
        from comum import PASTA_DADOS
        import json
        
        PASTA_DADOS.mkdir(parents=True, exist_ok=True)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        arquivo = PASTA_DADOS / f"telemetria_{timestamp}.md"
        
        linhas = [
            f"# Telemetria N.E.X.U.S. - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
            "",
            f"Total de eventos: {len(self._modelo._eventos)}",
            f"Filtro: {self._filtro_atual or 'TUDO'}",
            f"Busca: {self._busca_texto or 'nenhuma'}",
            "",
            "---",
            "",
        ]
        
        for e in self._modelo.obter_filtrados():
            ts = e.get("ts", "")
            tipo = e.get("tipo", "sistema")
            titulo = e.get("titulo", "")
            detalhe = e.get("detalhe", "")
            ok = e.get("ok")
            duracao = e.get("duracao_ms")
            exec_id = e.get("exec_id")
            
            status = "✓" if ok else "✗" if ok is False else "○"
            exec_str = f" EXEC #{exec_id:04d}" if exec_id is not None else ""
            dur_str = f" ({duracao}ms)" if isinstance(duracao, int) and duracao > 0 else ""
            
            linhas.append(f"- [{e.get('ts','')}] **{tipo.upper()}** {status} {titulo}{exec_str}{dur_str}")
            if detalhe:
                linhas.append(f"  → {detalhe}")
        
        try:
            arquivo.write_text("\n".join(linhas), encoding="utf-8")
            print(f"[log] Telemetria exportada para {arquivo}")
        except Exception as e:
            print(f"[log] Erro ao exportar: {e}")
    
    def _fechar_painel(self):
        self.btn_log.setChecked(False)
        self._iniciar_saida()
    
    def keyPressEvent(self, event):
        if event.key() == Qt.Key.Key_Escape:
            self._fechar_painel()
            event.accept()
        else:
            super().keyPressEvent(event)
    
    def mostrar(self):
        """Mostra o painel com animacao."""
        if self._animando:
            return
        self.show()
        self.raise_()
        
        # Posiciona no fundo da janela pai
        if not self.parent():
            return
        
        pw = self.parent().width()
        ph = self.parent().height()
        x = 0
        y = ph - 600  # altura fixa do painel
        self.setGeometry(0, ph, pw, 0)
        self.setFixedWidth(pw)
        
        self._anim_fade = QPropertyAnimation(self.graphicsEffect(), b"opacity")
        self._anim_fade.setDuration(200)
        self._anim_fade.setStartValue(0.0)
        self._anim_fade.setEndValue(1.0)
        self._anim_fade.setEasingCurve(QEasingCurve.Type.OutCubic)
        
        # Animacao de geometry (pos + size combinados)
        self._anim_geometry = QPropertyAnimation(self, b"geometry")
        self._anim_geometry.setDuration(250)
        self._anim_geometry.setStartValue(QRect(0, ph, pw, 0))
        self._anim_geometry.setEndValue(QRect(0, ph - 600, pw, 600))
        self._anim_geometry.setEasingCurve(QEasingCurve.Type.OutCubic)
        
        # Grupo de animacoes paralelas
        self._anim_grupo = QParallelAnimationGroup(self)
        self._anim_grupo.addAnimation(self._anim_fade)
        self._anim_grupo.addAnimation(self._anim_geometry)
        
        self._animando = True
        self._anim_grupo.finished.connect(lambda: setattr(self, "_animando", False))
        self._anim_grupo.start()
        
        self.raise_()
    
    def esconder(self):
        """Esconde o painel com animacao."""
        if self._animando:
            return
        self._iniciar_saida()
    
    def _iniciar_saida(self):
        if not self.parent():
            self.setVisible(False)
            self._animando = False
            self.fechar_painel.emit()
            return
        
        self._anim_fade = QPropertyAnimation(self.graphicsEffect(), b"opacity")
        self._anim_fade.setDuration(200)
        self._anim_fade.setStartValue(1.0)
        self._anim_fade.setEndValue(0.0)
        self._anim_fade.setEasingCurve(QEasingCurve.Type.InCubic)
        
        ph = self.parent().height()
        pw = self.width()
        # Animacao de geometry (pos + size combinados)
        self._anim_geometry = QPropertyAnimation(self, b"geometry")
        self._anim_geometry.setDuration(250)
        self._anim_geometry.setStartValue(QRect(self.x(), self.y(), pw, 600))
        self._anim_geometry.setEndValue(QRect(self.x(), ph, pw, 0))
        self._anim_geometry.setEasingCurve(QEasingCurve.Type.InCubic)
        
        # Grupo de animacoes paralelas
        self._anim_grupo = QParallelAnimationGroup(self)
        self._anim_grupo.addAnimation(self._anim_fade)
        self._anim_grupo.addAnimation(self._anim_geometry)
        
        self._animando = True
        self._anim_grupo.finished.connect(self._ao_saida_finalizada)
        self._anim_grupo.start()
    
    def _ao_saida_finalizada(self):
        self.setVisible(False)
        self._animando = False
        self.fechar_painel.emit()
    
    def _atualizar_botao_log(self):
        """Atualiza o estado do botao LOG na barra de titulo."""
        if hasattr(self, "btn_log"):
            # Atualiza contador de eventos novos
            pass
    
    @Slot(dict)
    def adicionar_evento(self, evento: dict):
        """Adiciona evento ao modelo (chamado via sinal da ponte)."""
        self._modelo.adicionar(evento)
        # Conta eventos novos se painel nao estiver visivel
        if not self.isVisible():
            self._novos_eventos += 1
        # Agrupa atualizacoes visuais
        self._pendentes.append(evento)
        # Atualiza contador no botao
        self._atualizar_botao_log()
    
    def _flush_pendentes(self):
        if self._pendentes:
            # Atualiza modelo e visual
            self._atualizar_visual()
            self._pendentes.clear()
    
    def _ao_scroll(self, value: int):
        """Chamado quando o usuario rola a lista."""
        # Verifica se rolou para o fim (auto-scroll)
        scrollbar = self._lista.verticalScrollBar()
        no_fim = value >= scrollbar.maximum() - 10
        
        if no_fim:
            self._rolagem_automatica = True
            # Esconde pilula "novos eventos" se existir
            if hasattr(self, "_pillula_novos") and self._pillula_novos is not None:
                self._pillula_novos.hide()
        else:
            self._rolagem_automatica = False
            # Mostra pilula "novos eventos" se nao existir
            if not hasattr(self, "_pillula_novos") or self._pillula_novos is None:
                self._criar_pillula_novos()
            self._pillula_novos.show()
    
    def _criar_pillula_novos(self):
        """Cria a pilula indicadora de novos eventos."""
        from PySide6.QtWidgets import QWidget, QHBoxLayout, QLabel, QPushButton
        self._pillula_novos = QWidget(self._lista.viewport())
        self._pillula_novos.setStyleSheet(f"""
            QWidget {{
                background-color: {COR_CIANO};
                border-radius: 12px;
                padding: 4px 12px;
            }}
            QLabel {{
                color: {COR_FUNDO};
                font-family: {FONTE_MONO};
                font-size: 10px;
                font-weight: bold;
            }}
            QPushButton {{
                background: transparent;
                border: none;
                color: {COR_FUNDO};
                font-size: 12px;
                font-weight: bold;
            }}
        """)
        layout = QHBoxLayout(self._pillula_novos)
        layout.setContentsMargins(8, 2, 8, 2)
        layout.setSpacing(6)
        
        self._lbl_novos = QLabel("↓ NOVOS EVENTOS")
        layout.addWidget(self._lbl_novos)
        
        btn_ir_fim = QPushButton("✕")
        btn_ir_fim.setFixedSize(18, 18)
        btn_ir_fim.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_ir_fim.clicked.connect(self._ir_para_fim)
        layout.addWidget(btn_ir_fim)
        
        # Posiciona no canto inferior direito da viewport
        self._pillula_novos.adjustSize()
        self._posicionar_pillula()
        
        # Conecta resize da viewport para reposicionar
        self._lista.viewport().installEventFilter(self)
    
    def _posicionar_pillula(self):
        if hasattr(self, "_pillula_novos") and self._pillula_novos is not None:
            vp = self._lista.viewport()
            x = vp.width() - self._pillula_novos.width() - 12
            y = vp.height() - self._pillula_novos.height() - 12
            self._pillula_novos.move(x, y)
    
    def _ir_para_fim(self):
        """Rola para o fim da lista."""
        scrollbar = self._lista.verticalScrollBar()
        scrollbar.setValue(scrollbar.maximum())
        self._rolagem_automatica = True
        if hasattr(self, "_pillula_novos") and self._pillula_novos is not None:
            self._pillula_novos.hide()
    
    def eventFilter(self, obj, event):
        if obj == self._lista.viewport() and event.type() == event.Type.Resize:
            self._posicionar_pillula()
        return super().eventFilter(obj, event)

    def _atualizar_botao_log(self):
        # Atualiza o texto do botao LOG com contador
        pass


# Exportar para uso
__all__ = ["PainelLog"]
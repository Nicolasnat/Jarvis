"""Popup especializado para exibicao de status do sistema no N.E.X.U.S.

Processa a saida real de psutil da ferramenta status_sistema com barras de
progresso estilizadas para CPU, RAM, Disco e Bateria, alem do uptime formatado.
Todos os comentarios e docstrings neste modulo usam exclusivamente ASCII.
"""
from datetime import datetime
from pathlib import Path
import re

from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import (
    QWidget,
    QFrame,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QProgressBar,
    QScrollArea,
)

from comum import garantir_pasta_dados
from interface.estilo import (
    COR_FUNDO_SUPERFICIE,
    COR_CIANO,
    COR_CIANO_BRILHO,
    COR_CIANO_ESCURO,
    COR_BORDA,
    COR_BORDA_SUAVE,
    COR_TEXTO,
    COR_TEXTO_MUTED,
    COR_TEXTO_BRANCO,
    COR_SUCESSO,
    COR_ALERTA,
    COR_PERIGO,
    FONTE_MONO,
    FONTE_UI,
)
from interface.popup_base import PopupBase


def parse_status_sistema(texto: str) -> dict:
    """Extrai metricas reais de CPU, RAM, Disco, Bateria e Uptime do texto."""
    dados = {
        "cpu": None,
        "ram": None,
        "ram_detalhe": "",
        "disco": None,
        "disco_detalhe": "",
        "uptime": "",
        "bateria": None,
        "bateria_estado": "",
    }
    if not texto or not isinstance(texto, str):
        return dados

    for linha in texto.splitlines():
        linha_limpa = linha.strip()
        if not linha_limpa:
            continue

        m_cpu = re.match(r"^CPU:\s*(\d+)%", linha_limpa, re.IGNORECASE)
        if m_cpu:
            dados["cpu"] = int(m_cpu.group(1))
            continue

        m_ram = re.match(r"^RAM:\s*(\d+)%(?:\s*\(([^)]+)\))?", linha_limpa, re.IGNORECASE)
        if m_ram:
            dados["ram"] = int(m_ram.group(1))
            if m_ram.group(2):
                dados["ram_detalhe"] = m_ram.group(2).strip()
            continue

        m_disco = re.match(r"^Disco[^:]*:\s*(\d+)%(?:\s*\(([^)]+)\))?", linha_limpa, re.IGNORECASE)
        if m_disco:
            dados["disco"] = int(m_disco.group(1))
            if m_disco.group(2):
                dados["disco_detalhe"] = m_disco.group(2).strip()
            continue

        m_up = re.match(r"^Ligado\s+h[aá]:\s*(.+)$", linha_limpa, re.IGNORECASE)
        if m_up:
            dados["uptime"] = m_up.group(1).strip()
            continue

        m_bat = re.match(r"^Bateria:\s*(\d+)%(?:\s*\(([^)]+)\))?", linha_limpa, re.IGNORECASE)
        if m_bat:
            dados["bateria"] = int(m_bat.group(1))
            if m_bat.group(2):
                dados["bateria_estado"] = m_bat.group(2).strip()
            continue

    return dados


class PopupStatusSistema(PopupBase):
    """Popup modal para visualizacao cibernetica das metricas de hardware do host."""

    def __init__(
        self,
        resultado: str = "",
        duracao: float = 0.0,
        parent=None,
    ):
        super().__init__(titulo="STATUS DO SISTEMA", parent=parent)

        self._resultado = str(resultado or "")
        self._duracao = float(duracao) if isinstance(duracao, (int, float)) else 0.0
        self._dados = parse_status_sistema(self._resultado)

        metricas_ativas = [
            k for k in ("cpu", "ram", "disco", "bateria")
            if self._dados.get(k) is not None
        ]
        total_metricas = len(metricas_ativas)
        self.definir_contagem(f"{total_metricas} MÉTRICAS" if total_metricas else "0 MÉTRICAS")

        self._montar_ui()
        self.exportar_telemetria_solicitado.connect(self._ao_exportar_telemetria)

    def _montar_ui(self) -> None:
        """Monta a aba principal com os medidores de hardware."""
        conteudo = QWidget()
        layout_raiz = QVBoxLayout(conteudo)
        layout_raiz.setContentsMargins(4, 4, 4, 4)
        layout_raiz.setSpacing(10)

        # Barra superior com latencia e status
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

        selo = QLabel("TELEMETRIA OPERACIONAL // ONLINE")
        selo.setStyleSheet(f"""
            color: {COR_SUCESSO};
            font-family: {FONTE_MONO};
            font-size: 10px;
            font-weight: bold;
            letter-spacing: 1px;
        """)
        layout_status.addWidget(selo)
        layout_status.addStretch(1)

        tempo_str = f"LATÊNCIA: {self._duracao:.2f}s"
        lbl_tempo = QLabel(tempo_str)
        lbl_tempo.setStyleSheet(f"""
            color: {COR_CIANO};
            font-family: {FONTE_MONO};
            font-size: 10px;
            font-weight: bold;
        """)
        layout_status.addWidget(lbl_tempo)
        layout_raiz.addWidget(barra_status)

        # Area com rolagem para as barras e uptime
        tem_conteudo = any(self._dados.get(k) is not None for k in ("cpu", "ram", "disco", "bateria")) or bool(self._dados.get("uptime"))

        if tem_conteudo:
            area_scroll = QScrollArea()
            area_scroll.setWidgetResizable(True)
            area_scroll.setFrameShape(QFrame.Shape.NoFrame)
            area_scroll.setStyleSheet("background: transparent; border: none;")

            cartao = QFrame()
            cartao.setStyleSheet(f"""
                QFrame {{
                    background-color: rgba(7, 27, 38, 0.7);
                    border: 1px solid {COR_BORDA_SUAVE};
                    border-radius: 8px;
                }}
            """)
            layout_cartao = QVBoxLayout(cartao)
            layout_cartao.setContentsMargins(14, 12, 14, 12)
            layout_cartao.setSpacing(12)

            # Barras estilizadas
            if self._dados["cpu"] is not None:
                layout_cartao.addWidget(self._criar_bloco_barra("CPU", self._dados["cpu"]))

            if self._dados["ram"] is not None:
                layout_cartao.addWidget(self._criar_bloco_barra("MEMÓRIA RAM", self._dados["ram"], self._dados["ram_detalhe"]))

            if self._dados["disco"] is not None:
                layout_cartao.addWidget(self._criar_bloco_barra("DISCO PRINCIPAL (/)", self._dados["disco"], self._dados["disco_detalhe"]))

            if self._dados["bateria"] is not None:
                layout_cartao.addWidget(self._criar_bloco_barra("BATERIA", self._dados["bateria"], self._dados["bateria_estado"]))

            # Bloco de Uptime
            if self._dados["uptime"]:
                quadro_uptime = QFrame()
                quadro_uptime.setStyleSheet(f"""
                    QFrame {{
                        background-color: rgba(11, 37, 53, 0.6);
                        border: 1px solid {COR_BORDA_SUAVE};
                        border-radius: 6px;
                    }}
                """)
                layout_up = QHBoxLayout(quadro_uptime)
                layout_up.setContentsMargins(10, 8, 10, 8)

                lbl_up_tit = QLabel("TEMPO LIGADO (UPTIME):")
                lbl_up_tit.setStyleSheet(f"""
                    color: {COR_TEXTO_MUTED};
                    font-family: {FONTE_MONO};
                    font-size: 10px;
                    font-weight: bold;
                """)
                layout_up.addWidget(lbl_up_tit)
                layout_up.addStretch(1)

                lbl_up_val = QLabel(self._dados["uptime"])
                lbl_up_val.setStyleSheet(f"""
                    color: {COR_CIANO_BRILHO};
                    font-family: {FONTE_MONO};
                    font-size: 11px;
                    font-weight: bold;
                """)
                layout_up.addWidget(lbl_up_val)
                layout_cartao.addWidget(quadro_uptime)

            layout_cartao.addStretch(1)
            area_scroll.setWidget(cartao)
            layout_raiz.addWidget(area_scroll, 1)
        else:
            # Fallback caso o resultado nao seja parseavel
            cartao_vazio = QFrame()
            cartao_vazio.setStyleSheet(f"""
                QFrame {{
                    background-color: rgba(7, 27, 38, 0.7);
                    border: 1px solid {COR_BORDA_SUAVE};
                    border-radius: 8px;
                }}
            """)
            layout_vazio = QVBoxLayout(cartao_vazio)
            layout_vazio.setContentsMargins(14, 14, 14, 14)
            lbl_texto = QLabel(self._resultado.strip() or "Nenhuma informação de telemetria recebida.")
            lbl_texto.setWordWrap(True)
            lbl_texto.setStyleSheet(f"color: {COR_TEXTO}; font-family: {FONTE_MONO}; font-size: 11px;")
            layout_vazio.addWidget(lbl_texto)
            layout_raiz.addWidget(cartao_vazio, 1)

        self.adicionar_aba("Telemetria", conteudo)

    def _criar_bloco_barra(self, titulo: str, valor: int, detalhe: str = "") -> QWidget:
        """Gera um bloco com rotulo, porcentagem, detalhe e QProgressBar estilizada."""
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)

        topo = QHBoxLayout()
        topo.setSpacing(8)

        lbl_tit = QLabel(titulo)
        lbl_tit.setStyleSheet(f"""
            color: {COR_TEXTO_BRANCO};
            font-family: {FONTE_MONO};
            font-size: 11px;
            font-weight: bold;
        """)
        topo.addWidget(lbl_tit)

        if detalhe:
            lbl_det = QLabel(f"({detalhe})")
            lbl_det.setStyleSheet(f"""
                color: {COR_TEXTO_MUTED};
                font-family: {FONTE_MONO};
                font-size: 10px;
            """)
            topo.addWidget(lbl_det)

        topo.addStretch(1)

        lbl_val = QLabel(f"{valor}%")
        lbl_val.setStyleSheet(f"""
            color: {COR_CIANO_BRILHO};
            font-family: {FONTE_MONO};
            font-size: 11px;
            font-weight: bold;
        """)
        topo.addWidget(lbl_val)
        layout.addLayout(topo)

        barra = QProgressBar()
        barra.setRange(0, 100)
        barra.setValue(max(0, min(100, valor)))
        barra.setTextVisible(False)
        barra.setFixedHeight(12)

        # Cor do preenchimento baseada no nivel de carga
        if valor >= 90:
            gradiente = f"qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 {COR_ALERTA}, stop:1 {COR_PERIGO})"
        else:
            gradiente = f"qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 {COR_CIANO_ESCURO}, stop:1 {COR_CIANO})"

        barra.setStyleSheet(f"""
            QProgressBar {{
                background-color: rgba(11, 37, 53, 0.8);
                border: 1px solid {COR_BORDA_SUAVE};
                border-radius: 6px;
            }}
            QProgressBar::chunk {{
                background: {gradiente};
                border-radius: 5px;
            }}
        """)
        layout.addWidget(barra)
        return widget

    def _ao_exportar_telemetria(self) -> Path:
        """Salva a telemetria do sistema em arquivo Markdown em dados/."""
        pasta = garantir_pasta_dados()
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        arquivo_md = pasta / f"status_sistema_{ts}.md"

        linhas = [
            "# Telemetria do Sistema // N.E.X.U.S.",
            "",
            f"- **Data/Hora:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
            f"- **Latência de Leitura:** {self._duracao:.2f}s",
            "",
            "## Recursos do Kernel",
        ]
        if self._dados["cpu"] is not None:
            linhas.append(f"- **CPU:** {self._dados['cpu']}%")
        if self._dados["ram"] is not None:
            linhas.append(f"- **RAM:** {self._dados['ram']}% ({self._dados['ram_detalhe']})")
        if self._dados["disco"] is not None:
            linhas.append(f"- **Disco:** {self._dados['disco']}% ({self._dados['disco_detalhe']})")
        if self._dados["bateria"] is not None:
            linhas.append(f"- **Bateria:** {self._dados['bateria']}% ({self._dados['bateria_estado']})")
        if self._dados["uptime"]:
            linhas.append(f"- **Tempo Ativo:** {self._dados['uptime']}")

        linhas.extend(["", "## Saida Original", "```", self._resultado, "```", ""])
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
        """Restaura o estilo padrao do botao de exportar telemetria."""
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
                color: {COR_FUNDO_SUPERFICIE};
            }}
        """)

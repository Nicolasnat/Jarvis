"""Popup especializado para controles de volume e brilho do N.E.X.U.S.

Processa a confirmacao real de ferramentas como definir_volume e definir_brilho,
exibindo um QSlider desabilitado (somente leitura) com a porcentagem ajustada.
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
    QSlider,
)

from comum import garantir_pasta_dados
from interface.estilo import (
    COR_FUNDO_SUPERFICIE,
    COR_CIANO,
    COR_CIANO_BRILHO,
    COR_CIANO_ESCURO,
    COR_BORDA_SUAVE,
    COR_TEXTO,
    COR_TEXTO_MUTED,
    COR_TEXTO_BRANCO,
    COR_SUCESSO,
    FONTE_MONO,
)
from interface.popup_base import PopupBase


def parse_controle(resultado: str, nome_ferramenta: str = "") -> tuple[str, int | None]:
    """Extrai o tipo de controle (VOLUME ou BRILHO) e o percentual numerico."""
    texto = str(resultado or "").strip()

    # Detecta tipo baseado na ferramenta ou na mensagem
    tipo = "VOLUME" if "volume" in nome_ferramenta.lower() or "volume" in texto.lower() else "BRILHO"

    m = re.search(r"(?:volume|brilho)\s+ajustado\s+para\s+(\d+)%", texto, re.IGNORECASE)
    if not m:
        m = re.search(r"(\d+)%", texto)

    if m:
        try:
            return tipo, int(m.group(1))
        except ValueError:
            pass

    return tipo, None


class PopupControles(PopupBase):
    """Popup modal para visualizacao de ajuste de volume e brilho de tela."""

    def __init__(
        self,
        nome_ferramenta: str = "definir_volume",
        resultado: str = "",
        duracao: float = 0.0,
        parent=None,
    ):
        super().__init__(titulo="CONTROLES DO SISTEMA", parent=parent)

        self._nome_ferramenta = str(nome_ferramenta or "").strip()
        self._resultado = str(resultado or "").strip()
        self._duracao = float(duracao) if isinstance(duracao, (int, float)) else 0.0

        self._tipo, self._nivel = parse_controle(self._resultado, self._nome_ferramenta)

        if self._nivel is not None:
            self.definir_contagem(f"{self._tipo}: {self._nivel}%")
        else:
            self.definir_contagem(f"{self._tipo}")

        self._montar_ui()
        self.exportar_telemetria_solicitado.connect(self._ao_exportar_telemetria)

    def _montar_ui(self) -> None:
        """Monta a interface com o slider em estado somente leitura."""
        conteudo = QWidget()
        layout_raiz = QVBoxLayout(conteudo)
        layout_raiz.setContentsMargins(4, 4, 4, 4)
        layout_raiz.setSpacing(12)

        # Barra de status do ajuste
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

        selo_texto = "AJUSTE CONFIRMADO" if self._nivel is not None else "RESPOSTA DO HARDWARE"
        selo = QLabel(selo_texto)
        selo.setStyleSheet(f"""
            color: {COR_SUCESSO if self._nivel is not None else COR_TEXTO_MUTED};
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

        # Painel central
        cartao = QFrame()
        cartao.setStyleSheet(f"""
            QFrame {{
                background-color: rgba(7, 27, 38, 0.75);
                border: 1px solid {COR_BORDA_SUAVE};
                border-radius: 10px;
            }}
        """)
        layout_cartao = QVBoxLayout(cartao)
        layout_cartao.setContentsMargins(18, 20, 18, 20)
        layout_cartao.setSpacing(14)

        if self._nivel is not None:
            # Topo com icone, rotulo e grande indicador numerico
            topo_indicador = QHBoxLayout()
            topo_indicador.setSpacing(10)

            icone = "🔊" if self._tipo == "VOLUME" else "☀️"
            lbl_icone = QLabel(icone)
            lbl_icone.setStyleSheet("font-size: 24px;")
            topo_indicador.addWidget(lbl_icone)

            bloco_texto = QVBoxLayout()
            bloco_texto.setSpacing(2)

            lbl_rotulo = QLabel(f"NÍVEL DE {self._tipo}")
            lbl_rotulo.setStyleSheet(f"""
                color: {COR_TEXTO_MUTED};
                font-family: {FONTE_MONO};
                font-size: 11px;
                font-weight: bold;
                letter-spacing: 1px;
            """)
            bloco_texto.addWidget(lbl_rotulo)

            lbl_subtexto = QLabel("Ação executada no kernel com sucesso")
            lbl_subtexto.setStyleSheet(f"color: {COR_TEXTO}; font-size: 10px;")
            bloco_texto.addWidget(lbl_subtexto)
            topo_indicador.addLayout(bloco_texto, 1)

            lbl_porcentagem = QLabel(f"{self._nivel}%")
            lbl_porcentagem.setStyleSheet(f"""
                color: {COR_CIANO_BRILHO};
                font-family: {FONTE_MONO};
                font-size: 26px;
                font-weight: bold;
            """)
            topo_indicador.addWidget(lbl_porcentagem)
            layout_cartao.addLayout(topo_indicador)

            # Slider desabilitado (apenas leitura)
            slider = QSlider(Qt.Orientation.Horizontal)
            slider.setRange(0, 100)
            slider.setValue(max(0, min(100, self._nivel)))
            slider.setEnabled(False)
            slider.setFixedHeight(26)
            slider.setStyleSheet(f"""
                QSlider::groove:horizontal {{
                    background-color: rgba(11, 37, 53, 0.9);
                    height: 8px;
                    border-radius: 4px;
                    border: 1px solid {COR_BORDA_SUAVE};
                }}
                QSlider::sub-page:horizontal {{
                    background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 {COR_CIANO_ESCURO}, stop:1 {COR_CIANO});
                    border-radius: 4px;
                }}
                QSlider::handle:horizontal {{
                    background-color: {COR_CIANO_BRILHO};
                    border: 1px solid {COR_CIANO};
                    width: 18px;
                    margin-top: -5px;
                    margin-bottom: -5px;
                    border-radius: 9px;
                }}
            """)
            layout_cartao.addWidget(slider)

            # Marcadores de escala 0% e 100%
            escala = QHBoxLayout()
            lbl_min = QLabel("0%")
            lbl_min.setStyleSheet(f"color: {COR_TEXTO_MUTED}; font-family: {FONTE_MONO}; font-size: 9px;")
            escala.addWidget(lbl_min)
            escala.addStretch(1)
            lbl_max = QLabel("100%")
            lbl_max.setStyleSheet(f"color: {COR_TEXTO_MUTED}; font-family: {FONTE_MONO}; font-size: 9px;")
            escala.addWidget(lbl_max)
            layout_cartao.addLayout(escala)

            # Mensagem textual real abaixo
            lbl_saida = QLabel(self._resultado)
            lbl_saida.setStyleSheet(f"color: {COR_TEXTO}; font-family: {FONTE_MONO}; font-size: 11px;")
            layout_cartao.addWidget(lbl_saida)
        else:
            # Exibicao textual direta caso o valor numerico nao seja identificado
            lbl_aviso = QLabel(self._resultado or "Comando executado sem retorno numérico.")
            lbl_aviso.setWordWrap(True)
            lbl_aviso.setStyleSheet(f"""
                color: {COR_TEXTO};
                font-family: {FONTE_MONO};
                font-size: 11px;
                line-height: 1.4;
            """)
            layout_cartao.addWidget(lbl_aviso)

        layout_raiz.addWidget(cartao, 1)
        self.adicionar_aba("Ajuste", conteudo)

    def _ao_exportar_telemetria(self) -> Path:
        """Exporta os dados do ajuste para Markdown."""
        pasta = garantir_pasta_dados()
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        arquivo_md = pasta / f"controle_{self._tipo.lower()}_{ts}.md"

        linhas = [
            f"# Controle de Hardware // {self._tipo}",
            "",
            f"- **Data/Hora:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
            f"- **Parâmetro:** {self._tipo}",
            f"- **Nível Definido:** {self._nivel}%" if self._nivel is not None else "- **Nível Definido:** Indeterminado",
            f"- **Latência:** {self._duracao:.2f}s",
            "",
            "## Saída Real",
            "```",
            self._resultado,
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

"""Popup especializado para o subsistema de Documentos (RAG) do N.E.X.U.S.

Processa e exibe em destaque respostas contextuais de perguntas sobre documentos
e confirmacoes de indexacao vetorial (ChromaDB), relacionando fontes citadas.
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
    QScrollArea,
)

from comum import garantir_pasta_dados
from interface.estilo import (
    COR_FUNDO_SUPERFICIE,
    COR_CIANO,
    COR_CIANO_BRILHO,
    COR_BORDA,
    COR_BORDA_SUAVE,
    COR_TEXTO,
    COR_TEXTO_MUTED,
    COR_TEXTO_BRANCO,
    COR_SUCESSO,
    COR_ALERTA,
    FONTE_MONO,
    FONTE_UI,
)
from interface.popup_base import PopupBase


def parse_documentos(resultado: str) -> dict:
    """Extrai resposta RAG, relacao de fontes e estatisticas de indexacao."""
    dados = {
        "tipo": "consulta",
        "resposta": "",
        "fontes": [],
        "trechos": None,
        "arquivos": None,
        "caminho": "",
    }
    texto = str(resultado or "").strip()
    if not texto:
        return dados

    # 1. Confirmacao de indexacao: 'Indexados N trechos de M arquivo(s) em /caminho.'
    m_idx = re.search(r"Indexados\s+(\d+)\s+trechos\s+de\s+(\d+)\s+arquivo\(s\)\s+em\s+(.+?)(?:\.|$)", texto, re.IGNORECASE)
    if m_idx:
        dados["tipo"] = "indexacao"
        dados["trechos"] = int(m_idx.group(1))
        dados["arquivos"] = int(m_idx.group(2))
        dados["caminho"] = m_idx.group(3).strip()
        dados["resposta"] = texto
        return dados

    # 2. Resposta RAG com fontes: 'Texto...\n\nFontes: arq1, arq2'
    partes_fonte = re.split(r"\n\s*Fontes:\s*", texto, flags=re.IGNORECASE)
    if len(partes_fonte) > 1:
        dados["resposta"] = partes_fonte[0].strip()
        fontes_brutas = partes_fonte[1].strip()
        lista_fontes = [f.strip() for f in re.split(r",|\n", fontes_brutas) if f.strip()]
        dados["fontes"] = lista_fontes
    else:
        dados["resposta"] = texto

    return dados


class PopupDocumentos(PopupBase):
    """Popup modal para visualizacao de respostas RAG e indexacoes do ChromaDB."""

    def __init__(
        self,
        nome_ferramenta: str = "perguntar_documentos",
        resultado: str = "",
        duracao: float = 0.0,
        parent=None,
    ):
        super().__init__(titulo="DOCUMENTOS (RAG)", parent=parent)

        self._nome_ferramenta = str(nome_ferramenta or "").strip()
        self._resultado = str(resultado or "").strip()
        self._duracao = float(duracao) if isinstance(duracao, (int, float)) else 0.0

        self._dados = parse_documentos(self._resultado)

        if self._dados["tipo"] == "indexacao":
            self.definir_contagem(f"{self._dados['trechos']} TRECHOS")
        elif self._dados["fontes"]:
            self.definir_contagem(f"{len(self._dados['fontes'])} FONTES")
        else:
            self.definir_contagem("RAG LOCAL")

        self._montar_ui()
        self.exportar_telemetria_solicitado.connect(self._ao_exportar_telemetria)

    def _montar_ui(self) -> None:
        """Monta as abas de resposta e de fontes consultadas."""
        aba_principal = self._criar_aba_principal()
        self.adicionar_aba("Documentos (RAG)", aba_principal)

        if self._dados["fontes"]:
            aba_fontes = self._criar_aba_fontes()
            self.adicionar_aba(f"Fontes ({len(self._dados['fontes'])})", aba_fontes)

    def _criar_aba_principal(self) -> QWidget:
        """Cria o painel principal com destaque de resultado."""
        conteudo = QWidget()
        layout_raiz = QVBoxLayout(conteudo)
        layout_raiz.setContentsMargins(4, 4, 4, 4)
        layout_raiz.setSpacing(10)

        # Barra de status superior
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

        selo = QLabel("DOCUMENTOS (RAG) // VETORIAL LOCAL")
        selo.setStyleSheet(f"""
            color: {COR_SUCESSO if self._dados['resposta'] else COR_TEXTO_MUTED};
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

        # Painel em destaque para o conteudo
        area_scroll = QScrollArea()
        area_scroll.setWidgetResizable(True)
        area_scroll.setFrameShape(QFrame.Shape.NoFrame)
        area_scroll.setStyleSheet("background: transparent; border: none;")

        cartao = QFrame()
        cartao.setStyleSheet(f"""
            QFrame {{
                background-color: rgba(7, 27, 38, 0.75);
                border: 1px solid {COR_BORDA_SUAVE};
                border-radius: 8px;
            }}
        """)
        layout_cartao = QVBoxLayout(cartao)
        layout_cartao.setContentsMargins(14, 12, 14, 12)
        layout_cartao.setSpacing(12)

        if self._dados["tipo"] == "indexacao":
            # Estatisticas de indexacao
            topo_idx = QHBoxLayout()
            lbl_ico = QLabel("📚")
            lbl_ico.setStyleSheet("font-size: 24px;")
            topo_idx.addWidget(lbl_ico)

            info_idx = QVBoxLayout()
            info_idx.setSpacing(2)

            lbl_idx_tit = QLabel("INDEXAÇÃO VETORIAL CONCLUÍDA")
            lbl_idx_tit.setStyleSheet(f"""
                color: {COR_TEXTO_BRANCO};
                font-family: {FONTE_MONO};
                font-size: 12px;
                font-weight: bold;
            """)
            info_idx.addWidget(lbl_idx_tit)

            lbl_sub = QLabel(f"Diretório: {self._dados['caminho']}")
            lbl_sub.setWordWrap(True)
            lbl_sub.setStyleSheet(f"color: {COR_CIANO}; font-family: {FONTE_MONO}; font-size: 10px;")
            info_idx.addWidget(lbl_sub)
            topo_idx.addLayout(info_idx, 1)
            layout_cartao.addLayout(topo_idx)

            # Cartoes de metricas
            layout_metricas = QHBoxLayout()
            layout_metricas.setSpacing(10)

            c1 = self._criar_card_metrica("TRECHOS GERADOS", str(self._dados["trechos"]))
            c2 = self._criar_card_metrica("ARQUIVOS PROCESSADOS", str(self._dados["arquivos"]))
            layout_metricas.addWidget(c1)
            layout_metricas.addWidget(c2)
            layout_cartao.addLayout(layout_metricas)

        else:
            # Resposta textual RAG
            lbl_resp = QLabel(self._dados["resposta"] or "Sem resposta gerada pelo modelo local.")
            lbl_resp.setWordWrap(True)
            lbl_resp.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
            lbl_resp.setStyleSheet(f"""
                color: {COR_TEXTO};
                font-family: {FONTE_UI};
                font-size: 11px;
                line-height: 1.45;
            """)
            layout_cartao.addWidget(lbl_resp)

            # Mini-bloco de fontes se houver
            if self._dados["fontes"]:
                lbl_fontes_tit = QLabel("FONTES CITADAS:")
                lbl_fontes_tit.setStyleSheet(f"""
                    color: {COR_TEXTO_MUTED};
                    font-family: {FONTE_MONO};
                    font-size: 10px;
                    font-weight: bold;
                    margin-top: 8px;
                """)
                layout_cartao.addWidget(lbl_fontes_tit)

                for fonte in self._dados["fontes"][:4]:
                    lbl_f = QLabel(f"• {Path(fonte).name} ({fonte})")
                    lbl_f.setWordWrap(True)
                    lbl_f.setStyleSheet(f"color: {COR_CIANO}; font-family: {FONTE_MONO}; font-size: 10px;")
                    layout_cartao.addWidget(lbl_f)

        layout_cartao.addStretch(1)
        area_scroll.setWidget(cartao)
        layout_raiz.addWidget(area_scroll, 1)

        return conteudo

    def _criar_card_metrica(self, titulo: str, valor: str) -> QFrame:
        """Gera um mini-card para metricas de indexacao."""
        quadro = QFrame()
        quadro.setStyleSheet(f"""
            QFrame {{
                background-color: rgba(11, 37, 53, 0.6);
                border: 1px solid {COR_BORDA_SUAVE};
                border-radius: 6px;
            }}
        """)
        layout = QVBoxLayout(quadro)
        layout.setContentsMargins(10, 8, 10, 8)
        layout.setSpacing(2)

        lbl_tit = QLabel(titulo)
        lbl_tit.setStyleSheet(f"color: {COR_TEXTO_MUTED}; font-family: {FONTE_MONO}; font-size: 9px; font-weight: bold;")
        layout.addWidget(lbl_tit)

        lbl_val = QLabel(valor)
        lbl_val.setStyleSheet(f"color: {COR_CIANO_BRILHO}; font-family: {FONTE_MONO}; font-size: 16px; font-weight: bold;")
        layout.addWidget(lbl_val)

        return quadro

    def _criar_aba_fontes(self) -> QWidget:
        """Gera a aba dedicada a listagem completa de arquivos fonte."""
        conteudo = QWidget()
        layout_raiz = QVBoxLayout(conteudo)
        layout_raiz.setContentsMargins(4, 4, 4, 4)

        area_scroll = QScrollArea()
        area_scroll.setWidgetResizable(True)
        area_scroll.setFrameShape(QFrame.Shape.NoFrame)
        area_scroll.setStyleSheet("background: transparent; border: none;")

        conteudo_scroll = QWidget()
        layout_lista = QVBoxLayout(conteudo_scroll)
        layout_lista.setContentsMargins(0, 4, 0, 0)
        layout_lista.setSpacing(8)

        for i, fonte in enumerate(self._dados["fontes"], 1):
            card = QFrame()
            card.setStyleSheet(f"""
                QFrame {{
                    background-color: rgba(11, 37, 53, 0.6);
                    border: 1px solid {COR_BORDA_SUAVE};
                    border-radius: 6px;
                }}
            """)
            layout_c = QHBoxLayout(card)
            layout_c.setContentsMargins(10, 8, 10, 8)
            layout_c.setSpacing(10)

            lbl_num = QLabel(f"{i:02d}.")
            lbl_num.setStyleSheet(f"color: {COR_CIANO}; font-family: {FONTE_MONO}; font-size: 11px; font-weight: bold;")
            layout_c.addWidget(lbl_num)

            bloco_f = QVBoxLayout()
            bloco_f.setSpacing(2)

            lbl_nome = QLabel(Path(fonte).name)
            lbl_nome.setStyleSheet(f"color: {COR_TEXTO_BRANCO}; font-family: {FONTE_MONO}; font-size: 11px; font-weight: bold;")
            bloco_f.addWidget(lbl_nome)

            lbl_caminho = QLabel(fonte)
            lbl_caminho.setStyleSheet(f"color: {COR_TEXTO_MUTED}; font-family: {FONTE_MONO}; font-size: 10px;")
            lbl_caminho.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
            bloco_f.addWidget(lbl_caminho)

            layout_c.addLayout(bloco_f, 1)
            layout_lista.addWidget(card)

        layout_lista.addStretch(1)
        area_scroll.setWidget(conteudo_scroll)
        layout_raiz.addWidget(area_scroll)

        return conteudo

    def _ao_exportar_telemetria(self) -> Path:
        """Salva a saida do RAG e fontes em arquivo Markdown."""
        pasta = garantir_pasta_dados()
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        arquivo_md = pasta / f"documentos_rag_{ts}.md"

        linhas = [
            "# Telemetria Documentos (RAG) // N.E.X.U.S.",
            "",
            f"- **Data/Hora:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
            f"- **Ferramenta:** {self._nome_ferramenta}",
            f"- **Latência:** {self._duracao:.2f}s",
            f"- **Total de Fontes:** {len(self._dados['fontes'])}",
            "",
            "## Conteúdo / Resposta",
            self._dados["resposta"],
            "",
        ]

        if self._dados["fontes"]:
            linhas.append("## Fontes Consultadas")
            for f in self._dados["fontes"]:
                linhas.append(f"- `{f}`")
            linhas.append("")

        linhas.extend(["## Saída Bruta", "```", self._resultado, "```", ""])
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

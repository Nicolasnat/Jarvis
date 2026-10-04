"""Popups especializados para Projetos, Programas e Area de Transferencia do N.E.X.U.S.

Fornece PopupProjetos (listagem de diretorios de codigo), PopupProgramas
(gerenciamento e descoberta de executaveis) e PopupClipboard (area de transferencia).
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
    FONTE_MONO,
    FONTE_UI,
)
from interface.popup_base import PopupBase


# ============================================================================
# 1. PopupProjetos
# ============================================================================

def parse_projetos(resultado: str) -> list[dict]:
    """Extrai os projetos e metadados reais da saida de listar_projetos."""
    projetos = []
    texto = str(resultado or "").strip()
    if not texto:
        return projetos

    padrao = re.compile(
        r"^-\s*(?P<nome>[^\(]+?)\s*\((?P<itens>\d+)\s*itens,\s*modificado\s+em\s+(?P<data>[^\)]+)\)",
        re.MULTILINE,
    )
    for m in padrao.finditer(texto):
        projetos.append({
            "nome": m.group("nome").strip(),
            "itens": int(m.group("itens")),
            "data": m.group("data").strip(),
        })

    return projetos


class PopupProjetos(PopupBase):
    """Popup modal para visualizacao de projetos de codigo e operacoes de pastas."""

    def __init__(
        self,
        nome_ferramenta: str = "listar_projetos",
        resultado: str = "",
        duracao: float = 0.0,
        parent=None,
    ):
        super().__init__(titulo="PROJETOS", parent=parent)

        self._nome_ferramenta = str(nome_ferramenta or "").strip()
        self._resultado = str(resultado or "").strip()
        self._duracao = float(duracao) if isinstance(duracao, (int, float)) else 0.0

        self._projetos = parse_projetos(self._resultado)
        if self._projetos:
            self.definir_contagem(f"{len(self._projetos)} PROJETOS")
        else:
            self.definir_contagem("DIRETÓRIOS")

        self._montar_ui()
        self.exportar_telemetria_solicitado.connect(self._ao_exportar_telemetria)

    def _montar_ui(self) -> None:
        """Monta a aba com os cartoes de projeto ou confirmacao de acao."""
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

        selo = QLabel("WORKSPACE DO PROJETO // KERNEL")
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

        # Area com rolagem para a lista de projetos
        area_scroll = QScrollArea()
        area_scroll.setWidgetResizable(True)
        area_scroll.setFrameShape(QFrame.Shape.NoFrame)
        area_scroll.setStyleSheet("background: transparent; border: none;")

        conteudo_scroll = QWidget()
        layout_scroll = QVBoxLayout(conteudo_scroll)
        layout_scroll.setContentsMargins(0, 4, 0, 0)
        layout_scroll.setSpacing(8)

        if self._projetos:
            for proj in self._projetos:
                card = self._criar_cartao_projeto(proj)
                layout_scroll.addWidget(card)
            layout_scroll.addStretch(1)
        else:
            # Acoes pontuais (criar pasta, abrir vscode, etc.) ou estado vazio
            card_acao = QFrame()
            card_acao.setStyleSheet(f"""
                QFrame {{
                    background-color: rgba(7, 27, 38, 0.75);
                    border: 1px solid {COR_BORDA_SUAVE};
                    border-radius: 8px;
                }}
            """)
            layout_acao = QVBoxLayout(card_acao)
            layout_acao.setContentsMargins(14, 14, 14, 14)

            lbl_acao = QLabel(self._resultado or "Nenhum projeto encontrado no diretório de trabalho.")
            lbl_acao.setWordWrap(True)
            lbl_acao.setStyleSheet(f"color: {COR_TEXTO}; font-family: {FONTE_MONO}; font-size: 11px;")
            layout_acao.addWidget(lbl_acao)
            layout_scroll.addWidget(card_acao)

        area_scroll.setWidget(conteudo_scroll)
        layout_raiz.addWidget(area_scroll, 1)

        self.adicionar_aba("Projetos", conteudo)

    def _criar_cartao_projeto(self, proj: dict) -> QFrame:
        """Cria o cartao com nome, quantidade de arquivos e data de modificacao."""
        card = QFrame()
        card.setStyleSheet(f"""
            QFrame {{
                background-color: rgba(11, 37, 53, 0.65);
                border: 1px solid {COR_BORDA_SUAVE};
                border-radius: 8px;
            }}
            QFrame:hover {{
                border-color: {COR_CIANO};
            }}
        """)
        layout = QHBoxLayout(card)
        layout.setContentsMargins(12, 10, 12, 10)
        layout.setSpacing(12)

        lbl_ico = QLabel("📁")
        lbl_ico.setStyleSheet("font-size: 18px;")
        layout.addWidget(lbl_ico)

        bloco_info = QVBoxLayout()
        bloco_info.setSpacing(3)

        lbl_nome = QLabel(proj["nome"])
        lbl_nome.setStyleSheet(f"""
            color: {COR_TEXTO_BRANCO};
            font-family: {FONTE_MONO};
            font-size: 12px;
            font-weight: bold;
        """)
        bloco_info.addWidget(lbl_nome)

        lbl_sub = QLabel(f"Modificado em {proj['data']}")
        lbl_sub.setStyleSheet(f"color: {COR_TEXTO_MUTED}; font-family: {FONTE_MONO}; font-size: 10px;")
        bloco_info.addWidget(lbl_sub)
        layout.addLayout(bloco_info, 1)

        # Selo de contagem de arquivos
        lbl_itens = QLabel(f"{proj['itens']} itens")
        lbl_itens.setStyleSheet(f"""
            color: {COR_CIANO_BRILHO};
            background-color: rgba(0, 229, 255, 0.12);
            border: 1px solid {COR_BORDA};
            border-radius: 4px;
            padding: 3px 8px;
            font-family: {FONTE_MONO};
            font-size: 10px;
            font-weight: bold;
        """)
        layout.addWidget(lbl_itens)

        return card

    def _ao_exportar_telemetria(self) -> Path:
        """Salva informacoes de projetos em formato Markdown."""
        pasta = garantir_pasta_dados()
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        arquivo_md = pasta / f"projetos_{ts}.md"

        linhas = [
            "# Telemetria de Projetos // N.E.X.U.S.",
            "",
            f"- **Data/Hora:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
            f"- **Ferramenta:** {self._nome_ferramenta}",
            f"- **Total de Projetos:** {len(self._projetos)}",
            f"- **Latência:** {self._duracao:.2f}s",
            "",
            "## Projetos Mapeados",
        ]
        if self._projetos:
            for p in self._projetos:
                linhas.append(f"- **{p['nome']}**: {p['itens']} itens (modificado em {p['data']})")
        else:
            linhas.append("*Sem projetos listados.*")

        linhas.extend(["", "## Saída Bruta", "```", self._resultado, "```", ""])
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


# ============================================================================
# 2. PopupProgramas
# ============================================================================

def parse_programas(resultado: str) -> dict:
    """Extrai lista de programas instalados ou detalhes de acoes de aplicacao."""
    dados = {
        "tipo": "acao",
        "total_filtrado": 0,
        "total_geral": 0,
        "apps": [],
        "mensagem": str(resultado or "").strip(),
    }
    texto = str(resultado or "").strip()
    if not texto:
        return dados

    # Listagem de apps: 'N de M aplicativos (config/apps.json): app1, app2...'
    m = re.match(r"^(\d+)\s+de\s+(\d+)\s+aplicativos\s*\([^)]*\):\s*(.*)$", texto, re.IGNORECASE)
    if m:
        dados["tipo"] = "lista"
        dados["total_filtrado"] = int(m.group(1))
        dados["total_geral"] = int(m.group(2))
        corpo = m.group(3).strip()
        dados["apps"] = [a.strip() for a in corpo.split(",") if a.strip()]
        return dados

    # Descoberta de apps: 'Registrei N aplicativos em ... (X descobertos...)'
    m_desc = re.match(r"^Registrei\s+(\d+)\s+aplicativos", texto, re.IGNORECASE)
    if m_desc:
        dados["tipo"] = "descoberta"
        dados["total_geral"] = int(m_desc.group(1))
        return dados

    return dados


class PopupProgramas(PopupBase):
    """Popup modal para visualizacao de programas instalados e operacoes de ciclo de vida."""

    def __init__(
        self,
        nome_ferramenta: str = "listar_apps",
        resultado: str = "",
        duracao: float = 0.0,
        parent=None,
    ):
        super().__init__(titulo="PROGRAMAS", parent=parent)

        self._nome_ferramenta = str(nome_ferramenta or "").strip()
        self._resultado = str(resultado or "").strip()
        self._duracao = float(duracao) if isinstance(duracao, (int, float)) else 0.0

        self._dados = parse_programas(self._resultado)
        if self._dados["tipo"] == "lista":
            self.definir_contagem(f"{len(self._dados['apps'])} APPS")
        elif self._dados["tipo"] == "descoberta":
            self.definir_contagem(f"{self._dados['total_geral']} APPS")
        else:
            self.definir_contagem("PROGRAMAS")

        self._montar_ui()
        self.exportar_telemetria_solicitado.connect(self._ao_exportar_telemetria)

    def _montar_ui(self) -> None:
        """Monta o painel de aplicativos em cartoes ou mensagem de operacao."""
        conteudo = QWidget()
        layout_raiz = QVBoxLayout(conteudo)
        layout_raiz.setContentsMargins(4, 4, 4, 4)
        layout_raiz.setSpacing(10)

        # Barra de status
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

        selo = QLabel("CATÁLOGO DE SOFTWARES // DESKTOP")
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

        # Area central com rolagem
        area_scroll = QScrollArea()
        area_scroll.setWidgetResizable(True)
        area_scroll.setFrameShape(QFrame.Shape.NoFrame)
        area_scroll.setStyleSheet("background: transparent; border: none;")

        conteudo_scroll = QWidget()
        layout_scroll = QVBoxLayout(conteudo_scroll)
        layout_scroll.setContentsMargins(0, 4, 0, 0)
        layout_scroll.setSpacing(8)

        if self._dados["tipo"] == "lista" and self._dados["apps"]:
            for app_nome in self._dados["apps"]:
                card = QFrame()
                card.setStyleSheet(f"""
                    QFrame {{
                        background-color: rgba(11, 37, 53, 0.6);
                        border: 1px solid {COR_BORDA_SUAVE};
                        border-radius: 6px;
                    }}
                    QFrame:hover {{
                        border-color: {COR_CIANO};
                    }}
                """)
                layout_c = QHBoxLayout(card)
                layout_c.setContentsMargins(10, 6, 10, 6)
                layout_c.setSpacing(10)

                lbl_ico = QLabel("🚀")
                lbl_ico.setStyleSheet("font-size: 14px;")
                layout_c.addWidget(lbl_ico)

                lbl_nome = QLabel(app_nome)
                lbl_nome.setStyleSheet(f"color: {COR_TEXTO_BRANCO}; font-family: {FONTE_MONO}; font-size: 11px; font-weight: bold;")
                layout_c.addWidget(lbl_nome, 1)

                layout_scroll.addWidget(card)
            layout_scroll.addStretch(1)
        else:
            # Exibicao textual destacada (abrir_programa, fechar_programa, descobrir_apps)
            card_texto = QFrame()
            card_texto.setStyleSheet(f"""
                QFrame {{
                    background-color: rgba(7, 27, 38, 0.75);
                    border: 1px solid {COR_BORDA_SUAVE};
                    border-radius: 8px;
                }}
            """)
            layout_t = QVBoxLayout(card_texto)
            layout_t.setContentsMargins(14, 14, 14, 14)

            lbl_msg = QLabel(self._resultado or "Comando de programa executado.")
            lbl_msg.setWordWrap(True)
            lbl_msg.setStyleSheet(f"color: {COR_TEXTO}; font-family: {FONTE_MONO}; font-size: 11px; line-height: 1.4;")
            layout_t.addWidget(lbl_msg)
            layout_scroll.addWidget(card_texto)

        area_scroll.setWidget(conteudo_scroll)
        layout_raiz.addWidget(area_scroll, 1)

        self.adicionar_aba("Programas", conteudo)

    def _ao_exportar_telemetria(self) -> Path:
        """Salva a lista de programas em Markdown."""
        pasta = garantir_pasta_dados()
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        arquivo_md = pasta / f"programas_{ts}.md"

        linhas = [
            "# Catálogo de Programas // N.E.X.U.S.",
            "",
            f"- **Data/Hora:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
            f"- **Ferramenta:** {self._nome_ferramenta}",
            f"- **Total Listado:** {len(self._dados['apps'])}",
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


# ============================================================================
# 3. PopupClipboard
# ============================================================================

class PopupClipboard(PopupBase):
    """Popup modal para visualizacao e confirmacao da area de transferencia."""

    def __init__(
        self,
        nome_ferramenta: str = "ler_clipboard",
        resultado: str = "",
        duracao: float = 0.0,
        parent=None,
    ):
        super().__init__(titulo="ÁREA DE TRANSFERÊNCIA", parent=parent)

        self._nome_ferramenta = str(nome_ferramenta or "").strip()
        self._resultado = str(resultado or "").strip()
        self._duracao = float(duracao) if isinstance(duracao, (int, float)) else 0.0

        # Trata prefixo 'Area de transferencia:\n' se presente
        texto_limpo = self._resultado
        prefixo = "Area de transferencia:\n"
        if texto_limpo.startswith(prefixo):
            texto_limpo = texto_limpo[len(prefixo):]
        self._conteudo_clipboard = texto_limpo

        caracteres = len(self._conteudo_clipboard)
        self.definir_contagem(f"{caracteres} CARACTERES" if caracteres else "VAZIO")

        self._montar_ui()
        self.exportar_telemetria_solicitado.connect(self._ao_exportar_telemetria)

    def _montar_ui(self) -> None:
        """Monta o painel de exibicao do conteudo do clipboard."""
        conteudo = QWidget()
        layout_raiz = QVBoxLayout(conteudo)
        layout_raiz.setContentsMargins(4, 4, 4, 4)
        layout_raiz.setSpacing(10)

        # Barra de status
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

        selo = QLabel("CLIPBOARD DO SISTEMA // BUFFER")
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

        # Area com rolagem para o texto do buffer
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

        lbl_texto = QLabel(self._conteudo_clipboard or "A área de transferência está vazia.")
        lbl_texto.setWordWrap(True)
        lbl_texto.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        lbl_texto.setStyleSheet(f"""
            color: {COR_TEXTO};
            font-family: {FONTE_MONO};
            font-size: 11px;
            line-height: 1.4;
        """)
        layout_cartao.addWidget(lbl_texto)

        area_scroll.setWidget(cartao)
        layout_raiz.addWidget(area_scroll, 1)

        self.adicionar_aba("Área de Transferência", conteudo)

    def _ao_exportar_telemetria(self) -> Path:
        """Salva o conteudo da area de transferencia em Markdown."""
        pasta = garantir_pasta_dados()
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        arquivo_md = pasta / f"clipboard_{ts}.md"

        linhas = [
            "# Conteúdo da Área de Transferência // N.E.X.U.S.",
            "",
            f"- **Data/Hora:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
            f"- **Operação:** {self._nome_ferramenta}",
            f"- **Tamanho:** {len(self._conteudo_clipboard)} caracteres",
            f"- **Latência:** {self._duracao:.2f}s",
            "",
            "## Conteúdo do Buffer",
            "```",
            self._conteudo_clipboard,
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

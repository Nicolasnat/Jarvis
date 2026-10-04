"""Popup especializado para exibicao de listas (Tarefas, Lembretes, Memoria e Notas).

Renderiza itens estruturados em cartoes visuais com estilizacao distinta para
tarefas pendentes e concluidas, alem de suporte a estado vazio elegante.
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


def extrair_titulo_lista(nome_ferramenta: str) -> str:
    """Mapeia o nome da ferramenta para o titulo amigavel de lista."""
    nome = (nome_ferramenta or "").lower().strip()
    if "tarefa" in nome:
        return "TAREFAS"
    if "lembrete" in nome:
        return "LEMBRETES"
    if "memoria" in nome or "fato" in nome:
        return "MEMÓRIA"
    if "nota" in nome or "anotar" in nome:
        return "ANOTAÇÕES"
    return "LISTA"


def parse_itens_lista(texto: str, nome_ferramenta: str = "") -> list[dict]:
    """Parseia tarefas, lembretes, memorias ou anotacoes em itens estruturados."""
    itens = []
    bruto = str(texto or "").strip()
    if not bruto:
        return itens

    # Identifica mensagens de estado vazio
    indicadores_vazio = (
        "nenhuma tarefa",
        "nenhum lembrete",
        "nada encontrado na memoria",
        "nenhuma tarefa pendente",
        "nada para anotar",
        "a tarefa veio vazia",
    )
    if any(indicador in bruto.lower() for indicador in indicadores_vazio):
        return []

    linhas = bruto.splitlines()
    secao_atual = "pendente"

    for linha in linhas:
        l = linha.strip()
        if not l:
            continue

        l_lower = l.lower()
        if l_lower.startswith("pendentes:"):
            secao_atual = "pendente"
            continue
        if l_lower.startswith("concluidas:"):
            secao_atual = "concluida"
            continue
        if l_lower.startswith("lembretes pendentes:") or l_lower.startswith("memoria:"):
            continue

        # 1. Tarefa listada: '- #id texto'
        m_tarefa = re.match(r"^-\s*#(\d+)\s*(.*)$", l)
        if m_tarefa and ("tarefa" in nome_ferramenta or secao_atual in ("pendente", "concluida")):
            # Se a linha contiver data/hora, e provavelmente um lembrete
            if re.search(r"\d{2}/\d{2}/\d{4}", m_tarefa.group(2)):
                pass
            else:
                itens.append({
                    "id": m_tarefa.group(1),
                    "texto": m_tarefa.group(2).strip(),
                    "tipo": secao_atual,
                    "metadado": "",
                })
                continue

        # 2. Tarefa adicionada: 'Tarefa #id adicionada: texto'
        m_add = re.match(r"^Tarefa\s+#(\d+)\s+adicionada:\s*(.*)$", l, re.IGNORECASE)
        if m_add:
            itens.append({
                "id": m_add.group(1),
                "texto": m_add.group(2).strip(),
                "tipo": "pendente",
                "metadado": "Recém-adicionada",
            })
            continue

        # 3. Tarefas concluidas inline: 'Concluidas: nome1, nome2'
        if l.startswith("Concluidas:"):
            corpo = l[len("Concluidas:"):].strip()
            for parte in corpo.split(","):
                if parte.strip():
                    itens.append({
                        "id": "",
                        "texto": parte.strip(),
                        "tipo": "concluida",
                        "metadado": "Concluída",
                    })
            continue

        # 4. Lembrete listado: '- #id dd/mm/aaaa hh:mm: mensagem'
        m_lembrete = re.match(r"^-\s*#(\d+)\s+(\d{2}/\d{2}/\d{4}\s+\d{2}:\d{2}):\s*(.*)$", l)
        if m_lembrete:
            itens.append({
                "id": m_lembrete.group(1),
                "texto": m_lembrete.group(3).strip(),
                "tipo": "lembrete",
                "metadado": m_lembrete.group(2),
            })
            continue

        # 5. Lembrete agendado: 'Lembrete #id agendado para ...: texto'
        m_agendado = re.match(r"^Lembrete\s+#(\d+)\s+agendado\s+para\s+([^:]+):\s*(.*)$", l, re.IGNORECASE)
        if m_agendado:
            itens.append({
                "id": m_agendado.group(1),
                "texto": m_agendado.group(3).strip(),
                "tipo": "lembrete",
                "metadado": m_agendado.group(2).strip(),
            })
            continue

        # 6. Memoria listada: '- fato'
        if l.startswith("- ") and ("memoria" in nome_ferramenta or "fato" in nome_ferramenta):
            itens.append({
                "id": "",
                "texto": l[2:].strip(),
                "tipo": "memoria",
                "metadado": "",
            })
            continue

        # 7. Memoria salva: 'Anotado na memoria: fato' ou 'Ja estava na memoria: fato'
        for prefixo, rotulo in [("Anotado na memoria:", "Novo"), ("Ja estava na memoria:", "Existente")]:
            if l.startswith(prefixo):
                itens.append({
                    "id": "",
                    "texto": l[len(prefixo):].strip(),
                    "tipo": "memoria",
                    "metadado": rotulo,
                })
                break
        else:
            # 8. Anotacao: 'Anotado em arquivo: texto'
            m_nota = re.match(r"^Anotado\s+em\s+([^:]+):\s*(.*)$", l, re.IGNORECASE)
            if m_nota:
                itens.append({
                    "id": "",
                    "texto": m_nota.group(2).strip(),
                    "tipo": "nota",
                    "metadado": Path(m_nota.group(1).strip()).name,
                })
                continue

            # 9. Cancelamentos ou acoes pontuais
            if "cancelado" in l_lower or "esqueci" in l_lower:
                itens.append({
                    "id": "",
                    "texto": l,
                    "tipo": "acao",
                    "metadado": "",
                })

    return itens


class PopupLista(PopupBase):
    """Popup modal para exibicao e gerenciamento de tarefas, lembretes e notas."""

    def __init__(
        self,
        nome_ferramenta: str = "listar_tarefas",
        resultado: str = "",
        duracao: float = 0.0,
        parent=None,
    ):
        titulo_amigavel = extrair_titulo_lista(nome_ferramenta)
        super().__init__(titulo=titulo_amigavel, parent=parent)

        self._nome_ferramenta = str(nome_ferramenta or "").strip()
        self._resultado = str(resultado or "").strip()
        self._duracao = float(duracao) if isinstance(duracao, (int, float)) else 0.0

        self._itens = parse_itens_lista(self._resultado, self._nome_ferramenta)
        self.definir_contagem(f"{len(self._itens)} ITENS" if self._itens else "0 ITENS")

        self._montar_ui()
        self.exportar_telemetria_solicitado.connect(self._ao_exportar_telemetria)

    def _montar_ui(self) -> None:
        """Monta a aba com a lista de cartoes ou estado vazio."""
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

        selo = QLabel("REGISTRO SINCRONIZADO" if self._itens else "CONSULTA CONCLUÍDA")
        selo.setStyleSheet(f"""
            color: {COR_SUCESSO if self._itens else COR_TEXTO_MUTED};
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

        # Area com rolagem ou estado vazio
        if self._itens:
            area_scroll = QScrollArea()
            area_scroll.setWidgetResizable(True)
            area_scroll.setFrameShape(QFrame.Shape.NoFrame)
            area_scroll.setStyleSheet("background: transparent; border: none;")

            conteudo_scroll = QWidget()
            layout_lista = QVBoxLayout(conteudo_scroll)
            layout_lista.setContentsMargins(0, 4, 0, 0)
            layout_lista.setSpacing(8)

            for item in self._itens:
                card = self._criar_cartao_item(item)
                layout_lista.addWidget(card)

            layout_lista.addStretch(1)
            area_scroll.setWidget(conteudo_scroll)
            layout_raiz.addWidget(area_scroll, 1)
        else:
            layout_raiz.addWidget(self._criar_widget_vazio(), 1)

        self.adicionar_aba("Itens", conteudo)

    def _criar_cartao_item(self, item: dict) -> QFrame:
        """Renderiza um cartao individual com marcacao visual distinta."""
        card = QFrame()
        tipo = item.get("tipo", "pendente")

        # Diferencia estilo para pendente, concluida, lembrete, memoria e nota
        if tipo == "concluida":
            cor_borda = "rgba(0, 230, 118, 0.25)"
            bg_card = "rgba(7, 27, 38, 0.5)"
        elif tipo == "lembrete":
            cor_borda = "rgba(0, 229, 255, 0.3)"
            bg_card = "rgba(11, 37, 53, 0.65)"
        else:
            cor_borda = COR_BORDA_SUAVE
            bg_card = "rgba(11, 37, 53, 0.6)"

        card.setStyleSheet(f"""
            QFrame {{
                background-color: {bg_card};
                border: 1px solid {cor_borda};
                border-radius: 8px;
            }}
            QFrame:hover {{
                border-color: {COR_CIANO};
            }}
        """)
        layout = QHBoxLayout(card)
        layout.setContentsMargins(10, 8, 10, 8)
        layout.setSpacing(10)

        # Marcador visual lateral
        if tipo == "concluida":
            icone_marcador = QLabel("✓")
            icone_marcador.setStyleSheet(f"color: {COR_SUCESSO}; font-size: 13px; font-weight: bold;")
        elif tipo == "pendente":
            icone_marcador = QLabel("○")
            icone_marcador.setStyleSheet(f"color: {COR_CIANO}; font-size: 13px; font-weight: bold;")
        elif tipo == "lembrete":
            icone_marcador = QLabel("⏰")
            icone_marcador.setStyleSheet("font-size: 13px;")
        elif tipo == "memoria":
            icone_marcador = QLabel("◈")
            icone_marcador.setStyleSheet(f"color: {COR_CIANO_BRILHO}; font-size: 13px; font-weight: bold;")
        elif tipo == "nota":
            icone_marcador = QLabel("📝")
            icone_marcador.setStyleSheet("font-size: 13px;")
        else:
            icone_marcador = QLabel("•")
            icone_marcador.setStyleSheet(f"color: {COR_TEXTO_MUTED}; font-size: 13px;")

        icone_marcador.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft)
        layout.addWidget(icone_marcador)

        # Bloco central com id, metadado e texto
        centro = QVBoxLayout()
        centro.setSpacing(2)

        topo = QHBoxLayout()
        topo.setSpacing(6)

        if item.get("id"):
            lbl_id = QLabel(f"#{item['id']}")
            cor_id = COR_SUCESSO if tipo == "concluida" else COR_CIANO
            lbl_id.setStyleSheet(f"""
                color: {cor_id};
                font-family: {FONTE_MONO};
                font-size: 10px;
                font-weight: bold;
            """)
            topo.addWidget(lbl_id)

        if item.get("metadado"):
            lbl_meta = QLabel(item["metadado"])
            lbl_meta.setStyleSheet(f"""
                color: {COR_TEXTO_MUTED};
                background-color: rgba(255, 255, 255, 0.05);
                border-radius: 4px;
                padding: 1px 5px;
                font-family: {FONTE_MONO};
                font-size: 9px;
            """)
            topo.addWidget(lbl_meta)

        topo.addStretch(1)
        centro.addLayout(topo)

        # Texto principal
        lbl_texto = QLabel(item.get("texto", ""))
        lbl_texto.setWordWrap(True)

        if tipo == "concluida":
            lbl_texto.setStyleSheet(f"""
                color: {COR_TEXTO_MUTED};
                font-family: {FONTE_UI};
                font-size: 11px;
                text-decoration: line-through;
            """)
        else:
            lbl_texto.setStyleSheet(f"""
                color: {COR_TEXTO_BRANCO};
                font-family: {FONTE_UI};
                font-size: 11px;
            """)

        centro.addWidget(lbl_texto)
        layout.addLayout(centro, 1)

        return card

    def _criar_widget_vazio(self) -> QWidget:
        """Gera o estado vazio obrigatorio quando nao ha itens."""
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(12, 40, 12, 40)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.setSpacing(8)

        icone = QLabel("◈")
        icone.setStyleSheet(f"color: {COR_TEXTO_MUTED}; font-size: 24px;")
        icone.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(icone)

        texto = QLabel("Nenhum item")
        texto.setStyleSheet(f"""
            color: {COR_TEXTO_MUTED};
            font-family: {FONTE_MONO};
            font-size: 12px;
            font-weight: bold;
            letter-spacing: 1px;
        """)
        texto.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(texto)

        subtexto = QLabel("Não existem registros cadastrados ou correspondentes no momento.")
        subtexto.setStyleSheet(f"""
            color: {COR_TEXTO_MUTED};
            font-size: 10px;
        """)
        subtexto.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(subtexto)

        return widget

    def _ao_exportar_telemetria(self) -> Path:
        """Salva a relacao de itens em formato Markdown."""
        pasta = garantir_pasta_dados()
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        arquivo_md = pasta / f"lista_{self._nome_ferramenta}_{ts}.md"

        linhas = [
            f"# Relatório de Dados // {self._titulo_base}",
            "",
            f"- **Data/Hora:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
            f"- **Ferramenta:** {self._nome_ferramenta}",
            f"- **Total de Itens:** {len(self._itens)}",
            f"- **Latência:** {self._duracao:.2f}s",
            "",
            "## Itens Estruturados",
        ]

        if self._itens:
            for item in self._itens:
                id_str = f"#{item['id']} " if item.get("id") else ""
                tipo_str = f"[{item.get('tipo', '').upper()}] " if item.get("tipo") else ""
                meta_str = f" ({item['metadado']})" if item.get("metadado") else ""
                linhas.append(f"- {tipo_str}{id_str}{item.get('texto', '')}{meta_str}")
        else:
            linhas.append("*Nenhum item cadastrado.*")

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

"""Popup de Pesquisa Global para o N.E.X.U.S.

Processa e exibe dados retornados pela ferramenta pesquisar_na_web com
sintese algoritmica, relacao de fontes orbitais, cronograma temporal e
exportacao de telemetria em Markdown.
Todos os comentarios e docstrings neste modulo usam exclusivamente ASCII.
"""
from datetime import datetime
from pathlib import Path
import re
from urllib.parse import urlparse

from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import (
    QWidget,
    QFrame,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QScrollArea,
    QSizePolicy,
)

from comum import garantir_pasta_dados
from interface.estilo import (
    COR_FUNDO_SECUNDARIO,
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
    FONTE_MONO,
    FONTE_UI,
)
from interface.popup_base import PopupBase


def extrair_dominio(link: str) -> str:
    """Extrai o host/dominio limpo da URL (ex. www.nasa.gov -> nasa.gov)."""
    if not link:
        return ""
    try:
        url = link if "://" in link else f"https://{link}"
        parsed = urlparse(url)
        host = (parsed.netloc or parsed.path).lower().split(":")[0]
        if host.startswith("www."):
            host = host[4:]
        return host
    except Exception:
        return ""


def extrair_etiqueta_fonte(link: str) -> str:
    """Deriva a etiqueta da fonte em maiusculas a partir do dominio.

    Exemplo: nasa.gov -> NASA; se vazio ou invalido, devolve 'WEB'.
    """
    dominio = extrair_dominio(link)
    if not dominio:
        return "WEB"
    partes = [p for p in dominio.split(".") if p]
    if not partes:
        return "WEB"
    # Trata subdominios comuns de idioma/regiao (ex. pt.wikipedia.org -> WIKIPEDIA)
    if len(partes) >= 3 and partes[0] in ("en", "pt", "es", "m", "blog", "news", "noticias", "wiki"):
        nome = partes[1]
    else:
        nome = partes[0]
    return nome.upper() if nome else "WEB"


def parse_pesquisa(resultado: str) -> list[dict]:
    """Extrai os blocos reais (titulo, resumo, link) da busca na web.

    Ignora entradas incompletas e nao inventa dados. Devolve lista vazia se
    o retorno nao contiver registros validos.
    """
    if not resultado or not isinstance(resultado, str):
        return []

    texto = resultado.strip()
    if texto.startswith("Nenhum resultado encontrado") or texto.startswith("Erro ao realizar a busca"):
        return []

    itens = []
    # Divide pelos blocos separados por quebras de linha duplas
    blocos = re.split(r"\n\s*\n", texto)
    for bloco in blocos:
        bloco = bloco.strip()
        if not ("Titulo:" in bloco and "Link:" in bloco):
            continue

        titulo = ""
        link = ""
        resumo_linhas = []
        campo_atual = None

        for linha in bloco.splitlines():
            linha_strip = linha.strip()
            if linha_strip.startswith("Titulo:"):
                titulo = linha_strip[len("Titulo:"):].strip()
                campo_atual = "titulo"
            elif linha_strip.startswith("Resumo:"):
                resumo_linhas.append(linha_strip[len("Resumo:"):].strip())
                campo_atual = "resumo"
            elif linha_strip.startswith("Link:"):
                link = linha_strip[len("Link:"):].strip()
                campo_atual = "link"
            elif campo_atual == "resumo":
                resumo_linhas.append(linha_strip)

        resumo = " ".join(r for r in resumo_linhas if r).strip()

        # Ignorar entradas incompletas: exige titulo e link
        if titulo and link:
            itens.append({
                "titulo": titulo,
                "resumo": resumo,
                "link": link,
            })

    # Fallback por expressao regular caso o formato de quebras varie
    if not itens and "Titulo:" in texto:
        padrao = re.compile(
            r"Titulo:\s*(?P<titulo>[^\r\n]+)\r?\n"
            r"Resumo:\s*(?P<resumo>.*?)\r?\n"
            r"Link:\s*(?P<link>https?://\S+|[^\s\r\n]+)",
            re.DOTALL,
        )
        for m in padrao.finditer(texto):
            tit = m.group("titulo").strip()
            res = m.group("resumo").strip()
            lnk = m.group("link").strip()
            if tit and lnk:
                itens.append({"titulo": tit, "resumo": res, "link": lnk})

    return itens


def extrair_marcos_temporais(texto: str) -> list[dict]:
    """Extrai datas (dd/mm/aaaa ou aaaa) e frases de contexto no texto."""
    if not texto:
        return []

    # Procura datas nos formatos dd/mm/aaaa ou ano entre 1800 e 2099
    padrao = re.compile(r"\b(\d{1,2}/\d{1,2}/\d{2,4}|(?:18|19|20)\d{2})\b")
    pedacos = [p.strip() for p in re.split(r"[\n\r]+|[.!?]\s+", texto) if p.strip()]

    marcos = []
    vistos = set()

    for pedaco in pedacos:
        if pedaco.startswith("http://") or pedaco.startswith("https://") or "Link:" in pedaco:
            continue

        for m in padrao.finditer(pedaco):
            data = m.group(1)
            frase = pedaco
            for prefixo in ("Titulo:", "Resumo:", "Informacoes encontradas na web:"):
                frase = frase.replace(prefixo, "").strip()

            chave = (data, frase[:50])
            if chave in vistos:
                continue
            vistos.add(chave)

            marcos.append({
                "data": data,
                "descricao": frase,
            })

    def _chave_ordenacao(item):
        d = item["data"]
        if "/" in d:
            partes = d.split("/")
            ano = int(partes[-1]) if len(partes) >= 3 else 0
            if ano < 100:
                ano += 2000
            return ano
        try:
            return int(d)
        except ValueError:
            return 9999

    marcos.sort(key=_chave_ordenacao)
    return marcos


class PopupPesquisaGlobal(PopupBase):
    """Popup modal especializado na visualizacao de buscas globais."""

    def __init__(
        self,
        resultado: str = "",
        duracao: float = 0.0,
        termo_busca: str = "",
        parent=None,
    ):
        super().__init__(titulo="PESQUISA GLOBAL", parent=parent)

        self._resultado_bruto = str(resultado or "")
        self._duracao = float(duracao) if isinstance(duracao, (int, float)) else 0.0
        self._termo_busca = str(termo_busca or "").strip()
        if not self._termo_busca:
            # Tenta inferir termo de mensagens padrao
            m = re.search(r"Nenhum resultado encontrado para '([^']+)'", self._resultado_bruto)
            if m:
                self._termo_busca = m.group(1)
            else:
                self._termo_busca = "Pesquisa Global"

        self._itens = parse_pesquisa(self._resultado_bruto)
        self.definir_contagem(f"FONTES: {len(self._itens)}")

        self._montar_abas()
        self.exportar_telemetria_solicitado.connect(self._ao_exportar_telemetria)

    def _montar_abas(self) -> None:
        """Cria e registra as 3 abas operacionais do popup."""
        aba_resposta = self._criar_aba_resposta()
        self.adicionar_aba("Resposta Sintetizada", aba_resposta)

        aba_fontes = self._criar_aba_fontes()
        self.adicionar_aba(f"Fontes Orbitais ({len(self._itens)})", aba_fontes)

        aba_cronograma = self._criar_aba_cronograma()
        self.adicionar_aba("Cronograma", aba_cronograma)

    def _criar_aba_resposta(self) -> QWidget:
        """Monta a aba 'Resposta Sintetizada' com destaque e cartoes numerados."""
        container = QWidget()
        layout_raiz = QVBoxLayout(container)
        layout_raiz.setContentsMargins(4, 4, 4, 4)
        layout_raiz.setSpacing(10)

        # 1. Caixa de destaque
        caixa_destaque = QFrame()
        caixa_destaque.setStyleSheet(f"""
            QFrame {{
                background-color: {COR_FUNDO_SUPERFICIE};
                border: 1px solid {COR_BORDA};
                border-left: 3px solid {COR_CIANO};
                border-radius: 8px;
            }}
        """)
        layout_destaque = QVBoxLayout(caixa_destaque)
        layout_destaque.setContentsMargins(10, 8, 10, 8)
        layout_destaque.setSpacing(6)

        # Topo da caixa de destaque: selo e tempo
        topo_destaque = QHBoxLayout()
        topo_destaque.setSpacing(8)

        selo_texto = "CONSOLIDACAO ALGORITMICA CONCLUIDA" if self._itens else "CONSULTA CONCLUIDA"
        selo = QLabel(selo_texto)
        bg_selo = "rgba(0, 230, 118, 0.12)" if self._itens else "rgba(84, 110, 122, 0.15)"
        cor_selo = COR_SUCESSO if self._itens else COR_TEXTO_MUTED
        selo.setStyleSheet(f"""
            color: {cor_selo};
            background-color: {bg_selo};
            border: 1px solid {cor_selo};
            border-radius: 4px;
            padding: 2px 6px;
            font-family: {FONTE_MONO};
            font-size: 9px;
            font-weight: bold;
            letter-spacing: 1px;
        """)
        topo_destaque.addWidget(selo)
        topo_destaque.addStretch(1)

        tempo_str = f"{self._duracao:.2f}s"
        lbl_tempo = QLabel(tempo_str)
        lbl_tempo.setStyleSheet(f"""
            color: {COR_CIANO};
            font-family: {FONTE_MONO};
            font-size: 10px;
            font-weight: bold;
        """)
        topo_destaque.addWidget(lbl_tempo)
        layout_destaque.addLayout(topo_destaque)

        # Texto do resumo: resultado limpo sem o cabecalho padrao
        texto_limpo = self._resultado_bruto
        for prefixo in (
            "Informacoes encontradas na web:\n\n",
            "Informacoes encontradas na web:\n",
            "Informacoes encontradas na web:",
        ):
            if texto_limpo.startswith(prefixo):
                texto_limpo = texto_limpo[len(prefixo):].strip()
                break

        if self._itens:
            # Exibe sintese do primeiro item ou texto limpo sintetizado
            resumo_texto = self._itens[0].get("resumo") or texto_limpo
            if len(resumo_texto) > 220:
                resumo_texto = resumo_texto[:220].rstrip() + "..."
        else:
            resumo_texto = texto_limpo or "Sem dados consolidados retornados para esta consulta."

        lbl_resumo = QLabel(resumo_texto)
        lbl_resumo.setWordWrap(True)
        lbl_resumo.setStyleSheet(f"""
            color: {COR_TEXTO};
            font-family: {FONTE_UI};
            font-size: 11px;
            line-height: 1.4;
        """)
        layout_destaque.addWidget(lbl_resumo)
        layout_raiz.addWidget(caixa_destaque)

        # 2. Cartoes numerados com rolagem
        area_scroll = QScrollArea()
        area_scroll.setWidgetResizable(True)
        area_scroll.setFrameShape(QFrame.Shape.NoFrame)
        area_scroll.setStyleSheet("background: transparent; border: none;")

        conteudo_scroll = QWidget()
        layout_cards = QVBoxLayout(conteudo_scroll)
        layout_cards.setContentsMargins(0, 4, 0, 0)
        layout_cards.setSpacing(8)

        if self._itens:
            for i, item in enumerate(self._itens, 1):
                card = self._criar_cartao_resumo(i, item)
                layout_cards.addWidget(card)
            layout_cards.addStretch(1)
        else:
            lbl_vazio = self._criar_widget_vazio("Sem registros estruturados identificados.")
            layout_cards.addWidget(lbl_vazio)

        area_scroll.setWidget(conteudo_scroll)
        layout_raiz.addWidget(area_scroll, 1)

        return container

    def _criar_cartao_resumo(self, indice: int, item: dict) -> QFrame:
        """Cria um cartao numerado '01.' com titulo, resumo truncado e fonte."""
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
        layout.setContentsMargins(10, 8, 10, 8)
        layout.setSpacing(10)

        # Numero "01."
        lbl_num = QLabel(f"{indice:02d}.")
        lbl_num.setStyleSheet(f"""
            color: {COR_CIANO};
            font-family: {FONTE_MONO};
            font-size: 13px;
            font-weight: bold;
        """)
        lbl_num.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft)
        layout.addWidget(lbl_num)

        # Centro: Titulo e resumo truncado
        centro = QVBoxLayout()
        centro.setSpacing(3)

        lbl_tit = QLabel(item.get("titulo", "Sem titulo"))
        lbl_tit.setWordWrap(True)
        lbl_tit.setStyleSheet(f"""
            color: {COR_TEXTO_BRANCO};
            font-weight: bold;
            font-size: 11px;
        """)
        centro.addWidget(lbl_tit)

        resumo = item.get("resumo", "").strip()
        resumo_curto = (resumo[:130].rstrip() + "...") if len(resumo) > 130 else (resumo or "Sem descricao.")
        lbl_desc = QLabel(resumo_curto)
        lbl_desc.setWordWrap(True)
        lbl_desc.setStyleSheet(f"""
            color: {COR_TEXTO_MUTED};
            font-size: 10px;
        """)
        centro.addWidget(lbl_desc)
        layout.addLayout(centro, 1)

        # Direita: Etiqueta da fonte derivada do dominio
        etiqueta = extrair_etiqueta_fonte(item.get("link", ""))
        lbl_fonte = QLabel(etiqueta)
        lbl_fonte.setStyleSheet(f"""
            color: {COR_CIANO_BRILHO};
            background-color: rgba(0, 229, 255, 0.12);
            border: 1px solid {COR_BORDA};
            border-radius: 4px;
            padding: 2px 6px;
            font-family: {FONTE_MONO};
            font-size: 9px;
            font-weight: bold;
        """)
        lbl_fonte.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignRight)
        layout.addWidget(lbl_fonte)

        return card

    def _criar_aba_fontes(self) -> QWidget:
        """Monta a aba 'Fontes Orbitais' com lista de fontes e links clicaveis."""
        container = QWidget()
        layout = QVBoxLayout(container)
        layout.setContentsMargins(4, 4, 4, 4)

        area_scroll = QScrollArea()
        area_scroll.setWidgetResizable(True)
        area_scroll.setFrameShape(QFrame.Shape.NoFrame)
        area_scroll.setStyleSheet("background: transparent; border: none;")

        conteudo = QWidget()
        layout_lista = QVBoxLayout(conteudo)
        layout_lista.setContentsMargins(0, 4, 0, 0)
        layout_lista.setSpacing(8)

        if self._itens:
            for i, item in enumerate(self._itens, 1):
                item_fonte = QFrame()
                item_fonte.setStyleSheet(f"""
                    QFrame {{
                        background-color: rgba(11, 37, 53, 0.6);
                        border: 1px solid {COR_BORDA_SUAVE};
                        border-radius: 8px;
                    }}
                    QFrame:hover {{
                        border-color: {COR_CIANO};
                    }}
                """)
                layout_item = QVBoxLayout(item_fonte)
                layout_item.setContentsMargins(10, 8, 10, 8)
                layout_item.setSpacing(4)

                topo = QHBoxLayout()
                lbl_tit = QLabel(f"{i:02d}. {item.get('titulo', 'Fonte')}")
                lbl_tit.setWordWrap(True)
                lbl_tit.setStyleSheet(f"color: {COR_TEXTO_BRANCO}; font-weight: bold; font-size: 11px;")
                topo.addWidget(lbl_tit, 1)

                dominio = extrair_dominio(item.get("link", ""))
                lbl_dom = QLabel(dominio)
                lbl_dom.setStyleSheet(f"""
                    color: {COR_CIANO};
                    font-family: {FONTE_MONO};
                    font-size: 9px;
                """)
                topo.addWidget(lbl_dom)
                layout_item.addLayout(topo)

                link = item.get("link", "")
                lbl_link = QLabel(f'<a href="{link}" style="color: {COR_CIANO_BRILHO}; text-decoration: underline;">{link}</a>')
                lbl_link.setOpenExternalLinks(True)
                lbl_link.setTextFormat(Qt.TextFormat.RichText)
                lbl_link.setWordWrap(True)
                lbl_link.setStyleSheet(f"font-family: {FONTE_MONO}; font-size: 10px;")
                layout_item.addWidget(lbl_link)

                layout_lista.addWidget(item_fonte)
            layout_lista.addStretch(1)
        else:
            layout_lista.addWidget(self._criar_widget_vazio("Sem fontes orbitais identificadas."))

        area_scroll.setWidget(conteudo)
        layout.addWidget(area_scroll)
        return container

    def _criar_aba_cronograma(self) -> QWidget:
        """Monta a aba 'Cronograma' com identificacao de marcos temporais."""
        container = QWidget()
        layout = QVBoxLayout(container)
        layout.setContentsMargins(4, 4, 4, 4)

        marcos = extrair_marcos_temporais(self._resultado_bruto)

        area_scroll = QScrollArea()
        area_scroll.setWidgetResizable(True)
        area_scroll.setFrameShape(QFrame.Shape.NoFrame)
        area_scroll.setStyleSheet("background: transparent; border: none;")

        conteudo = QWidget()
        layout_lista = QVBoxLayout(conteudo)
        layout_lista.setContentsMargins(4, 6, 4, 6)
        layout_lista.setSpacing(10)

        if marcos:
            for marco in marcos:
                no = QFrame()
                no.setStyleSheet(f"""
                    QFrame {{
                        background-color: rgba(11, 37, 53, 0.5);
                        border-left: 2px solid {COR_CIANO};
                        border-radius: 4px;
                        padding: 2px;
                    }}
                """)
                layout_no = QHBoxLayout(no)
                layout_no.setContentsMargins(10, 6, 8, 6)
                layout_no.setSpacing(10)

                lbl_data = QLabel(marco["data"])
                lbl_data.setStyleSheet(f"""
                    color: {COR_CIANO};
                    background-color: rgba(0, 229, 255, 0.12);
                    border: 1px solid {COR_BORDA};
                    border-radius: 4px;
                    padding: 2px 6px;
                    font-family: {FONTE_MONO};
                    font-size: 10px;
                    font-weight: bold;
                """)
                layout_no.addWidget(lbl_data)

                lbl_desc = QLabel(marco["descricao"])
                lbl_desc.setWordWrap(True)
                lbl_desc.setStyleSheet(f"""
                    color: {COR_TEXTO};
                    font-size: 11px;
                """)
                layout_no.addWidget(lbl_desc, 1)

                layout_lista.addWidget(no)
            layout_lista.addStretch(1)
        else:
            layout_lista.addWidget(self._criar_widget_vazio("Sem marcos temporais identificados"))

        area_scroll.setWidget(conteudo)
        layout.addWidget(area_scroll)
        return container

    def _criar_widget_vazio(self, mensagem: str) -> QWidget:
        """Gera um estado vazio elegante e estilizado."""
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(12, 32, 12, 32)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.setSpacing(8)

        icone = QLabel("◈")
        icone.setStyleSheet(f"color: {COR_TEXTO_MUTED}; font-size: 20px;")
        icone.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(icone)

        texto = QLabel(mensagem)
        texto.setStyleSheet(f"""
            color: {COR_TEXTO_MUTED};
            font-family: {FONTE_MONO};
            font-size: 11px;
            font-weight: bold;
            letter-spacing: 1px;
        """)
        texto.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(texto)

        return widget

    def _ao_exportar_telemetria(self) -> Path:
        """Salva arquivo Markdown com dados da pesquisa na pasta dados/."""
        pasta = garantir_pasta_dados()
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        arquivo_md = pasta / f"pesquisa_{timestamp}.md"

        linhas = [
            "# Telemetria de Pesquisa Global // N.E.X.U.S.",
            "",
            f"- **Data/Hora:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
            f"- **Termo de Consulta:** {self._termo_busca}",
            f"- **Latencia Operacional:** {self._duracao:.2f}s",
            f"- **Total de Fontes Catalogadas:** {len(self._itens)}",
            "",
            "## Fontes Orbitais",
            "",
        ]

        if self._itens:
            for i, item in enumerate(self._itens, 1):
                linhas.append(f"### {i}. {item.get('titulo', 'Sem titulo')}")
                linhas.append(f"- **Etiqueta:** {extrair_etiqueta_fonte(item.get('link', ''))}")
                linhas.append(f"- **Dominio:** {extrair_dominio(item.get('link', ''))}")
                linhas.append(f"- **Link:** {item.get('link', '')}")
                linhas.append(f"- **Resumo:** {item.get('resumo', '')}")
                linhas.append("")
        else:
            linhas.append("*Nenhuma fonte orbital estruturada.*")
            linhas.append("")

        linhas.append("## Saida Bruta")
        linhas.append("```")
        linhas.append(self._resultado_bruto)
        linhas.append("```")
        linhas.append("")

        arquivo_md.write_text("\n".join(linhas), encoding="utf-8")

        # Feedback visual no botao de exportar
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
        """Restaura o visual padrao do botao de exportar telemetria."""
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
                color: {COR_FUNDO_SECUNDARIO};
            }}
        """)

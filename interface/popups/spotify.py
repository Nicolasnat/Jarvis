"""Popup especializado para integracao e reproducao no Spotify no N.E.X.U.S.

Processa as respostas reais de spotify.py e _spotify.py, exibindo cartao de
faixa/artista/playlist, barra de volume e controles de reproducao decorativos.
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
    QPushButton,
    QProgressBar,
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
    FONTE_MONO,
    FONTE_UI,
)
from interface.popup_base import PopupBase


def parse_spotify(texto: str) -> dict:
    """Extrai metadados estruturados (faixa, artista, playlist, volume, estado) do retorno."""
    dados = {
        "faixa": "",
        "artista": "",
        "playlist": "",
        "total_musicas": "",
        "volume": None,
        "estado": "",
        "outras_opcoes": "",
        "acao": "",
    }
    bruto = str(texto or "").strip()
    if not bruto:
        return dados

    # 1. Volume: 'Volume do Spotify em N por cento.'
    m_vol = re.search(r"Volume\s+do\s+Spotify\s+em\s+(\d+)\s+por\s+cento", bruto, re.IGNORECASE)
    if m_vol:
        dados["volume"] = int(m_vol.group(1))

    # 2. Outras opcoes: 'Outras opcoes: ...'
    m_outras = re.search(r"Outras\s+op[cç][oõ]es:\s*([^.]+)\.?", bruto, re.IGNORECASE)
    if m_outras:
        dados["outras_opcoes"] = m_outras.group(1).strip()

    # 3. Playlist: 'Tocando a playlist Nome (N musicas).'
    m_play = re.search(r"Tocando\s+a\s+playlist\s+([^(]+?)\s*\(([^)]+)\)", bruto, re.IGNORECASE)
    if m_play:
        dados["playlist"] = m_play.group(1).strip()
        dados["total_musicas"] = m_play.group(2).strip()
        dados["estado"] = "tocando"
        return dados

    # 4. Tocando faixa e artista: 'Tocando Faixa - Artista.'
    m_tocar = re.search(r"^Tocando\s+(.+?)\s*-\s*([^.]+?)(?:\.|\s+Outras|$)", bruto, re.IGNORECASE)
    if m_tocar:
        dados["faixa"] = m_tocar.group(1).strip()
        dados["artista"] = m_tocar.group(2).strip()
        dados["estado"] = "tocando"
        return dados

    # 5. Consulta 'tocando': 'Faixa - Artista (tocando/pausado).'
    m_status = re.search(r"^(.+?)\s*-\s*(.+?)\s*\((tocando|pausado)\)\.?$", bruto, re.IGNORECASE)
    if m_status:
        dados["faixa"] = m_status.group(1).strip()
        dados["artista"] = m_status.group(2).strip()
        dados["estado"] = m_status.group(3).lower()
        return dados

    # 6. Acoes pontuais
    for acao_rotulo, estado in [
        ("Pausado.", "pausado"),
        ("Voltando a tocar.", "tocando"),
        ("Proxima musica.", "avanco"),
        ("Musica anterior.", "retrocesso"),
    ]:
        if acao_rotulo.lower() in bruto.lower():
            dados["acao"] = acao_rotulo
            dados["estado"] = estado
            break

    return dados


class PopupSpotify(PopupBase):
    """Popup modal especializado na visualizacao de status e reproducao do Spotify."""

    def __init__(
        self,
        resultado: str = "",
        duracao: float = 0.0,
        parent=None,
    ):
        super().__init__(titulo="SPOTIFY", parent=parent)

        self._resultado = str(resultado or "").strip()
        self._duracao = float(duracao) if isinstance(duracao, (int, float)) else 0.0
        self._dados = parse_spotify(self._resultado)

        if self._dados["estado"] == "tocando":
            self.definir_contagem("REPRODUZINDO")
        elif self._dados["estado"] == "pausado":
            self.definir_contagem("PAUSADO")
        elif self._dados["volume"] is not None:
            self.definir_contagem(f"VOL: {self._dados['volume']}%")
        else:
            self.definir_contagem("SPOTIFY")

        self._montar_ui()
        self.exportar_telemetria_solicitado.connect(self._ao_exportar_telemetria)

    def _montar_ui(self) -> None:
        """Constroi o layout com o card de reproducao, controles e volume."""
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

        selo_txt = "CONEXÃO ATIVA // SPOTIFY WEB API" if self._resultado else "SPOTIFY OCIOSO"
        selo = QLabel(selo_txt)
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

        # Cartao central de reproducao
        cartao = QFrame()
        cartao.setStyleSheet(f"""
            QFrame {{
                background-color: rgba(7, 27, 38, 0.75);
                border: 1px solid {COR_BORDA_SUAVE};
                border-radius: 10px;
            }}
        """)
        layout_cartao = QVBoxLayout(cartao)
        layout_cartao.setContentsMargins(16, 14, 16, 14)
        layout_cartao.setSpacing(12)

        tem_midia = bool(self._dados["faixa"] or self._dados["playlist"] or self._dados["acao"])

        if tem_midia:
            # Cabecalho da midia
            topo_midia = QHBoxLayout()
            topo_midia.setSpacing(12)

            lbl_vinil = QLabel("🎧")
            lbl_vinil.setStyleSheet("font-size: 28px;")
            topo_midia.addWidget(lbl_vinil)

            info_midia = QVBoxLayout()
            info_midia.setSpacing(3)

            titulo_principal = self._dados["faixa"] or self._dados["playlist"] or self._dados["acao"]
            lbl_tit = QLabel(titulo_principal)
            lbl_tit.setWordWrap(True)
            lbl_tit.setStyleSheet(f"""
                color: {COR_TEXTO_BRANCO};
                font-family: {FONTE_UI};
                font-size: 13px;
                font-weight: bold;
            """)
            info_midia.addWidget(lbl_tit)

            subtitulo = ""
            if self._dados["artista"]:
                subtitulo = f"Artista: {self._dados['artista']}"
            elif self._dados["playlist"]:
                subtitulo = f"Playlist ({self._dados['total_musicas']})"
            elif self._dados["estado"]:
                subtitulo = f"Estado: {self._dados['estado'].upper()}"

            if subtitulo:
                lbl_sub = QLabel(subtitulo)
                lbl_sub.setStyleSheet(f"color: {COR_CIANO}; font-family: {FONTE_MONO}; font-size: 11px;")
                info_midia.addWidget(lbl_sub)

            topo_midia.addLayout(info_midia, 1)
            layout_cartao.addLayout(topo_midia)

            # Controles de reproducao visuais e decorativos
            layout_controles = QHBoxLayout()
            layout_controles.setAlignment(Qt.AlignmentFlag.AlignCenter)
            layout_controles.setSpacing(14)

            btn_ant = QPushButton("⏮")
            btn_ant.setFixedSize(36, 32)
            btn_ant.setToolTip("Faixa Anterior (Visual)")

            icone_play = "⏸" if self._dados["estado"] == "tocando" else "▶"
            btn_play = QPushButton(icone_play)
            btn_play.setFixedSize(44, 36)
            btn_play.setStyleSheet(f"""
                QPushButton {{
                    background-color: {COR_CIANO};
                    color: {COR_FUNDO_SUPERFICIE};
                    border: 1px solid {COR_CIANO_BRILHO};
                    border-radius: 18px;
                    font-size: 14px;
                    font-weight: bold;
                }}
            """)
            btn_play.setToolTip("Play/Pause (Visual)")

            btn_prox = QPushButton("⏭")
            btn_prox.setFixedSize(36, 32)
            btn_prox.setToolTip("Próxima Faixa (Visual)")

            layout_controles.addWidget(btn_ant)
            layout_controles.addWidget(btn_play)
            layout_controles.addWidget(btn_prox)
            layout_cartao.addLayout(layout_controles)

        # Barra de volume se informada
        if self._dados["volume"] is not None:
            bloco_vol = QVBoxLayout()
            bloco_vol.setSpacing(4)

            topo_vol = QHBoxLayout()
            lbl_vol_rot = QLabel("VOLUME DO SPOTIFY")
            lbl_vol_rot.setStyleSheet(f"color: {COR_TEXTO_MUTED}; font-family: {FONTE_MONO}; font-size: 10px; font-weight: bold;")
            topo_vol.addWidget(lbl_vol_rot)
            topo_vol.addStretch(1)
            lbl_vol_val = QLabel(f"{self._dados['volume']}%")
            lbl_vol_val.setStyleSheet(f"color: {COR_CIANO_BRILHO}; font-family: {FONTE_MONO}; font-size: 11px; font-weight: bold;")
            topo_vol.addWidget(lbl_vol_val)
            bloco_vol.addLayout(topo_vol)

            barra_vol = QProgressBar()
            barra_vol.setRange(0, 100)
            barra_vol.setValue(max(0, min(100, self._dados["volume"])))
            barra_vol.setTextVisible(False)
            barra_vol.setFixedHeight(8)
            barra_vol.setStyleSheet(f"""
                QProgressBar {{
                    background-color: rgba(11, 37, 53, 0.9);
                    border: 1px solid {COR_BORDA_SUAVE};
                    border-radius: 4px;
                }}
                QProgressBar::chunk {{
                    background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 {COR_CIANO_ESCURO}, stop:1 {COR_CIANO});
                    border-radius: 3px;
                }}
            """)
            bloco_vol.addWidget(barra_vol)
            layout_cartao.addLayout(bloco_vol)

        # Outras opcoes de busca, se houver
        if self._dados["outras_opcoes"]:
            lbl_outras_tit = QLabel("Outras opções:")
            lbl_outras_tit.setStyleSheet(f"color: {COR_TEXTO_MUTED}; font-family: {FONTE_MONO}; font-size: 10px; font-weight: bold;")
            layout_cartao.addWidget(lbl_outras_tit)

            lbl_outras = QLabel(self._dados["outras_opcoes"])
            lbl_outras.setWordWrap(True)
            lbl_outras.setStyleSheet(f"color: {COR_TEXTO}; font-family: {FONTE_MONO}; font-size: 10px;")
            layout_cartao.addWidget(lbl_outras)

        # Se nao for midia estruturada, exibe o texto real diretamente
        if not tem_midia and self._dados["volume"] is None:
            lbl_texto = QLabel(self._resultado or "Nenhum retorno do Spotify.")
            lbl_texto.setWordWrap(True)
            lbl_texto.setStyleSheet(f"""
                color: {COR_TEXTO};
                font-family: {FONTE_MONO};
                font-size: 11px;
                line-height: 1.4;
            """)
            layout_cartao.addWidget(lbl_texto)

        layout_raiz.addWidget(cartao, 1)
        self.adicionar_aba("Player", conteudo)

    def _ao_exportar_telemetria(self) -> Path:
        """Salva a telemetria do player Spotify em arquivo Markdown."""
        pasta = garantir_pasta_dados()
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        arquivo_md = pasta / f"spotify_{ts}.md"

        linhas = [
            "# Telemetria do Spotify // N.E.X.U.S.",
            "",
            f"- **Data/Hora:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
            f"- **Faixa:** {self._dados['faixa'] or 'N/A'}",
            f"- **Artista:** {self._dados['artista'] or 'N/A'}",
            f"- **Playlist:** {self._dados['playlist'] or 'N/A'}",
            f"- **Estado:** {self._dados['estado'] or 'N/A'}",
            f"- **Volume:** {self._dados['volume']}%" if self._dados['volume'] is not None else "- **Volume:** N/A",
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

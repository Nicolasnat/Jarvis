"""Tokens visuais e folha de estilos (QSS) para a interface do N.E.X.U.S.

Define a paleta cibernetica com azul-petroleo, ciano e tipografia monoespacada.
Todos os comentarios e docstrings neste modulo usam exclusivamente ASCII.
"""

# Cores fundamentais (paleta escura com azul-petroleo e ciano)
COR_FUNDO = "#04121a"
COR_FUNDO_SECUNDARIO = "#071b26"
COR_FUNDO_SUPERFICIE = "#0b2535"
COR_FUNDO_TRANSLUCIDO = "rgba(4, 18, 26, 235)"

# Cores de destaque e acento
COR_CIANO = "#00e5ff"
COR_CIANO_BRILHO = "#80f3ff"
COR_CIANO_ESCURO = "#00838f"
COR_CIANO_TRANSPARENTE = "rgba(0, 229, 255, 0.15)"
COR_CIANO_SUAVE = "rgba(0, 229, 255, 0.08)"

# Bordas e estados
COR_BORDA = "rgba(0, 229, 255, 0.35)"
COR_BORDA_FOCO = "#00e5ff"
COR_BORDA_SUAVE = "rgba(0, 229, 255, 0.18)"

# Estados do sistema
COR_SUCESSO = "#00e676"
COR_ALERTA = "#ffab00"
COR_PERIGO = "#ff5252"

# Tipografia
COR_TEXTO = "#e0f7fa"
COR_TEXTO_MUTED = "#546e7a"
COR_TEXTO_BRANCO = "#ffffff"

FONTE_MONO = "Consolas, 'DejaVu Sans Mono', 'Fira Code', 'Roboto Mono', monospace"
FONTE_UI = "'Segoe UI', 'Ubuntu', 'Cantarell', 'DejaVu Sans', sans-serif"


def obter_stylesheet() -> str:
    """Retorna a folha de estilos global (QSS) com cantos arredondados."""
    return f"""
    QWidget {{
        background-color: transparent;
        color: {COR_TEXTO};
        font-family: {FONTE_UI};
        font-size: 13px;
        selection-background-color: {COR_CIANO_ESCURO};
        selection-color: {COR_TEXTO_BRANCO};
    }}

    /* Paineis e cartoes arredondados */
    QFrame#cartao_principal, QFrame[classe="cartao"] {{
        background-color: {COR_FUNDO_SECUNDARIO};
        border: 1px solid {COR_BORDA};
        border-radius: 14px;
    }}

    /* Barra de comando e campos de texto */
    QLineEdit {{
        background-color: {COR_FUNDO_SUPERFICIE};
        border: 1px solid {COR_BORDA_SUAVE};
        border-radius: 18px;
        padding: 6px 14px;
        color: {COR_TEXTO_BRANCO};
        font-family: {FONTE_MONO};
        font-size: 13px;
    }}

    QLineEdit:focus {{
        border: 1px solid {COR_BORDA_FOCO};
        background-color: {COR_FUNDO_SECUNDARIO};
    }}

    QLineEdit::placeholder {{
        color: {COR_TEXTO_MUTED};
    }}

    /* Botoes padrao */
    QPushButton {{
        background-color: {COR_CIANO_TRANSPARENTE};
        border: 1px solid {COR_BORDA};
        border-radius: 14px;
        color: {COR_CIANO};
        font-family: {FONTE_MONO};
        font-weight: bold;
        padding: 6px 14px;
        outline: none;
    }}

    QPushButton:hover {{
        background-color: {COR_CIANO};
        color: {COR_FUNDO};
        border: 1px solid {COR_CIANO_BRILHO};
    }}

    QPushButton:pressed {{
        background-color: {COR_CIANO_ESCURO};
        color: {COR_TEXTO_BRANCO};
    }}

    QPushButton:disabled {{
        background-color: transparent;
        border: 1px solid {COR_TEXTO_MUTED};
        color: {COR_TEXTO_MUTED};
    }}

    /* Barras de rolagem discretas */
    QScrollBar:vertical {{
        border: none;
        background: {COR_FUNDO};
        width: 6px;
        margin: 0px;
        border-radius: 3px;
    }}

    QScrollBar::handle:vertical {{
        background: {COR_CIANO_ESCURO};
        min-height: 20px;
        border-radius: 3px;
    }}

    QScrollBar::handle:vertical:hover {{
        background: {COR_CIANO};
    }}

    QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
        height: 0px;
    }}

    /* Tooltips no estilo HUD */
    QToolTip {{
        background-color: {COR_FUNDO_SECUNDARIO};
        color: {COR_CIANO};
        border: 1px solid {COR_BORDA};
        padding: 4px 8px;
        border-radius: 4px;
        font-family: {FONTE_MONO};
    }}
    """

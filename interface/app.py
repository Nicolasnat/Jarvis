"""Ponto de entrada do subsistema de interface grafica do N.E.X.U.S.

Inicializa o QApplication, a JanelaPrincipal e orquestra a conexao dos sinais da
Ponte com os widgets de apresentacao visual.
Todos os comentarios e docstrings neste modulo usam exclusivamente ASCII.
"""
import os
import sys


class JaEmExecucao(RuntimeError):
    """Sinaliza que ja existe uma instancia da interface em execucao."""


def _caminho_trava() -> str:
    """Caminho do arquivo de trava de instancia unica (em dados/)."""
    raiz = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    pasta = os.path.join(raiz, "dados")
    try:
        os.makedirs(pasta, exist_ok=True)
    except OSError:
        pasta = os.path.join(raiz)
    return os.path.join(pasta, "nexus_interface.lock")


def disponivel() -> bool:
    """Verifica se o ambiente suporta execucao de interface grafica."""
    try:
        import PySide6  # noqa: F401
    except ImportError:
        return False

    # Permite execucao offscreen para testes automatizados
    if os.environ.get("QT_QPA_PLATFORM") == "offscreen":
        return True

    # Verifica se existe um servidor de exibicao grafico ativo (X11 ou Wayland)
    tem_display = bool(os.environ.get("DISPLAY") or os.environ.get("WAYLAND_DISPLAY"))
    if not tem_display:
        return False
    return _plugin_qt_carrega()


def _plugin_qt_carrega() -> bool:
    """Testa num subprocesso se o plugin Qt consegue inicializar.

    Falhas de plugin (ex. libxcb-cursor ausente) encerram o processo com abort,
    o que nao da para capturar aqui; por isso a checagem roda isolada.
    """
    import subprocess

    codigo = "from PySide6.QtWidgets import QApplication; QApplication([])"
    try:
        processo = subprocess.run(
            [sys.executable, "-c", codigo],
            capture_output=True,
            timeout=20,
        )
    except (OSError, subprocess.SubprocessError):
        return False
    return processo.returncode == 0


class ControladorInterface:
    """Controlador que encapsula a aplicacao e a janela principal."""

    def __init__(self, app, janela, ponte=None, gerenciador=None):
        self.app = app
        self.janela = janela
        self.ponte = ponte
        self.gerenciador = gerenciador

    @property
    def popup_confirmacao(self):
        """Retorna o popup de confirmacao ativo, se houver."""
        return getattr(self.janela, "_popup_confirmacao_ativo", None)

    def executar(self) -> int:
        """Inicia o loop de eventos principal do Qt."""
        return self.app.exec()


def iniciar_interface(ponte=None) -> ControladorInterface:
    """Inicializa a aplicacao Qt, cria a janela e conecta os sinais da ponte.

    Levanta RuntimeError caso nao haja servidor grafico disponivel.
    """
    if not disponivel():
        raise RuntimeError(
            "Ambiente grafico indisponivel (DISPLAY/WAYLAND ausente ou PySide6 nao encontrado)."
        )

    from PySide6.QtCore import QLockFile, QTimer
    from PySide6.QtWidgets import QApplication
    from interface.estilo import obter_stylesheet
    from interface.janela_principal import JanelaPrincipal
    from interface.popups.gerenciador import GerenciadorPopups
    from interface.popups.confirmacao import PopupConfirmacao

    trava = QLockFile(_caminho_trava())
    if not trava.tryLock(100):
        raise JaEmExecucao(
            "Ja existe uma instancia do N.E.X.U.S. com interface em execucao."
        )

    app = QApplication.instance()
    if app is None:
        app = QApplication(sys.argv)
        app.setStyleSheet(obter_stylesheet())
    app._trava_interface = trava

    janela = JanelaPrincipal()
    gerenciador = GerenciadorPopups(janela)
    janela.gerenciador = gerenciador

    tempos_inicio = {}
    termos_busca = {}

    if ponte is not None:
        # Conecta eventos da ponte aos widgets da janela
        ponte.estado_mudou.connect(janela.definir_estado)
        ponte.fala_nivel.connect(janela.orbe.set_nivel)
        janela.comando_digitado.connect(ponte.emitir_comando)
        janela.mic_pressionado.connect(ponte.mic_clicado.emit)
        ponte.wakeword.connect(janela.mostrar_ou_trazer)

        def _ao_iniciar_ferramenta(nome: str, argumentos: dict) -> None:
            janela.definir_estado("executando")
            import time
            tempos_inicio[nome] = time.time()
            if isinstance(argumentos, dict) and "busca" in argumentos:
                termos_busca[nome] = str(argumentos.get("busca", ""))

        def _ao_concluir_ferramenta(nome: str, resultado: str) -> None:
            import time
            inicio = tempos_inicio.pop(nome, None)
            duracao = max(0.0, time.time() - inicio) if inicio is not None else 0.0
            termo = termos_busca.pop(nome, "")

            def _abrir() -> None:
                gerenciador.abrir_popup(
                    nome=nome,
                    resultado=resultado,
                    duracao=duracao,
                    termo_busca=termo,
                )

            QTimer.singleShot(0, _abrir)

        ponte.ferramenta_iniciada.connect(_ao_iniciar_ferramenta)
        ponte.ferramenta_concluida.connect(_ao_concluir_ferramenta)

        # Gerenciamento de confirmacao de seguranca
        popup_confirmacao_ativo = None

        def _fechar_popup_confirmacao_ativo() -> None:
            nonlocal popup_confirmacao_ativo
            if popup_confirmacao_ativo is not None:
                popup = popup_confirmacao_ativo
                popup_confirmacao_ativo = None
                janela._popup_confirmacao_ativo = None
                try:
                    popup._ja_respondeu = True
                    popup.fechar()
                except Exception:
                    pass

        def _ao_pedir_confirmacao(comandos: list) -> None:
            nonlocal popup_confirmacao_ativo
            janela.mostrar_ou_trazer()
            if gerenciador is not None:
                gerenciador.fechar_popup_ativo()

            if popup_confirmacao_ativo is not None:
                try:
                    popup_confirmacao_ativo.fechar()
                except Exception:
                    pass
                popup_confirmacao_ativo = None

            popup = PopupConfirmacao(comandos, parent=janela)
            popup_confirmacao_ativo = popup
            janela._popup_confirmacao_ativo = popup
            popup.respondida.connect(ponte.responder_confirmacao)

            def _ao_fechar() -> None:
                nonlocal popup_confirmacao_ativo
                if popup_confirmacao_ativo is popup:
                    popup_confirmacao_ativo = None
                if getattr(janela, "_popup_confirmacao_ativo", None) is popup:
                    janela._popup_confirmacao_ativo = None

            popup.fechado.connect(_ao_fechar)

            if not janela.isVisible():
                janela.show()
            popup.resize(janela.size())
            popup.move(0, 0)
            popup.abrir()

        def _ao_confirmacao_respondida(_aprovado: bool = False) -> None:
            _fechar_popup_confirmacao_ativo()

        ponte.pedir_confirmacao.connect(_ao_pedir_confirmacao)
        ponte.confirmacao_respondida.connect(_ao_confirmacao_respondida)

    janela.mostrar_ou_trazer()

    return ControladorInterface(app, janela, ponte, gerenciador)

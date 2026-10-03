"""Voz do Jarvis: wakeword, transcricao e fala. Tudo local (offline).

A captura de audio usa o binario 'arecord' (alsa-utils), evitando depender de
PortAudio/sounddevice. O wakeword usa openwakeword (modelo 'hey_jarvis') e a
transcricao usa faster-whisper. A fala tenta espeak-ng, espeak e spd-say.
"""
import shutil
import subprocess
import tempfile
import warnings
from pathlib import Path

TAXA = 16000
MODELO_WHISPER = "small"
LIMITE_WAKEWORD = 0.5
DURACAO_FALA = 6.0

_modelo_wake = None
_modelo_fala = None


def _faltando():
    faltas = []
    if shutil.which("arecord") is None:
        faltas.append("arecord (alsa-utils)")
    try:
        import openwakeword  # noqa: F401
    except Exception:
        faltas.append("openwakeword (pip)")
    try:
        import faster_whisper  # noqa: F401
    except Exception:
        faltas.append("faster-whisper (pip)")
    return faltas


def disponivel() -> bool:
    return not _faltando()


def mensagem_indisponivel() -> str:
    faltas = _faltando()
    if not faltas:
        return ""
    return "Voz indisponivel. Falta: " + ", ".join(faltas) + "."


def _comando_fala():
    if shutil.which("espeak-ng"):
        return ["espeak-ng", "-v", "pt-br", "-s", "165"]
    if shutil.which("espeak"):
        return ["espeak", "-v", "pt-br", "-s", "165"]
    if shutil.which("spd-say"):
        return ["spd-say", "-l", "pt-BR", "-w"]
    return None


def falar(texto: str):
    texto = (texto or "").strip()
    if not texto:
        return
    comando = _comando_fala()
    if comando is None:
        print("[voz] Nenhum sintetizador encontrado (instale espeak-ng).")
        return
    try:
        subprocess.run(
            comando + [texto],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=120,
        )
    except (OSError, subprocess.SubprocessError) as erro:
        print(f"[voz] Falha ao falar: {erro}")


def _carregar_wake():
    global _modelo_wake
    if _modelo_wake is None:
        import openwakeword
        caminhos = [p for p in openwakeword.get_pretrained_model_paths() if "hey_jarvis" in p]
        if not caminhos:
            raise RuntimeError("modelo 'hey_jarvis' nao encontrado no openwakeword")
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            _modelo_wake = openwakeword.Model(wakeword_model_paths=caminhos)
    return _modelo_wake


def _abrir_microfone():
    return subprocess.Popen(
        ["arecord", "-q", "-f", "S16_LE", "-r", str(TAXA), "-c", "1", "-t", "raw"],
        stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
    )


def escutar_wakeword(parar=None) -> bool:
    """Bloqueia ouvindo ate detectar 'Jarvis'. Devolve True ao detectar."""
    import numpy as np

    modelo = _carregar_wake()
    processo = _abrir_microfone()
    try:
        while True:
            if parar is not None and parar():
                return False
            dados = processo.stdout.read(1280 * 2)  # ~80 ms de audio
            if not dados:
                return False
            amostras = np.frombuffer(dados, dtype=np.int16)
            scores = modelo.predict(amostras)
            if max(scores.values(), default=0.0) >= LIMITE_WAKEWORD:
                return True
    finally:
        processo.terminate()
        try:
            processo.wait(timeout=3)
        except subprocess.TimeoutExpired:
            processo.kill()


def _carregar_fala():
    global _modelo_fala
    if _modelo_fala is None:
        from faster_whisper import WhisperModel
        _modelo_fala = WhisperModel(MODELO_WHISPER, device="cpu", compute_type="int8")
    return _modelo_fala


def transcrever(segundos=DURACAO_FALA) -> str:
    arquivo = Path(tempfile.gettempdir()) / "jarvis_voz.wav"
    try:
        subprocess.run(
            ["arecord", "-q", "-f", "S16_LE", "-r", str(TAXA), "-c", "1",
             "-d", str(int(segundos)), str(arquivo)],
            check=True, timeout=segundos + 15,
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        )
    except (OSError, subprocess.SubprocessError) as erro:
        print(f"[voz] Falha ao gravar: {erro}")
        return ""
    modelo = _carregar_fala()
    segmentos, _ = modelo.transcribe(str(arquivo), language="pt", beam_size=5)
    return " ".join(seg.text.strip() for seg in segmentos).strip()

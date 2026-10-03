"""Voz do Jarvis: wakeword, transcricao e fala. Tudo local (offline).

A captura de audio usa o binario 'arecord' (alsa-utils), evitando depender de
PortAudio/sounddevice. O wakeword usa openwakeword (modelo 'hey_jarvis') e a
transcricao usa faster-whisper. A fala usa Piper (voz neural pt-BR); se ele nao
estiver disponivel, cai para espeak-ng/espeak/spd-say.
"""
import ctypes
import gc
import re
import shutil
import subprocess
import tempfile
import threading
import warnings
import wave
from pathlib import Path

from comum import PASTA_DADOS

TAXA = 16000
MODELO_WHISPER = "small"
LIMITE_WAKEWORD = 0.5
DURACAO_FALA = 6.0
IDIOMA_ESPEAK = "pt-br"
IDIOMA_SPD = "pt-BR"
VOZ_SPD = "Portuguese (Brazil)"

PASTA_VOZES = PASTA_DADOS / "voz"
MODELO_PIPER = "pt_BR-faber-medium"

_modelo_wake = None
_modelo_fala = None
_voz_piper = None
_piper_avisado = False
_lock_fala = threading.Lock()

# Descarga agressiva: mantem em RAM apenas o wakeword (que precisa ficar sempre
# ouvindo). Whisper e Piper sao liberados depois de cada uso para o servico em
# segundo plano ficar leve.
LIBERAR_APOS_FALAR = True
LIBERAR_APOS_TRANSCREVER = True

try:
    _libc = ctypes.CDLL("libc.so.6")
except Exception:
    _libc = None


def _devolver_ram():
    gc.collect()
    if _libc is not None:
        try:
            _libc.malloc_trim(0)
        except Exception:
            pass


def descarregar(fala=True, piper=True):
    """Libera os modelos pesados e devolve a RAM ao sistema."""
    global _modelo_fala, _voz_piper
    if fala:
        _modelo_fala = None
    if piper:
        _voz_piper = None
    _devolver_ram()


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
        return ["espeak-ng", "-v", IDIOMA_ESPEAK, "-s", "165"]
    if shutil.which("espeak"):
        return ["espeak", "-v", IDIOMA_ESPEAK, "-s", "165"]
    if shutil.which("spd-say"):
        return ["spd-say", "-l", IDIOMA_SPD, "-y", VOZ_SPD, "-w"]
    return None


def _carregar_piper():
    global _voz_piper, _piper_avisado
    if _voz_piper is not None:
        return _voz_piper
    caminho = PASTA_VOZES / f"{MODELO_PIPER}.onnx"
    if not caminho.exists():
        if not _piper_avisado:
            print(f"[voz] Voz natural nao encontrada em {caminho}.")
            print("[voz] Baixe com: "
                  f"./venv/bin/python -m piper.download_voices {MODELO_PIPER} "
                  f"--download-dir {PASTA_VOZES}")
            _piper_avisado = True
        return None
    try:
        from piper import PiperVoice
        _voz_piper = PiperVoice.load(str(caminho))
    except Exception as erro:
        print(f"[voz] Piper indisponivel ({erro}); usando espeak.")
        return None
    return _voz_piper


def _tocar(arquivo) -> bool:
    for nome, comando in (("paplay", ["paplay"]), ("pw-play", ["pw-play"]), ("aplay", ["aplay", "-q"])):
        if shutil.which(nome):
            subprocess.run(
                comando + [str(arquivo)],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=180,
            )
            return True
    return False


def _limpar_para_fala(texto: str) -> str:
    texto = re.sub(r"```.*?```", " (bloco de codigo) ", texto, flags=re.S)
    texto = re.sub(r"`([^`]*)`", r"\1", texto)
    texto = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", texto)
    texto = re.sub(r"https?://\S+", "link", texto)
    texto = re.sub(r"[*_#>~]+", "", texto)
    return " ".join(texto.split()).strip()


def falar(texto: str):
    texto = _limpar_para_fala(texto or "")
    if not texto:
        return
    with _lock_fala:
        voz = _carregar_piper()
        if voz is not None:
            try:
                arquivo = Path(tempfile.gettempdir()) / "jarvis_fala.wav"
                with wave.open(str(arquivo), "wb") as wav:
                    voz.synthesize_wav(texto, wav)
                if LIBERAR_APOS_FALAR:
                    descarregar(fala=False, piper=True)
                if _tocar(arquivo):
                    return
            except Exception as erro:
                print(f"[voz] Piper falhou ({erro}); usando espeak.")
        comando = _comando_fala()
        if comando is None:
            print("[voz] Nenhum sintetizador encontrado (instale espeak-ng ou piper-tts).")
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
    texto = " ".join(seg.text.strip() for seg in segmentos).strip()
    if LIBERAR_APOS_TRANSCREVER:
        descarregar(fala=True, piper=False)
    return texto

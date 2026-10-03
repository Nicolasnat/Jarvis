"""Voz do Jarvis: wakeword, transcricao e fala. Tudo local (offline).

A captura de audio usa o binario 'arecord' (alsa-utils), evitando depender de
PortAudio/sounddevice. O wakeword usa openwakeword (modelo 'hey_jarvis') e a
transcricao usa faster-whisper. A fala usa Piper (voz neural pt-BR); se ele nao
estiver disponivel, cai para espeak-ng/espeak/spd-say.
"""
import contextlib
import ctypes
import gc
import math
import re
import shutil
import subprocess
import tempfile
import threading
import time
import warnings
import wave
from pathlib import Path

from comum import PASTA_CONFIG, PASTA_DADOS, ler_json, salvar_json

TAXA = 16000
MODELO_WHISPER = "small"
# O 'hey_jarvis_v0.1' para em ~0.46 falando "Jarvis" e fica em ~0.01 no ruido
# de fundo. Com 0.25 a separacao continua grande (25x) e a deteccao para de
# depender de o usuario estar com a boca perto do microfone.
LIMITE_WAKEWORD = 0.25
LIMITE_ESPECIAL = 29360   # ~90% de 32767, evita sinal estourado
ALVO_RMS = 0.07           # nivel em que o modelo responde bem
GANHO_MAXIMO = 20.0       # teto do amplificador de software
RMS_MINIMO = 0.0008       # abaixo disso e silencio: nao compensa o ganho
DURACAO_FALA = 6.0

# O que o Jarvis diz assim que acorda. TEMPO_AVISO e o quanto o microfone fica
# sem escutar antes de comecar a considerar que voce falou, para o aviso nao
# virar transcricao.
AVISO = "Pois nao?"
TEMPO_AVISO = 0.9

# Para de gravar 0.8s depois de voce parar de falar, em vez de esperar os 6s.
ESPERA_SILENCIO = 0.8
IDIOMA_ESPEAK = "pt-br"
IDIOMA_SPD = "pt-BR"
VOZ_SPD = "Portuguese (Brazil)"

PASTA_VOZES = PASTA_DADOS / "voz"

# A voz fica em config/voz.json para nao exigir editar codigo. Veja
# 'python -m ferramentas.trocar_voz --listar' para as opcoes em portugues.
ARQUIVO_VOZ = PASTA_CONFIG / "voz.json"
VOZES_PADRAO = {
    "modelo": "pt_BR-faber-medium",
    "velocidade": 1.0,   # acima de 1 fala mais rapido
    "profundidade": 1.0,  # acima de 1 deixa mais dramatico
}


def carregar_config_voz() -> dict:
    config = dict(VOZES_PADRAO)
    config.update(ler_json(ARQUIVO_VOZ, {}) or {})
    return config


def salvar_config_voz(config: dict) -> None:
    salvar_json(ARQUIVO_VOZ, config)


CONFIG_VOZ = carregar_config_voz()
MODELO_PIPER = CONFIG_VOZ["modelo"]
VELOCIDADE_FALA = CONFIG_VOZ["velocidade"]
PROFUNDIDADE_FALA = CONFIG_VOZ["profundidade"]

_modelo_wake = None
_modelo_fala = None
_ultimo_uso_fala = 0.0
_voz_piper = None
_piper_avisado = False
_lock_fala = threading.Lock()

# Descarga agressiva: mantem em RAM apenas o wakeword (que precisa ficar sempre
# ouvindo). Whisper e Piper sao liberados depois de cada uso para o servico em
# segundo plano ficar leve.
LIBERAR_APOS_FALAR = True
LIBERAR_APOS_TRANSCREVER = True

# O Piper e pequeno (134 MB) e o servico vive ligado: recarregar o modelo a cada
# frase custava ~1s de silencio antes da resposta. Como o usuario ouve a resposta
# imediatamente, esse tempo e todo atraso perceptivel.
LIBERAR_PIPER_APOS_FALAR = False

# Tempo de silencio antes de devolver os 627 MB do Whisper para o sistema.
OCIOS_LIBERAR_FALA_SEGUNDOS = 180

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


def _config_sintese():
    """Ajustes de timbre e velocidade do piper.

    Estes campos NAO sao argumentos de synthesize_wav(): vao num
    SynthesisConfig. Passar direto levanta TypeError e, como o espeak-ng nao
    esta instalado aqui, o Jarvis fica mudo em silencio.
    """
    from piper.config import SynthesisConfig

    return SynthesisConfig(
        length_scale=1.0 / max(0.1, VELOCIDADE_FALA),
        noise_scale=0.667 * PROFUNDIDADE_FALA,
        noise_w_scale=0.8 * PROFUNDIDADE_FALA,
    )


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
                    voz.synthesize_wav(texto, wav, syn_config=_config_sintese())
                if LIBERAR_PIPER_APOS_FALAR:
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


def _nivelar(amostras, ganho):
    """Aplica um ganho em software, segurando o pico para nao estourar.

    O 'hey_jarvis_v0.1' so responde bem com o audio em um nivel especifico: se o
    ganho do microfone vem de fabrica no maximo o sinal estoura (e o modelo
    nao reconhece nada) e se vem baixo demais o modelo nao chega no limiar.
    Normalizar aqui deixa a deteccao independente do hardware.
    """
    import numpy as np

    ajustado = amostras.astype(np.float32) * ganho
    pico = float(np.abs(ajustado).max()) if ajustado.size else 0.0
    if pico > LIMITE_ESPECIAL:
        ajustado *= LIMITE_ESPECIAL / pico
    return ajustado.astype(np.int16)


def _ganho_para(rms):
    """Ganho de software que leva um trecho ao nivel que o modelo espera."""
    if rms <= 0:
        return 1.0
    return min(ALVO_RMS / rms, GANHO_MAXIMO)


def escutar_wakeword(parar=None) -> bool:
    """Bloqueia ouvindo ate detectar 'Jarvis'. Devolve True ao detectar."""
    import numpy as np

    modelo = _carregar_wake()
    processo = _abrir_microfone()
    ganho = 1.0
    try:
        while True:
            if parar is not None and parar():
                return False
            dados = processo.stdout.read(1280 * 2)  # ~80 ms de audio
            if not dados:
                return False
            amostras = np.frombuffer(dados, dtype=np.int16)
            rms = float(np.sqrt((amostras.astype(np.float32) / 32768.0).__pow__(2).mean()))
            if rms >= RMS_MINIMO:
                ganho = _ganho_para(rms)
            scores = modelo.predict(_nivelar(amostras, ganho))
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
        # 6 threads: mediram-se 3.09s com 1 thread e 1.69s com 12, sempre com o
        # mesmo texto. Nao vamos ate 12 porque o openwakeword precisa de CPU
        # para continuar ouvindo 'Jarvis' durante a transcricao.
        _modelo_fala = WhisperModel(
            MODELO_WHISPER, device="cpu", compute_type="int8", cpu_threads=6,
        )
    return _modelo_fala


def _rms(bloco: bytes) -> float:
    """Nivel de audio de um bloco PCM 16 bits, na mesma escala do wakeword."""
    if len(bloco) < 2:
        return 0.0
    amostras = memoryview(bloco).cast("h")
    return math.sqrt(sum(a * a for a in amostras) / len(amostras)) / 32768.0


def gravar_ate_silencio(destino: Path, segundos=DURACAO_FALA, espera_silencio=0.8,
                         atencao_inicial=0.0, limiar=RMS_MINIMO * 6):
    """Grava e PARA SOZINHO quando o usuario termina de falar.

    Antes isso gravava os 6 segundos inteiros, faltando 1s e ainda esperando 5s
    de silencio. Parar no fim da fala economiza quase 4s em cada comando.

    espera_silencio: quantos segundos de silencio encerram a gravacao.
    atencao_inicial: periodo ignorado, para o microfone nao pegar a resposta
    'Pois nao?' que o Jarvis esta falando ao mesmo tempo.
    """
    proc = subprocess.Popen(
        ["arecord", "-q", "-f", "S16_LE", "-r", str(TAXA), "-c", "1", "-t", "raw"],
        stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
    )
    amostras = bytearray()
    bytesegs = TAXA * 2
    passo = bytesegs // 10  # 100 ms
    falando = False
    silencio = 0.0
    decorrido = 0.0

    try:
        with contextlib.closing(proc.stdout) as fluxo:
            while True:
                bloco = fluxo.read(passo)
                if not bloco:
                    break
                amostras += bloco
                decorrido += len(bloco) / bytesegs

                if decorrido < atencao_inicial:
                    continue

                if _rms(bloco) > limiar:
                    falando = True
                    silencio = 0.0
                elif falando:
                    silencio += len(bloco) / bytesegs
                    if silencio >= espera_silencio:
                        break

                if decorrido >= segundos:
                    break
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=3)
        except subprocess.TimeoutExpired:
            proc.kill()

    with wave.open(str(destino), "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(TAXA)
        wav.writeframes(bytes(amostras))
    return destino, falando


def transcrever(segundos=DURACAO_FALA, espera_silencio=0.8, atencao_inicial=0.0) -> str:
    global _ultimo_uso_fala
    pasta = tempfile.mkdtemp()
    arquivo = Path(pasta) / "jarvis_voz.wav"
    try:
        destino, falando = gravar_ate_silencio(
            arquivo, segundos=segundos,
            espera_silencio=espera_silencio, atencao_inicial=atencao_inicial,
        )
        if not falando:
            return ""

        modelo = _carregar_fala()
        # beam_size=5 (o padrao) mediu o mesmo tempo do greedy, entao nao vale
        # trocar por velocidade. condition_on_previous_text=False evita a
        # repeticao inventada que aparecia quando o audio era silencio.
        segmentos, _ = modelo.transcribe(
            str(destino), language="pt", beam_size=5,
            condition_on_previous_text=False,
        )
        texto = " ".join(seg.text.strip() for seg in segmentos).strip()
        _ultimo_uso_fala = time.time()
        return texto
    except Exception as erro:  # noqa: BLE001 - falha de audio vira texto vazio
        print(f"[voz] Falha ao transcrever: {erro}")
        return ""
    finally:
        try:
            arquivo.unlink(missing_ok=True)
            Path(pasta).rmdir()
        except OSError:
            pass


def transcrever_arquivo(destino: Path) -> str:
    global _ultimo_uso_fala
    try:
        if not destino.exists() or destino.stat().st_size == 0:
            return ""
        modelo = _carregar_fala()
        # beam_size=5 (o padrao) mediu o mesmo tempo do greedy, entao nao vale
        # trocar por velocidade. condition_on_previous_text=False evita a
        # repeticao inventada que aparecia quando o audio era silencio.
        segmentos, _ = modelo.transcribe(
            str(destino), language="pt", beam_size=5,
            condition_on_previous_text=False,
        )
        texto = " ".join(seg.text.strip() for seg in segmentos).strip()
        _ultimo_uso_fala = time.time()
        return texto
    except Exception as erro:  # noqa: BLE001 - falha de audio vira texto vazio
        print(f"[voz] Falha ao transcrever: {erro}")
        return ""
    finally:
        try:
            destino.unlink(missing_ok=True)
            destino.parent.rmdir()
        except OSError:
            pass


def comecar_a_gravar(segundos=DURACAO_FALA, espera_silencio=0.8, atencao_inicial=0.0):
    """Comeca a gravar em segundo plano, para o Jarvis falar enquanto ouve.

    O microfone ja esta pegando quando o 'Pois nao?' comeca, entao o usuario
    pode responder na mesma frase e nada do que ele diz se perde. Por isso
    atencao_inicial: o proprio aviso do Jarvis nao pode contar como fala.
    """
    pasta = tempfile.mkdtemp()
    arquivo = Path(pasta) / "jarvis_voz.wav"

    def trabalho():
        try:
            gravar_ate_silencio(arquivo, segundos, espera_silencio, atencao_inicial)
        except Exception as erro:  # noqa: BLE001
            print(f"[voz] Falha ao gravar: {erro}")

    return arquivo, threading.Thread(target=trabalho, daemon=True)


def limpar_ocios():
    """Devolve a RAM do Whisper quando o usuario para de falar.

    Recarregar o modelo custava ~0.8s no comeco de cada frase, que e atraso
    puro na resposta. Mas o Whisper sao 627 MB, entao nao da pra deixar sempre
    carregado. Ele fica em RAM enquanto a conversa estiver rolando e cai depois
    de alguns minutos de silencio.
    """
    if not LIBERAR_APOS_TRANSCREVER or _modelo_fala is None:
        return
    if time.time() - _ultimo_uso_fala > OCIOS_LIBERAR_FALA_SEGUNDOS:
        descarregar(fala=True, piper=False)

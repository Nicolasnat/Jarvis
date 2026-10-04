"""Voz do Nexus: wakeword, transcricao e fala. Tudo local (offline).

A captura de audio usa o binario 'arecord' (alsa-utils), evitando depender de
PortAudio/sounddevice. O wakeword usa o Vosk (reconhecimento por palavras-chave:
'Nexus', 'Hey Nexus', 'Nexus iniciar'...) e a transcricao usa faster-whisper. A
fala usa Piper (voz neural pt-BR); se ele nao estiver disponivel, cai para
espeak-ng/espeak/spd-say.

O modelo do Vosk e baixado para dados/vosk/ (ver README/INSTALACAO); as frases
que acordam o Nexus ficam em config/voz.json ('wake_frases').
"""
import contextlib
import ctypes
import gc
import math
import os
import re
import shutil
import subprocess
import tempfile
import threading
import time
import wave
from pathlib import Path

from comum import PASTA_CONFIG, PASTA_DADOS, ler_json, salvar_json

TAXA = 16000
MODELO_WHISPER = "small"

# Palavra/frase que acorda o Nexus. O Vosk faz reconhecimento por palavras-
# chave, entao vale a lista em 'wake_frases' (config/voz.json) e nao um unico
# modelo acustico fixo. 'WAKEWORD' e apenas o rotulo mostrado ao usuario.
WAKEWORD = "Nexus"
FRASES_WAKE = ["nexus", "nexo", "nexus iniciar", "oi nexus", "hey nexus"]
PALAVRAS_WAKE = {"nexus", "nexo"}
CONFIRMACAO_WAKEWORD = 2         # blocos de 100 ms seguidos confirmando o nome
LIMITE_ESPECIAL = 29360   # ~90% de 32767, evita sinal estourado
ALVO_RMS = 0.10           # nivel em que o modelo responde bem
GANHO_MAXIMO = 40.0       # teto do amplificador de software
RMS_MINIMO = 0.0008       # abaixo disso e silencio: nao compensa o ganho
DURACAO_FALA = 6.0

# Vocabulario que ajuda o Whisper a acertar os comandos mais comuns do Nexus.
# Sem isso, em audio fraco ele tende a inventar frases parecidas com o prompt.
PROMPT_INICIAL = (
    "Nexus, para, cancela. Abra o VS Code, o Chrome, o terminal e a pasta "
    "projetos. Toque a playlist no Spotify, pause, proxima musica, aumenta o "
    "volume."
)

# Interrupcao por voz (barge-in): enquanto o Nexus trabalha ou fala, uma
# thread fica de olho no microfone e qualquer fala sua cancela a acao.
#
# O gatilho tem duas partes: um piso absoluto e uma multiplicacao do chao de
# ruido da sala medido no inicio da vigia. O piso cobre o caso de silencio
# absoluto; a multiplicacao cobre o caso comum, em que o microfone da maquina
# e fraco e o silencio sozinho ja passa de qualquer numero sensato.
LIMITE_BARGE_IN = 0.008           # piso absoluto, mic em silencio
FATOR_BARGE_IN = 2.5              # voz = 2,5x o chao (~8 dB acima do ruido)
LIMITE_BARGE_IN_FALANDO = 0.012   # piso absoluto durante a fala do Nexus
FATOR_BARGE_IN_ECHO = 3.0         # sobe o alvo se o mic captar a propria voz
DURACAO_BARGE_IN = 0.45           # segundos de fala continua para interromper
CALIBRACAO_VIGIA_BLOCOS = 5       # 5 x 80 ms medindo o chao antes de armar

# Para de gravar 1.5s depois de voce parar de falar, em vez de esperar os 6s.
ESPERA_SILENCIO = 1.5
IDIOMA_ESPEAK = "pt-br"
IDIOMA_SPD = "pt-BR"
VOZ_SPD = "Portuguese (Brazil)"

PASTA_VOZES = PASTA_DADOS / "voz"
# Modelo do Vosk (reconhecimento por palavras-chave). Baixado uma vez em
# dados/vosk/; ver README/INSTALACAO. Nao e versionado.
PASTA_VOSK = PASTA_DADOS / "vosk" / "vosk-model-small-pt-0.3"

# A voz fica em config/voz.json para nao exigir editar codigo. Veja
# 'python -m ferramentas.trocar_voz --listar' para as opcoes em portugues.
# O mesmo arquivo calibra o wakeword e a interrupcao por voz, que sao exatamente
# as duas coisas que dependem do microfone da maquina.
ARQUIVO_VOZ = PASTA_CONFIG / "voz.json"
VOZES_PADRAO = {
    "modelo": "pt_BR-faber-medium",
    "velocidade": 1.0,   # acima de 1 fala mais rapido
    "profundidade": 1.0,  # acima de 1 deixa mais dramatico
    "wake_frases": FRASES_WAKE,
    "wake_confirmacao": CONFIRMACAO_WAKEWORD,
    "wake_debug": False,  # true volta a logar o nivel do som e o que o Vosk ouviu
    "barge_limiar": LIMITE_BARGE_IN,
    "barge_fator": FATOR_BARGE_IN,
    "barge_limiar_falando": LIMITE_BARGE_IN_FALANDO,
    "barge_fator_falando": FATOR_BARGE_IN_ECHO,
    "barge_duracao": DURACAO_BARGE_IN,
}


def _numero(config: dict, chave: str, padrao: float) -> float:
    """Le um numero do config, ignorando o que estiver quebrado."""
    try:
        return float(config[chave])
    except (KeyError, TypeError, ValueError):
        return padrao


def _sinalizador(config: dict, chave: str, padrao: bool) -> bool:
    try:
        return bool(config[chave])
    except (KeyError, TypeError):
        return padrao


def _lista(config: dict, chave: str, padrao: list) -> list:
    """Le uma lista de textos do config, ignorando o que estiver quebrado."""
    valor = config.get(chave)
    if isinstance(valor, list) and valor and all(isinstance(i, str) for i in valor):
        return valor
    return padrao


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
FRASES_WAKE = _lista(CONFIG_VOZ, "wake_frases", FRASES_WAKE)
CONFIRMACAO_WAKEWORD = int(_numero(CONFIG_VOZ, "wake_confirmacao", CONFIRMACAO_WAKEWORD))
WAKE_DEBUG = _sinalizador(CONFIG_VOZ, "wake_debug", False)
LIMITE_BARGE_IN = _numero(CONFIG_VOZ, "barge_limiar", LIMITE_BARGE_IN)
FATOR_BARGE_IN = _numero(CONFIG_VOZ, "barge_fator", FATOR_BARGE_IN)
LIMITE_BARGE_IN_FALANDO = _numero(CONFIG_VOZ, "barge_limiar_falando", LIMITE_BARGE_IN_FALANDO)
FATOR_BARGE_IN_ECHO = _numero(CONFIG_VOZ, "barge_fator_falando", FATOR_BARGE_IN_ECHO)
DURACAO_BARGE_IN = _numero(CONFIG_VOZ, "barge_duracao", DURACAO_BARGE_IN)
ESPERA_SILENCIO = _numero(CONFIG_VOZ, "espera_silencio", ESPERA_SILENCIO)

_modelo_vosk = None
_modelo_fala = None
_ultimo_uso_fala = 0.0
_voz_piper = None
_piper_avisado = False
_lock_fala = threading.Lock()

# Interrupcao por voz. '_evento_parada' e o pedido de cancelar a acao atual;
# '_evento_fim_vigia' apenas encerra a thread que escuta, e existe para nao
# precisar reusar o primeiro (que pode ja estar marcado por um barge-in real).
_evento_parada = threading.Event()
_evento_fim_vigia = threading.Event()
_lock_vigia = threading.Lock()
_vigia = None
NIVEL_ESCALA = 25.0
_nivel_callback = None
_reproduzindo_fala = threading.Event()

# Quantas partes do codigo estao com o microfone aberto ao mesmo tempo. Dois
# 'arecord' disputando o mesmo dispositivo nao e garantia de nada: um deles
# falha ou rouba a captura do outro. Como o aviso 'Pois nao?' toca enquanto o
# gravador ainda esta pegando a sua voz, e a vigia de interrupcao roda durante
# a fala, esse conflito acontece de verdade.
_lock_mic = threading.Lock()
_mic_ocupado = 0

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
        import vosk  # noqa: F401
    except Exception:
        faltas.append("vosk (pip)")
    if not PASTA_VOSK.exists():
        faltas.append(f"modelo Vosk em {PASTA_VOSK} (ver README)")
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
            return _esperar_ouvindo(comando + [str(arquivo)], timeout=180)
    return False


def _esperar_ouvindo(comando, timeout) -> bool:
    """Roda um programa de audio e o mata no instante em que voce o interrompe.

    Antes era subprocess.run(), que so termina quando o audio acaba: com uma
    resposta longa nao havia como Nexus calar a boca. O laco de 100ms acorda
    varias vezes por segundo para checar o pedido de parada, o que mantem o
    atraso de perceocao em um piscar de olhos.
    """
    try:
        processo = subprocess.Popen(
            comando, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        )
    except OSError:
        return False

    limite = time.time() + timeout
    while True:
        if _evento_parada.is_set():
            _matar(processo)
            return True
        try:
            processo.wait(timeout=0.1)
            return True
        except subprocess.TimeoutExpired:
            pass
        if time.time() > limite:
            _matar(processo)
            return True


def _matar(processo):
    try:
        processo.kill()
    except OSError:
        pass
    try:
        processo.wait(timeout=2)
    except subprocess.TimeoutExpired:
        pass


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
    esta instalado aqui, o Nexus fica mudo em silencio.
    """
    from piper.config import SynthesisConfig

    return SynthesisConfig(
        length_scale=1.0 / max(0.1, VELOCIDADE_FALA),
        noise_scale=0.667 * PROFUNDIDADE_FALA,
        noise_w_scale=0.8 * PROFUNDIDADE_FALA,
    )


# ---------- Interrupcao por voz (barge-in) ----------
#
# O fluxo antigo era estritamente sequencial: microfone fechado enquanto o
# modelo pensava e enquanto o Nexus falava, so que um 'para' dito na mao
# nao chegava a lugar nenhum. Agora, sempre que existe algo para interromper
# (resposta longa, agente de codigo rodando), uma thread abre o microfone e
# espera voce falar. O que dispara o cancelamento e qualquer fala continua
# acima do chao de ruido: um simples 'para' basta.


def interrompido() -> bool:
    """True quando voce mandou interromper a acao em andamento."""
    return _evento_parada.is_set()


def pedir_parada() -> None:
    """Cancela a acao atual (falando ou nao)."""
    _evento_parada.set()


def limpar_parada() -> None:
    """Abre uma nova acao: limpa o pedido de parada anterior."""
    _evento_parada.clear()


def ao_nivel(fn):
    """Registra callback para monitoramento do nivel de audio (0.0 a 1.0)."""
    global _nivel_callback
    _nivel_callback = fn


def _emitir_nivel(valor: float) -> None:
    """Dispara o callback de nivel registrado de forma segura."""
    cb = _nivel_callback
    if cb is None:
        return
    try:
        cb(float(valor))
    except Exception:
        pass


def _normalizar_nivel(rms: float) -> float:
    """Normaliza RMS para a escala de 0.0 a 1.0."""
    return min(1.0, max(0.0, float(rms) * NIVEL_ESCALA))


def _nivel(amostras):
    """RMS de um array int16, na mesma escala usada pelo wakeword e pela VAD."""
    import numpy as np

    if amostras.size == 0:
        return 0.0
    return float(np.sqrt((amostras.astype(np.float32) / 32768.0).__pow__(2).mean()))


def _emitir_envelope_wav(caminho_wav, evento_fim):
    """Calcula e emite o envelope RMS do arquivo WAV em tempo real."""
    import numpy as np

    _reproduzindo_fala.set()
    try:
        with wave.open(str(caminho_wav), "rb") as wf:
            taxa = wf.getframerate()
            canais = wf.getnchannels()
            largura = wf.getsampwidth()
            n_frames = wf.getnframes()
            if taxa <= 0 or n_frames <= 0:
                return
            dados = wf.readframes(n_frames)

        if largura == 2:
            amostras = np.frombuffer(dados, dtype=np.int16)
        elif largura == 1:
            amostras = (np.frombuffer(dados, dtype=np.uint8).astype(np.int16) - 128) * 256
        else:
            return

        if canais > 1:
            amostras = amostras[::canais]

        # Blocos de ~50 ms
        tamanho_bloco = max(1, int(taxa * 0.05))
        duracao_bloco = float(tamanho_bloco) / taxa
        blocos = [amostras[i:i + tamanho_bloco] for i in range(0, len(amostras), tamanho_bloco)]
        niveis = [_nivel(pedaco) for pedaco in blocos]
        # Normaliza pelo pico da propria fala: sem isso o orbe fica saturado
        # durante toda a resposta em vez de ondular com as silabas.
        pico = max(niveis) if niveis else 0.0
        fator = (1.0 / pico) if pico > 1e-6 else 0.0

        for nivel in niveis:
            if evento_fim.is_set() or _evento_parada.is_set():
                break
            t_inicio = time.time()
            _emitir_nivel(min(1.0, nivel * fator))

            tempo_espera = duracao_bloco - (time.time() - t_inicio)
            if tempo_espera > 0:
                if evento_fim.wait(timeout=tempo_espera) or _evento_parada.is_set():
                    break
            elif evento_fim.is_set() or _evento_parada.is_set():
                break
    except Exception:
        pass
    finally:
        _reproduzindo_fala.clear()
        _emitir_nivel(0.0)


def _vigia_corpo(limiar, duracao, fator):
    """Espera voce falar para interromper. Sai assim que a fala e detectada.

    O gatilho e a propria voz continua acima do chao de ruido, sem palavra-
    chave: falar 'para' (ou qualquer frase) ja cancela. Um reconhecedor aqui so
    disputaria CPU e microfone com a gravacao, sem ganho real.
    """
    import numpy as np

    processo = _abrir_microfone()
    fala = 0.0
    try:
        # Mede o chao de ruido da sala antes de armar o gatilho. Um limiar
        # absoluto nao funciona em duas maquinas: nesta o silencio ja da 0.003 e
        # a fala mal passa de 0.02, num microfone de mesa o silencio e 0.0001.
        # Comparar com o proprio chao da sala e o que faz o gatilho valer nas
        # duas. Se o silencio for absoluto, sobra o limiar absoluto mesmo.
        leitura = []
        for _ in range(CALIBRACAO_VIGIA_BLOCOS):
            dados = processo.stdout.read(1280 * 2)  # ~80 ms cada
            if not dados:
                break
            leitura.append(_nivel(np.frombuffer(dados, dtype=np.int16)))
        chao = max(leitura) if leitura else 0.0
        alvo = max(limiar, chao * fator)

        while not _evento_fim_vigia.is_set() and not _evento_parada.is_set():
            dados = processo.stdout.read(1280 * 2)  # ~80 ms de audio
            if not dados:
                time.sleep(0.1)
                continue

            amostras = np.frombuffer(dados, dtype=np.int16)
            rms = _nivel(amostras)
            if _nivel_callback is not None and not _reproduzindo_fala.is_set():
                _emitir_nivel(_normalizar_nivel(rms))

            # Fala continua, e nao um estalo ou o barulho de uma cadeira.
            if rms >= alvo:
                fala += len(dados) / (TAXA * 2)
            else:
                fala = 0.0
            if fala >= duracao:
                _evento_parada.set()
                return
    except Exception as erro:  # noqa: BLE001 - a vigia nunca derruba o Nexus
        print(f"[voz] Vigia de interrupcao parou ({erro}).", flush=True)
    finally:
        _encerrar_microfone(processo)
        if not _reproduzindo_fala.is_set():
            _emitir_nivel(0.0)


def vigiar_interrupcao(limiar=None, fator=None) -> bool:
    """Abre o microfone para voce poder interromper. Devolve True se iniciou.

    limiar/fator padrao: o par sem eco. Passe LIMITE_BARGE_IN_FALANDO e
    FATOR_BARGE_IN_ECHO quando o Nexus estiver falando, senao ele escuta a
    propria voz e se cala sozinho.
    """
    global _vigia

    if limiar is None:
        limiar = LIMITE_BARGE_IN
    if fator is None:
        fator = FATOR_BARGE_IN
    # O aviso 'Pois nao?' toca com o gravador ainda aberto. Abrir um segundo
    # 'arecord' ali e pedir para os dois perderem a captura, entao nesse
    # intervalo a interrupcao fica sem vigia. Nao faz falta: o que voce disser
    # agora entra direto na gravacao e o nexus.py reconhece o 'para'.
    if not mic_livre():
        return False
    with _lock_vigia:
        if _vigia is not None and _vigia.is_alive():
            return False
        _evento_fim_vigia.clear()
        _vigia = threading.Thread(
            target=_vigia_corpo, args=(limiar, DURACAO_BARGE_IN, fator), daemon=True,
        )
        _vigia.start()
    return True


def parar_vigia(timeout=2.0) -> None:
    """Encerra a escuta de interrupcao, se estiver aberta."""
    global _vigia

    with _lock_vigia:
        vigia, _vigia = _vigia, None
    if vigia is None:
        return
    _evento_fim_vigia.set()
    if vigia.is_alive():
        vigia.join(timeout=timeout)


def _encerrar_microfone(processo):
    global _mic_ocupado

    with _lock_mic:
        _mic_ocupado = max(0, _mic_ocupado - 1)
    try:
        processo.terminate()
    except OSError:
        return
    try:
        processo.wait(timeout=3)
    except subprocess.TimeoutExpired:
        _matar(processo)


def falar(texto: str, vigiar: bool = True):
    texto = _limpar_para_fala(texto or "")
    if not texto:
        return
    if _evento_parada.is_set():
        return

    with _lock_fala:
        # Par preventive: com o Nexus falando, o limiar sobe. Medido nesta
        # maquina o microfone quase nao capta a caixa de som (0.004), entao nem
        # seria preciso, mas num notebook com microfone em cima do alto-falante
        # seria o eco da propria voz cortando a frase pela metade.
        # 'vigiar=False' e para a saudacao curta: abrir a vigia ali criaria um
        # segundo 'arecord' enquanto a resposta ja esta sendo gravada.
        vigia_antes = _vigia is not None and _vigia.is_alive()
        if vigiar and not vigia_antes:
            vigiar_interrupcao(LIMITE_BARGE_IN_FALANDO, FATOR_BARGE_IN_ECHO)
        try:
            voz = _carregar_piper()
            if voz is not None:
                try:
                    arquivo = Path(tempfile.gettempdir()) / "nexus_fala.wav"
                    with wave.open(str(arquivo), "wb") as wav:
                        voz.synthesize_wav(texto, wav, syn_config=_config_sintese())
                    if LIBERAR_PIPER_APOS_FALAR:
                        descarregar(fala=False, piper=True)
                    fim_reproducao = threading.Event()
                    thread_nivel = None
                    if _nivel_callback is not None:
                        thread_nivel = threading.Thread(
                            target=_emitir_envelope_wav,
                            args=(arquivo, fim_reproducao),
                            daemon=True,
                        )
                        thread_nivel.start()
                    try:
                        if _tocar(arquivo):
                            return
                    finally:
                        fim_reproducao.set()
                        if thread_nivel is not None:
                            thread_nivel.join(timeout=0.2)
                except Exception as erro:
                    print(f"[voz] Piper falhou ({erro}); usando espeak.")
            comando = _comando_fala()
            if comando is None:
                print("[voz] Nenhum sintetizador encontrado (instale espeak-ng ou piper-tts).")
                return
            _esperar_ouvindo(comando + [texto], timeout=120)
        finally:
            if vigiar and not vigia_antes:
                parar_vigia()


def _carregar_vosk():
    global _modelo_vosk
    if _modelo_vosk is None:
        import vosk

        vosk.SetLogLevel(-1)  # silencia os LOG(...) do Kaldi no stderr
        if not PASTA_VOSK.exists():
            raise RuntimeError(
                f"modelo do Vosk nao encontrado em {PASTA_VOSK} "
                "(baixe conforme o README/INSTALACAO)"
            )
        _modelo_vosk = vosk.Model(str(PASTA_VOSK))
    return _modelo_vosk


def _abrir_microfone():
    """Abre o 'arecord' e registra que o microfone esta ocupado.

    Toda abertura passa por aqui e todo fechamento por _encerrar_microfone, e o
    par mantem a contagem do microfone em dia sem ninguem precisar lembrar de
    decrementar nada.
    """
    global _mic_ocupado
    processo = subprocess.Popen(
        ["arecord", "-q", "-f", "S16_LE", "-r", str(TAXA), "-c", "1", "-t", "raw"],
        stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
    )
    with _lock_mic:
        _mic_ocupado += 1
    return processo


def mic_livre() -> bool:
    """True quando ninguem esta com o microfone aberto."""
    with _lock_mic:
        return _mic_ocupado == 0


def _nivelar(amostras, ganho):
    """Aplica um ganho em software, segurando o pico para nao estourar.

    O reconhecimento (Vosk no wakeword, Whisper na transcricao) responde melhor
    com o audio em um nivel previsivel: ganho de fabrica no maximo estoura o
    sinal e baixo demais some no ruido. Normalizar aqui deixa a deteccao
    independente do hardware.
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


def _e_wake(texto: str) -> bool:
    """True se o texto reconhecido (parcial ou final) tem o nome de ativacao."""
    palavras = re.findall(r"[a-zá-ú]+", (texto or "").lower())
    return any(p in PALAVRAS_WAKE for p in palavras)


@contextlib.contextmanager
def _sem_ruido():
    """Silencia o stderr do Kaldi durante uma chamada.

    O Vosk avisa a cada reconhecedor criado que 'hey' nao esta no vocabulario
    do modelo pt-BR. O aviso e inofensivo ('Hey Nexus' funciona pelo 'nexus'),
    mas enfileirava uma linha de WARNING no journal a cada escuta.
    """
    try:
        salvo = os.dup(2)
    except OSError:
        yield
        return
    nulo = os.open(os.devnull, os.O_WRONLY)
    try:
        os.dup2(nulo, 2)
        yield
    finally:
        os.dup2(salvo, 2)
        os.close(nulo)
        os.close(salvo)


def _novo_reconhecedor():
    """Cria um KaldiRecognizer novo a cada escuta.

    Nao reaproveite com Reset(): ele nao limpa o estado o bastante e um
    reconhecedor reciclado acabou aceitando 'bom dia' como wakeword.
    """
    import json
    import vosk

    with _sem_ruido():
        return vosk.KaldiRecognizer(_carregar_vosk(), TAXA, json.dumps(FRASES_WAKE + ["[unk]"]))


def escutar_wakeword(parar=None) -> bool:
    """Bloqueia ouvindo ate reconhecer uma das 'wake_frases'. True ao detectar.

    O Vosk roda com a gramatica restrita as frases de ativacao: qualquer coisa
    fora delas cai em '[unk]' e nao acorda. O resultado parcial ja entrega o
    nome assim que ele e pronunciado, sem esperar a pausa que finaliza a frase.
    """
    import json
    import numpy as np

    reconhecedor = _novo_reconhecedor()
    processo = _abrir_microfone()
    ganho = 1.0
    confirmados = 0
    ultimo, pico_som, ouvido = time.time(), 0.0, ""
    passo = TAXA * 2 // 10  # 100 ms
    try:
        while True:
            # Uma parada pedida durante a acao anterior ja foi tratada; se
            # sobrou marca aqui, e para nao acordar com a boca cheia.
            _evento_parada.clear()
            if parar is not None and parar():
                return False
            dados = processo.stdout.read(passo)
            if not dados:
                return False
            amostras = np.frombuffer(dados, dtype=np.int16)
            rms = _nivel(amostras)
            if rms >= RMS_MINIMO:
                ganho = _ganho_para(rms)
            bloco = _nivelar(amostras, ganho).tobytes()

            if reconhecedor.AcceptWaveform(bloco):
                texto = json.loads(reconhecedor.Result()).get("text", "")
                if _e_wake(texto):
                    print(f"[wake] reconhecido: {texto!r}", flush=True)
                    return True
                confirmados = 0
            else:
                texto = json.loads(reconhecedor.PartialResult()).get("partial", "")
                # Confirmacao em blocos seguidos: um parcial isolado (ruido que
                # o Vosk encaixou como 'nexo') nao acorda; a palavra falada
                # persiste por varios blocos.
                confirmados = confirmados + 1 if _e_wake(texto) else 0
                if confirmados >= CONFIRMACAO_WAKEWORD:
                    print(f"[wake] reconhecido: {texto!r}", flush=True)
                    return True

            if WAKE_DEBUG:
                # Silencioso por padrao: a cada 10s de espera esse log enche o
                # journal sem dizer nada. Ligue 'wake_debug' em config/voz.json
                # so quando estiver investigando o microfone.
                pico_som = max(pico_som, rms)
                if texto:
                    ouvido = texto
                if time.time() - ultimo >= 10:
                    print(f"[wake] 10s: som maximo {pico_som:.4f} (minimo {RMS_MINIMO}), "
                          f"ouvido: {ouvido!r}", flush=True)
                    ultimo, pico_som, ouvido = time.time(), 0.0, ""
    finally:
        _encerrar_microfone(processo)


def _carregar_fala():
    global _modelo_fala
    if _modelo_fala is None:
        from faster_whisper import WhisperModel
        # 6 threads: mediram-se 3.09s com 1 thread e 1.69s com 12, sempre com o
        # mesmo texto. Nao vamos ate 12 porque o Vosk precisa de CPU para
        # continuar ouvindo o nome de ativacao durante a transcricao.
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


def gravar_ate_silencio(destino: Path, segundos=DURACAO_FALA, espera_silencio=ESPERA_SILENCIO,
                         atencao_inicial=0.0, limiar=RMS_MINIMO * 6, inicio=None):
    """Grava e PARA SOZINHO quando o usuario termina de falar.

    Antes isso gravava os 6 segundos inteiros, faltando 1s e ainda esperando 5s
    de silencio. Parar no fim da fala economiza quase 4s em cada comando.

    espera_silencio: quantos segundos de silencio encerram a gravacao.
    atencao_inicial: periodo fixo ignorado, em segundos.
    inicio: se for um threading.Event, ignora o audio ate ele ser marcado. E o
    jeito correto de nao gravar a saudacao do Nexus: em vez de chutar uma
    janela fixa (que cortava o comeco do comando quando o aviso era curto e
    vazava o aviso quando era longo), a captura comeca exatamente quando a fala
    termina.

    Nao existe vigia de interrupcao aqui: o microfone ja esta aberto para esta
    gravacao e dois 'arecord' ao mesmo tempo brigam pelo dispositivo. Quem
    trata do 'para' dito no meio e o nexus.py, que le a transcricao e
    descarta o turno.
    """
    proc = _abrir_microfone()
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
                decorrido += len(bloco) / bytesegs

                if inicio is not None:
                    if not inicio.is_set():
                        continue
                elif decorrido < atencao_inicial:
                    continue

                amostras += bloco

                rms_bloco = _rms(bloco)
                if _nivel_callback is not None:
                    _emitir_nivel(_normalizar_nivel(rms_bloco))

                if rms_bloco > limiar:
                    falando = True
                    silencio = 0.0
                elif falando:
                    silencio += len(bloco) / bytesegs
                    if silencio >= espera_silencio:
                        break

                if decorrido >= segundos:
                    break
    finally:
        _encerrar_microfone(proc)
        _emitir_nivel(0.0)

    with wave.open(str(destino), "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(TAXA)
        wav.writeframes(bytes(amostras))
    return destino, falando


def transcrever(segundos=DURACAO_FALA, espera_silencio=ESPERA_SILENCIO, atencao_inicial=0.0) -> str:
    global _ultimo_uso_fala
    pasta = tempfile.mkdtemp()
    arquivo = Path(pasta) / "nexus_voz.wav"
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
            initial_prompt=PROMPT_INICIAL,
            condition_on_previous_text=False, vad_filter=True,
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
            initial_prompt=PROMPT_INICIAL,
            condition_on_previous_text=False, vad_filter=True,
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


def comecar_a_gravar(segundos=DURACAO_FALA, espera_silencio=ESPERA_SILENCIO, atencao_inicial=0.0,
                     inicio=None):
    """Comeca a gravar em segundo plano, para o Nexus falar enquanto ouve.

    O microfone ja esta pegando quando a saudacao comeca, entao o usuario pode
    responder na mesma frase e nada do que ele diz se perde. 'inicio' (Event)
    marca o instante em que o aviso terminou: antes disso o audio e descartado.
    """
    pasta = tempfile.mkdtemp()
    arquivo = Path(pasta) / "nexus_voz.wav"

    def trabalho():
        try:
            gravar_ate_silencio(arquivo, segundos, espera_silencio, atencao_inicial, inicio=inicio)
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

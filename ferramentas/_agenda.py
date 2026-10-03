"""Agenda de lembretes em segundo plano, com persistencia em dados/lembretes.json.

Nao e um plugin (nome comeca com '_'); os plugins agendar_lembrete/listar_lembretes/
cancelar_lembrete usam estas funcoes.
"""
import re
import subprocess
import threading
import time
from datetime import datetime, timedelta

from comum import ARQUIVO_LEMBRETES, ler_json, salvar_json

_lock = threading.Lock()
_aviso = None  # callback opcional para falar o lembrete (ligado na Etapa 4/voz)


def _carregar():
    return ler_json(ARQUIVO_LEMBRETES, [])


def _salvar(itens):
    salvar_json(ARQUIVO_LEMBRETES, itens)


def _absoluto(hora, minuto, texto, agora):
    if not (0 <= hora <= 23 and 0 <= minuto <= 59):
        return None
    alvo = agora.replace(hour=hora, minute=minuto, second=0, microsecond=0)
    if "amanha" in texto or alvo <= agora:
        alvo += timedelta(days=1)
    return alvo


def interpretar_quando(quando: str):
    """Converte texto livre em datetime. Suporta: 'em 20 minutos', '2 horas',
    'amanha as 8h', '18:30'. Devolve None se nao entender."""
    texto = (quando or "").strip().lower()
    agora = datetime.now()

    # 1) Horario de relogio com minutos: 18:30, 08h15.
    relogio = re.search(r"\b(\d{1,2})\s*[:h]\s*(\d{2})\b", texto)
    if relogio:
        return _absoluto(int(relogio.group(1)), int(relogio.group(2)), texto, agora)

    # 2) Duracao relativa: 'em 20 minutos', '2 horas', '20 min'.
    relativo = re.search(r"(?:em\s+)?(\d+)\s*(minutos?|mins?|horas?|h)\b", texto)
    if relativo and ("em " in texto or re.search(r"min|hora", texto)):
        quantidade = int(relativo.group(1))
        unidade = relativo.group(2)
        delta = timedelta(hours=quantidade) if unidade.startswith("h") else timedelta(minutes=quantidade)
        return agora + delta

    # 3) Hora cheia: 'amanha as 8h', 'as 20'.
    cheia = re.search(r"\b(\d{1,2})\s*h(?:oras?)?\b", texto)
    if not cheia:
        cheia = re.search(r"\bas\s+(\d{1,2})\b", texto)
    if cheia:
        return _absoluto(int(cheia.group(1)), 0, texto, agora)

    return None


def agendar(mensagem: str, quando: str):
    alvo = interpretar_quando(quando)
    if alvo is None:
        return ("Nao entendi o horario. Use por exemplo 'em 20 minutos', "
                "'amanha as 8h' ou '18:30'.")

    with _lock:
        itens = _carregar()
        novo_id = max([item.get("id", 0) for item in itens], default=0) + 1
        itens.append({
            "id": novo_id,
            "mensagem": (mensagem or "").strip(),
            "quando": alvo.isoformat(timespec="seconds"),
            "criado": datetime.now().isoformat(timespec="seconds"),
        })
        _salvar(itens)
    return f"Lembrete #{novo_id} agendado para {alvo:%d/%m/%Y %H:%M}: {mensagem}"


def listar():
    itens = _carregar()
    if not itens:
        return "Nenhum lembrete agendado."
    linhas = ["Lembretes pendentes:"]
    for item in itens:
        try:
            alvo = datetime.fromisoformat(item.get("quando", ""))
            quando = f"{alvo:%d/%m/%Y %H:%M}"
        except ValueError:
            quando = item.get("quando", "?")
        linhas.append(f"- #{item.get('id')} {quando}: {item.get('mensagem', '')}")
    return "\n".join(linhas)


def cancelar(identificador):
    try:
        alvo_id = int(str(identificador).strip().lstrip("#"))
    except ValueError:
        alvo_id = None

    with _lock:
        itens = _carregar()
        restantes = [
            item for item in itens
            if not (item.get("id") == alvo_id
                    or (alvo_id is None and str(identificador).lower() in item.get("mensagem", "").lower()))
        ]
        removidos = len(itens) - len(restantes)
        _salvar(restantes)
    if removidos:
        return f"Lembrete(s) cancelado(s): {removidos}."
    return "Nenhum lembrete correspondente encontrado."


def _notificar(mensagem: str):
    try:
        subprocess.run(["notify-send", "Jarvis", mensagem], timeout=10, check=False)
    except (FileNotFoundError, subprocess.SubprocessError):
        pass
    if _aviso:
        try:
            _aviso(mensagem)
        except Exception:
            pass
    print(f"\n[jarvis] LEMBRETE: {mensagem}", flush=True)


def _loop():
    while True:
        agora = datetime.now()
        disparados = []
        with _lock:
            itens = _carregar()
            pendentes = []
            for item in itens:
                try:
                    alvo = datetime.fromisoformat(item.get("quando", ""))
                except ValueError:
                    continue
                if alvo <= agora:
                    disparados.append(item)
                else:
                    pendentes.append(item)
            if disparados:
                _salvar(pendentes)
        for item in disparados:
            _notificar(item.get("mensagem", "lembrete"))
        time.sleep(20)


def iniciar(aviso_cb=None):
    """Liga a thread de lembretes. Idempotente o suficiente para chamar uma vez no main."""
    global _aviso
    _aviso = aviso_cb
    threading.Thread(target=_loop, daemon=True).start()

"""Funcoes e constantes compartilhadas entre o Nexus e os plugins.
Fica num modulo separado para que os plugins possam importar helpers sem
criar import circular com o nexus.py (que roda como __main__).
"""
import json
import re
import time
import unicodedata
from pathlib import Path
from typing import Optional

BASE_PROJETO = Path(__file__).resolve().parent
PASTA_TRABALHO = Path.home() / "projetos"
PASTA_TRABALHO.mkdir(parents=True, exist_ok=True)
PASTA_DADOS = BASE_PROJETO / "dados"
PASTA_CONFIG = BASE_PROJETO / "config"
PASTA_NOTAS = PASTA_DADOS / "notas"

MODELO_ESPECIALISTA = "qwen2.5:7b"

REDUNDANTES = {"projetos", "projects", "projeto", "project"}


def resolver(caminho) -> Path:
    """Normaliza um caminho para dentro de PASTA_TRABALHO (ou mantem absolutos)."""
    raw = str(caminho).strip().strip("\"'")
    # Detecta caminho absoluto estilo Windows (C:\...) e pega só o nome final
    if re.match(r"^[A-Za-z]:[\\/]", raw):
        # No Linux o Path nao reconhece backslash como separador
        raw = raw.replace("\\", "/").split("/")[-1]
    pasta = Path(raw).expanduser()

    if not pasta.is_absolute():
        partes = pasta.parts
        if partes and partes[0].lower() in REDUNDANTES:
            partes = partes[1:]
        return PASTA_TRABALHO.joinpath(*partes) if partes else PASTA_TRABALHO

    try:
        relativo = pasta.relative_to(PASTA_TRABALHO)
    except ValueError:
        return pasta

    partes = list(relativo.parts)
    while partes and partes[0].lower() in REDUNDANTES:
        partes.pop(0)
    return PASTA_TRABALHO.joinpath(*partes) if partes else PASTA_TRABALHO


def permitido_para_escrita(pasta) -> bool:
    """So permite criar/escrever dentro da pasta de projetos ou do proprio Nexus."""
    alvo = Path(pasta).resolve()
    for base in (PASTA_TRABALHO.resolve(), BASE_PROJETO.resolve()):
        try:
            alvo.relative_to(base)
            return True
        except ValueError:
            continue
    return False


def esquema(propriedades, obrigatorias):
    return {"type": "object", "properties": propriedades, "required": obrigatorias}


ARTIGOS = {"o", "a", "os", "as", "um", "uma"}


def sem_acentos(texto: str) -> str:
    """'Acentuação' vira 'Acentuacao', para comparar o que foi falado com o nome do app."""
    normalizado = unicodedata.normalize("NFKD", str(texto or ""))
    return "".join(c for c in normalizado if not unicodedata.combining(c))


def chave_nome(texto: str) -> str:
    """Normaliza um nome falado para comparar: minusculo, sem acento e sem artigos.

    'o Visual Studio Code' e 'visual studio code' viram a mesma chave, que e o
    que o Whisper devolve depois de listening do usuario. Preposicoes sao
    mantidas de proposito: em portugues boa parte dos apps se chama
    'gerenciador de arquivos', 'mesa de som'.
    """
    limpo = sem_acentos(texto).lower()
    limpo = re.sub(r"[^a-z0-9]+", " ", limpo)
    palavras = [p for p in limpo.split() if p and p not in ARTIGOS]
    return " ".join(palavras)


TEXTO = {"type": "string"}


def limpar_ansi(texto: str) -> str:
    return re.sub(r"\x1b\[[0-9;?]*[a-zA-Z]|\x1b\][^\x07]*\x07", "", texto)


def resumir_busca(web: str, limite=1800) -> str:
    if len(web) <= limite:
        return web
    return web[:limite] + "\n...[conteudo truncado]"


def garantir_pasta_dados() -> Path:
    PASTA_DADOS.mkdir(parents=True, exist_ok=True)
    return PASTA_DADOS


def ler_json(caminho, padrao):
    """Le um JSON local; devolve o padrao se o arquivo nao existir ou estiver corrompido."""
    try:
        return json.loads(Path(caminho).read_text())
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return padrao


def salvar_json(caminho, dados):
    caminho = Path(caminho)
    caminho.parent.mkdir(parents=True, exist_ok=True)
    caminho.write_text(json.dumps(dados, indent=2, ensure_ascii=False))
    return caminho


ARQUIVO_MEMORIA = PASTA_DADOS / "memoria.json"
ARQUIVO_TAREFAS = PASTA_DADOS / "tarefas.json"
ARQUIVO_LEMBRETES = PASTA_DADOS / "lembretes.json"
ARQUIVO_APPS = PASTA_CONFIG / "apps.json"


def memoria_para_prompt(limite=8, busca: str = "", modo_privado: bool = False, cerebro_nuvem: bool = False) -> str:
    """Devolve um resumo curto da memoria para injetar no prompt do sistema.
    Usa memoria ativa (embeddings) se disponivel, fallback para recentes/palavras.
    """
    from ferramentas.memoria_ativa import obter_fatos_relevantes, formatar_bloco_memoria
    fatos = obter_fatos_relevantes(busca, modo_privado=modo_privado, cerebro_nuvem=cerebro_nuvem)
    return formatar_bloco_memoria(fatos)


# Controle de log de comandos (pode ser desativado se necessario)
LOG_REGISTRAR_FALA = True
LOG_REGISTRAR_COMANDOS = True


def executar_comando(
    comando: list,
    tempo: int = 120,
    pasta: Optional[str] = None,
    mostrar: bool = True,
    stdin_nulo: bool = True,
    env_extra: Optional[dict] = None,
    registrar: bool = True,
) -> str:
    """Wrapper para executar comandos do sistema com registro de log.
    
    Este wrapper deve ser usado em vez de chamar subprocess diretamente
    quando se quer que o comando apareca no painel de log.
    
    Args:
        comando: Lista com o comando e argumentos (ex.: ['xdg-open', '/home/user'])
        tempo: Timeout em segundos
        pasta: Diretorio de trabalho
        mostrar: Se True, imprime a saida no console
        stdin_nulo: Se True, ignora stdin
        env_extra: Variaveis de ambiente extras
        registrar: Se True, registra o comando no log de eventos
    
    Returns:
        Saida do comando como string
    """
    # Importa aqui para evitar import circular
    from nexus import rodar as _rodar
    from eventos import log_comando
    
    comando_str = " ".join(str(c) for c in comando)
    inicio = time.time()
    
    if registrar and LOG_REGISTRAR_COMANDOS:
        log_comando(f"$ {comando_str}", f"Executando em {pasta or '.'}", exec_id=None)
    
    try:
        resultado = _rodar(comando, tempo=tempo, pasta=pasta, mostrar=mostrar, stdin_nulo=stdin_nulo, env_extra=env_extra)
        duracao_ms = int((time.time() - inicio) * 1000)
        
        if registrar and LOG_REGISTRAR_COMANDOS:
            ok = "erro" not in resultado.lower() and "falha" not in resultado.lower() and "falhou" not in resultado.lower()
            log_comando(f"$ {comando_str}", resultado, ok, duracao_ms)
        
        return resultado
    except Exception as e:
        duracao_ms = int((time.time() - inicio) * 1000)
        if registrar and LOG_REGISTRAR_COMANDOS:
            log_comando(f"$ {comando_str}", f"Excecao: {e}", False, duracao_ms)
        raise

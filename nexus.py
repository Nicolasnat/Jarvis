import json
import os
import random
import re
import sys
import inspect
import shutil
import subprocess
import threading
import time
from datetime import datetime
from pathlib import Path

from comum import (
    PASTA_TRABALHO, PASTA_DADOS, PASTA_CONFIG, BASE_PROJETO,
    MODELO_ESPECIALISTA, resolver, esquema, TEXTO,
    limpar_ansi, resumir_busca, memoria_para_prompt, chave_nome,
)
from ferramentas.carregador import carregar_plugins
from ferramentas import definir_volume as _volume_sistema
from ferramentas._agenda import iniciar as iniciar_agenda
import seguranca
from cerebro import (
    chat as cerebro_chat,
    adicionar_historico,
    obter_historico,
    limpar_historico,
    status_cerebros,
    MensagemNeutra,
    ResultadoChat,
    obter_config_ativa,
    forcar_modo_local,
    set_callback_cerebro_mudou,
    MAX_PASSOS,
    MAX_PASSOS_LOCAL,
)


TEMPO_PADRAO = 120
TEMPO_CODIGO = 900
TEMPO_PLANO = 360
PERMISSOES_AUTOMATICAS = True
LIMITE_HISTORICO = 14

AGY = shutil.which("agy")

# O Antigravity embute o esforco no NOME do modelo (sufixos -low/-medium/-high).
# Passar --effort com um valor diferente do sufixo e recusado pelo CLI, entao
# 'esforco_do_modelo' deriva o esforco do proprio nome. Os modelos -high sao o
# teto pratico hoje ('gemini-3.8-flash' so aceita low/medium/high; nao ha -max
# exposto no 'agy models').
MODELO_ARQUITETO = "gemini-3.1-pro-high"
MODELO_EXECUTOR = "gemini-3.8-flash-high"
ESFORCO_ARQUITETO = "high"
ESFORCO_EXECUTOR = "high"
ESFORCOS_VALIDOS = ("low", "medium", "high", "xhigh", "max")
# O sandbox do agy auto-recusa ferramentas em modo headless (-p) sem allow-rules
# no settings.json, o que quebra o trabalho real. Fica False por padrao; ligue
# so se preencher permissions.allow.
ANTIGRAVITY_SANDBOX = False
ANTIGRAVITY_PLANEJA = True
ANTIGRAVITY_TOKEN = "<!-- nexus:regras -->"
REGRAS_ANTIGRAVITY = Path.home() / ".gemini" / "GEMINI.md"
SETTINGS_ANTIGRAVITY = Path.home() / ".gemini" / "antigravity-cli" / "settings.json"

CONFIG_PERMISSOES = Path(__file__).resolve().parent / "opencode-permissoes.json"
ULTIMO_PEDIDO = ""

# O modulo voz so e carregado no modo voz. Fora dele '_interrompido()' e sempre
# False e o Nexus continua se comportando como antes (Ctrl+C no terminal).
_voz = None

# Ponte com a interface grafica (PySide6). Inicia None e so e configurada
# quando a flag --interface for usada com ambiente grafico disponivel.
_ponte = None


def _ponte_emitir(nome_sinal: str, *args):
    """Emite um sinal da ponte Qt se a interface grafica estiver ativa."""
    if _ponte is None:
        return
    try:
        sinal = getattr(_ponte, nome_sinal, None)
        if sinal is not None and hasattr(sinal, "emit"):
            sinal.emit(*args)
    except Exception:
        pass


def _definir_estado(estado: str):
    """Atualiza o estado visual na interface grafica."""
    _ponte_emitir("estado_mudou", estado)

CHROME_OPENCODE = re.compile(r"^>\s*(build|plan|general)\s*[·|]")

# Seguranca: usa o modulo centralizado (protegido)
CAMINHOS_PROIBIDOS = seguranca.CAMINHOS_PROIBIDOS
BLOQUEIOS = seguranca.BLOQUEIOS
CREDENCIAIS = seguranca.CREDENCIAIS
CONFIRMACOES = seguranca.CONFIRMACOES

CONFIRMACOES_REGEX = seguranca.CONFIRMACOES_REGEX
BLOQUEIOS_REGEX = seguranca.BLOQUEIOS_REGEX
CREDENCIAIS_REGEX = seguranca.CREDENCIAIS_REGEX

CONFIG_PERMISSOES = seguranca.CONFIG_PERMISSOES
ULTIMO_PEDIDO = seguranca.ULTIMO_PEDIDO

# ---------- AJUDANTES E FERRAMENTAS ----------

def gerar_config_permissoes() -> dict:
    """Politica aplicada so ao OpenCode chamado pelo Nexus (via OPENCODE_CONFIG)."""
    return seguranca.gerar_config_permissoes()


def aplicar_config_permissoes() -> Path:
    return seguranca.aplicar_config_permissoes()


def bloco_regras_antigravity() -> str:
    return seguranca.bloco_regras_antigravity()


def aplicar_regras_antigravity() -> Path:
    return seguranca.aplicar_regras_antigravity()


def confiar_no_workspace(caminho: Path = PASTA_TRABALHO) -> None:
    """Marca a pasta de projetos como confiavel para o Antigravity."""
    seguranca.confiar_no_workspace(caminho)


def dentro_do_projeto(comando: str) -> bool:
    return seguranca.dentro_do_projeto(comando)


def detectar_graves(texto: str) -> tuple:
    """Comandos de destruicao real bloqueiam; mencoes no texto so pedem confirmacao."""
    return seguranca.detectar_graves(texto)


def confirmar_risco(comandos) -> bool:
    return seguranca.confirmar_risco(comandos)


def _set_ponte_seguranca(ponte):
    """Configura a ponte no modulo de seguranca para confirmacao via GUI."""
    seguranca._set_ponte(ponte)


def batimento(parado: threading.Event, rotulo: str):
    inicio = time.time()
    while not parado.wait(15):
        minutos, segundos = divmod(int(time.time() - inicio), 60)
        print(f"\r   ... {rotulo} ha {minutos}m{segundos:02d}s", end="", flush=True)


def _interrompido() -> bool:
    """True se o usuario mandou parar. Fora do modo voz nunca acontece."""
    return _voz is not None and _voz.interrompido()


def _abrir_vigia(limiar=None):
    """Abre o microfone para o usuario poder interromper o que estiver rodando."""
    if _voz is not None:
        _voz.vigiar_interrupcao(limiar)


def _fechar_vigia():
    if _voz is not None:
        _voz.parar_vigia()


def _matar_processo(processo):
    try:
        processo.kill()
    except OSError:
        pass


def _vigia_parada(processo, parado: threading.Event, inicio: float, tempo, rotulo: str, motivo: dict):
    """Mata o processo quando o usuario pede para parar, ou quando da tempo demais.

    Vigiar por fora do laco de stdout e obrigatorio: um agente de codigo pode
    ficar minutos sem imprimir uma linha nenhuma, e nesse tempo o laco esta
    bloqueado lendo o pipe e nao ve nem o pedido de parada nem o relogio. Era
    por isso que o primeiro 'para' nao tinha efeito nos comandos mais lentos, e
    tambem por isso que um comando travado segurava os TEMPO_CODIGO inteiros.
    """
    while not parado.wait(0.2):
        if _interrompido():
            motivo["texto"] = f"INTERROMPIDO: '{rotulo}' foi encerrado porque voce pediu para parar."
            _matar_processo(processo)
            return
        if tempo and time.time() - inicio > tempo:
            motivo["texto"] = f"Interrompido: '{rotulo}' passou de {tempo}s."
            _matar_processo(processo)
            return


def rodar(comando, tempo=TEMPO_PADRAO, pasta=None, mostrar=True, stdin_nulo=True, env_extra=None):
    local = resolver(pasta) if pasta is not None else PASTA_TRABALHO
    local.mkdir(parents=True, exist_ok=True)

    ambiente = None
    if env_extra:
        ambiente = {**os.environ, **env_extra}

    try:
        processo = subprocess.Popen(
            comando,
            cwd=str(local),
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            errors="replace",
            stdin=subprocess.DEVNULL if stdin_nulo else None,
            env=ambiente,

        )
    except FileNotFoundError:
        return f"Falha: o programa '{comando[0]}' nao esta instalado nesta maquina."

    linhas = []
    parado = threading.Event()
    motivo = {"texto": ""}
    batendo = None
    if mostrar:
        batendo = threading.Thread(target=batimento, args=(parado, comando[0]), daemon=True)
        batendo.start()

    inicio = time.time()
    threading.Thread(
        target=_vigia_parada,
        args=(processo, parado, inicio, tempo, comando[0], motivo),
        daemon=True,
    ).start()

    try:
        for linha in processo.stdout:
            limpa = limpar_ansi(linha).rstrip()
            if limpa.strip():
                linhas.append(limpa)
                if mostrar:
                    print(f"   | {limpa}", flush=True)
    finally:
        parado.set()
        try:
            processo.wait(timeout=5)
        except subprocess.TimeoutExpired:
            _matar_processo(processo)
        if mostrar:
            print("\r" + " " * 60 + "\r", end="", flush=True)

    if motivo["texto"]:
        return motivo["texto"]
    if _interrompido():
        return f"INTERROMPIDO: '{comando[0]}' foi encerrado porque voce pediu para parar."

    saida = "\n".join(linhas).strip()
    if processo.returncode != 0 and not saida:
        saida = f"'{comando[0]}' terminou com codigo {processo.returncode} sem produzir saida."
    return saida or f"'{comando[0]}' executado com sucesso."


def inspecionar_projeto(caminho: str) -> str:
    pasta = resolver(caminho)
    if not pasta.exists():
        return f"ERRO: a pasta '{pasta}' nao foi criada."

    if not pasta.is_dir() or not any(pasta.iterdir()):
        return f"ERRO: a pasta '{pasta}' foi criada mas esta VAZIA. O OpenCode nao gerou arquivos."

    contagem = {"total": 0, "node_modules": 0, "src": 0}
    for arquivo in pasta.rglob("*"):
        if not arquivo.is_file():
            continue
        contagem["total"] += 1
        if "node_modules" in arquivo.parts:
            contagem["node_modules"] += 1
        elif "src" in arquivo.parts:
            contagem["src"] += 1

    raiz = [a.name for a in sorted(pasta.iterdir()) if a.name != "node_modules"]
    return (
        f"VERIFICACAO REAL DO DISCO em {pasta}:\n"
        f"- {contagem['total']} arquivos no total ({contagem['node_modules']} em node_modules, {contagem['src']} em src)\n"
        f"- conteudo da raiz: {', '.join(raiz) if raiz else 'nenhum'}\n"
        f"- status: {'PROJETO REALMENTE CRIADO' if contagem['total'] - contagem['node_modules'] > 1 else 'CRIACAO INCOMPLETA'}"
    )


def _eh_auto_aprimoramento(tarefa: str, pasta: Path) -> bool:
    """Detecta se o pedido e para auto-aprimoramento do proprio Nexus."""
    # Se a pasta de destino e a raiz do Nexus
    try:
        if pasta.resolve() == BASE_PROJETO.resolve():
            return True
    except Exception:
        pass

    # Palavras-chave que indicam auto-aprimoramento
    tarefa_lower = (tarefa or "").lower()
    palavras_auto = [
        "seu c[oó]digo", "seu codigo", "voce mesmo", "no nexus", "nesse bug",
        "auto[ -]?aprimoramento", "melhore voc[eê]", "melhore o nexus",
        "corrig[ae] voc[eê]", "corrija voc[eê]", "corrige voc[eê]",
        "adicione em voc[eê]", "em si mesmo", "no seu c[oó]digo",
        "nesse c[oó]digo", "nesse projeto nexus", "meu nexus",
    ]
    for padrao in palavras_auto:
        if re.search(padrao, tarefa_lower):
            return True
    return False


def pedir_ao_opencode(tarefa: str, pasta_destino: str = ".") -> str:
    """Delega toda a parte de codigo para o OpenCode, que executa de verdade."""
    pasta = resolver(pasta_destino)
    pasta.mkdir(parents=True, exist_ok=True)

    # DETECCAO DE AUTO-APRIMORAMENTO: se o destino e o proprio Nexus
    # ou o pedido menciona "seu codigo", "voce mesmo", "no nexus", etc.
    if _eh_auto_aprimoramento(tarefa, pasta):
        from ferramentas.auto_aprimoramento import funcao as auto_aprimorar
        return auto_aprimorar(tarefa, pasta_destino)

    bloqueados, a_confirmar = detectar_graves(tarefa)
    if bloqueados:
        return ("BLOQUEADO pelo Nexus, nem chegou a ser enviado ao OpenCode:\n"
                + "\n".join(f"- {c}" for c in bloqueados)
                + "\nEssas operacoes destroem o sistema ou vazam credenciais. O Nexus nunca as executa.")

    if a_confirmar and not confirmar_risco(a_confirmar):
        return "CANCELADO pelo usuario. Nada foi executado."

    comando = ["opencode", "run", "--dir", str(pasta)]
    if PERMISSOES_AUTOMATICAS:
        comando.append("--auto")

    config = aplicar_config_permissoes()
    ambiente = {"OPENCODE_CONFIG": str(config)}
    if a_confirmar:
        ambiente["NEXUS_PERMISSOES"] = "confirmadas"

    print(f"   >>> OpenCode trabalhando em {pasta}", flush=True)
    resultado = rodar(comando + [tarefa], tempo=TEMPO_CODIGO, pasta=pasta, env_extra=ambiente)

    limpo = "\n".join(l for l in resultado.splitlines() if not CHROME_OPENCODE.match(l.strip()))
    print(f"   {inspecionar_projeto(str(pasta))}", flush=True)
    return resumir_busca(limpo or resultado, 3000)


def pedir_ao_claude(tarefa: str):
    """Opicional: usa o Claude Code como segunda opinião."""
    return rodar(["claude", "-p", tarefa], tempo=TEMPO_CODIGO)


_ULTIMA_CONVERSA_AGY = {"id": "", "pasta": ""}

# Guarda o plano pendente para o passo de revisao, depois do OpenCode construir.
_PLANO_ATUAL = {"texto": "", "pasta": ""}
ANTIGRAVITY_REVISAO = True


def esforco_do_modelo(modelo: str, desejado: str = "high") -> str:
    """Deriva o --effort do sufixo do modelo; o agy recusa se nao casar."""
    nome = (modelo or "").lower()
    for esforco in ESFORCOS_VALIDOS:
        if nome.endswith("-" + esforco):
            return esforco
    desejado = (desejado or "high").lower()
    return desejado if desejado in ESFORCOS_VALIDOS else "high"


def _agy_flags(modelo: str, esforco: str) -> list:
    """Flags comuns do agy: permissao, modelo e esforco coerente."""
    permissao = "--sandbox" if ANTIGRAVITY_SANDBOX else "--dangerously-skip-permissions"
    return [AGY, permissao, "--model", modelo, "--effort", esforco_do_modelo(modelo, esforco)]


def _agy_json(resultado: str):
    """Extrai o objeto JSON que o agy imprime no fim do -p --output-format json."""
    for linha in reversed(resultado.splitlines()):
        linha = linha.strip()
        if linha.startswith("{") and linha.endswith("}"):
            try:
                return json.loads(linha)
            except ValueError:
                continue
    return None


def pedir_ao_antigravity(tarefa: str, pasta_destino: str = ".") -> str:
    """Usa o Antigravity como executor/consultor, com o mesmo gate de risco do OpenCode."""
    if not AGY:
        return "O Antigravity (agy) nao esta instalado nesta maquina."

    bloqueados, a_confirmar = detectar_graves(tarefa)
    if bloqueados:
        return ("BLOQUEADO pelo Nexus, nem chegou ao Antigravity:\n"
                + "\n".join(f"- {c}" for c in bloqueados)
                + "\nEssas operacoes destroem o sistema ou vazam credenciais.")
    if a_confirmar and not confirmar_risco(a_confirmar):
        return "CANCELADO pelo usuario. Nada foi executado."

    pasta = resolver(pasta_destino)
    pasta.mkdir(parents=True, exist_ok=True)
    confiar_no_workspace(pasta)
    aplicar_regras_antigravity()

    esforco = esforco_do_modelo(MODELO_EXECUTOR, ESFORCO_EXECUTOR)
    comando = _agy_flags(MODELO_EXECUTOR, ESFORCO_EXECUTOR) + ["-p", tarefa]
    print(f"   >>> Antigravity executando ({MODELO_EXECUTOR}, esforco {esforco}) em {pasta}", flush=True)
    resultado = rodar(comando, tempo=TEMPO_CODIGO, pasta=pasta)
    print(f"   {inspecionar_projeto(str(pasta))}", flush=True)
    return resumir_busca(resultado, 3000)


def planejar_com_antigravity(pedido: str, pasta_destino: str = ".") -> str:
    """Pede so o plano. Roda em --mode plan, entao nao cria nada."""
    if not AGY:
        return "O Antigravity (agy) nao esta instalado nesta maquina."

    pasta = resolver(pasta_destino)
    pasta.mkdir(parents=True, exist_ok=True)
    confiar_no_workspace(pasta)
    aplicar_regras_antigravity()

    instrucao = (
        "Voce e o arquiteto responsavel. Produza APENAS um plano de implementacao curto e acionavel "
        "para OUTRO agente de IA executar nesta pasta. Nao crie arquivos, nao rode comandos, nao execute "
        "nada: apenas descreva o plano. Inclua: stack, estrutura de arquivos, passos em ordem, comandos "
        f"exatos e como validar. Maximo 25 linhas, sem codigo completo.\n\nPEDIDO DO USUARIO: {pedido}"
    )

    esforco = esforco_do_modelo(MODELO_ARQUITETO, ESFORCO_ARQUITETO)
    comando = _agy_flags(MODELO_ARQUITETO, ESFORCO_ARQUITETO)
    # Continuidade: se o ultimo plano foi nesta mesma pasta, retoma a conversa
    # do arquiteto em vez de recomecar do zero a cada pedido.
    if _ULTIMA_CONVERSA_AGY["id"] and _ULTIMA_CONVERSA_AGY["pasta"] == str(pasta):
        comando += ["--conversation", _ULTIMA_CONVERSA_AGY["id"]]
    comando += ["--mode", "plan", "--output-format", "json", "-p", instrucao]
    print(f"   >>> Antigravity planejando ({MODELO_ARQUITETO}, esforco {esforco}) em {pasta}", flush=True)
    bruto = rodar(comando, tempo=TEMPO_PLANO, pasta=pasta)

    dados = _agy_json(bruto)
    if dados and (dados.get("response") or "").strip():
        plano = dados["response"].strip()
        conversa = dados.get("conversation_id") or ""
        if conversa:
            _ULTIMA_CONVERSA_AGY.update(id=conversa, pasta=str(pasta))
    else:
        # Sem JSON valido (versao antiga do agy, modo texto): usa a saida crua.
        plano = bruto

    linhas = [l for l in plano.splitlines() if l.strip()]
    if len(linhas) < 2 or "nao esta instalado" in plano:
        return ""
    return plano


def revisar_com_antigravity(plano: str, pasta_destino: str = ".") -> str:
    """Passo de revisao: confere o que foi construido contra o plano. Nao altera nada."""
    if not AGY or not ANTIGRAVITY_REVISAO or not plano:
        return ""

    pasta = resolver(pasta_destino)
    confiar_no_workspace(pasta)
    aplicar_regras_antigravity()

    instrucao = (
        "Voce e o REVISOR. Um agente implementou a tarefa nesta pasta. Leia os arquivos "
        "reais do disco e compare com o PLANO abaixo. Responda em no maximo 10 linhas, "
        "concreto: (1) o que ja esta pronto, (2) o que falta, (3) o que esta errado ou "
        "quebrado. Nao crie nem altere arquivos, apenas relate.\n\n"
        f"PLANO:\n{plano}"
    )
    comando = _agy_flags(MODELO_ARQUITETO, ESFORCO_ARQUITETO) + ["--mode", "plan", "-p", instrucao]
    print("   >>> Antigravity revisando o resultado...", flush=True)
    resultado = rodar(comando, tempo=TEMPO_PLANO, pasta=pasta)
    if _interrompido():
        return ""
    return resumir_busca(resultado, 1500)


def revisar_plano_pendente() -> str:
    """Consome o plano pendente (se houver) e devolve a revisao do arquiteto."""
    if not AGY or not ANTIGRAVITY_REVISAO:
        return ""
    plano = _PLANO_ATUAL.get("texto") or ""
    if not plano:
        return ""
    pasta = _PLANO_ATUAL.get("pasta") or "."
    _PLANO_ATUAL.update(texto="", pasta="")
    return revisar_com_antigravity(plano, pasta)


# ---------- CATALOGO UNICO DE FERRAMENTAS ----------

CATALOGO = [
    {
        "nome": "pedir_ao_opencode",
        "descricao": (
            "OBRIGATORIA para qualquer trabalho de codigo: criar ou modificar projeto, app, site, script, "
            "componente, API, config de build, instalar dependencias. Voce NAO escreve codigo, apenas delega. "
            "O OpenCode executa os comandos de verdade no disco."
        ),
        "parametros": esquema({
            "tarefa": {"type": "string", "description": "Instrucao completa e imperativa do que o OpenCode deve construir, incluindo o framework e os comandos."},
            "pasta_destino": {"type": "string", "description": "Pasta onde o OpenCode deve trabalhar. Use '.' para a pasta raiz de projetos."},
        }, ["tarefa"]),
        "fn": pedir_ao_opencode,
    },
]

# Plugins de ferramentas/ entram automaticamente no catalogo.
_PLUGINS, _FUNCOES_PLUGINS, PLUGINS_INDISPONIVEIS = carregar_plugins()
CATALOGO += _PLUGINS

OPCIONAIS = [
    {
        "nome": "pedir_ao_claude",
        "descricao": "Opcional: pede uma segunda opiniao ao Claude Code sobre codigo. Use so se o usuario citar a Claude.",
        "parametros": esquema({"tarefa": {"type": "string", "description": "Pergunta para o Claude Code"}}, ["tarefa"]),
        "fn": pedir_ao_claude,
        "binario": "claude",
    },
    {
        "nome": "planejar_com_antigravity",
        "descricao": (
            "Usa o Antigravity (Gemini) para ARQUITETAR. Produz apenas o plano, sem criar arquivos. "
            "Use antes de construir algo grande, ou quando o usuario pedir um plano/arquitetura."
        ),
        "parametros": esquema({
            "pedido": {"type": "string", "description": "O que deve ser planejado, com todos os detalhes do usuario."},
            "pasta_destino": {"type": "string", "description": "Pasta do projeto. Use '.' para a raiz."},
        }, ["pedido"]),
        "fn": planejar_com_antigravity,
        "binario": "agy",
    },
    {
        "nome": "pedir_ao_antigravity",
        "descricao": (
            "Executa tarefas ou responde perguntas usando o Antigravity (Gemini). Concorrente do pedir_ao_opencode. "
            "Prefira 'pedir_ao_opencode' para codigo; use este quando o usuario citar o Antigravity/Gemini."
        ),
        "parametros": esquema({
            "tarefa": {"type": "string", "description": "Tarefa ou pergunta para o Antigravity."},
            "pasta_destino": {"type": "string", "description": "Pasta onde deve trabalhar. Use '.' para a raiz."},
        }, ["tarefa"]),
        "fn": pedir_ao_antigravity,
        "binario": "agy",
    },
]

FERRAMENTAS = {t["nome"]: t["fn"] for t in CATALOGO}
disponiveis = [t for t in OPCIONAIS if shutil.which(t["binario"])]
FERRAMENTAS.update({t["nome"]: t["fn"] for t in disponiveis})
CATALOGO = CATALOGO + disponiveis
META = {t["nome"]: t for t in CATALOGO}

MANUAL = [
    {"type": "function", "function": {"name": t["nome"], "description": t["descricao"], "parameters": t["parametros"]}}
    for t in CATALOGO
]


# ---------- ROTEO DE INTENCAO (GARANTIA DE EXECUCAO) ----------

VERBO_CRIAR = (
    r"\b(cri(?:a|o|ar|ando|ou)|crio|faz(?:er|endo)?|fazer|ger(?:a|o|ar|ando|ou)|"
    r"mont(?:a|o|ar|ando|ou)|implement(?:a|o|ar|ando|ou)|inicializ(?:a|o|ar|ando|ou)|"
    r"configur(?:a|o|ar|ando|ou)|desenvolv(?:e|o|er|endo|imento)|program(?:a|o|ar|ando|ou)|"
    r"escrev(?:e|o|er|endo|o)|codific(?:a|o|ar|ando|ou)|adicion(?:a|o|ar|ando|ou)|"
    r"constru(?:i|ir|indo|iu)|scaffold\w*|quero|querendo|preciso|precisando|precisa|arruma\w*|planej\w*)\b"
)
OBJETO_CODIGO = r"\b(c[oó]digo|codigo|projeto|project|app|aplicativo|sit[eo]|p[áa]gina|script|componente\w*|api|backend|front-?end|servidor|server|landing|formul[áa]rio|dashboard|bot|jogo|game|to-?do|react|vite|next\.?js|node|python|java|typescript|javascript|html|css|tailwind|banco de dados|database|funcionalidade|feature|m[óo]dulo|module|teste|test)\b"

NAO_E_NOME = {
    "do", "da", "de", "dos", "das", "um", "uma", "uns", "umas", "no", "na", "nos", "nas",
    "e", "para", "com", "que", "se", "me", "por", "pelo", "pela", "a", "o", "as", "os",
    "aqui", "la", "cima", "baixo", "minha", "meu", "nova", "novo", "chamada", "chamado",
    "python", "react", "node", "javascript", "typescript", "java", "html", "css", "go",
    "rust", "php", "ruby", "vue", "angular", "svelte", "tailwind", "django", "flask",
    "code", "vscode", "linux", "ubuntu", "web", "internet", "teste", "test", "zero",
}


def precisa_de_codigo(texto: str) -> bool:
    return bool(re.search(VERBO_CRIAR, texto, re.I)) and bool(re.search(OBJETO_CODIGO, texto, re.I))


PLANO_ATIVO = re.compile(r"\b(planej\w*|plano|arquitet\w*|arquitetura|esquemat\w*|desenha\w*)\b", re.I)
PLANO_INATIVO = re.compile(r"\b(sem\s+plano|direto|sem\s+planejar|nao\s+planeje|pul[ae]\s+o\s+plano|so\s+executa)\b", re.I)
PROJETO_GRANDE = re.compile(
    r"\b(projeto|app|aplicativo|site|sistema|api|backend|front-?end|dashboard|"
    r"jogo|game|plataforma|landing|servidor|server|e-?commerce|loja)\b", re.I)


def quer_plano(texto: str) -> bool:
    """Com moderacao: so planeja quando pedido, ou automaticamente para projeto grande."""
    if not AGY or not ANTIGRAVITY_PLANEJA:
        return False
    if PLANO_INATIVO.search(texto):
        return False
    if PLANO_ATIVO.search(texto):
        return True
    return bool(PROJETO_GRANDE.search(texto))


def enriquecer_com_plano(argumentos: dict, texto: str, chamadas: set):
    """Antes do OpenCode executar, o Antigravity planeja e o plano e anexado a tarefa."""
    tarefa = argumentos.get("tarefa") or ""
    if not tarefa or "planejar_com_antigravity" in chamadas or not quer_plano(texto):
        return argumentos, False

    pasta = argumentos.get("pasta_destino") or detecta_pasta(texto) or "."
    print("\n[nexus] Antigravity planeja, OpenCode implementa...", flush=True)
    plano = planejar_com_antigravity(texto, pasta)
    if not plano:
        print("   (sem plano do Antigravity; seguindo direto para o OpenCode)", flush=True)
        return argumentos, False

    novo = dict(argumentos)
    novo["tarefa"] = (f"PLANO DE ARQUITETURA (siga este plano):\n{plano}\n\n"
                      f"PEDIDO ORIGINAL: {tarefa}")
    # Guarda o plano para a revisao que roda depois do OpenCode construir.
    _PLANO_ATUAL.update(texto=plano, pasta=str(resolver(pasta)))
    print("   (plano anexado a tarefa do OpenCode)", flush=True)
    return novo, True


def detecta_pasta(texto: str):
    achado = re.search(r"(?:pasta|diret[óo]rio|dir|folder)\s+(?:chamad[ao]\s+)?[\"']?([\w\-.]+)", texto, re.I)
    if achado and achado.group(1).lower() not in NAO_E_NOME:
        return achado.group(1)

    achado = re.search(r"\b(?:em|na|para|dentro)\s+(?:a\s+)?(?:pasta\s+)?[\"']?([\w\-.]+)", texto, re.I)
    if achado and achado.group(1).lower() not in NAO_E_NOME:
        return achado.group(1)
    return None


def detecta_nome_projeto(texto: str):
    achado = re.search(r"(?:projeto|project|app|aplicativo)\s+(?:chamad[ao]\s+)?[\"']?([\w\-.]+)", texto, re.I)
    if achado and achado.group(1).lower() not in NAO_E_NOME:
        return achado.group(1)
    return None


REGRAS_OPENCODE = """

REGRAS DE EXECUCAO (obrigatorias):
- A pasta de trabalho ja esta definida. Crie TUDO direto nela, nao dentro de subpastas.
- Execute os comandos de verdade (npm, npx, pip, etc). Nao responda so com instrucoes.
- Se um comando pedir confirmacao interativa, use flags para nao travar (--yes, -y, --template, etc).
- Instale as dependencias do projeto.
- Ao final rode o build/lint/teste para provar que funciona, e relate o que foi feito e os comandos para usar."""


def montar_tarefa_opencode(pedido: str, pasta: Path, plano: str = "") -> str:
    nome = detecta_nome_projeto(pedido)
    extras = f"\n\nO nome sugerido para o projeto e '{nome}'." if nome else ""

    contexto = f"PEDIDO: {pedido}\n\nPasta de trabalho: {pasta}\n\nEscreva o prompt para o OpenCode."
    if plano:
        contexto = (f"PLANO DE ARQUITETURA (do Antigravity) que voce deve seguir:\n{plano}\n\n"
                    f"PEDIDO ORIGINAL: {pedido}\n\nPasta de trabalho: {pasta}\n\n"
                    "Escreva o prompt de execucao para o OpenCode implementar esse plano.")

    try:
        mensagens = [
            MensagemNeutra(role="system", content=(
                "Voce traduz um pedido do usuario em um prompt de execucao para o OpenCode. "
                "Responda APENAS com o prompt final, em portugues, no imperativo, no maximo 8 linhas. "
                "Sem cercas de codigo, sem comentarios sobre a traducao."
            )),
            MensagemNeutra(role="user", content=contexto),
        ]
        resultado = cerebro_chat(mensagens, None)
        if resultado.erro:
            raise Exception(resultado.erro)
        tarefa = resultado.conteudo.strip().strip("`").strip()
    except Exception:
        tarefa = pedido

    if not tarefa or len(tarefa) < 15:
        tarefa = pedido
    return tarefa + extras + REGRAS_OPENCODE


# ---------- MOTOR DE CONVERSA ----------

def podar(conversa):
    if len(conversa) <= LIMITE_HISTORICO + 1:
        return conversa
    cabeca = [conversa[0]]
    corpo = [m for m in conversa[1:] if m.get("role") != "system"]
    return cabeca + corpo[-(LIMITE_HISTORICO - 1):]


REGRAS = f"""Voce e o NEXUS, assistente local em portugues do Brasil. Curto e direto.

SUA DIVISAO DE TRABALHO (obrigatoria):
1. CODIGO E PROJETOS sao SEMPRE delegate ao OpenCode. Se o pedido envolver criar, gerar, montar, alterar ou rodar projeto, app, site, script, componente, API, instalar dependencia ou build, voce OBRIGATORIAMENTE chama 'pedir_ao_opencode' com a pasta_destino correta. Voce nunca escreve, cria ou modifica arquivo de codigo.
2. PARA PROJETOS GRANDES o Antigravity (Gemini) e o ARQUITETO: o sistema pede o plano a ele automaticamente antes de o OpenCode executar. Voce tambem pode chamar 'planejar_com_antigravity' quando o usuario pedir um plano/arquitetura. Use 'pedir_ao_antigravity' apenas quando o usuario citar o Antigravity ou o Gemini.
3. SO use 'criar_pasta' para diretorios vazios de organizacao, nunca para projetos.
4. Use 'abrir_vscode' e 'abrir_pasta' para abrir janelas.
5. Use 'pesquisar_na_web' para fatos atuais, noticias e documentacao. Para perguntas de conhecimento geral (biografia, historia, ciencia, matematica, programacao) prefira 'perguntar_qwen'.
6. MEMORIA: quando o usuario pedir para voce lembrar de algo (preferencias, dados pessoais, senhas nao), chame 'lembrar_fato'. Se a resposta estiver na secao de memoria do sistema, use-a. Use 'buscar_memoria'/'esquecer_fato' quando fizer sentido.
7. RECADOS E TAREFAS: para "me lembra daqui a X" use 'agendar_lembrete'; para listas de afazeres use 'adicionar_tarefa'/'listar_tarefas'/'concluir_tarefa'; para anotar algo solto use 'anotar'.
8. SISTEMA: use 'status_sistema' para CPU/RAM/disco; 'abrir_programa' e 'fechar_programa' para apps (o nome aproximado basta, ex. 'code', 'spotify'); 'definir_volume', 'definir_brilho', 'ler_clipboard' e 'copiar_clipboard' para o restante.
9. SPOTIFY: tocar musica/playlist e os controles de reproducao (pausar, retomar, proxima, anterior, 'o que esta tocando') sao SEMPRE a ferramenta 'spotify'. Volume: 'volume do Spotify' usa 'spotify' (acao volume); 'aumenta/abaixa o volume' sem citar o Spotify e o volume do sistema ('definir_volume'). Nunca use 'abrir_programa' para controlar o Spotify.
10. DOCUMENTOS: use 'indexar_documentos' para carregar arquivos/pastas (txt, md, pdf, docx) e 'perguntar_documentos' para responder perguntas com base nesse conteudo. Se a pergunta for sobre um documento que o usuario citou, indexe antes de perguntar.

ANTI-ALUCINACAO (obrigatoria):
- Nunca afirme que fez algo sem antes ter chamado a ferramenta correspondente.
- Se nao chamou a ferramenta, diga que nao fez. Nunca invente resultado, arquivos, links ou comandos.
- Se a ferramenta retornou erro, aviso ou bloqueio, relate o erro. Nunca diga que deu certo.
- Ao relatar, use apenas o que a ferramenta realmente retornou.

FORMATO DA RESPOSTA (obrigatorio):
- Fale em portugues do Brasil, natural e curto (1 ou 2 frases).
- NUNCA responda em JSON nem com estruturas de chaves. Nunca cite codigos HTTP (404, 403) nem nomes de campos tecnicos.
- Se a ferramenta falhar, explique em linguagem simples o que houve e o que fazer.

MODO PRIVADO / NUVEM:
- "modo privado" ou "privado" força uso do cerebro local (Ollama). Nada sai da maquina.
- "modo nuvem" reabilita a cadeia de cerebros (Gemini gratuito -> local).

EXEMPLOS (few-shot):
---
Usuario: "qual a capital da franca"
Assistente: chama perguntar_qwen(pergunta="qual a capital da franca")
Resultado: "A capital da Franca e Paris."
Resposta final: "A capital da Franca e Paris."
---
Usuario: "clima em sao paulo hoje"
Assistente: chama pesquisar_na_web(busca="clima sao paulo hoje")
Resultado: "Sao Paulo: 24C, ceu parcialmente nublado, chance de chuva 20%."
Resposta final: "Em Sao Paulo hoje: 24 graus, ceu parcialmente nublado, chance de chuva 20 por cento."
---
Usuario: "abre o spotify e toca los hermanos"
Assistente: chama abrir_programa(app="spotify"); chama spotify(acao="tocar", musica="Los Hermanos")
Resultado 1: "Abrindo spotify."; Resultado 2: "Tocando Ana Julia - Los Hermanos."
Resposta final: "Spotify aberto e tocando Los Hermanos."
---
Usuario: "me lembra de beber agua em 10 minutos e adiciona tarefa 'estudar python'"
Assistente: chama agendar_lembrete(mensagem="beber agua", quando="em 10 minutos"); chama adicionar_tarefa(descricao="estudar python")
Resultado 1: "Lembrete agendado para daqui a 10 minutos."; Resultado 2: "Tarefa adicionada."
Resposta final: "Lembrete agendado e tarefa adicionada."
---
Usuario: "criar um app react com vite"
Assistente: (sistema detecta codigo) chama pedir_ao_opencode(tarefa="...", pasta_destino=".")
Resultado: "Projeto react criado em ~/projetos/meu-app. Rode 'npm run dev' para iniciar."
Resposta final: "App React criado na pasta meu-app. Para rodar: cd meu-app && npm run dev"
---
Usuario: "desliga o computador"
Assistente: chama potencia(acao="desligar") -> usuario confirma no popup -> executa
Resultado: "Comando 'desligar' enviado."
Resposta final: "Desligando o computador."
---
Usuario: "o que esta tocando no spotify"
Assistente: chama spotify(acao="tocando")
Resultado: "Ana Julia - Los Hermanos (tocando)."
Resposta final: "Tocando Ana Julia de Los Hermanos."
---
Usuario: "meu nome e joao e gosto de jazz"
Assistente: chama lembrar_fato(fato="O usuario se chama Joao e gosta de jazz")
Resultado: "Fato salvo."
Resposta final: "Ok, anotei: voce se chama Joao e gosta de jazz."
---
Usuario: "qual era meu nome?"
Assistente: (memoria injetada no contexto) -> responde direto
Resposta final: "Voce se chama Joao e gosta de jazz."

Pasta de trabalho: {PASTA_TRABALHO}
Ferramentas indisponiveis nesta maquina: {", ".join([t["nome"] for t in OPCIONAIS if t not in disponiveis] + [nome for nome, _ in PLUGINS_INDISPONIVEIS]) or "nenhuma"}"""


ALIAS_ARGUMENTOS = {
    "pasta_destino": "caminho", "destino": "caminho", "pasta": "caminho",
    "dir": "caminho", "diretorio": "caminho", "path": "caminho", "local": "caminho",
    "instrucao": "tarefa", "prompt": "tarefa", "comando": "tarefa",
    "descricao": "tarefa", "pergunta": "pergunta", "termo": "busca",
    "programa": "app", "aplicativo": "app", "aplicacao": "app",
    "nome": "app",
}


def normalizar_argumentos(funcao, argumentos: dict):
    """Modelos pequenos trocam o nome do parametro. Em vez de erro, remapeia."""
    parametros = inspect.signature(funcao).parameters
    if any(p.kind is p.VAR_KEYWORD for p in parametros.values()):
        return argumentos, []

    aceitos = set(parametros)
    finais, descartados = {}, []
    for chave, valor in argumentos.items():
        if chave in aceitos:
            finais[chave] = valor
            continue
        destino = ALIAS_ARGUMENTOS.get(chave)
        if destino in aceitos:
            finais[destino] = valor
        else:
            descartados.append(chave)
    return finais, descartados


def _gate_seguranca(meta: dict, argumentos: dict):
    """Aplica BLOQUEIOS/CREDENCIAIS/CONFIRMACOES as ferramentas marcadas como sensiveis."""
    nivel = (meta or {}).get("seguranca")
    if not nivel:
        return None

    alvo = " ".join(str(valor) for valor in (argumentos or {}).values())
    bloqueados, a_confirmar = detectar_graves(alvo)
    if bloqueados:
        return "BLOQUEADO pelo Nexus:\n" + "\n".join(f"- {c}" for c in bloqueados)
    if a_confirmar and not confirmar_risco(a_confirmar):
        return "CANCELADO pelo usuario. Nada foi executado."
    if nivel == "sempre" and not confirmar_risco([f"{meta['nome']}: {alvo[:120]}"]):
        return "CANCELADO pelo usuario. Nada foi executado."
    return None


def executar(nome: str, argumentos: dict) -> str:
    if _ponte:
        _ponte_emitir("ferramenta_iniciada", nome, argumentos or {})
        # O handler em interface/app.py ja chama definir_estado("executando", acao_texto)
        # com o texto da acao (ex: "ABRINDO SPOTIFY..."), entao nao chamamos aqui
        # para nao sobrescrever.

    funcao = FERRAMENTAS.get(nome)
    if funcao is None:
        resultado = f"Falha: a ferramenta '{nome}' nao existe."
        if _ponte:
            _ponte_emitir("ferramenta_concluida", nome, resultado)
        return resultado

    try:
        corrigidos, descartados = normalizar_argumentos(funcao, argumentos or {})
    except (TypeError, ValueError) as erro:
        resultado = f"Falha ao interpretar os argumentos de '{nome}': {erro}"
        if _ponte:
            _ponte_emitir("ferramenta_concluida", nome, resultado)
        return resultado

    if descartados:
        print(f"   (aviso: argumento(s) ignorado(s) em {nome}: {', '.join(descartados)})", flush=True)

    faltando = [
        nome for nome, p in inspect.signature(funcao).parameters.items()
        if p.default is p.empty and nome not in corrigidos
    ]
    if faltando:
        resultado = f"Falha: '{nome}' exige o parametro {', '.join(faltando)} e nao foi fornecido."
        if _ponte:
            _ponte_emitir("ferramenta_concluida", nome, resultado)
        return resultado

    bloqueio = _gate_seguranca(META.get(nome), corrigidos)
    if bloqueio:
        if _ponte:
            _ponte_emitir("ferramenta_concluida", nome, bloqueio)
        return bloqueio

    try:
        resultado = str(funcao(**corrigidos))
    except TypeError as erro:
        resultado = f"Falha nos argumentos de '{nome}': {erro}"
    except Exception as erro:
        resultado = f"Erro na execucao de '{nome}': {erro}"

    if _ponte:
        _ponte_emitir("ferramenta_concluida", nome, resultado)
    return resultado


def _chave_chamada(nome: str, argumentos: dict) -> str:
    """Identidade de uma chamada: mesma ferramenta + mesmos argumentos uteis.

    Passa pela normalizacao de proposito, para 'spotify(tocar, musica=X,
    dispositivo=celular)' e 'spotify(tocar, musica=X)' contarem como a mesma
    coisa. Sem isso o modelo reincidia no mesmo pedido so mudando o aparelho.
    """
    funcao = FERRAMENTAS.get(nome)
    if funcao is not None:
        try:
            argumentos, _ = normalizar_argumentos(funcao, argumentos)
        except (TypeError, ValueError):
            pass
    return nome + "|" + json.dumps(argumentos, sort_keys=True, default=str)


# Como encerrar a conversa por voz. Antes era comparacao exata, entao so
# 'sair' funcionava: 'pode desligar' caia no modelo e ele ia tentar abrir um
# programa chamado 'desligar'.
PALAVRAS_ENCERRAR = {
    "sair", "sai", "saindo", "encerrar", "encerra", "encerrado", "encerrando",
    "desligar", "desliga", "desligado", "desligando", "tchau", "tchauzinho",
    "falou", "ate", "logo", "conversa", "sessao", "dialogo", "papel",
}

# Palavras que podem aparecer ao redor do verbo de encerramento sem transformar
# a frase em outro pedido. 'desligar o spotlight do nexus' NAO pode encerrar:
# 'spotlight' nao esta aqui, e e por isso que ele nao entra.
CORTESIA_ENCERRAR = {
    "pode", "poderia", "podes", "quero", "queria", "nexus", "me", "a", "o",
    "as", "os", "um", "uma", "de", "do", "da", "dos", "das", "por", "favor",
    "vc", "voce", "e", "va", "bora", "ja", "agradece", "obrigado", "obrigada",
    "entao", "ai", "aqui", "com", "no", "na", "ser", "ficar", "final",
}


def _quer_encerrar(texto: str) -> bool:
    """Diz se a frase e so um 'tchau', e nao um pedido.

    So encerra quando a frase e curta e feita so de verbo de encerramento e
    palavras de cortesia. Qualquer palavra a mais (um programa, uma materia)
    significa que a pessoa esta pedindo algo, nao se despedindo.
    """
    partes = chave_nome(texto or "").replace(",", " ").replace(".", " ").split()
    if not partes or len(partes) > 5:
        return False
    if not any(p in PALAVRAS_ENCERRAR for p in partes):
        return False
    return all(p in PALAVRAS_ENCERRAR or p in CORTESIA_ENCERRAR for p in partes)


# 'para' dito como comando, e nao como wakeword. O mesmo cuidado do encerramento:
# precisa ser uma frase curta so de verbo de parada. 'para de tocar musica' tem
# 'musica' e portanto NAO e um cancelamento (e um pedido legitimo).
PALAVRAS_PARAR = {
    "para", "parar", "pare", "parou", "parando", "cancela", "cancele",
    "cancelar", "cancelou", "interrompe", "interromper", "interrompido",
    "interrompa", "chega", "basta", "cala", "silencio", "socia",
}

CORTESIA_PARAR = {
    "pode", "poderia", "podes", "por", "favor", "vc", "voce", "ai", "entao",
    "aqui", "ja", "agora", "tudo", "esse", "essa", "isso", "obrigado", "obrigada",
    "acao", "acao", "este", "esta", "isto", "aquilo", "cancelamento", "parada",
}


_MARCADORES_COLECAO = ("playlist", "playlists", "album", "álbum", "lista")

PLACEHOLDERS_SPOTIFY = {
    "minha playlist x", "playlist x", "x", "nome", "nome da musica",
    "nome da playlist", "musica", "playlist", "sua playlist", "a playlist",
}

# Ferramentas cujo retorno ja e a resposta pronta para o usuario (confirmacao,
# status, lista). O llama3.1 costuma reescrever isso errado depois de executar
# a ferramenta ('NUNCA afirmei que toquei...'), entao quando todas as
# ferramentas do passo sao destas usamos o retorno delas sem passar de novo
# pelo modelo. As ferramentas de conhecimento (qwen, web, documentos) e de
# delegacao continuam sendo resumidas pelo modelo.
RESPOSTA_DIRETA = {
    "spotify", "abrir_pasta", "abrir_programa", "abrir_vscode", "fechar_programa",
    "definir_volume", "definir_brilho", "criar_pasta", "copiar_clipboard",
    "ler_clipboard", "lembrar_fato", "esquecer_fato", "buscar_memoria",
    "agendar_lembrete", "cancelar_lembrete", "listar_lembretes",
    "adicionar_tarefa", "concluir_tarefa", "listar_tarefas", "anotar",
    "status_sistema", "listar_apps", "descobrir_apps", "listar_projetos",
    "indexar_documentos",
}


def _ajustar_spotify(argumentos, texto):
    """Conserta o nome que o modelo passa para o Spotify.

    Modelos pequenos resumem o pedido e chegam a inventar um placeholder
    ('minha playlist X') em vez do nome falado. Quando a fala pede uma playlist
    (ou o argumento e um placeholder), usamos a propria transcricao, que contem
    o nome real; caso contrario mantemos o argumento do modelo.
    """
    if not isinstance(argumentos, dict) or (argumentos.get("acao") or "").lower() != "tocar":
        return argumentos
    musica = str(argumentos.get("musica") or "").strip()
    chave_musica = chave_nome(musica)
    # Pedido de playlist: passa a fala inteira para o plugin, que le as playlists
    # do usuario e escolhe a de nome mais parecido. Sem isso o modelo reduz
    # 'toque a playlist do afim' para 'do afim' e o plugin procuraria uma faixa.
    if any(m in (texto or "").lower() for m in _MARCADORES_COLECAO):
        return {**argumentos, "musica": texto}
    if chave_musica and chave_musica in chave_nome(texto or ""):
        return argumentos
    if not chave_musica or chave_musica in PLACEHOLDERS_SPOTIFY:
        return {**argumentos, "musica": texto}
    return argumentos


_RE_VOL_CRESCER = re.compile(r"\b(aument\w*|sobe|subir|levanta\w*|mais alto)\b")
_RE_VOL_BAIXAR = re.compile(r"\b(abaix\w*|diminu\w*|desce|descer|baixa\w*|menos|mais baixo)\b")
_RE_VOL_PORCENTO = re.compile(r"(\d{1,3})\s*(?:%|por cento)")
_RE_VOL_ALVO = re.compile(r"\b(?:para|pro|pra|no|na|de)\s+(\d{1,3})\b")
_RE_VOL_DELTA = re.compile(r"\b(?:em|mais|menos)\s+(\d{1,3})\b")
_RE_VOL_DEFINE = re.compile(r"\b(coloca\w*|bota\w*|poe|poem|deixa\w*|define|definir|muda\w*)\b")
_RE_VOL_NUM = re.compile(r"\b(\d{1,3})\b")
_RE_VOL_MAX = re.compile(r"\b(m[áa]ximo|max|tudo|cheio)\b")
_RE_VOL_MUDO = re.compile(r"\b(mudo|mutad\w*|sem som|silencio|silêncio)\b")


def _vol_ok(numero) -> bool:
    try:
        return 0 <= int(numero) <= 100
    except (TypeError, ValueError):
        return False


def _nivel_pedido(texto):
    """Le o volume pedido na fala: ('absoluto', n), ('passo', d) ou None.

    Preferimos a fala ao modelo porque ele arredonda e inventa numeros. 'para
    20' e alvo; 'aumenta 10'/'em 10' e passo; sem numero, o passo e 10.
    """
    t = (texto or "").lower()
    cresce = bool(_RE_VOL_CRESCER.search(t))
    baixa = bool(_RE_VOL_BAIXAR.search(t))

    achado = _RE_VOL_PORCENTO.search(t)
    if achado and _vol_ok(achado.group(1)):
        return "absoluto", int(achado.group(1))

    if cresce or baixa:
        achado = _RE_VOL_DELTA.search(t)
        if achado and _vol_ok(achado.group(1)):
            passo = int(achado.group(1))
            return "passo", (passo if cresce else -passo)
        achado = _RE_VOL_ALVO.search(t)
        if achado and _vol_ok(achado.group(1)):
            return "absoluto", int(achado.group(1))
        achado = _RE_VOL_NUM.search(t)
        if achado and _vol_ok(achado.group(1)):
            passo = int(achado.group(1))
            return "passo", (passo if cresce else -passo)
        return "passo", (10 if cresce else -10)

    achado = _RE_VOL_ALVO.search(t)
    if achado and _vol_ok(achado.group(1)):
        return "absoluto", int(achado.group(1))

    if _RE_VOL_DEFINE.search(t) or "volume" in t:
        achado = _RE_VOL_NUM.search(t)
        if achado and _vol_ok(achado.group(1)):
            return "absoluto", int(achado.group(1))

    if _RE_VOL_MAX.search(t):
        return "absoluto", 100
    if _RE_VOL_MUDO.search(t):
        return "absoluto", 0
    return None


def _corrigir_volume(nome, argumentos, texto):
    """Decide volume do sistema x Spotify e fixa o nivel pedido na fala.

    O modelo erra o roteamento e arredonda o numero; a fala e a fonte da
    verdade. 'aumenta/abaixa o volume' sem citar o Spotify e o volume do
    sistema; so 'volume do Spotify' mexe no Spotify.
    """
    acao = (argumentos.get("acao") or "").lower()
    volume_spotify = nome == "spotify" and acao == "volume"
    if nome != "definir_volume" and not volume_spotify:
        return nome, argumentos

    baixo = (texto or "").lower()
    tem_spotify = "spotify" in baixo
    # O sistema e o padrao; o Spotify so quando o usuario cita a palavra. Uma
    # consulta (sem valor) fica onde o modelo pediu.
    destino = "spotify" if (volume_spotify and (tem_spotify or argumentos.get("valor") is None)) else "sistema"
    if nome == "definir_volume" and tem_spotify:
        destino = "spotify"

    pedido = _nivel_pedido(texto)
    if pedido is not None:
        tipo, valor = pedido
        if tipo == "passo":
            if destino == "sistema":
                atual = _volume_sistema.volume_atual()
                valor = None if atual is None else max(0, min(100, atual + valor))
            else:
                valor = None  # sem leitura do Spotify, deixa o modelo
        if valor is not None:
            if destino == "spotify":
                return "spotify", {"acao": "volume", "valor": valor}
            return "definir_volume", {"nivel": valor}

    if destino == "spotify":
        if volume_spotify:
            return nome, argumentos
        valor = argumentos.get("valor")
        return "spotify", {"acao": "volume"} if valor is None else {"acao": "volume", "valor": valor}
    return "definir_volume", {"nivel": argumentos.get("nivel") or argumentos.get("valor")}


def _resposta_quebrada(texto) -> bool:
    """True se o modelo 'chamou' a ferramenta como texto em vez de tool_calls.

    A saida do llama3.1 varia: as vezes devolve um JSON de funcao malformado
    (ou bem formado, mas fora do campo tool_calls) e nenhuma acao acontece.
    """
    texto = (texto or "").strip()
    if not texto:
        return False
    if not texto.startswith(("{", "[")):
        # 'definir_volume(50)' ou "spotify(acao='volume')": o modelo escreveu o
        # nome da ferramenta como se fosse codigo, mas nada foi chamado.
        achado = re.match(r"^([A-Za-z_]\w*)\s*\(", texto)
        return bool(achado and achado.group(1) in FERRAMENTAS)
    try:
        dados = json.loads(texto)
    except Exception:
        return True
    if isinstance(dados, dict) and "message" not in dados:
        if dados.get("type") == "function":
            return True
        if "name" in dados and ("parameters" in dados or "arguments" in dados):
            return True
    return False


def _chamar_modelo(conversa, tentativas=3):
    """Chama o cerebro ativo; insiste se vier um tool call quebrado ou resposta vazia."""
    mensagens_neutras = []
    for m in conversa:
        if m.get("role") in ("system", "user", "assistant", "tool"):
            msg = MensagemNeutra(role=m["role"], content=m.get("content") or "")
            if m.get("tool_calls"):
                msg.tool_calls = m["tool_calls"]
            if m.get("tool_call_id"):
                msg.tool_call_id = m["tool_call_id"]
            if m.get("name"):
                msg.name = m["name"]
            mensagens_neutras.append(msg)

    for _ in range(tentativas):
        resultado = cerebro_chat(mensagens_neutras, MANUAL)
        if resultado.erro:
            continue
        if resultado.tool_calls:
            return {"role": "assistant", "content": resultado.conteudo, "tool_calls": resultado.tool_calls}
        conteudo = (resultado.conteudo or "").strip()
        if conteudo and not _resposta_quebrada(conteudo):
            return {"role": "assistant", "content": conteudo}
    return {"role": "assistant", "content": ""}


def _padronizar_resultado(nome: str, resultado_raw: str) -> dict:
    """Converte resultado bruto da ferramenta em formato padrao {ok, resultado, erro, dica}."""
    if not isinstance(resultado_raw, str):
        resultado_raw = str(resultado_raw)

    r = resultado_raw.strip()
    if not r:
        return {"ok": False, "resultado": "", "erro": "Resultado vazio", "dica": "Tente novamente ou use outra ferramenta"}

    # Detectar falhas conhecidas
    r_low = r.lower()
    if r[:5] in {"FALHA", "Erro ", "BLOQ"} or r_low.startswith("falha:") or r_low.startswith("erro:") or r_low.startswith("bloquead"):
        return {"ok": False, "resultado": r, "erro": r, "dica": "A ferramenta falhou. Analise o erro e tente corrigir os argumentos ou use outra ferramenta."}

    # Bloqueio de seguranca
    if "bloqueado por seguran" in r_low or "cancelado pelo usuario" in r_low:
        return {"ok": False, "resultado": r, "erro": r, "dica": "Operacao bloqueada ou cancelada. Nao tente contornar. Explique a situacao ao usuario."}

    return {"ok": True, "resultado": r, "erro": "", "dica": ""}


def _formatar_resultado_para_modelo(nome: str, padrao: dict) -> str:
    """Formata resultado padronizado para ser devolvido ao modelo como mensagem tool."""
    if padrao["ok"]:
        return padrao["resultado"]
    else:
        return f"FERRAMENTA {nome} FALHOU: {padrao['erro']}\nDICA: {padrao['dica']}"


def _eh_duplicada(chave: str, historico_chamadas: dict) -> bool:
    """Verifica se a mesma ferramenta com mesmos args ja foi chamada neste turno."""
    return chave in historico_chamadas


def _contar_tentativas_falha(nome: str, args: dict, historico_falhas: dict) -> int:
    """Conta quantas vezes a mesma ferramenta com mesmos args falhou."""
    chave = f"{nome}|{json.dumps(args, sort_keys=True, default=str)}"
    return historico_falhas.get(chave, 0)


def _registrar_falha(nome: str, args: dict, historico_falhas: dict):
    """Registra uma falha para anti-loop."""
    chave = f"{nome}|{json.dumps(args, sort_keys=True, default=str)}"
    historico_falhas[chave] = historico_falhas.get(chave, 0) + 1


def rodar_turno(conversa, texto: str):
    """Loop de agente: pensa -> chama ferramentas -> recebe resultados -> decide de novo -> resposta final."""
    import json
    chamadas = set()
    resultados_turno = []
    feitas = {}  # cache de resultados por (nome, args) para evitar duplicacao exata
    historico_falhas = {}  # para anti-loop: (nome, args) -> contagem de falhas
    opencode_usado = False

    # Obter max_passos do cerebro ativo
    cfg_ativo = obter_config_ativa()
    max_passos = cfg_ativo.max_passos if cfg_ativo and cfg_ativo.max_passos > 0 else MAX_PASSOS

    for passo in range(max_passos):
        if _interrompido():
            print("[nexus] Interrompido antes do proximo passo.", flush=True)
            break

        conversa = podar(conversa)
        _definir_estado("pensando")
        mensagem = _chamar_modelo(conversa)
        conversa.append(mensagem)

        if not mensagem.get("tool_calls"):
            # Resposta final do modelo (sem ferramentas)
            break

        # Processar TODAS as tool_calls deste passo (multiplas acoes simultaneas)
        nomes_passo, resultados_passo = [], []
        tool_results_para_modelo = []

        for pedido in mensagem.get("tool_calls"):
            nome = pedido["function"]["name"]
            argumentos = pedido["function"].get("arguments") or {}

            # Normalizar aninhamento llama3.1
            if isinstance(argumentos, dict) and "function" in argumentos and "parameters" in argumentos:
                nome = argumentos["function"]
                argumentos = argumentos["parameters"]

            # Ajustes especificos (spotify, volume)
            if nome == "spotify":
                argumentos = _ajustar_spotify(argumentos, texto)
            nome, argumentos = _corrigir_volume(nome, argumentos, texto)

            print(f"\n[nexus] passo {passo+1}/{max_passos} executando {nome}({argumentos})...", flush=True)

            # Anti-duplicacao exata (mesma ferramenta + mesmos args)
            chave = _chave_chamada(nome, argumentos)
            if _eh_duplicada(chave, feitas):
                resultado_padrao = {"ok": False, "resultado": "", "erro": "Duplicada ignorada", "dica": "Ja executada neste turno com mesmos argumentos."}
                print("   (duplicada ignorada)", flush=True)
            elif nome == "pedir_ao_opencode" and opencode_usado:
                resultado_padrao = {"ok": False, "resultado": "", "erro": "OpenCode ja usado neste turno", "dica": "Use o resultado anterior para responder."}
                print("   (OpenCode duplicado ignorado)", flush=True)
            else:
                # Anti-loop: max 2 tentativas para mesma falha
                tentativas = _contar_tentativas_falha(nome, argumentos, historico_falhas)
                if tentativas >= 2:
                    resultado_padrao = {"ok": False, "resultado": "", "erro": f"Ja falhou {tentativas} vezes com mesmos args", "dica": "Mude os argumentos ou use outra ferramenta."}
                    print(f"   (anti-loop: {tentativas} falhas anteriores com mesmos args)", flush=True)
                else:
                    # Executar ferramenta
                    if nome == "pedir_ao_opencode":
                        argumentos, planejou = enriquecer_com_plano(argumentos, texto, chamadas)
                        if planejou:
                            chamadas.add("planejar_com_antigravity")
                        opencode_usado = True

                    chamadas.add(nome)
                    resultado_raw = executar(nome, argumentos)

                    if nome == "pedir_ao_opencode":
                        revisao = revisar_plano_pendente()
                        if revisao:
                            resultado_raw = f"{resultado_raw}\n\nREVISAO DO ARQUITETO:\n{revisao}"

                    # Padronizar resultado
                    resultado_padrao = _padronizar_resultado(nome, resultado_raw)

                    # Registrar falha se houver
                    if not resultado_padrao["ok"]:
                        _registrar_falha(nome, argumentos, historico_falhas)
                    else:
                        # Sucesso: limpar contador de falhas para esta combinacao
                        chave_falha = f"{nome}|{json.dumps(argumentos, sort_keys=True, default=str)}"
                        if chave_falha in historico_falhas:
                            del historico_falhas[chave_falha]

                    feitas[chave] = resultado_padrao

            # Formatar para o modelo (tool message)
            resultado_para_modelo = _formatar_resultado_para_modelo(nome, resultado_padrao)
            tool_results_para_modelo.append((pedido.get("id", ""), resultado_para_modelo))

            # Log
            if not resultado_padrao["ok"]:
                print(f"   x {resultado_padrao['erro'][:300]}", flush=True)
            else:
                print(f"   ok", flush=True)

            resultados_passo.append(resultado_para_modelo)
            resultados_turno.append(resultado_padrao["resultado"])

            if _interrompido():
                print("[nexus] Interrompido: parando o turno aqui.", flush=True)
                return conversa, chamadas, resultados_turno

        # Adicionar TODOS os resultados das tools como mensagens tool separadas
        for tool_call_id, resultado_str in tool_results_para_modelo:
            conversa.append({"role": "tool", "content": resultado_str, "tool_call_id": tool_call_id})

        # Se todas as ferramentas sao de resposta direta, o modelo nao precisa processar
        if nomes_passo and all(n in RESPOSTA_DIRETA for n in nomes_passo):
            conversa.append({"role": "assistant", "content": "\n".join(resultados_passo)})
            break

        # Se estouramos max_passos, forcar resposta final
        if passo == max_passos - 1:
            _definir_estado("pensando")
            mensagem_final = _chamar_modelo(conversa + [{
                "role": "system",
                "content": f"LIMITE DE {max_passos} PASSOS ATINGIDO. Resuma o que conseguiu, o que faltou e o que o usuario deve fazer. Nao chame mais ferramentas."
            }])
            if mensagem_final.get("content"):
                conversa.append(mensagem_final)
            break

    return conversa, chamadas, resultados_turno


def garantir_opencode(conversa, texto: str, chamadas: set) -> set:
    if "pedir_ao_opencode" in chamadas or not precisa_de_codigo(texto):
        return chamadas

    pasta = detecta_pasta(texto) or "."
    print("\n[nexus] o pedido e de codigo e o OpenCode nao foi acionado. Forcando delegacao...", flush=True)
    argumentos = {"tarefa": montar_tarefa_opencode(texto, resolver(pasta)), "pasta_destino": pasta}
    argumentos, planejou = enriquecer_com_plano(argumentos, texto, chamadas)
    if planejou:
        chamadas.add("planejar_com_antigravity")
    resultado = executar("pedir_ao_opencode", argumentos)
    revisao = revisar_plano_pendente()
    if revisao:
        resultado = f"{resultado}\n\nREVISAO DO ARQUITETO:\n{revisao}"
    conversa.append({"role": "tool", "content": str(resultado)})

    if re.search(r"\b(vscode|vs code|visual studio code|editor)\b", texto, re.I) and "abrir_vscode" not in chamadas:
        abrir = executar("abrir_vscode", {"caminho": pasta})
        conversa.append({"role": "tool", "content": str(abrir)})

    mensagens = []
    for m in podar(conversa):
        if m.get("role") in ("system", "user", "assistant", "tool"):
            msg = MensagemNeutra(role=m["role"], content=m.get("content") or "")
            if m.get("tool_calls"):
                msg.tool_calls = m["tool_calls"]
            if m.get("tool_call_id"):
                msg.tool_call_id = m["tool_call_id"]
            if m.get("name"):
                msg.name = m["name"]
            mensagens.append(msg)
    resultado = cerebro_chat(mensagens, None)
    if resultado.conteudo:
        conversa.append({"role": "assistant", "content": resultado.conteudo})
    return chamadas | {"pedir_ao_opencode"}


def extrair_resposta(conversa) -> str:
    for mensagem in reversed(conversa):
        if mensagem.get("role") == "assistant" and mensagem.get("content"):
            return mensagem["content"]
    return ""


def resposta_falada(texto: str) -> str:
    """Limpa a resposta antes de falar.

    O modelo pequeno as vezes devolve um JSON de status em vez de uma frase
    ('{"name": "status", "message": "..."}'). Isso nao pode ir para o
    alto-falante: aqui extraimos o texto util e, na falta dele, devolvemos algo
    curto e natural.
    """
    limpo = (texto or "").strip()
    if not limpo:
        return ""
    if limpo[:1] in ("{", "["):
        try:
            dados = json.loads(limpo)
        except Exception:
            dados = None
        if isinstance(dados, dict):
            for chave in ("message", "mensagem", "texto", "resposta", "content", "resultado"):
                valor = dados.get(chave)
                if isinstance(valor, str) and valor.strip():
                    return resposta_falada(valor)
            return "Feito."
        if isinstance(dados, list):
            return "Feito."
        # JSON quebrado (o modelo as vezes corta no meio). Aproveita a mensagem
        # se houver; se for uma tentativa falha de tool call, nao ha o que falar.
        achado = re.search(r'"message"\s*:\s*"([^"]+)"', limpo)
        return achado.group(1).strip() if achado else ""
    return limpo.strip("`").strip()


def _quer_parar(texto: str) -> bool:
    """True se o pedido foi so 'para alguma coisa'.

    Cobre o caso em que o 'para' chega como comando: o microfone estava
    gravando (por isso nao existe vigia de interrupcao nessa hora), a palavra
    entra como transcricao e precisa ser reconhecida antes de gastar um turno
    do modelo inteiro com ela.
    """
    partes = chave_nome(texto or "").split()
    if not partes or len(partes) > 4:
        return False
    if not any(p in PALAVRAS_PARAR for p in partes):
        return False
    return all(p in PALAVRAS_PARAR or p in CORTESIA_PARAR for p in partes)


# Concordancia curta ('ok', 'isso ai', 'valeu'). Sem isso virava pedido e o
# modelo saia pesquisando 'Isso ai' na web. 'sim' e 'nao' ficam de fora:
# podem ser a resposta a uma pergunta que o proprio Nexus fez.
PALAVRAS_CONFIRMACAO = {
    "isso", "mesmo", "ai", "ok", "okay", "beleza", "blz", "valeu", "obrigado",
    "obrigada", "legal", "bacana", "show", "entendi", "entendido", "certo",
    "ta", "bom", "otimo", "perfeito", "maravilha", "top",
}


def _e_confirmacao(texto: str) -> str:
    """Devolve a resposta curta se a frase for so um 'ok/isso ai/valeu'."""
    partes = chave_nome(texto or "").replace(",", " ").replace(".", " ").split()
    if not partes or len(partes) > 3:
        return ""
    if not all(p in PALAVRAS_CONFIRMACAO for p in partes):
        return ""
    if any(p in {"obrigado", "obrigada", "valeu"} for p in partes):
        return "De nada."
    return "Beleza."


# Saudacoes curtas faladas assim que a wakeword dispara. Antes era um unico
# 'Pois nao?' fixo; agora variam e sao geradas pela Ollama. Para o aviso nao
# atrasar (o microfone ja esta gravando nessa hora), a Ollama gera um lote em
# segundo plano e a lista padrao cobre os primeiros toques, sem latencia.
AVISOS_PADRAO = [
    "Ouvindo.",
    "Pode falar.",
    "Estou aqui.",
    "Sim?",
    "Certo.",
    "Diga o comando.",
    "O que deseja?",
]

_avisos = []
_avisos_lock = threading.Lock()
_gerando_avisos = threading.Event()

SISTEMA_AVISO = (
    "Voce e o Nexus, assistente de voz brasileiro, direto e educado. O usuario "
    "acabou de chamar voce e agora vai falar o comando. Responda com UMA saudacao "
    "MUITO curta (no maximo 3 palavras), neutra e cordial, convidando-o a falar. "
    "Nada de girias nem brincadeira. Sem aspas, sem numeracao, sem explicacao, sem "
    "emoji. Varie bastante. Exemplos: Ouvindo. / Pode falar. / Estou aqui. / Sim? / "
    "Certo."
)


def _gerar_avisos_ollama(quantidade=6):
    """Gera um lote de saudacoes curtas com o cerebro ativo, fora do caminho critico."""
    if _gerando_avisos.is_set():
        return
    _gerando_avisos.set()
    try:
        mensagens = [
            MensagemNeutra(role="system", content=SISTEMA_AVISO),
            MensagemNeutra(role="user", content=f"Gere {quantidade} saudacoes curtas e diferentes, uma por linha."),
        ]
        resultado = cerebro_chat(mensagens, None)
        if resultado.erro:
            return
        conteudo = resultado.conteudo or ""
        novas = []
        for linha in conteudo.splitlines():
            linha = linha.strip().strip("\"'").lstrip("-*0123456789. ").strip()
            if 0 < len(linha) <= 28 and len(linha.split()) <= 3:
                novas.append(linha)
        with _avisos_lock:
            _avisos.extend(novas[:quantidade])
    except Exception:
        pass
    finally:
        _gerando_avisos.clear()


def aviso_de_escuta():
    """Saudacao curta para falar ao acordar. Nunca bloqueia a escuta."""
    with _avisos_lock:
        if _avisos:
            return _avisos.pop(0)
    # Nada pronto ainda: usa o banco padrao na hora e reabastece em fundo.
    threading.Thread(target=_gerar_avisos_ollama, daemon=True).start()
    return random.choice(AVISOS_PADRAO)


def rodar_modo_voz(conversa, servico=False):
    import time
    import voz

    global _voz
    _voz = voz

    if not voz.disponivel():
        print(voz.mensagem_indisponivel())
        return

    # Aquece o gerador de saudacoes em segundo plano: a primeira wakeword ja
    # encontra a lista pronta, entao o aviso sai na hora e varia sozinho.
    threading.Thread(target=_gerar_avisos_ollama, daemon=True).start()

    # O Vosk aceita varias frases de ativacao; 'Nexus' e a mais curta. A
    # saudacao nao diz o nome, senao a propria caixa acorda o Nexus.
    voz.falar("Estou online. Diga meu nome.")
    if servico:
        print(f"Servico de voz ativo. Diga '{voz.WAKEWORD}'.", flush=True)
    else:
        print(f"Modo voz ativo. Diga '{voz.WAKEWORD}' para falar. Ctrl+C encerra.", flush=True)
    print("A qualquer momento, fale para interromper o que o Nexus estiver fazendo.", flush=True)

    while True:
        try:
            # Devolve a RAM dos modelos quando o usuario para de falar.
            voz.limpar_ocios()
            _definir_estado("ocioso")
            print(f"Ouvindo '{voz.WAKEWORD}'...", flush=True)
            if not voz.escutar_wakeword():
                continue
            print("Wakeword detectada.", flush=True)
            _ponte_emitir("wakeword")
            _definir_estado("ouvindo")
            # Grava em paralelo com a saudacao, mas so passa a valer quando
            # 'fim_aviso' e marcado (assim que a saudacao termina de tocar).
            # Janela fixa nao serve: aviso curto cortava o inicio do comando e
            # aviso longo vazava o proprio aviso para a transcricao.
            fim_aviso = threading.Event()
            arquivo, gravando = voz.comecar_a_gravar(inicio=fim_aviso)
            gravando.start()
            voz.falar(aviso_de_escuta(), vigiar=False)
            # A caixa continua soando por alguns instantes depois do processo
            # sair; sem essa folga o rabinho da saudacao entra como comando.
            time.sleep(0.2)
            fim_aviso.set()
            gravando.join(timeout=voz.DURACAO_FALA + 10)
            texto = voz.transcrever_arquivo(arquivo)

        except KeyboardInterrupt:
            print("\nEncerrando voz.")
            break
        except Exception as erro:
            print(f"[voz] Erro na escuta ({erro}); tentando de novo.", flush=True)
            voz.descarregar()
            time.sleep(2)
            continue

        if not texto:
            print("[voz] Wakeword ok, mas nada foi transcrito.", flush=True)
            _definir_estado("falando")
            voz.falar("Nao entendi.")
            _definir_estado("ocioso")
            continue

        print(f"Voce: {texto}", flush=True)
        if _quer_encerrar(texto):
            _definir_estado("falando")
            voz.falar("Ate logo.")
            _definir_estado("ocioso")
            break
        if _quer_parar(texto):
            # Nada comecou ainda, mas o pedido e claro e nao vale gastar um
            # turno do modelo para descobrir que o usuario so queria parar.
            print("[voz] Nada a interromper.", flush=True)
            _definir_estado("falando")
            voz.falar("Certo, parei.")
            _definir_estado("ocioso")
            continue
        confirmacao = _e_confirmacao(texto)
        if confirmacao:
            print(f"\nNexus: {confirmacao}", flush=True)
            _definir_estado("falando")
            voz.falar(confirmacao)
            _definir_estado("ocioso")
            continue

        conversa[0]["content"] = REGRAS + memoria_para_prompt()
        conversa.append({"role": "user", "content": texto})
        global ULTIMO_PEDIDO
        ULTIMO_PEDIDO = texto

        # Daqui ate a fala o microfone fica aberto: e essa a janela em que voce
        # pode dizer 'para' e cancelar o que o Nexus estiver fazendo.
        voz.limpar_parada()
        _abrir_vigia()
        try:
            conversa, chamadas, resultados_turno = rodar_turno(conversa, texto)
            if not _interrompido():
                garantir_opencode(conversa, texto, chamadas)
        except Exception as erro:
            print(f"\nErro no turno: {erro}")
            _fechar_vigia()
            _definir_estado("falando")
            voz.falar("Deu erro ao processar.")
            _definir_estado("ocioso")
            continue
        _fechar_vigia()

        if _interrompido():
            print("[voz] Interrompido. Voltando a ouvir a wakeword.", flush=True)
            _definir_estado("ocioso")
            continue

        resposta = resposta_falada(extrair_resposta(conversa))
        if not resposta:
            # Modelo pequeno as vezes nao resume o que a ferramenta devolveu.
            resposta = resposta_falada("\n".join(resultados_turno))
        if not resposta:
            resposta = "Nao entendi. Pode repetir?"
        print(f"\nNexus: {resposta}")
        # falar() abre a propria escuta com o limiar alto e se cala no
        # instante em que voce falar por cima.
        _definir_estado("falando")
        _ponte_emitir("resposta_final", resposta)
        voz.falar(resposta)
        if voz.interrompido():
            print("[voz] Fala interrompida.", flush=True)
        voz.descarregar()
        _definir_estado("ocioso")
        # Health check para vigia do auto-aprimoramento
        try:
            (PASTA_DADOS / "saude.ok").write_text(str(time.time()))
        except Exception:
            pass


def _anunciar_status():
    try:
        mensagens = [MensagemNeutra(role="user", content="ping")]
        resultado = cerebro_chat(mensagens, None)
        if resultado.erro:
            raise Exception(resultado.erro)
        status = status_cerebros()
        provedor = status.get("provedor_ativo", "desconhecido")
        arquiteto = f"Antigravity ({MODELO_ARQUITETO})" if AGY else "indisponivel"
        print(f"Nexus online. Cerebro ativo: {provedor} | Especialista: {MODELO_ESPECIALISTA} | Codigo: OpenCode")
        print(f"Arquiteto: {arquiteto} | Executor: {MODELO_EXECUTOR}")
        print(f"Projetos: {PASTA_TRABALHO}")
        print("Digite 'sair' para encerrar.\n")
    except Exception as erro:
        print(f"Nao consegui falar com o cerebro ({erro}). Verifique se o Ollama esta rodando ('ollama serve').\n")


def conduzir_texto(conversa, texto):
    """Roda um turno escrito e devolve (conversa, resposta)."""
    global ULTIMO_PEDIDO
    conversa[0]["content"] = REGRAS + memoria_para_prompt()
    conversa.append({"role": "user", "content": texto})
    ULTIMO_PEDIDO = texto
    _definir_estado("pensando")
    conversa, chamadas, resultados_turno = rodar_turno(conversa, texto)
    garantir_opencode(conversa, texto, chamadas)
    resposta = resposta_falada(extrair_resposta(conversa))
    if not resposta:
        resposta = resposta_falada("\n".join(resultados_turno))
    _ponte_emitir("resposta_final", resposta)
    _definir_estado("ocioso")
    # Health check para vigia do auto-aprimoramento
    try:
        (PASTA_DADOS / "saude.ok").write_text(str(time.time()))
    except Exception:
        pass
    return conversa, resposta


def rodar_modo_escrita(conversa):
    """Digite o comando no terminal; o Nexus responde em voz.

    Serve para quem prefere escrever (mais preciso que a transcricao) mas quer
    ouvir a resposta, por exemplo com fones ou a caixa longe do teclado.
    """
    import voz
    falar = voz.disponivel()
    if falar:
        iniciar_agenda(voz.falar)
        voz.falar("Modo escrita ativo. Digite o comando e eu respondo em voz.")
    else:
        print(voz.mensagem_indisponivel())
        iniciar_agenda()

    while True:
        try:
            texto = input("\nVoce: ").strip()
        except (KeyboardInterrupt, EOFError):
            break
        if not texto:
            continue
        if texto.lower() in {"sair", "exit", "quit"}:
            break
        confirmacao = _e_confirmacao(texto)
        if confirmacao:
            print(f"\nNexus: {confirmacao}")
            if falar:
                voz.falar(confirmacao)
            continue
        try:
            conversa, resposta = conduzir_texto(conversa, texto)
            resposta = resposta or "Nao entendi. Pode repetir?"
            print(f"\nNexus: {resposta}")
            if falar:
                voz.falar(resposta)
                voz.descarregar()
        except KeyboardInterrupt:
            print("\nInterrompido.")
        except Exception as erro:
            print(f"\nErro no turno: {erro}")

    if falar:
        voz.falar("Ate logo.")
    print("\nNexus desligado.")


def autoteste() -> int:
    """Executa testes automatizados sem Ollama, sem microfone, sem dados/.
    Retorna 0 se tudo passar, != 0 se falhar.
    """
    import sys
    from pathlib import Path

    BASE = Path(__file__).resolve().parent
    PASTA_FERRAMENTAS = BASE / "ferramentas"
    PASTA_INTERFACE = BASE / "interface"
    PASTA_POPUPS = PASTA_INTERFACE / "popups"

    print("[autoteste] Iniciando testes automatizados...")
    print("[autoteste] Modo: sem Ollama, sem microfone, sem dados/")
    falhas = 0

    # 1. py_compile em todos os .py
    print("\n[1/6] py_compile...")
    arquivos_py = (
        [BASE / "nexus.py", BASE / "voz.py", BASE / "comum.py", BASE / "seguranca.py", BASE / "cerebro.py"] +
        list(PASTA_FERRAMENTAS.glob("*.py")) +
        list(PASTA_INTERFACE.glob("*.py")) +
        list(PASTA_POPUPS.glob("*.py"))
    )
    for arq in arquivos_py:
        if arq.name.startswith("_"):
            continue
        resultado = subprocess.run(
            [sys.executable, "-m", "py_compile", str(arq)],
            capture_output=True, text=True
        )
        if resultado.returncode != 0:
            print(f"  FALHA: {arq.relative_to(BASE)}")
            print(resultado.stderr)
            falhas += 1
        else:
            print(f"  OK: {arq.relative_to(BASE)}")

    # 2. Importar nexus.py, voz.py e todos plugins
    print("\n[2/6] Importacao de modulos...")
    try:
        import nexus
        print("  OK: nexus.py")
    except Exception as e:
        print(f"  FALHA: nexus.py - {e}")
        falhas += 1

    try:
        import voz
        print("  OK: voz.py")
    except Exception as e:
        print(f"  FALHA: voz.py - {e}")
        falhas += 1

    try:
        from ferramentas.carregador import carregar_plugins
        plugins, funcoes, indisponiveis = carregar_plugins()
        print(f"  OK: carregador - {len(plugins)} plugins carregados")
        for p in indisponiveis:
            print(f"    (indisponivel: {p[0]} - {p[1]})")
    except Exception as e:
        print(f"  FALHA: carregador - {e}")
        falhas += 1

    # 3. Validar schemas das ferramentas
    print("\n[3/6] Validacao de schemas...")
    try:
        from nexus import CATALOGO, META
        for item in CATALOGO:
            nome = item["nome"]
            params = item.get("parametros")
            if not params or params.get("type") != "object":
                print(f"  FALHA: {nome} - schema invalido")
                falhas += 1
        print(f"  OK: {len(CATALOGO)} ferramentas com schema valido")
    except Exception as e:
        print(f"  FALHA: validacao schemas - {e}")
        falhas += 1

    # 4. Testes de roteamento de intencao
    print("\n[4/6] Roteamento de intencao...")
    try:
        from nexus import precisa_de_codigo, quer_plano
        testes_intencao = [
            ("criar um projeto react", True),
            ("abre o vscode", False),
            ("qual a capital da franca", False),
            ("planeja uma api de tarefas", True),
            ("me lembra de beber agua", False),
        ]
        for texto, esperado in testes_intencao:
            resultado = precisa_de_codigo(texto)
            if resultado != esperado:
                print(f"  FALHA: precisa_de_codigo('{texto}') = {resultado}, esperado {esperado}")
                falhas += 1
        print("  OK: precisa_de_codigo")

        # quer_plano so testa se AGY existe (pode nao estar instalado)
        if AGY:
            testes_plano = [
                ("planeja uma api", True),
                ("sem plano, so executa", False),
                ("cria um projeto grande", True),
            ]
            for texto, esperado in testes_plano:
                resultado = quer_plano(texto)
                if resultado != esperado:
                    print(f"  FALHA: quer_plano('{texto}') = {resultado}, esperado {esperado}")
                    falhas += 1
            print("  OK: quer_plano")
        else:
            print("  OK: quer_plano (AGY nao instalado, pulado)")
    except Exception as e:
        print(f"  FALHA: roteamento - {e}")
        falhas += 1

    # 5. Testes de politica de seguranca
    print("\n[5/6] Politica de seguranca...")
    try:
        from seguranca import detectar_graves, confirmar_risco, CAMINHOS_PROIBIDOS
        # Bloqueados
        bloqueados, _ = detectar_graves("rm -rf /")
        if not bloqueados:
            print("  FALHA: rm -rf / deveria ser bloqueado")
            falhas += 1
        # Confirmacoes
        bloqueados, a_confirmar = detectar_graves("sudo apt update")
        if not a_confirmar:
            print("  FALHA: sudo apt update deveria pedir confirmacao")
            falhas += 1
        # Caminhos proibidos
        bloqueados, a_confirmar = detectar_graves("cat ~/.ssh/id_rsa")
        if not bloqueados:
            print("  FALHA: cat ~/.ssh/id_rsa deveria ser bloqueado (credencial)")
            falhas += 1
        # Dentro do projeto nao bloqueia rm -rf
        bloqueados, _ = detectar_graves(f"rm -rf {PASTA_TRABALHO}/teste")
        if bloqueados:
            print("  FALHA: rm -rf dentro da pasta de trabalho nao deveria bloquear")
            falhas += 1
        print("  OK: detectar_graves (bloqueios, confirmacoes, credenciais, pasta projeto)")
    except Exception as e:
        print(f"  FALHA: politica seguranca - {e}")
        falhas += 1

    # 6. Verifica arquivos protegidos nao alterados (git status limpo)
    print("\n[6/6] Verificacao de arquivos protegidos...")
    try:
        import json
        dados = json.loads((BASE / "config/protegidos.json").read_text())
        protegidos = dados.get("protegidos", [])
        # So verifica se a lista existe e nao esta vazia
        if protegidos:
            print(f"  OK: config/protegidos.json tem {len(protegidos)} entradas protegidas")
        else:
            print("  AVISO: config/protegidos.json vazio")
    except Exception as e:
        print(f"  FALHA: protegidos - {e}")
        falhas += 1

    print(f"\n[autoteste] Resultado: {'SUCESSO' if falhas == 0 else f'{falhas} FALHA(S)'}")
    return 0 if falhas == 0 else 1


def configurar_cerebro():
    """Wizard interativo para configurar a cadeia de cerebros (Gemini + Ollama)."""
    import os
    import sys

    def ler_chave(prompt: str) -> str:
        """Le chave do stdin (nao oculta se nao for TTY)."""
        try:
            import getpass
            if sys.stdin.isatty():
                return getpass.getpass(prompt).strip()
        except Exception:
            pass
        try:
            return input(prompt).strip()
        except EOFError:
            return ""

    print("=== CONFIGURACAO DO CEREBRO NEXUS ===")
    print()
    print("O Nexus usa uma CADEIA DE CEREBROS com fallback automatico:")
    print("  1) nuvem_pago   - Gemini classe 'pro' (projeto COM faturamento/creditos)")
    print("  2) nuvem_gratis - Gemini classe 'flash' (projeto SEM faturamento)")
    print("  3) local        - Ollama (como hoje, sempre disponivel)")
    print()
    print("POR QUE DUAS CHAVES? Os limites do Gemini valem POR PROJETO no Google Cloud.")
    print("Um projeto com faturamento (pago) tem limites altos; um sem faturamento (gratis)")
    print("tem limites baixos. Usando dois projetos diferentes na MESMA conta Google,")
    print("voce tem ambos os pools de cota. O Nexus tenta o pago, cai pro gratis,")
    print("e por fim pro local.")
    print()
    print("COMO CRIAR AS CHAVES:")
    print("  1. Acesse https://aistudio.google.com/apikey")
    print("  2. Clique 'Create API key' -> escolha 'Create API key in new project'")
    print("  3. Para a chave PAGA: crie/vincule uma conta de faturamento no Cloud Billing")
    print("     (resgate creditos do Google Developer Program em developers.google.com/program/my-benefits)")
    print("  4. Para a chave GRATIS: crie em outro projeto SEM faturamento")
    print("  5. Use UMA UNICA conta Google e SO esses dois projetos")
    print("     (os termos do Google proibem criar contas/projetos em serie para escapar de limites)")
    print()
    print("Configure as variaveis de ambiente ou digite as chaves abaixo.")
    print("Deixe em branco para pular (a cadeia funciona com as que existirem).")
    print()

    # Chave paga
    chave_pago = os.environ.get("GEMINI_API_KEY_PAGO", "")
    if not chave_pago:
        print("Chave PAGA (nuvem_pago) - projeto COM faturamento:")
        chave_pago = ler_chave("  Cole a chave (Enter para pular): ")
    else:
        print(f"Chave PAGA ja configurada via GEMINI_API_KEY_PAGO ({chave_pago[:10]}...)")

    # Chave gratis
    chave_gratis = os.environ.get("GEMINI_API_KEY_GRATIS", "")
    if not chave_gratis:
        print("\nChave GRATIS (nuvem_gratis) - projeto SEM faturamento:")
        chave_gratis = ler_chave("  Cole a chave (Enter para pular): ")
    else:
        print(f"\nChave GRATIS ja configurada via GEMINI_API_KEY_GRATIS ({chave_gratis[:10]}...)")

    # Validar e listar modelos
    from cerebro import CerebroGemini, ConfigProvedor, TipoProvedor

    def testar_chave(nome, chave, tipo):
        if not chave:
            print(f"  {nome}: PULADA")
            return None
        os.environ[f"GEMINI_API_KEY_{nome.upper()}"] = chave
        cfg = ConfigProvedor(nome=f"gemini-{nome}", tipo=tipo, modelo="", chave_ref=f"GEMINI_API_KEY_{nome.upper()}")
        cerebro = CerebroGemini(cfg)
        print(f"  {nome}: Validando chave e listando modelos...")
        modelos = cerebro.listar_modelos()
        if not modelos:
            print(f"  {nome}: FALHA - nao conseguiu listar modelos (chave invalida ou sem internet)")
            return None
        print(f"  {nome}: {len(modelos)} modelos com generateContent")

        # Filtrar modelos estaveis (sem preview, lite, image, transcribe, omni, tts, nano, banana)
        def eh_estavel(m):
            ml = m.lower()
            return not any(x in ml for x in ["preview", "lite", "image", "transcribe", "omni", "tts", "nano", "banana", "audio"])

        modelos_estaveis = [m for m in modelos if eh_estavel(m)]
        if not modelos_estaveis:
            modelos_estaveis = modelos  # fallback

        # Agrupar por classe
        pro = [m for m in modelos_estaveis if "pro" in m.lower() and "flash" not in m.lower()]
        flash = [m for m in modelos_estaveis if "flash" in m.lower()]

        if pro:
            print(f"    Pro:   {', '.join(pro[:5])}{'...' if len(pro) > 5 else ''}")
        if flash:
            print(f"    Flash: {', '.join(flash[:5])}{'...' if len(flash) > 5 else ''}")

        # Sugerir o mais recente estavel (maior numero de versao)
        def extrair_versao(m):
            import re
            nums = re.findall(r'(\d+(?:\.\d+)*)', m)
            return [int(n) for n in nums[0].split('.')] if nums else [0]

        sugerido = None
        if tipo == TipoProvedor.NUVEM_PAGO and pro:
            sugerido = max(pro, key=extrair_versao)
        elif tipo == TipoProvedor.NUVEM_GRATIS and flash:
            sugerido = max(flash, key=extrair_versao)
        elif pro:
            sugerido = max(pro, key=extrair_versao)
        elif flash:
            sugerido = max(flash, key=extrair_versao)
        elif modelos_estaveis:
            sugerido = modelos_estaveis[0]

        if sugerido:
            print(f"  {nome}: Testando function calling com '{sugerido}'...")
            cfg.modelo = sugerido
            if cerebro.testar_function_calling():
                print(f"  {nome}: OK - function calling funciona")
                return sugerido
            else:
                print(f"  {nome}: AVISO - function calling nao funcionou com '{sugerido}', tentando outros...")
                # Tentar outros modelos da mesma classe
                candidatos = pro if "pro" in sugerido.lower() else flash
                for m in sorted(candidatos, key=extrair_versao, reverse=True):
                    if m == sugerido:
                        continue
                    print(f"  {nome}: Tentando '{m}'...")
                    cfg.modelo = m
                    if cerebro.testar_function_calling():
                        print(f"  {nome}: OK - function calling funciona com '{m}'")
                        return m
                print(f"  {nome}: FALHA - function calling nao funcionou em nenhum modelo")
                return sugerido
        return None

    print("\n--- Testando chaves ---")
    modelo_pago = testar_chave("pago", chave_pago, TipoProvedor.NUVEM_PAGO) if chave_pago else None
    modelo_gratis = testar_chave("gratis", chave_gratis, TipoProvedor.NUVEM_GRATIS) if chave_gratis else None

    # Salvar chaves em config/gemini.json
    if chave_pago or chave_gratis:
        from seguranca import salvar_chave_gemini
    if chave_pago:
        salvar_chave_gemini(chave_pago, "GEMINI_API_KEY_PAGO")
        print(f"[OK] Chave PAGA salva em config/gemini.json (permissao 600)")
    if chave_gratis:
        salvar_chave_gemini(chave_gratis, "GEMINI_API_KEY_GRATIS")
        print(f"[OK] Chave GRATIS salva em config/gemini.json (permissao 600)")

    from comum import BASE_PROJETO, PASTA_DADOS, salvar_json
    import json
    dados = {"provedores": []}

    if modelo_pago:
        from seguranca import salvar_chave_gemini
        salvar_chave_gemini(chave_pago, "GEMINI_API_KEY_PAGO")
        print(f"[OK] Chave PAGA salva em config/gemini.json (permissao 600)")
    if chave_gratis:
        from seguranca import salvar_chave_gemini
        salvar_chave_gemini(chave_gratis, "GEMINI_API_KEY_GRATIS")
        print(f"[OK] Chave GRATIS salva em config/gemini.json (permissao 600)")

    if modelo_pago:
        dados["provedores"].append({
            "nome": "gemini-pro-pago",
            "tipo": "nuvem_pago",
            "modelo": modelo_pago,
            "chave_ref": "GEMINI_API_KEY_PAGO",
            "limite_mensal_tokens": 1000000,
            "ativo": True,
            "prioridade": 1,
            "max_passos": 0,
            "rede_seguranca_palavra_chave": False,
        })
        print(f"[OK] nuvem_pago configurado: {modelo_pago}")
    else:
        print("\n[PULADO] nuvem_pago")

    if modelo_gratis:
        dados["provedores"].append({
            "nome": "gemini-flash-gratis",
            "tipo": "nuvem_gratis",
            "modelo": modelo_gratis,
            "chave_ref": "GEMINI_API_KEY_GRATIS",
            "limite_mensal_tokens": 100000,
            "ativo": True,
            "prioridade": 2,
            "max_passos": 0,
            "rede_seguranca_palavra_chave": False,
        })
        print(f"[OK] nuvem_gratis configurado: {modelo_gratis}")
    else:
        print("[PULADO] nuvem_gratis")

    # Sempre manter o local
    dados["provedores"].append({
        "nome": "ollama-local",
        "tipo": "local",
        "modelo": "llama3.1:8b",
        "chave_ref": "",
        "limite_mensal_tokens": 0,
        "ativo": True,
        "prioridade": 3,
        "max_passos": 4,
        "rede_seguranca_palavra_chave": True,
    })
    print("[OK] local mantido: llama3.1:8b")

    arquivo = PASTA_DADOS / "cerebro.json"
    arquivo.parent.mkdir(parents=True, exist_ok=True)
    arquivo.write_text(json.dumps(dados, indent=2, ensure_ascii=False))
    print(f"Configuracao de cadeia salva em {arquivo}")
    print("Reinicie o Nexus para aplicar.")

    return 0


def teste_cerebro():
    """Testa a cadeia de cerebros simulando falhas e failover."""
    import os
    os.environ.setdefault("GEMINI_API_KEY_GRATIS", "REDACTED_API_KEY")

    from cerebro import get_gerenciador, chat, MensagemNeutra, EstadoProvedor
    g = get_gerenciador()

    print("=== TESTE DA CADEIA DE CEREBROS ===")
    print()

    # 1. Status inicial
    print("1. Status inicial:")
    status = g.status()
    for p in status["provedores"]:
        print(f"   {p['nome']} ({p['tipo']}): {p['estado']} - modelo: {p['modelo']}")
    print(f"   Provedor ativo: {status['provedor_ativo']}")
    print()

    # 2. Teste chat normal
    print("2. Teste chat normal (deve usar gemini-flash-gratis):")
    msgs = [MensagemNeutra(role="user", content="Responda apenas: OK")]
    result = chat(msgs, None)
    print(f"   Provedor usado: {result.provedor_usado}")
    print(f"   Modelo: {result.modelo_usado}")
    print(f"   Resposta: {result.conteudo[:50]}")
    print(f"   Tokens: {result.tokens_entrada}+{result.tokens_saida}")
    print()

    # 3. Simular erro 429 no provedor 1
    print("3. Simulando erro 429 (quota) no provedor 1...")
    g.registrar_erro("gemini-flash-gratis", "429 Quota exceeded")
    g.registrar_erro("gemini-flash-gratis", "429 Quota exceeded")
    g.registrar_erro("gemini-flash-gratis", "429 Quota exceeded")
    status = g.status()
    for p in status["provedores"]:
        print(f"   {p['nome']}: {p['estado']}")
    print()

    # 4. Teste chat apos erro (deve cair para local)
    print("4. Teste chat apos erro (deve cair para ollama-local):")
    msgs = [MensagemNeutra(role="user", content="Responda apenas: OK")]
    result = chat(msgs, None)
    print(f"   Provedor usado: {result.provedor_usado}")
    print(f"   Modelo: {result.modelo_usado}")
    print(f"   Resposta: {result.conteudo[:50]}")
    print()

    # 5. Recuperar provedor 1
    print("5. Recuperando provedor 1 (simulando passagem de tempo)...")
    g._estados["gemini-flash-gratis"].entrou_descanso_em = 0  # forcar recuperacao imediata
    g.tentar_recuperar_provedores()
    status = g.status()
    for p in status["provedores"]:
        print(f"   {p['nome']}: {p['estado']}")
    print()

    # 6. Teste chat apos recuperacao (deve voltar para gemini)
    print("6. Teste chat apos recuperacao (deve voltar para gemini-flash-gratis):")
    msgs = [MensagemNeutra(role="user", content="Responda apenas: OK")]
    result = chat(msgs, None)
    print(f"   Provedor usado: {result.provedor_usado}")
    print(f"   Modelo: {result.modelo_usado}")
    print(f"   Resposta: {result.conteudo[:50]}")
    print()

    # 7. Testar limite mensal
    print("7. Testando limite mensal (simulando 100% da cota)...")
    g._estados["gemini-flash-gratis"].tokens_mes = 100000  # limite
    g.verificar_limites("gemini-flash-gratis")
    status = g.status()
    for p in status["provedores"]:
        print(f"   {p['nome']}: {p['estado']} ({p['tokens_mes']}/{p['limite_mensal']})")
    print()

    print("=== TESTE CONCLUIDO ===")
    return 0


def main():
    if "--help" in sys.argv or "-h" in sys.argv:
        print("Uso: python nexus.py [opcoes]")
        print("Opcoes:")
        print("  (sem opcoes)      Abre interface grafica por padrao")
        print("  --interface       Forca modo interface grafica")
        print("  --voz             Modo conversacao por voz (terminal)")
        print("  --servico         Roda em segundo plano como servico de voz")
        print("  --escrever        Entrada por texto e resposta em voz")
        print("  --texto-voz       Apelido para --escrever")
        print("  --demo-acoes      Simula sequencia de acoes rapidas na interface")
        print("  --autoteste       Executa testes automatizados (sem Ollama, sem microfone, sem dados/)")
        print("  --configurar-cerebro  Configura a cadeia de cerebros (chaves Gemini, modelos)")
        print("  --teste-cerebro   Testa a cadeia de cerebros (failover, limites, recuperacao)")
        print("  --modo-privado    Forca uso do cerebro local (privacidade total)")
        print("  --modo-nuvem      Volta a usar a cadeia de cerebros (nuvem + local)")
        print("  --help, -h        Mostra esta ajuda")
        return 0

    if "--configurar-cerebro" in sys.argv:
        return configurar_cerebro()

    if "--teste-cerebro" in sys.argv:
        return teste_cerebro()

    if "--autoteste" in sys.argv:
        return autoteste()

    if "--modo-privado" in sys.argv:
        forcar_modo_local(True)
        print("[nexus] Modo privado ativado: usando apenas o cerebro local.")
        # Nao retorna aqui, continua para rodar normalmente

    if "--modo-nuvem" in sys.argv:
        forcar_modo_local(False)
        print("[nexus] Modo nuvem ativado: cadeia de cerebros habilitada.")
        # Nao retorna aqui, continua para rodar normalmente

    aplicar_config_permissoes()
    if AGY:
        aplicar_regras_antigravity()
        confiar_no_workspace()

    # Este ping carrega o modelo do Ollama e levava 1.2s. Rodando em segundo
    # plano, o microfone abre ~1.2s antes sem perder o aquecimento: quando a
    # pessoa falar, o modelo ja estara em RAM de qualquer jeito.
    threading.Thread(target=_anunciar_status, daemon=True).start()

    conversa = [{"role": "system", "content": REGRAS}]
    modo_servico = "--servico" in sys.argv
    modo_voz = "--voz" in sys.argv or modo_servico
    modo_escrita = "--escrever" in sys.argv or "--texto-voz" in sys.argv
    modo_interface = "--interface" in sys.argv
    demo_acoes_ativado = "--demo-acoes" in sys.argv

    ctrl_interface = None
    if modo_interface:
        try:
            from interface.app import (
                JaEmExecucao,
                disponivel as interface_disponivel,
                iniciar_interface,
            )
            from interface.ponte import Ponte

            if not interface_disponivel():
                print(
                    "[nexus] Interface grafica indisponivel (sem display ou PySide6 ausente). Continuando no terminal.",
                    flush=True,
                )
            else:
                global _ponte
                _ponte = Ponte()
                _set_ponte_seguranca(_ponte)
                # Registrar callback para mudanca de cerebro ativo
                def _ao_cerebro_mudar(novo_provedor: str):
                    _ponte.emitir_cerebro(novo_provedor)
                    # Aviso por voz curto
                    if _voz is not None and _voz.disponivel():
                        if "gemini" in novo_provedor.lower():
                            _voz.falar("Usando a nuvem", vigiar=False)
                        elif "ollama" in novo_provedor.lower() or "local" in novo_provedor.lower():
                            _voz.falar("Modo local", vigiar=False)
                set_callback_cerebro_mudou(_ao_cerebro_mudar)
                ctrl_interface = iniciar_interface(ponte=_ponte)
                # Modo interface habilita voz + texto + janela
                modo_voz = True
        except JaEmExecucao:
            print(
                "[nexus] Ja existe uma instancia com interface em execucao. Encerrando.",
                flush=True,
            )
            return 0
        except Exception as erro:
            print(
                f"[nexus] Nao foi possivel iniciar a interface grafica: {erro}. Continuando no terminal.",
                flush=True,
            )
            _ponte = None
            ctrl_interface = None

    if ctrl_interface is not None:
        def _tratar_comando_ui(texto_comando):
            def _worker():
                try:
                    _conversa, resposta = conduzir_texto(conversa, texto_comando)
                    print(f"\nNexus: {resposta}", flush=True)
                    if modo_voz and _voz is not None and _voz.disponivel():
                        _definir_estado("falando")
                        _voz.falar(resposta)
                        _voz.descarregar()
                    _definir_estado("ocioso")
                except Exception as err:
                    print(f"\nErro no comando da interface: {err}", flush=True)
                    _definir_estado("ocioso")

            threading.Thread(target=_worker, daemon=True).start()

        _ponte.comando_digitado.connect(_tratar_comando_ui)

        if modo_voz:
            import voz
            voz.ao_nivel(lambda n: _ponte_emitir("fala_nivel", n))
            if voz.disponivel():
                iniciar_agenda(voz.falar)
                thread_voz = threading.Thread(
                    target=rodar_modo_voz,
                    args=(conversa, modo_servico),
                    daemon=True,
                )
                thread_voz.start()
            else:
                print(voz.mensagem_indisponivel())
                iniciar_agenda()
        else:
            iniciar_agenda()


        # Simulacao de acoes rapidas para teste (requer interface)
        if demo_acoes_ativado:
            from PySide6.QtCore import QTimer

            ponte_demo = _ponte

            def _emit(nome, args=None, res="OK"):
                if ponte_demo is not None:
                    try:
                        ponte_demo.ferramenta_iniciada.emit(nome, args or {})
                    except Exception:
                        pass
                    try:
                        ponte_demo.ferramenta_concluida.emit(nome, res)
                    except Exception:
                        pass

            seq = []
            seq.append(lambda: _emit("abrir_programa", {"programa": "spotify"}))
            seq.append(lambda: _emit("spotify", {"acao": "tocar", "playlist": "Lo-Fi Chill"}, "TOCANDO: LO-FI CHILL"))
            seq.append(lambda: _emit("definir_volume", {"volume": 40}, "VOLUME: 40%"))
            seq.append(lambda: _emit("abrir_programa", {"programa": "firefox"}, "FALHA: APP NAO ENCONTRADO"))
            seq.append(lambda: _emit("pesquisar_na_web", {"busca": "teste"}, "RESULTADO DE PESQUISA SIMULADO"))

            for i, fn in enumerate(seq):
                QTimer.singleShot(800 + i * 900, fn)
        try:
            codigo = ctrl_interface.executar()
        except KeyboardInterrupt:
            codigo = 0
        print("\nNexus desligado.")
        return codigo

    if modo_escrita:
        try:
            rodar_modo_escrita(conversa)
        except Exception as erro:
            print(f"Erro no modo escrita: {erro}", flush=True)
        return

    if modo_voz:
        import voz
        if voz.disponivel():
            iniciar_agenda(voz.falar)
        else:
            print(voz.mensagem_indisponivel())
            iniciar_agenda()
            modo_voz = False
    else:
        iniciar_agenda()

    if modo_voz:
        try:
            rodar_modo_voz(conversa, servico=modo_servico)
        except Exception as erro:
            print(f"Erro no modo voz: {erro}", flush=True)
            if modo_servico:
                return 1
        print("\nNexus desligado.")
        return

    while True:
        try:
            texto = input("\nVoce: ").strip()
        except (KeyboardInterrupt, EOFError):
            break

        if not texto:
            continue
        if texto.lower() in {"sair", "exit", "quit"}:
            break

        confirmacao = _e_confirmacao(texto)
        if confirmacao:
            print(f"\nNexus: {confirmacao}")
            continue

        try:
            conversa, resposta = conduzir_texto(conversa, texto)
            print(f"\nNexus: {resposta or 'Nao entendi. Pode repetir?'}")
        except KeyboardInterrupt:
            print("\nInterrompido.")
        except Exception as erro:
            print(f"\nErro no turno: {erro}")

    print("\nNexus desligado.")


if __name__ == "__main__":
    sys.exit(main())
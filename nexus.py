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

import ollama

from comum import (
    PASTA_TRABALHO, PASTA_DADOS, PASTA_CONFIG, BASE_PROJETO,
    MODELO_ESPECIALISTA, resolver, esquema, TEXTO,
    limpar_ansi, resumir_busca, memoria_para_prompt, chave_nome,
)
from ferramentas.carregador import carregar_plugins
from ferramentas._agenda import iniciar as iniciar_agenda


MODELO = "llama3.1:8b"

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

CHROME_OPENCODE = re.compile(r"^>\s*(build|plan|general)\s*[·|]")

CAMINHOS_PROIBIDOS = [
    "~/.ssh/**", "~/.aws/**", "~/.gnupg/**", "~/.kube/**",
    "~/.config/opencode/**", "~/.config/gh/**", "~/.docker/config.json",
    "/etc/**", "/usr/**", "/bin/**", "/sbin/**", "/boot/**", "/lib/**", "/lib64/**",
    "/proc/**", "/sys/**", "/dev/**",
]

# Destruicao do sistema, do disco ou vazamento de credenciais. O OpenCode bloqueia
# sozinho e o --auto nao burla isso. Nao ha como o Nexus liberar.
BLOQUEIOS = [
    "rm -rf /", "rm -rf /*", "rm -rf ~", "rm -rf ~/*", "rm -rf $HOME", "rm -rf $HOME/*",
    "rm -fr /", "rm -fr /*", "rm -fr ~", "rm -fr ~/*",
    "rm -rf /etc*", "rm -rf /usr*", "rm -rf /bin*", "rm -rf /sbin*",
    "rm -rf /boot*", "rm -rf /lib*", "rm -rf /var*", "rm -rf /proc*", "rm -rf /sys*",
    "mkfs*", "fdisk*", "parted*", "wipefs*",
    "dd if=* of=/dev/*", "dd of=/dev/*",
    "> /dev/sd*", "> /dev/nvme*", "> /dev/mmc*",
    "chmod -R 777 /*", "chmod 777 /*", "chown -R * /*", "chown * /*",
    ":(){:|:&};:",
    "cat ~/.ssh*", "cat ~/.aws*", "cat ~/.gnupg*", "cat *auth.json*",
    "cat ~/.config/opencode/*", "cat ~/.docker/config.json",
    "history -c*", "shred *", "wipe *",
]

# Vazamento de credenciais em linguagem natural (texto, nao comando exato).
CREDENCIAIS = [
    "*.ssh*", "*.aws*", "*.gnupg*", "*.netrc*", "*/.kube/*",
    "*id_rsa*", "*id_ed25519*", "*auth.json*",
    "*.docker/config.json*", "*.config/opencode/*",
]

# Coisas destrutivas ou irreversiveis, mas legitimas em contexto. O Nexus pergunta
# uma vez e, se voce confirmar, executa normalmente.
CONFIRMACOES = [
    "sudo *", "sudo", "su *", "su", "doas *",
    "shutdown*", "reboot*", "halt*", "poweroff*", "init 0*", "init 6*", "systemctl *", "service *",
    "apt *", "apt-get *", "aptitude *", "snap install*", "snap remove*",
    "git push*", "git reset --hard*", "git clean -fd*", "git clean -df*", "git checkout .*",
    "npm publish*", "yarn publish*", "pnpm publish*",
    "curl * | sh", "curl * | bash", "wget * | sh", "wget * | bash",
    "curl * | sudo *", "wget * | sudo *",
    "crontab*", "visudo*",
    "chmod *", "chown *", "chgrp *",
    "kill -9 *", "killall*", "pkill*",
    "dropdb*", "drop table*", "delete from*",
]


# ---------- AJUDANTES E FERRAMENTAS ----------

def gerar_config_permissoes() -> dict:
    """Politica aplicada so ao OpenCode chamado pelo Nexus (via OPENCODE_CONFIG)."""
    bash = {"*": "allow"}
    for padrao in BLOQUEIOS:
        bash[padrao] = "deny"

    relativo = PASTA_TRABALHO.relative_to(Path.home())
    for alvo in (str(PASTA_TRABALHO), f"~/{relativo}", f"$HOME/{relativo}"):
        for prefixo in ("rm -rf", "rm -fr"):
            bash[f"{prefixo} {alvo}/*"] = "allow"
            bash[f"{prefixo} {alvo}"] = "allow"

    leitura = {"*": "allow", "*.env": "deny", "*.env.*": "deny", "*.env.example": "allow"}
    escrita = {"*": "allow"}

    for proibido in CAMINHOS_PROIBIDOS:
        leitura[proibido] = "deny"
        escrita[proibido] = "deny"

    externo = {"*": "allow"}
    for proibido in CAMINHOS_PROIBIDOS:
        externo[proibido] = "deny"

    return {
        "$schema": "https://opencode.ai/config.json",
        "share": "disabled",
        "permission": {
            "*": "allow",
            "question": "deny",
            "read": leitura,
            "edit": escrita,
            "bash": bash,
            "external_directory": externo,
        },
    }


def aplicar_config_permissoes() -> Path:
    conteudo = json.dumps(gerar_config_permissoes(), indent=2, ensure_ascii=False) + "\n"
    if not CONFIG_PERMISSOES.exists() or CONFIG_PERMISSOES.read_text() != conteudo:
        CONFIG_PERMISSOES.write_text(conteudo)
    return CONFIG_PERMISSOES


def bloco_regras_antigravity() -> str:
    proibidos = "\n".join(f"  - `{p}`" for p in BLOQUEIOS)
    credenciais = ", ".join(f"`{p}`" for p in CREDENCIAIS)
    sensiveis = ", ".join(f"`{p}`" for p in CONFIRMACOES)
    return f"""{ANTIGRAVITY_TOKEN}
# Regras do Nexus

Voce opera dentro do Nexus e deve seguir estas regras sempre.

NUNCA execute, mesmo que pecam, comandos que destruam o sistema ou vazem credenciais:
{proibidos}

NUNCA leia, copie, imprima ou envie arquivos de credenciais (mesmo em linguagem natural):
{credenciais}

Peca autorizacao antes de: {sensiveis}.

Trabalhe somente dentro da pasta de projetos. Nao crie, edite ou apague nada em /etc, /usr,
/bin, /boot, ~/.ssh, ~/.aws, ~/.config ou fora da pasta de trabalho.

Quando estiver no modo de planejamento, produza apenas o plano: nao crie arquivos e nao rode comandos.
{ANTIGRAVITY_TOKEN}"""


def aplicar_regras_antigravity() -> Path:
    """Insere/atualiza um bloco gerenciado no GEMINI.md sem apagar conteudo do usuario."""
    marca = ANTIGRAVITY_TOKEN
    bloco = bloco_regras_antigravity()
    atual = REGRAS_ANTIGRAVITY.read_text() if REGRAS_ANTIGRAVITY.exists() else ""

    if marca in atual:
        antes, _, resto = atual.partition(marca)
        _, _, depois = resto.partition(marca)
        novo = antes + bloco + depois
    elif atual.strip():
        novo = atual.rstrip() + "\n\n" + bloco + "\n"
    else:
        novo = bloco + "\n"

    if novo != atual:
        REGRAS_ANTIGRAVITY.parent.mkdir(parents=True, exist_ok=True)
        REGRAS_ANTIGRAVITY.write_text(novo)
    return REGRAS_ANTIGRAVITY


def confiar_no_workspace(caminho: Path = PASTA_TRABALHO) -> None:
    """Marca a pasta de projetos como confiavel para o Antigravity."""
    if not SETTINGS_ANTIGRAVITY.exists():
        return
    try:
        dados = json.loads(SETTINGS_ANTIGRAVITY.read_text() or "{}")
    except (json.JSONDecodeError, OSError):
        return

    confiaveis = dados.setdefault("trustedWorkspaces", [])
    alvo = str(caminho)
    if alvo not in confiaveis:
        confiaveis.append(alvo)
        SETTINGS_ANTIGRAVITY.write_text(json.dumps(dados, indent=2) + "\n")


def para_regex(padrao: str, ancorar: bool = True) -> re.Pattern:
    corpo = []
    for caractere in padrao:
        if caractere == "*":
            corpo.append(".*")
        elif caractere == "?":
            corpo.append(".")
        else:
            corpo.append(re.escape(caractere))
    return re.compile(("^" if ancorar else r"(?:^|\s)") + "".join(corpo), re.I)


CONFIRMACOES_REGEX = [(p, para_regex(p), para_regex(p, ancorar=False)) for p in CONFIRMACOES]
BLOQUEIOS_REGEX = [(p, para_regex(p), para_regex(p, ancorar=False)) for p in BLOQUEIOS]
CREDENCIAIS_REGEX = [(p, para_regex(p, ancorar=False)) for p in CREDENCIAIS]


def dentro_do_projeto(comando: str) -> bool:
    return str(PASTA_TRABALHO) in comando


def detectar_graves(texto: str) -> tuple:
    """Comandos de destruicao real bloqueiam; mencoes no texto so pedem confirmacao."""
    texto = f"{texto}\n{ULTIMO_PEDIDO}"
    bloqueados, a_confirmar = [], []
    for bruto in re.split(r"&&|\|\||;|\||\n|`", texto):
        comando = bruto.strip().lstrip("$(").strip()
        if not comando:
            continue

        if any(solto.search(comando) for _, solto in CREDENCIAIS_REGEX):
            bloqueados.append(comando)
            continue

        if any(regex.match(comando) for _, regex, _ in BLOQUEIOS_REGEX):
            bloqueados.append(comando)
            continue

        if dentro_do_projeto(comando):
            continue

        for _, _, solto in BLOQUEIOS_REGEX:
            achado = solto.search(comando)
            if achado:
                a_confirmar.append(f"{comando}  (apos: {achado.group(0).strip()})")
                break
        else:
            for _, regex, solto in CONFIRMACOES_REGEX:
                if regex.match(comando) or solto.search(comando):
                    a_confirmar.append(comando)
                    break

    return bloqueados, a_confirmar


def confirmar_risco(comandos) -> bool:
    print("\n[nexus] ATENCAO: a tarefa envolve operacoes sensiveis:")
    for comando in comandos:
        print(f"    ! {comando[:160]}")
    while True:
        try:
            resposta = input("[nexus] Confirma a execucao? (digite 'sim'): ").strip().lower()
        except (KeyboardInterrupt, EOFError):
            return False
        if resposta in {"sim", "s", "yes", "y"}:
            return True
        if resposta in {"nao", "não", "n", "no"}:
            return False
        print("[nexus] Responda 'sim' ou 'nao'.")


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


def pedir_ao_opencode(tarefa: str, pasta_destino: str = ".") -> str:
    """Delega toda a parte de codigo para o OpenCode, que executa de verdade."""
    pasta = resolver(pasta_destino)
    pasta.mkdir(parents=True, exist_ok=True)

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
    r"constru(?:i|ir|indo|iu)|scaffold\w*|quero|querendo|preciso|precisando|precisa|arruma\w*)\b"
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
        r = ollama.chat(
            model=MODELO,
            messages=[
                {"role": "system", "content": (
                    "Voce traduz um pedido do usuario em um prompt de execucao para o OpenCode. "
                    "Responda APENAS com o prompt final, em portugues, no imperativo, no maximo 8 linhas. "
                    "Sem cercas de codigo, sem comentarios sobre a traducao."
                )},
                {"role": "user", "content": contexto},
            ],
        )
        tarefa = r["message"]["content"].strip().strip("`").strip()
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

Pasta de trabalho: {PASTA_TRABALHO}
Ferramentas indisponiveis nesta maquina: {", ".join([t["nome"] for t in OPCIONAIS if t not in disponiveis] + [nome for nome, _ in PLUGINS_INDISPONIVEIS]) or "nenhuma"}"""


ALIAS_ARGUMENTOS = {
    "pasta_destino": "caminho", "destino": "caminho", "pasta": "caminho",
    "dir": "caminho", "diretorio": "caminho", "path": "caminho", "local": "caminho",
    "instrucao": "tarefa", "prompt": "tarefa", "comando": "tarefa",
    "descricao": "tarefa", "pergunta": "pergunta", "termo": "busca",
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
    funcao = FERRAMENTAS.get(nome)
    if funcao is None:
        return f"Falha: a ferramenta '{nome}' nao existe."

    try:
        corrigidos, descartados = normalizar_argumentos(funcao, argumentos or {})
    except (TypeError, ValueError) as erro:
        return f"Falha ao interpretar os argumentos de '{nome}': {erro}"

    if descartados:
        print(f"   (aviso: argumento(s) ignorado(s) em {nome}: {', '.join(descartados)})", flush=True)

    faltando = [
        nome for nome, p in inspect.signature(funcao).parameters.items()
        if p.default is p.empty and nome not in corrigidos
    ]
    if faltando:
        return f"Falha: '{nome}' exige o parametro {', '.join(faltando)} e nao foi fornecido."

    bloqueio = _gate_seguranca(META.get(nome), corrigidos)
    if bloqueio:
        return bloqueio

    try:
        return str(funcao(**corrigidos))
    except TypeError as erro:
        return f"Falha nos argumentos de '{nome}': {erro}"
    except Exception as erro:
        return f"Erro na execucao de '{nome}': {erro}"


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


def _corrigir_volume(nome, argumentos, texto):
    """Desempata o volume: do sistema por padrao, do Spotify so se citado.

    O modelo decide isso por conta propria e erra; a fala e a fonte da verdade.
    """
    baixo = (texto or "").lower()
    tem_spotify = "spotify" in baixo
    if nome == "spotify" and (argumentos.get("acao") or "").lower() == "volume":
        # Sem citar o Spotify, 'aumenta o volume' e o volume do notebook. Sem
        # valor e so uma consulta: deixamos no Spotify para nao quebrar.
        if tem_spotify or argumentos.get("valor") is None:
            return nome, argumentos
        return "definir_volume", {"nivel": argumentos.get("valor")}
    if nome == "definir_volume" and tem_spotify:
        return "spotify", {"acao": "volume", "valor": argumentos.get("nivel")}
    return nome, argumentos


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
    """Chama o Ollama; insiste se vier um tool call quebrado ou resposta vazia."""
    mensagem = {"content": ""}
    for _ in range(tentativas):
        r = ollama.chat(model=MODELO, messages=podar(conversa), tools=MANUAL)
        mensagem = r["message"]
        if mensagem.get("tool_calls"):
            return mensagem
        conteudo = (mensagem.get("content") or "").strip()
        if conteudo and not _resposta_quebrada(conteudo):
            return mensagem
    return mensagem


def rodar_turno(conversa, texto: str):
    chamadas = set()
    # Resultados das ferramentas deste turno (nao do historico inteiro): sem
    # isso o fallback podia repetir a resposta de um pedido anterior.
    resultados_turno = []
    # Modelos pequenos repetem a mesma ferramenta no mesmo turno (o Spotify foi
    # chamado duas vezes seguidas com a mesma musica, so mudando o aparelho).
    # Cada repeticao custa um ida-e-volta ao Ollama, entao a segunda e as
    # seguintes reaproveitam o resultado da primeira.
    feitas = {}
    for _ in range(8):
        # A chamada ao Ollama em si nao tem como ser morta no meio, mas da para
        # parar de pedir mais coisa assim que ela volta: sem isso um 'para' dito
        # durante o raciocinio do modelo so era notado 30s depois, na fala.
        if _interrompido():
            print("[nexus] Interrompido antes do proximo passo.", flush=True)
            break
        conversa = podar(conversa)
        mensagem = _chamar_modelo(conversa)
        conversa.append(mensagem)

        if not mensagem.get("tool_calls"):
            # A resposta final e impressa (e falada) por quem chamou.
            break

        nomes_passo, resultados_passo = [], []
        for pedido in mensagem.get("tool_calls"):
            nome = pedido["function"]["name"]
            argumentos = pedido["function"].get("arguments") or {}
            if nome == "spotify":
                argumentos = _ajustar_spotify(argumentos, texto)
            nome, argumentos = _corrigir_volume(nome, argumentos, texto)
            print(f"\n[nexus] executando {nome}({argumentos})...", flush=True)

            chave = _chave_chamada(nome, argumentos)
            if chave in feitas:
                resultado = feitas[chave]
                print("   (duplicado ignorado)", flush=True)
            elif nome == "pedir_ao_opencode" and "pedir_ao_opencode" in chamadas:
                resultado = ("O OpenCode ja foi acionado neste turno. Use o resultado anterior "
                             "para responder, em vez de chamar a ferramenta de novo.")
                print("   (duplicado ignorado)", flush=True)
            else:
                if nome == "pedir_ao_opencode":
                    argumentos, planejou = enriquecer_com_plano(argumentos, texto, chamadas)
                    if planejou:
                        chamadas.add("planejar_com_antigravity")
                chamadas.add(nome)
                resultado = executar(nome, argumentos)
                if nome == "pedir_ao_opencode":
                    revisao = revisar_plano_pendente()
                    if revisao:
                        resultado = f"{resultado}\n\nREVISAO DO ARQUITETO:\n{revisao}"
                feitas[chave] = resultado

            if resultado[:5] in {"FALHA", "Erro ", "BLOQ"}:
                print(f"   x {resultado[:300]}", flush=True)
            conversa.append({"role": "tool", "content": str(resultado)})
            nomes_passo.append(nome)
            resultados_passo.append(str(resultado))
            resultados_turno.append(str(resultado))

            if _interrompido():
                print("[nexus] Interrompido: parando o turno aqui.", flush=True)
                return conversa, chamadas, resultados_turno

        if nomes_passo and all(n in RESPOSTA_DIRETA for n in nomes_passo):
            # O retorno ja e a resposta: fala direto, sem outra ida ao modelo
            # (que costuma deturpar o que a ferramenta devolveu).
            conversa.append({"role": "assistant", "content": "\n".join(resultados_passo)})
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

    r = ollama.chat(model=MODELO, messages=podar(conversa))
    if r["message"].get("content"):
        conversa.append(r["message"])
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
    """Gera um lote de saudacoes curtas com a Ollama, fora do caminho critico."""
    if _gerando_avisos.is_set():
        return
    _gerando_avisos.set()
    try:
        resposta = ollama.chat(
            model=MODELO,
            messages=[
                {"role": "system", "content": SISTEMA_AVISO},
                {"role": "user", "content": f"Gere {quantidade} saudacoes curtas e diferentes, uma por linha."},
            ],
            options={"temperature": 1.1, "num_predict": 80},
        )
        conteudo = (resposta.get("message") or {}).get("content") or ""
        novas = []
        for linha in conteudo.splitlines():
            linha = linha.strip().strip("\"'").lstrip("-*0123456789. ").strip()
            if 0 < len(linha) <= 28 and len(linha.split()) <= 3:
                novas.append(linha)
        with _avisos_lock:
            _avisos.extend(novas[:quantidade])
    except Exception:  # noqa: BLE001 - Ollama fora do ar nao pode travar a voz
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
            print(f"Ouvindo '{voz.WAKEWORD}'...", flush=True)
            if not voz.escutar_wakeword():
                continue
            print("Wakeword detectada.", flush=True)
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
            voz.falar("Nao entendi.")
            continue

        print(f"Voce: {texto}", flush=True)
        if _quer_encerrar(texto):
            voz.falar("Ate logo.")
            break
        if _quer_parar(texto):
            # Nada comecou ainda, mas o pedido e claro e nao vale gastar um
            # turno do modelo para descobrir que o usuario so queria parar.
            print("[voz] Nada a interromper.", flush=True)
            voz.falar("Certo, parei.")
            continue
        confirmacao = _e_confirmacao(texto)
        if confirmacao:
            print(f"\nNexus: {confirmacao}", flush=True)
            voz.falar(confirmacao)
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
            voz.falar("Deu erro ao processar.")
            continue
        _fechar_vigia()

        if _interrompido():
            print("[voz] Interrompido. Voltando a ouvir a wakeword.", flush=True)
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
        voz.falar(resposta)
        if voz.interrompido():
            print("[voz] Fala interrompida.", flush=True)
        voz.descarregar()


def _anunciar_status():
    try:
        ollama.chat(model=MODELO, messages=[{"role": "user", "content": "ping"}])
        arquiteto = f"Antigravity ({MODELO_ARQUITETO})" if AGY else "indisponivel"
        print(f"Nexus online. Cerebro: {MODELO} | Especialista: {MODELO_ESPECIALISTA} | Codigo: OpenCode")
        print(f"Arquiteto: {arquiteto} | Executor: {MODELO_EXECUTOR}")
        print(f"Projetos: {PASTA_TRABALHO}")
        print("Digite 'sair' para encerrar.\n")
    except Exception as erro:
        print(f"Nao consegui falar com o Ollama ({erro}). Ele esta rodando? Inicie com 'ollama serve'.\n")


def conduzir_texto(conversa, texto):
    """Roda um turno escrito e devolve (conversa, resposta)."""
    global ULTIMO_PEDIDO
    conversa[0]["content"] = REGRAS + memoria_para_prompt()
    conversa.append({"role": "user", "content": texto})
    ULTIMO_PEDIDO = texto
    conversa, chamadas, resultados_turno = rodar_turno(conversa, texto)
    garantir_opencode(conversa, texto, chamadas)
    resposta = resposta_falada(extrair_resposta(conversa))
    if not resposta:
        resposta = resposta_falada("\n".join(resultados_turno))
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


def main():
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
import json
import os
import re
import inspect
import shutil
import subprocess
import threading
import time
from datetime import datetime
from pathlib import Path

import ollama
from ddgs import DDGS


MODELO = "llama3.1:8b"
MODELO_ESPECIALISTA = "qwen2.5:7b"

PASTA_TRABALHO = Path.home() / "projetos"
PASTA_TRABALHO.mkdir(parents=True, exist_ok=True)

TEMPO_PADRAO = 120
TEMPO_CODIGO = 900
TEMPO_PLANO = 360
PERMISSOES_AUTOMATICAS = True
LIMITE_HISTORICO = 14

AGY = shutil.which("agy")
MODELO_ANTIGRAVITY = "gemini-3.1-pro-high"
ANTIGRAVITY_PLANEJA = True
ANTIGRAVITY_TOKEN = "<!-- jarvis:regras -->"
REGRAS_ANTIGRAVITY = Path.home() / ".gemini" / "GEMINI.md"
SETTINGS_ANTIGRAVITY = Path.home() / ".gemini" / "antigravity-cli" / "settings.json"

CONFIG_PERMISSOES = Path(__file__).resolve().parent / "opencode-permissoes.json"
ULTIMO_PEDIDO = ""
CHROME_OPENCODE = re.compile(r"^>\s*(build|plan|general)\s*[·|]")

CAMINHOS_PROIBIDOS = [
    "~/.ssh/**", "~/.aws/**", "~/.gnupg/**", "~/.kube/**",
    "~/.config/opencode/**", "~/.config/gh/**", "~/.docker/config.json",
    "/etc/**", "/usr/**", "/bin/**", "/sbin/**", "/boot/**", "/lib/**", "/lib64/**",
    "/proc/**", "/sys/**", "/dev/**",
]

# Destruicao do sistema, do disco ou vazamento de credenciais. O OpenCode bloqueia
# sozinho e o --auto nao burla isso. Nao ha como o Jarvis liberar.
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

# Coisas destrutivas ou irreversiveis, mas legitimas em contexto. O Jarvis pergunta
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

def limpar_ansi(texto: str) -> str:
    return re.sub(r"\x1b\[[0-9;?]*[a-zA-Z]|\x1b\][^\x07]*\x07", "", texto)


REDUNDANTES = {"projetos", "projects", "projeto", "project"}


def resolver(caminho: str) -> Path:
    pasta = Path(str(caminho).strip().strip("\"'")).expanduser()

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


def gerar_config_permissoes() -> dict:
    """Politica aplicada so ao OpenCode chamado pelo Jarvis (via OPENCODE_CONFIG)."""
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
# Regras do Jarvis

Voce opera dentro do Jarvis e deve seguir estas regras sempre.

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
    print("\n[jarvis] ATENCAO: a tarefa envolve operacoes sensiveis:")
    for comando in comandos:
        print(f"    ! {comando[:160]}")
    while True:
        try:
            resposta = input("[jarvis] Confirma a execucao? (digite 'sim'): ").strip().lower()
        except (KeyboardInterrupt, EOFError):
            return False
        if resposta in {"sim", "s", "yes", "y"}:
            return True
        if resposta in {"nao", "não", "n", "no"}:
            return False
        print("[jarvis] Responda 'sim' ou 'nao'.")


def batimento(parado: threading.Event, rotulo: str):
    inicio = time.time()
    while not parado.wait(15):
        minutos, segundos = divmod(int(time.time() - inicio), 60)
        print(f"\r   ... {rotulo} ha {minutos}m{segundos:02d}s", end="", flush=True)


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
    batendo = None
    if mostrar:
        batendo = threading.Thread(target=batimento, args=(parado, comando[0]), daemon=True)
        batendo.start()

    inicio = time.time()
    try:
        for linha in processo.stdout:
            limpa = limpar_ansi(linha).rstrip()
            if limpa.strip():
                linhas.append(limpa)
                if mostrar:
                    print(f"   | {limpa}", flush=True)
            if time.time() - inicio > tempo:
                processo.kill()
                return f"Interrompido: '{comando[0]}' passou de {tempo}s."
    finally:
        parado.set()
        processo.wait()
        if mostrar:
            print("\r" + " " * 60 + "\r", end="", flush=True)

    saida = "\n".join(linhas).strip()
    if processo.returncode != 0 and not saida:
        saida = f"'{comando[0]}' terminou com codigo {processo.returncode} sem produzir saida."
    return saida or f"'{comando[0]}' executado com sucesso."


def resumir_busca(web: str, limite=1800) -> str:
    if len(web) <= limite:
        return web
    return web[:limite] + "\n...[conteudo truncado]"


def pesquisar_na_web(busca: str) -> str:
    try:
        resultados = list(DDGS().text(busca, max_results=5))
        if not resultados:
            return f"Nenhum resultado encontrado para '{busca}'."

        conteudos = [
            f"Titulo: {r.get('title')}\nResumo: {r.get('body')}\nLink: {r.get('href')}"
            for r in resultados
        ]
        return resumir_busca("Informacoes encontradas na web:\n\n" + "\n\n".join(conteudos))
    except Exception as erro:
        return f"Erro ao realizar a busca na web: {erro}"


def criar_pasta(caminho: str):
    pasta = resolver(caminho)
    if pasta.exists() and any(pasta.iterdir()):
        return f"A pasta '{pasta}' ja existe e nao esta vazia."
    pasta.mkdir(parents=True, exist_ok=True)
    return f"Pasta criada em: {pasta}"


def listar_projetos(caminho="."):
    base = resolver(caminho)
    if not base.is_dir():
        return f"A pasta '{base}' nao existe."

    linhas = [f"Projetos em {base}:"]
    for item in sorted(base.iterdir()):
        if not item.is_dir() or item.name.startswith("."):
            continue
        arquivos = [a for a in item.iterdir() if a.name != "node_modules"]
        linhas.append(f"- {item.name} ({len(arquivos)} itens, modificado em {datetime.fromtimestamp(item.stat().st_mtime):%d/%m/%Y})")
    return "\n".join(linhas) if len(linhas) > 1 else f"Nenhum projeto em {base}."


def abrir_pasta(caminho: str):
    pasta = resolver(caminho)
    if not pasta.is_dir():
        return f"A pasta '{pasta}' nao existe."
    subprocess.Popen(["xdg-open", str(pasta)], stdout=subprocess.DEVNULL,
                     stderr=subprocess.DEVNULL, stdin=subprocess.DEVNULL, start_new_session=True)
    return f"Gerenciador de arquivos aberto em: {pasta}"


def abrir_vscode(caminho: str = "."):
    pasta = resolver(caminho)
    if not pasta.exists():
        pasta.mkdir(parents=True, exist_ok=True)
    try:
        subprocess.Popen(["code", str(pasta)], stdout=subprocess.DEVNULL,
                         stderr=subprocess.DEVNULL, stdin=subprocess.DEVNULL, start_new_session=True)
    except FileNotFoundError:
        return "Falha: o VS Code (comando 'code') nao esta instalado."
    return f"VS Code aberto em: {pasta}"


def perguntar_qwen(pergunta: str):
    """Especialista local para raciocinio, explicacoes e pesquisa de conhecimento."""
    try:
        r = ollama.chat(model=MODELO_ESPECIALISTA, messages=[{"role": "user", "content": pergunta}])
        return r["message"]["content"]
    except Exception as erro:
        return f"Falha ao consultar o {MODELO_ESPECIALISTA}: {erro}"


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
        return ("BLOQUEADO pelo Jarvis, nem chegou a ser enviado ao OpenCode:\n"
                + "\n".join(f"- {c}" for c in bloqueados)
                + "\nEssas operacoes destroem o sistema ou vazam credenciais. O Jarvis nunca as executa.")

    if a_confirmar and not confirmar_risco(a_confirmar):
        return "CANCELADO pelo usuario. Nada foi executado."

    comando = ["opencode", "run", "--dir", str(pasta)]
    if PERMISSOES_AUTOMATICAS:
        comando.append("--auto")

    config = aplicar_config_permissoes()
    ambiente = {"OPENCODE_CONFIG": str(config)}
    if a_confirmar:
        ambiente["JARVIS_PERMISSOES"] = "confirmadas"

    print(f"   >>> OpenCode trabalhando em {pasta}", flush=True)
    resultado = rodar(comando + [tarefa], tempo=TEMPO_CODIGO, pasta=pasta, env_extra=ambiente)

    limpo = "\n".join(l for l in resultado.splitlines() if not CHROME_OPENCODE.match(l.strip()))
    print(f"   {inspecionar_projeto(str(pasta))}", flush=True)
    return resumir_busca(limpo or resultado, 3000)


def pedir_ao_claude(tarefa: str):
    """Opicional: usa o Claude Code como segunda opinião."""
    return rodar(["claude", "-p", tarefa], tempo=TEMPO_CODIGO)


def pedir_ao_antigravity(tarefa: str, pasta_destino: str = ".") -> str:
    """Usa o Antigravity como executor/consultor, com o mesmo gate de risco do OpenCode."""
    if not AGY:
        return "O Antigravity (agy) nao esta instalado nesta maquina."

    bloqueados, a_confirmar = detectar_graves(tarefa)
    if bloqueados:
        return ("BLOQUEADO pelo Jarvis, nem chegou ao Antigravity:\n"
                + "\n".join(f"- {c}" for c in bloqueados)
                + "\nEssas operacoes destroem o sistema ou vazam credenciais.")
    if a_confirmar and not confirmar_risco(a_confirmar):
        return "CANCELADO pelo usuario. Nada foi executado."

    pasta = resolver(pasta_destino)
    pasta.mkdir(parents=True, exist_ok=True)
    confiar_no_workspace(pasta)
    aplicar_regras_antigravity()

    comando = [AGY, "--dangerously-skip-permissions", "--model", MODELO_ANTIGRAVITY, "-p", tarefa]
    print(f"   >>> Antigravity executando ({MODELO_ANTIGRAVITY}) em {pasta}", flush=True)
    resultado = rodar(comando, tempo=TEMPO_CODIGO, pasta=pasta)
    print(f"   {inspecionar_projeto(str(pasta))}", flush=True)
    return resumir_busca(resultado, 3000)


def planejar_com_antigravity(pedido: str, pasta_destino: str = ".") -> str:
    """Pede so o plano. Roda sem --dangerously-skip-permissions, entao nao cria nada."""
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
    comando = [AGY, "--mode", "plan", "--model", MODELO_ANTIGRAVITY, "-p", instrucao]
    print(f"   >>> Antigravity planejando ({MODELO_ANTIGRAVITY}) em {pasta}", flush=True)
    plano = rodar(comando, tempo=TEMPO_PLANO, pasta=pasta)

    linhas = [l for l in plano.splitlines() if l.strip()]
    if len(linhas) < 2 or "nao esta instalado" in plano:
        return ""
    return plano


# ---------- CATALOGO UNICO DE FERRAMENTAS ----------

def esquema(propriedades, obrigatorias):
    return {"type": "object", "properties": propriedades, "required": obrigatorias}


TEXTO = {"type": "string"}

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
    {
        "nome": "abrir_vscode",
        "descricao": "Abre uma pasta no Visual Studio Code. Use DEPOIS que o OpenCode terminar de criar o projeto.",
        "parametros": esquema({"caminho": {"type": "string", "description": "Pasta a abrir. Use '.' para a pasta raiz."}}, ["caminho"]),
        "fn": abrir_vscode,
    },
    {
        "nome": "criar_pasta",
        "descricao": "Cria apenas um diretorio vazio. NAO use para criar projetos: isso e responsabilidade do pedir_ao_opencode.",
        "parametros": esquema({"caminho": {"type": "string", "description": "Nome ou caminho da pasta"}}, ["caminho"]),
        "fn": criar_pasta,
    },
    {
        "nome": "listar_projetos",
        "descricao": "Lista os projetos existentes na pasta de trabalho.",
        "parametros": esquema({"caminho": TEXTO}, []),
        "fn": listar_projetos,
    },
    {
        "nome": "abrir_pasta",
        "descricao": "Abre uma pasta no gerenciador de arquivos do sistema (Nautilus).",
        "parametros": esquema({"caminho": {"type": "string", "description": "Pasta a abrir"}}, ["caminho"]),
        "fn": abrir_pasta,
    },
    {
        "nome": "pesquisar_na_web",
        "descricao": "Pesquisa na web e retorna titulos, resumos e links.",
        "parametros": esquema({"busca": {"type": "string", "description": "Termo de pesquisa"}}, ["busca"]),
        "fn": pesquisar_na_web,
    },
    {
        "nome": "perguntar_qwen",
        "descricao": f"Consulta o modelo local {MODELO_ESPECIALISTA} para perguntas de conhecimento, raciocinio ou texto. NAO serve para criar arquivos.",
        "parametros": esquema({"pergunta": {"type": "string", "description": "A pergunta a enviar ao especialista"}}, ["pergunta"]),
        "fn": perguntar_qwen,
    },
]

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
    print("\n[jarvis] Antigravity planeja, OpenCode implementa...", flush=True)
    plano = planejar_com_antigravity(texto, pasta)
    if not plano:
        print("   (sem plano do Antigravity; seguindo direto para o OpenCode)", flush=True)
        return argumentos, False

    novo = dict(argumentos)
    novo["tarefa"] = (f"PLANO DE ARQUITETURA (siga este plano):\n{plano}\n\n"
                      f"PEDIDO ORIGINAL: {tarefa}")
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


REGRAS = f"""Voce e o JARVIS, assistente local em portugues do Brasil. Curto e direto.

SUA DIVISAO DE TRABALHO (obrigatoria):
1. CODIGO E PROJETOS sao SEMPRE delegate ao OpenCode. Se o pedido envolver criar, gerar, montar, alterar ou rodar projeto, app, site, script, componente, API, instalar dependencia ou build, voce OBRIGATORIAMENTE chama 'pedir_ao_opencode' com a pasta_destino correta. Voce nunca escreve, cria ou modifica arquivo de codigo.
2. PARA PROJETOS GRANDES o Antigravity (Gemini) e o ARQUITETO: o sistema pede o plano a ele automaticamente antes de o OpenCode executar. Voce tambem pode chamar 'planejar_com_antigravity' quando o usuario pedir um plano/arquitetura. Use 'pedir_ao_antigravity' apenas quando o usuario citar o Antigravity ou o Gemini.
3. SO use 'criar_pasta' para diretorios vazios de organizacao, nunca para projetos.
4. Use 'abrir_vscode' e 'abrir_pasta' para abrir janelas.
5. Use 'pesquisar_na_web' para fatos atuais, noticias e documentacao. Para perguntas de conhecimento geral (biografia, historia, ciencia, matematica, programacao) prefira 'perguntar_qwen'.

ANTI-ALUCINACAO (obrigatoria):
- Nunca afirme que fez algo sem antes ter chamado a ferramenta correspondente.
- Se nao chamou a ferramenta, diga que nao fez. Nunca invente resultado, arquivos, links ou comandos.
- Se a ferramenta retornou erro, aviso ou bloqueio, relate o erro. Nunca diga que deu certo.
- Ao relatar, use apenas o que a ferramenta realmente retornou.

Pasta de trabalho: {PASTA_TRABALHO}
Ferramentas indisponiveis nesta maquina: {", ".join(t["nome"] for t in OPCIONAIS if t not in disponiveis) or "nenhuma"}"""


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

    try:
        return str(funcao(**corrigidos))
    except TypeError as erro:
        return f"Falha nos argumentos de '{nome}': {erro}"
    except Exception as erro:
        return f"Erro na execucao de '{nome}': {erro}"


def rodar_turno(conversa, texto: str):
    chamadas = set()
    for _ in range(8):
        conversa = podar(conversa)
        r = ollama.chat(model=MODELO, messages=conversa, tools=MANUAL)
        mensagem = r["message"]
        conversa.append(mensagem)

        if not mensagem.get("tool_calls"):
            if mensagem.get("content"):
                print(f"\nJarvis: {mensagem['content']}")
            break

        for pedido in mensagem["tool_calls"]:
            nome = pedido["function"]["name"]
            argumentos = pedido["function"].get("arguments") or {}
            print(f"\n[jarvis] executando {nome}({argumentos})...", flush=True)

            if nome == "pedir_ao_opencode" and "pedir_ao_opencode" in chamadas:
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

            if resultado[:5] in {"FALHA", "Erro ", "BLOQ"}:
                print(f"   x {resultado[:300]}", flush=True)
            conversa.append({"role": "tool", "content": str(resultado)})
    return conversa, chamadas


def garantir_opencode(conversa, texto: str, chamadas: set) -> set:
    if "pedir_ao_opencode" in chamadas or not precisa_de_codigo(texto):
        return chamadas

    pasta = detecta_pasta(texto) or "."
    print("\n[jarvis] o pedido e de codigo e o OpenCode nao foi acionado. Forcando delegacao...", flush=True)
    argumentos = {"tarefa": montar_tarefa_opencode(texto, resolver(pasta)), "pasta_destino": pasta}
    argumentos, planejou = enriquecer_com_plano(argumentos, texto, chamadas)
    if planejou:
        chamadas.add("planejar_com_antigravity")
    resultado = executar("pedir_ao_opencode", argumentos)
    conversa.append({"role": "tool", "content": str(resultado)})

    if re.search(r"\b(vscode|vs code|visual studio code|editor)\b", texto, re.I) and "abrir_vscode" not in chamadas:
        abrir = executar("abrir_vscode", {"caminho": pasta})
        conversa.append({"role": "tool", "content": str(abrir)})

    r = ollama.chat(model=MODELO, messages=podar(conversa))
    if r["message"].get("content"):
        print(f"\nJarvis: {r['message']['content']}")
    return chamadas | {"pedir_ao_opencode"}


def main():
    aplicar_config_permissoes()
    if AGY:
        aplicar_regras_antigravity()
        confiar_no_workspace()
    try:
        ollama.chat(model=MODELO, messages=[{"role": "user", "content": "ping"}])
        arquiteto = f"Antigravity ({MODELO_ANTIGRAVITY})" if AGY else "indisponivel"
        print(f"Jarvis online. Cerebro: {MODELO} | Especialista: {MODELO_ESPECIALISTA} | Codigo: OpenCode")
        print(f"Arquiteto: {arquiteto}")
        print(f"Projetos: {PASTA_TRABALHO}")
        print("Digite 'sair' para encerrar.\n")
    except Exception as erro:
        print(f"Nao consegui falar com o Ollama ({erro}). Ele esta rodando? Inicie com 'ollama serve'.\n")

    conversa = [{"role": "system", "content": REGRAS}]

    while True:
        try:
            texto = input("\nVoce: ").strip()
        except (KeyboardInterrupt, EOFError):
            break

        if not texto:
            continue
        if texto.lower() in {"sair", "exit", "quit"}:
            break

        conversa.append({"role": "user", "content": texto})
        global ULTIMO_PEDIDO
        ULTIMO_PEDIDO = texto
        try:
            conversa, chamadas = rodar_turno(conversa, texto)
            garantir_opencode(conversa, texto, chamadas)
        except KeyboardInterrupt:
            print("\nInterrompido.")
        except Exception as erro:
            print(f"\nErro no turno: {erro}")

    print("\nJarvis desligado.")


if __name__ == "__main__":
    main()
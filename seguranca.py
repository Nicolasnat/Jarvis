"""Modulo de segurança central do Nexus.

Contem as listas de bloqueio, credenciais, confirmacoes e caminhos proibidos,
bem como as funcoes de deteccao de risco e geracao de configuracao do OpenCode.
Este arquivo e PROTEGIDO: o auto-aprimoramento nao pode altera-lo.
"""
import json
import os
import re
import subprocess
import threading
from pathlib import Path

from comum import PASTA_TRABALHO, BASE_PROJETO, chave_nome


CAMINHOS_PROIBIDOS = [
    "~/.ssh/**", "~/.aws/**", "~/.gnupg/**", "~/.kube/**",
    "~/.config/opencode/**", "~/.config/gh/**", "~/.docker/config.json",
    "/etc/**", "/usr/**", "/bin/**", "/sbin/**", "/boot/**", "/lib/**", "/lib64/**",
    "/proc/**", "/sys/**", "/dev/**", "config/gemini.json", "config/cerebro.json", "dados/uso_cerebro.json"
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
    "cat ~/.config/opencode/*", "cat ~/.docker/config.json", "cat *gemini.json*",
    "history -c*", "shred *", "wipe *",
]

# Vazamento de credenciais em linguagem natural (texto, nao comando exato).
CREDENCIAIS = [
    "*.ssh*", "*.aws*", "*.gnupg*", "*.netrc*", "*/.kube/*",
    "*id_rsa*", "*id_ed25519*", "*auth.json*",
    "*.docker/config.json*", "*.config/opencode/*", "*gemini.json*", "AIza*"
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


CONFIG_PERMISSOES = BASE_PROJETO / "opencode-permissoes.json"
ULTIMO_PEDIDO = ""


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
    global ULTIMO_PEDIDO
    texto = f"{texto}\n{ULTIMO_PEDIDO}"
    bloqueados, a_confirmar = [], []
    for bruto in re.split(r"&&|\|\||;|\||\n|`", texto):
        comando = bruto.strip().lstrip("$(").strip()
        if not comando:
            continue

        if any(solto.search(comando) for _, solto in CREDENCIAIS_REGEX):
            bloqueados.append(comando)
            continue

        # Primeiro verifica se e dentro do projeto - se for, nao bloqueia nem pede confirmacao
        if dentro_do_projeto(comando):
            continue

        if any(regex.match(comando) for _, regex, _ in BLOQUEIOS_REGEX):
            bloqueados.append(comando)
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


_ponte = None


def _set_ponte(ponte):
    global _ponte
    _ponte = ponte


def confirmar_risco(comandos) -> bool:
    comandos = [str(c) for c in comandos]
    if _ponte is not None:
        try:
            return bool(_ponte.pedir_confirmacao_bloqueante(comandos))
        except Exception:
            pass
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


# Antigravity
ANTIGRAVITY_TOKEN = "<!-- nexus:regras -->"
REGRAS_ANTIGRAVITY = Path.home() / ".gemini" / "GEMINI.md"
SETTINGS_ANTIGRAVITY = Path.home() / ".gemini" / "antigravity-cli" / "settings.json"


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


def salvar_chave_gemini(chave: str, nome_ref: str = "GEMINI_API_KEY_GRATIS") -> Path:
    """Salva a chave da API Gemini em config/gemini.json com permissao 600."""
    from comum import BASE_PROJETO
    arquivo = BASE_PROJETO / "config" / "gemini.json"
    arquivo.parent.mkdir(parents=True, exist_ok=True)
    dados = {}
    if arquivo.exists():
        try:
            dados = json.loads(arquivo.read_text())
        except (json.JSONDecodeError, OSError):
            dados = {}
    dados[nome_ref] = chave
    # Escreve com permissao 600 (apenas dono le/escrita)
    arquivo.write_text(json.dumps(dados, indent=2, ensure_ascii=False))
    try:
        os.chmod(arquivo, 0o600)
    except OSError:
        pass
    return arquivo


def ler_chave_gemini(nome_ref: str = "GEMINI_API_KEY_GRATIS") -> str:
    """Le a chave da API Gemini do config/gemini.json."""
    from comum import BASE_PROJETO
    arquivo = BASE_PROJETO / "config" / "gemini.json"
    if not arquivo.exists():
        return ""
    try:
        dados = json.loads(arquivo.read_text())
        return dados.get(nome_ref, "")
    except (json.JSONDecodeError, OSError):
        return ""
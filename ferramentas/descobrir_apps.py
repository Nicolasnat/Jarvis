"""Plugin: escaneia os aplicativos instalados e registra em config/apps.json.

O usuario fala o nome do app ("abre oinkscape"), nao o caminho do executavel.
Este plugin le os arquivos .desktop do sistema, monta a lista de tudo que da
para abrir e grava em config/apps.json, de onde o 'abrir_programa' le.

Como os .desktop usam o nome do fabricante ("Visual Studio Code", "GNOME
System Monitor"), cada app ganha tambem um apelido com o nome do executavel
("code", "gnome-system-monitor"), que e o que a pessoa costuma dizer.
"""
import configparser
import os
import shutil
from pathlib import Path

from comum import ARQUIVO_APPS, PASTA_DADOS, chave_nome, ler_json, salvar_json, esquema

NOME = "descobrir_apps"
DESCRICAO = (
    "Escaneia os aplicativos instalados no sistema e registra na lista permitida "
    "(config/apps.json), para o Nexus conseguir abrir qualquer programa do usuario. "
    "Use quando o usuario pedir para ler/descobrir os aplicativos dele, ou quiser que "
    "o Nexus reconheca um programa novo."
)
PARAMETROS = esquema(
    {"aplicar": {"type": "boolean", "description": "true grava a lista; false so mostra o que foi encontrado"}},
    [],
)

MANIFESTO = Path(PASTA_DADOS) / "apps_gerados.json"

PASTAS = (
    "/usr/share/applications",
    "~/.local/share/applications",
    "/var/lib/snapd/desktop/applications",
    "/usr/local/share/applications",
    # Flatpak guarda os .desktop em "exports"; sem estas pastas o Google Chrome
    # (e qualquer outro app flatpak) nunca aparece na lista.
    "/var/lib/flatpak/exports/share/applications",
    "~/.local/share/flatpak/exports/share/applications",
)

CODIGOS_CAMPO = {"%f", "%F", "%u", "%U", "%i", "%c", "%k", "%d", "%D", "%n", "%N", "%v", "%m"}

# Nomes de fabricante -> como a pessoa normalmente fala.
APELIDOS = {
    "visual studio code": ["vscode", "code"],
    "gnome system monitor": ["monitor de sistema", "monitor do sistema"],
    "pulseaudio volume control": ["controle de volume", "pavucontrol"],
    "document viewer": ["leitor de pdf", "visualizador de pdf"],
    "image viewer": ["visualizador de imagem", "visor de imagem"],
    "files": ["arquivos", "nautilus", "explorador de arquivos", "gerenciador de arquivos"],
    "software updater": ["atualizador", "gerenciador de atualizacoes"],
    "software & updates": ["configuracoes de software"],
    "app center": ["loja de apps", "snap store", "snap-store"],
    "onlyoffice": ["onlyoffice desktop editors"],
    "opencode desktop": ["opencode"],
    "disk usage analyzer": ["analisador de disco", "baobab"],
    "advanced network configuration": ["editor de conexao", "gerenciador de rede"],
    "text editor": ["editor de texto"],
    "language support": ["suporte a idiomas"],
    "passwords and keys": ["senhas e chaves", "seahorse"],
    "nvidia x server settings": ["configuracoes da nvidia"],
    "system monitor": ["monitor de sistema"],
    "settings": ["configuracoes"],
    "software": ["loja", "ubuntu software"],
    "terminal": ["terminal"],
    "clock": ["relogio", "clocks", "despertador"],
}


def _comando_exec(exec_line: str):
    """Extrai o executavel de uma linha Exec, descartando %U/%F e afins."""
    partes = []
    atual = ""
    aspas = ""
    for caractere in exec_line:
        if aspas:
            if caractere == aspas:
                aspas = ""
            else:
                atual += caractere
        elif caractere in "\"'":
            aspas = caractere
        elif caractere.isspace():
            if atual:
                partes.append(atual)
                atual = ""
        else:
            atual += caractere
    if atual:
        partes.append(atual)

    uteis = [p for p in partes if p not in CODIGOS_CAMPO and not p.startswith("@@")]
    if not uteis:
        return None

    # Flatpak e Snap guardam o programa inteiro na linha Exec
    # ('flatpak run ... com.google.Chrome'), entao a linha toda e necessaria.
    if "flatpak" in Path(uteis[0]).name or uteis[0:2] == ["snap", "run"]:
        return uteis

    return uteis[:1]


def _instalado(comando) -> bool:
    executavel = comando[0]
    if os.path.isabs(executavel):
        return os.access(executavel, os.X_OK)
    return shutil.which(executavel) is not None


def _id_flatpak(comando):
    """Extrai o app-id ('com.google.Chrome') de um comando flatpak/snap."""
    for i, parte in enumerate(comando):
        if parte in {"run", "launch"}:
            candidatos = comando[i + 1:]
            break
    else:
        return None
    for parte in candidatos:
        if parte.startswith("-"):
            continue
        if parte.count(".") >= 1 and "/" not in parte:
            return parte
    return None


def _varrer():
    """Le os .desktop e devolve {chave: comando}."""
    encontrados = {}

    for pasta in PASTAS:
        raiz = Path(os.path.expanduser(pasta))
        if not raiz.is_dir():
            continue

        for arquivo in sorted(raiz.glob("*.desktop")):
            parser = configparser.RawConfigParser(strict=False, interpolation=None)
            try:
                with open(arquivo, encoding="utf-8", errors="replace") as fluxo:
                    parser.read_file(fluxo)
            except (configparser.Error, OSError, UnicodeError):
                continue

            if not parser.has_section("Desktop Entry"):
                continue

            secao = parser["Desktop Entry"]
            if secao.get("Type", "Application") != "Application":
                continue
            if secao.get("NoDisplay", "false").strip().lower() == "true":
                continue
            if secao.get("Hidden", "false").strip().lower() == "true":
                continue

            nome = (secao.get("Name") or "").strip()
            exec_line = (secao.get("Exec") or "").strip()
            if not nome or not exec_line:
                continue

            comando = _comando_exec(exec_line)
            if not comando or "pkexec" in " ".join(comando):
                continue

            if not _instalado(comando):
                continue

            base = Path(comando[0]).name
            variantes = [chave_nome(nome), chave_nome(base)]
            variantes += [chave_nome(a) for a in APELIDOS.get(chave_nome(nome), [])]

            # Flatpak/Snap: o id do app ('com.google.Chrome') vira apelido tambem,
            # para 'abre o chrome' funcionar sem o nome completo.
            identificador = _id_flatpak(comando)
            if identificador:
                variantes.append(chave_nome(identificador.split(".")[-1]))

            for variante in variantes:
                if variante and variante not in encontrados:
                    encontrados[variante] = list(comando)

    return encontrados


def funcao(aplicar: bool = True):
    encontrados = _varrer()
    if not encontrados:
        return (
            "Nenhum aplicativo encontrado. Verifique se existe "
            "/usr/share/applications com arquivos .desktop."
        )

    if not aplicar:
        return (
            f"Encontrei {len(encontrados)} aplicativos, mas nao gravei nada "
            f"(aplicar=false). Primeiros: {', '.join(sorted(encontrados)[:20])}."
        )

    atuais = ler_json(ARQUIVO_APPS, {})
    if not isinstance(atuais, dict):
        atuais = {}

    # Nomes de execucoes anteriores que hoje nao existem mais sao descartados, para
    # o scan nao acumular apelidos velhos a cada rodada. O que o usuario
    # cadastrou a mao (fora do manifesto) e preservado.
    gerados_anteriores = set(ler_json(MANIFESTO, []))
    manuais = {
        chave: comando for chave, comando in atuais.items()
        if chave not in gerados_anteriores
    }

    finais = dict(encontrados)
    for chave, comando in manuais.items():
        finais.setdefault(chave, comando)

    salvar_json(ARQUIVO_APPS, dict(sorted(finais.items())))
    salvar_json(MANIFESTO, sorted(encontrados))
    return (
        f"Registrei {len(finais)} aplicativos em {ARQUIVO_APPS} "
        f"({len(encontrados)} descobertos no sistema"
        f"{f', {len(manuais)} seus' if manuais else ''}). "
        f"Agora voce pode abrir qualquer um pelo nome, por exemplo: "
        f"{', '.join(sorted(encontrados)[:8])}."
    )
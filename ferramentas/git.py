"""Plugin: executa comandos git no repositorio do projeto."""
import subprocess
from comum import PASTA_TRABALHO, resolver, esquema

NOME = "git"
DESCRICAO = (
    "Executa comandos git no repositorio do projeto. "
    "QUANDO USAR: status, commit, push, pull, diff, log, branch, checkout, merge, stash, etc. "
    "O comando roda na pasta do projeto (ou subpasta especificada). "
    "QUANDO NAO USAR: para operacoes fora do repositorio do projeto, "
    "ou para criar repositorios novos (use 'criar_pasta' + 'git init' via OpenCode). "
    "ACOES DESTRUTIVAS (push, reset --hard, clean -fd, checkout .) EXIGEM CONFIRMACAO. "
    "Exemplos: comando='status', comando='commit -m \"feat: nova funcionalidade\"', "
    "comando='push origin main', comando='diff', comando='log --oneline -10'."
)
PARAMETROS = esquema(
    {
        "comando": {"type": "string", "description": "Comando git completo (ex.: 'status', 'commit -m \"mensagem\"', 'push origin main')"},
        "pasta": {"type": "string", "description": "Pasta onde executar (default: pasta raiz do projeto). Use '.' para a raiz."},
    },
    ["comando"],
)
SEGURANCA = "detectar"
BINARIO = "git"


def funcao(comando: str, pasta: str = ".") -> str:
    local = resolver(pasta)
    if not local.exists():
        return f"ERRO: a pasta '{local}' nao existe."

    if not (local / ".git").exists():
        return f"ERRO: '{local}' nao e um repositorio git (nao ha pasta .git)."

    try:
        resultado = subprocess.run(
            ["git"] + comando.split(),
            cwd=str(local),
            capture_output=True,
            text=True,
            timeout=60,
        )
    except FileNotFoundError:
        return "Falha: git nao esta instalado."
    except subprocess.TimeoutExpired:
        return "Erro: comando git excedeu 60 segundos."

    saida = resultado.stdout.strip()
    erro = resultado.stderr.strip()

    if resultado.returncode != 0:
        return f"Git falhou (codigo {resultado.returncode}):\n{erro or saida or 'sem saida'}"

    return saida or "(comando executado, sem saida)"
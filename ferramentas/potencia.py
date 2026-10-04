"""Plugin: desliga, reinicia ou suspende o computador."""
import subprocess
from comum import esquema

NOME = "potencia"
DESCRICAO = (
    "Controla a energia do sistema: desligar, reiniciar, suspender, hibernar. "
    "QUANDO USAR: usuario pede explicitamente 'desligar', 'reiniciar', 'suspender' ou 'hibernar' o computador. "
    "QUANDO NAO USAR: para fechar apenas um programa (use 'fechar_programa'), "
    "ou para reiniciar apenas um servico. "
    "EXIGE CONFIRMACAO DO USUARIO (gate de seguranca - acao irreversivel). "
    "Exemplos: acao='desligar', acao='reiniciar', acao='suspender', acao='hibernar'."
)
PARAMETROS = esquema(
    {
        "acao": {
            "type": "string",
            "description": "Acao a executar: desligar, reiniciar, suspender, hibernar",
            "enum": ["desligar", "reiniciar", "suspender", "hibernar"],
        }
    },
    ["acao"],
)
SEGURANCA = "sempre"


def funcao(acao: str):
    acao = (acao or "").strip().lower()
    comandos = {
        "desligar": ["systemctl", "poweroff"],
        "reiniciar": ["systemctl", "reboot"],
        "suspender": ["systemctl", "suspend"],
        "hibernar": ["systemctl", "hibernate"],
    }
    if acao not in comandos:
        return f"Acao invalida: {acao}. Use: desligar, reiniciar, suspender, hibernar."

    try:
        subprocess.run(comandos[acao], check=True)
        return f"Comando '{acao}' enviado."
    except subprocess.CalledProcessError as erro:
        return f"Falha ao executar '{acao}': {erro}"
    except FileNotFoundError:
        return "systemctl nao encontrado."
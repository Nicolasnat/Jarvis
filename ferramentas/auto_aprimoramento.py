"""Plugin: auto-aprimoramento supervisionado do proprio Nexus.

Permite que o usuario peca para o Nexus corrigir bugs ou adicionar funcoes em si mesmo.
Fluxo seguro: worktree isolada -> testes -> aprovacao -> merge -> vigia systemd + rollback.
"""
import json
import os
import shutil
import subprocess
import time
from datetime import datetime
from pathlib import Path

from comum import PASTA_TRABALHO, BASE_PROJETO, PASTA_DADOS, ler_json, salvar_json
from seguranca import confirmar_risco

NOME = "auto_aprimoramento"
DESCRICAO = (
    "Auto-aprimoramento supervisionado do Nexus: corrige bugs ou adiciona funcoes no proprio codigo. "
    "Cria worktree isolada, roda testes, pede sua aprovacao, aplica e vigia o servico. "
    "Use para 'corrige esse bug no seu codigo', 'adiciona tal funcao em voce', 'melhore o nexus'."
)
PARAMETROS = {
    "type": "object",
    "properties": {
        "pedido": {"type": "string", "description": "O que deve ser corrigido ou adicionado no Nexus (ex.: 'corrigir bug no abrir_programa', 'adicionar funcao X')."},
        "descricao": {"type": "string", "description": "Descricao opcional para o commit/tag (ex.: 'fix: abre steam corretamente')."},
    },
    "required": ["pedido"],
}
SEGURANCA = "sempre"


ARQUIVO_HISTORICO = PASTA_DADOS / "auto_aprimoramentos.json"
ARQUIVO_LOCK = PASTA_DADOS / "auto_aprimoramento.lock"
PASTA_WORKTREES = PASTA_TRABALHO / ".nexus-dev"
TEMPO_VIGIA = 60
MAX_TENTATIVAS_TESTE = 2
MAX_LINHAS_DIFF_AVISO = 500


def _eh_protegido(caminho: str) -> bool:
    """Verifica se o caminho esta na lista de protegidos."""
    try:
        dados = ler_json(BASE_PROJETO / "config/protegidos.json", {"protegidos": []})
        protegidos = dados.get("protegidos", [])
    except Exception:
        protegidos = []
    for p in protegidos:
        if p.endswith("/"):
            if caminho.startswith(p) or caminho == p.rstrip("/"):
                return True
        else:
            if caminho == p or caminho.startswith(p + "/"):
                return True
    return False


def _verificar_protegidos(worktree: Path) -> list:
    """Retorna lista de arquivos protegidos que foram alterados na worktree."""
    resultado = subprocess.run(
        ["git", "-C", str(worktree), "diff", "--name-only", "HEAD"],
        capture_output=True, text=True
    )
    if resultado.returncode != 0:
        return ["ERRO ao rodar git diff"]
    alterados = [l.strip() for l in resultado.stdout.splitlines() if l.strip()]
    return [a for a in alterados if _eh_protegido(a)]


def _rodar_autoteste(worktree: Path) -> tuple:
    """Roda python nexus.py --autoteste na worktree. Retorna (sucesso, saida)."""
    python_venv = BASE_PROJETO / "venv" / "bin" / "python"
    if not python_venv.exists():
        return False, "venv nao encontrado em " + str(python_venv)
    env = {**os.environ, "PYTHONPATH": str(worktree)}
    resultado = subprocess.run(
        [str(python_venv), "nexus.py", "--autoteste"],
        cwd=str(worktree),
        capture_output=True, text=True, timeout=300, env=env
    )
    return resultado.returncode == 0, resultado.stdout + "\n" + resultado.stderr


def _apresentar_diff(worktree: Path, tag_antes: str) -> str:
    """Gera resumo do diff para apresentacao ao usuario."""
    # diff --stat
    stat = subprocess.run(
        ["git", "-C", str(worktree), "diff", "--stat", tag_antes],
        capture_output=True, text=True
    )
    stat_txt = stat.stdout.strip()

    # diff resumido (primeiras 200 linhas)
    diff = subprocess.run(
        ["git", "-C", str(worktree), "diff", tag_antes],
        capture_output=True, text=True
    )
    diff_txt = diff.stdout.strip()
    linhas = diff_txt.splitlines()
    if len(linhas) > 200:
        diff_txt = "\n".join(linhas[:200]) + "\n... (diff truncado)"

    # Detecta se toca nucleo
    nucleo = any("nexus.py" in l or "voz.py" in l or "comum.py" in l or l.startswith("interface/") for l in stat_txt.splitlines())
    tag_nucleo = " **NUCLEO**" if nucleo else ""

    return f"{tag_nucleo}\n\nEstatisticas:\n{stat_txt}\n\nDiff:\n```diff\n{diff_txt}\n```"


def _registrar_historico(registro: dict) -> None:
    """Salva no historico de auto-aprimoramentos."""
    historico = ler_json(ARQUIVO_HISTORICO, [])
    historico.append(registro)
    salvar_json(ARQUIVO_HISTORICO, historico)


def _obter_lock() -> bool:
    """Tenta obter lock exclusivo para auto-aprimoramento."""
    try:
        PASTA_DADOS.mkdir(parents=True, exist_ok=True)
        with open(ARQUIVO_LOCK, "x") as f:
            f.write(str(os.getpid()))
        return True
    except FileExistsError:
        return False


def _liberar_lock() -> None:
    try:
        ARQUIVO_LOCK.unlink()
    except Exception:
        pass


def _limpar_worktree_antiga(worktree: Path, branch: str) -> None:
    """Remove worktree e branch se existirem."""
    try:
        subprocess.run(["git", "worktree", "remove", "--force", str(worktree)], capture_output=True)
    except Exception:
        pass
    try:
        subprocess.run(["git", "branch", "-D", branch], capture_output=True)
    except Exception:
        pass


def funcao(pedido: str, descricao: str = "") -> str:
    """Executa o fluxo completo de auto-aprimoramento."""
    # 1. PRE-CHECAGEM
    if not (BASE_PROJETO / ".git").exists():
        return "ERRO: nao e um repositorio git."

    # Verifica arvore limpa
    status = subprocess.run(
        ["git", "-C", str(BASE_PROJETO), "status", "--porcelain"],
        capture_output=True, text=True
    )
    if status.stdout.strip():
        return ("ERRO: arvore git nao esta limpa. Commite ou stash suas mudancas primeiro.\n"
                f"Arquivos sujos:\n{status.stdout}")

    # Lock
    if not _obter_lock():
        return "ERRO: ja existe um auto-aprimoramento em andamento (lock ativo)."

    # 2. PONTO DE RESTAURACAO
    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    tag_antes = f"nexus-antes-{timestamp}"
    subprocess.run(["git", "-C", str(BASE_PROJETO), "tag", tag_antes], check=True)

    # 3. WORKTREE ISOLADA
    auto_id = f"auto-{timestamp}"
    slug = "".join(c if c.isalnum() else "-" for c in pedido.lower()[:30]).strip("-")
    branch = f"auto/{auto_id}-{slug}"
    worktree = PASTA_WORKTREES / auto_id

    PASTA_WORKTREES.mkdir(parents=True, exist_ok=True)
    _limpar_worktree_antiga(worktree, branch)

    try:
        subprocess.run(
            ["git", "-C", str(BASE_PROJETO), "worktree", "add", "-b", branch, str(worktree)],
            check=True, capture_output=True, text=True
        )
    except subprocess.CalledProcessError as e:
        _liberar_lock()
        return f"ERRO ao criar worktree: {e.stderr}"

    try:
        # 4. CHAMA OPENCODE NA WORKTREE
        # Prepara a tarefa para o OpenCode
        tarefa_opencode = (
            f"AUTO-APRIMORAMENTO DO NEXUS\n\n"
            f"PEDIDO DO USUARIO: {pedido}\n\n"
            f"REGRAS OBRIGATORIAS:\n"
            f"- Voce esta em uma COPIA ISOLADA (git worktree) do Nexus.\n"
            f"- Nao altere arquivos protegidos (lista em config/protegidos.json).\n"
            f"- Rode os testes: python nexus.py --autoteste (sem Ollama, sem microfone, sem dados/).\n"
            f"- Se os testes falharem, corrija e tente de novo (max {MAX_TENTATIVAS_TESTE} tentativas).\n"
            f"- Faca mudancas minimas e focadas.\n"
            f"- Nao mexa em credenciais, chaves, .env, servicos systemd, instaladores.\n"
            f"- Se o pedido for amplo demais, avise e sugira dividir.\n"
        )
        if descricao:
            tarefa_opencode += f"\nDESCRICAO PARA COMMIT: {descricao}"

        # Chama pedir_ao_opencode (importa localmente para evitar circular)
        from nexus import pedir_ao_opencode
        resultado_opencode = pedir_ao_opencode(tarefa_opencode, str(worktree))

        # 5. VERIFICACAO DE PROTEGIDOS
        protegidos_tocados = _verificar_protegidos(worktree)
        if protegidos_tocados:
            _limpar_worktree_antiga(worktree, branch)
            subprocess.run(["git", "-C", str(BASE_PROJETO), "tag", "-d", tag_antes], capture_output=True)
            _liberar_lock()
            return ("REJEITADO: arquivos protegidos foram alterados:\n"
                    + "\n".join(f"  - {p}" for p in protegidos_tocados)
                    + "\n\nA worktree foi descartada. Nada foi aplicado.")

        # 6. VALIDACAO (autoteste)
        tentativas = 0
        while tentativas < MAX_TENTATIVAS_TESTE:
            ok, saida_teste = _rodar_autoteste(worktree)
            if ok:
                break
            tentativas += 1
            if tentativas < MAX_TENTATIVAS_TESTE:
                # Devolve o erro ao OpenCode para corrigir
                tarefa_correcao = (
                    f"O autoteste falhou. Corrija os erros abaixo e rode novamente python nexus.py --autoteste.\n\n"
                    f"SAIDA DO TESTE:\n{saida_teste}"
                )
                pedir_ao_opencode(tarefa_correcao, str(worktree))
            else:
                _limpar_worktree_antiga(worktree, branch)
                subprocess.run(["git", "-C", str(BASE_PROJETO), "tag", "-d", tag_antes], capture_output=True)
                _liberar_lock()
                return (f"FALHA NA VALIDACAO apos {MAX_TENTATIVAS_TESTE} tentativas.\n"
                        f"Ultimo erro:\n{saida_teste}\n\nWorktree descartada.")

        # 7. APRESENTACAO
        diff_resumo = _apresentar_diff(worktree, tag_antes)

        # 8. APROVACAO
        if not confirmar_risco([f"Aplicar auto-aprimoramento?\n\n{diff_resumo}"]):
            _limpar_worktree_antiga(worktree, branch)
            subprocess.run(["git", "-C", str(BASE_PROJETO), "tag", "-d", tag_antes], capture_output=True)
            _liberar_lock()
            return "CANCELADO pelo usuario. Worktree descartada."

        # 9. APLICACAO (merge fast-forward)
        tag_depois = f"nexus-depois-{auto_id}"
        subprocess.run(["git", "-C", str(BASE_PROJETO), "merge", "--ff-only", branch], check=True)
        subprocess.run(["git", "-C", str(BASE_PROJETO), "tag", tag_depois], check=True)

        # Limpa worktree e branch
        _limpar_worktree_antiga(worktree, branch)

        # 10. VIGIA (script shell independente)
        script_vigia = BASE_PROJETO / "scripts" / "aplicar_e_vigiar.sh"
        if script_vigia.exists():
            subprocess.Popen([str(script_vigia), tag_antes], start_new_session=True)
            msg_vigia = "Vigia iniciado em segundo plano (reinicia servico, checa saude, rollback se falhar)."
        else:
            msg_vigia = "AVISO: script scripts/aplicar_e_vigiar.sh nao encontrado. Vigia nao rodara."

        # 11. REGISTRO
        arquivos_alterados = _verificar_protegidos(worktree)  # reusa para listar todos
        if not arquivos_alterados:
            # pega lista real
            diff_files = subprocess.run(
                ["git", "-C", str(BASE_PROJETO), "diff", "--name-only", tag_antes],
                capture_output=True, text=True
            )
            arquivos_alterados = [l.strip() for l in diff_files.stdout.splitlines() if l.strip()]

        _registrar_historico({
            "id": auto_id,
            "data": datetime.now().isoformat(),
            "descricao": descricao or pedido,
            "pedido": pedido,
            "status": "aplicado",
            "arquivos": arquivos_alterados,
            "tags": {"antes": tag_antes, "depois": tag_depois},
        })

        _liberar_lock()
        return (f"AUTO-APRIMORAMENTO APLICADO COM SUCESSO\n\n"
                f"ID: {auto_id}\n"
                f"Tags: {tag_antes} -> {tag_depois}\n"
                f"Arquivos alterados: {len(arquivos_alterados)}\n"
                f"{msg_vigia}\n\n"
                f"Resumo:\n{diff_resumo}")

    except subprocess.CalledProcessError as e:
        _limpar_worktree_antiga(worktree, branch)
        subprocess.run(["git", "-C", str(BASE_PROJETO), "tag", "-d", tag_antes], capture_output=True)
        _liberar_lock()
        return f"ERRO durante o processo: {e.stderr or str(e)}"
    except Exception as e:
        _limpar_worktree_antiga(worktree, branch)
        subprocess.run(["git", "-C", str(BASE_PROJETO), "tag", "-d", tag_antes], capture_output=True)
        _liberar_lock()
        return f"ERRO inesperado: {e}"


def historico_aprimoramentos() -> str:
    """Retorna historico legivel de auto-aprimoramentos."""
    historico = ler_json(ARQUIVO_HISTORICO, [])
    if not historico:
        return "Nenhum auto-aprimoramento registrado ainda."
    linhas = []
    for h in historico[-10:]:
        data = h.get("data", "")[:19].replace("T", " ")
        status = h.get("status", "?")
        desc = h.get("descricao", "")[:60]
        arquivos = len(h.get("arquivos", []))
        linhas.append(f"  {data} | {status} | {arquivos} arqs | {desc}")
    return "Historico de auto-aprimoramentos (ultimos 10):\n" + "\n".join(linhas)


def desfazer_ultimo() -> str:
    """Desfaz o ultimo auto-aprimoramento aplicado (rollback para tag antes)."""
    historico = ler_json(ARQUIVO_HISTORICO, [])
    if not historico:
        return "Nenhum auto-aprimoramento para desfazer."

    ultimo = historico[-1]
    if ultimo.get("status") != "aplicado":
        return "Ultimo registro nao e um auto-aprimoramento aplicado."

    tag_antes = ultimo.get("tags", {}).get("antes")
    if not tag_antes:
        return "Tag de restauracao nao encontrada no historico."

    if not confirmar_risco([f"Desfazer auto-aprimoramento '{ultimo.get('descricao')}'?\n"
                            f"Isto fara git reset --hard {tag_antes} e reiniciara o servico."]):
        return "Cancelado pelo usuario."

    try:
        subprocess.run(["git", "-C", str(BASE_PROJETO), "reset", "--hard", tag_antes], check=True)
        # Roda vigia para reiniciar e checar
        script_vigia = BASE_PROJETO / "scripts" / "aplicar_e_vigiar.sh"
        if script_vigia.exists():
            subprocess.Popen([str(script_vigia), tag_antes], start_new_session=True)
        ultimo["status"] = "desfeito"
        salvar_json(ARQUIVO_HISTORICO, historico)
        return f"DESFEITO: rollback para {tag_antes} concluido. Vigia reiniciando servico."
    except Exception as e:
        return f"ERRO ao desfazer: {e}"
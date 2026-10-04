"""Resumo de contexto: mantem ultimas N mensagens integrais + resumo continuo do historico antigo.

Substitui o descarte simples por um resumo gerado pelo cerebro ativo.
Falha no resumo -> volta ao descarte antigo (podar original).
"""
import json
import threading
from pathlib import Path
from typing import Any

from comum import PASTA_DADOS, ler_json, salvar_json

ARQUIVO_RESUMO = PASTA_DADOS / "contexto_resumo.json"
LIMITE_MENSAGENS_INTEGRAS = 10  # ultimas N mensagens mantidas completas
LIMITE_TOTAL_MENSAGENS = 30  # trigger para resumir quando passar disso
ESTIMATIVA_TOKENS_POR_MENSAGEM = 200  # estimativa grosseira
LIMITE_TOKENS_ESTIMADO = 6000  # trigger por tokens estimados


_resumo_lock = threading.Lock()
_resumo_cache: str = ""


def _carregar_resumo() -> str:
    global _resumo_cache
    with _resumo_lock:
        if _resumo_cache:
            return _resumo_cache
        dados = ler_json(ARQUIVO_RESUMO, {"resumo": ""})
        _resumo_cache = dados.get("resumo", "")
        return _resumo_cache


def _salvar_resumo(resumo: str):
    global _resumo_cache
    with _resumo_lock:
        _resumo_cache = resumo
        salvar_json(ARQUIVO_RESUMO, {"resumo": resumo})


def _estimar_tokens(conversa: list[dict]) -> int:
    """Estima tokens totais da conversa (grosseiro)."""
    total_chars = sum(len(str(m.get("content", ""))) for m in conversa)
    return max(1, total_chars // 4)  # ~4 chars/token


def _precisa_resumir(conversa: list[dict]) -> bool:
    """Verifica se deve disparar resumo por mensagens ou tokens estimados."""
    msgs_sem_sistema = [m for m in conversa if m.get("role") != "system"]
    if len(msgs_sem_sistema) > LIMITE_TOTAL_MENSAGENS:
        return True
    tokens_est = _estimar_tokens(msgs_sem_sistema)
    return tokens_est > LIMITE_TOKENS_ESTIMADO


def _construir_prompt_resumo(conversa: list[dict], resumo_atual: str) -> str:
    """Constrói prompt para o modelo resumir o historico."""
    # Pega mensagens que NAO sao as ultimas LIMITE_MENSAGENS_INTEGRAS
    msgs_sem_sistema = [m for m in conversa if m.get("role") != "system"]
    if len(msgs_sem_sistema) <= LIMITE_MENSAGENS_INTEGRAS:
        return ""
    antigas = msgs_sem_sistema[:-LIMITE_MENSAGENS_INTEGRAS]

    partes = []
    for m in antigas:
        role = m.get("role", "")
        content = m.get("content", "") or ""
        if m.get("tool_calls"):
            tc_names = [tc["function"]["name"] for tc in m["tool_calls"]]
            content += f" [ferramentas: {', '.join(tc_names)}]"
        if role == "tool":
            role = "ferramenta"
        elif role == "assistant":
            role = "assistente"
        elif role == "user":
            role = "usuario"
        if content.strip():
            partes.append(f"{role}: {content.strip()}")

    historico_texto = "\n".join(partes)

    prompt = f"""Resuma o historico abaixo em portugues, MAXIMO 5 linhas.
Foque em: topicos principais, decisoes, fatos sobre o usuario, tarefas pendentes.
Ignore saudacoes, confirmacoes curtas e repeticoes.
Resumo anterior (se houver): {resumo_atual or 'nenhum'}

Historico:
{historico_texto}

Resumo conciso:"""
    return prompt


def resumir_contexto(conversa: list[dict], cerebro_chat_fn) -> list[dict]:
    """
    Se conversa passou do limite, resume as mensagens antigas e mantem so as ultimas N.
    Retorna nova conversa com: [system, resumo_como_mensagem, ultimas_N_mensagens].
    Falha -> retorna conversa podada pelo metodo antigo.
    """
    try:
        # Verifica se precisa resumir
        if not _precisa_resumir(conversa):
            return conversa

        # Carrega resumo atual
        resumo_atual = _carregar_resumo()

        # Pede resumo ao cerebro ativo
        prompt = _construir_prompt_resumo(conversa, resumo_atual)
        if not prompt:
            return conversa

        from cerebro import MensagemNeutra
        mensagens = [
            MensagemNeutra(role="system", content="Voce resume historicos de conversa. Seja conciso, max 5 linhas."),
            MensagemNeutra(role="user", content=prompt),
        ]
        resultado = cerebro_chat_fn(mensagens, None)
        if resultado.erro or not resultado.conteudo.strip():
            raise Exception(resultado.erro or "resumo vazio")

        novo_resumo = resultado.conteudo.strip()
        _salvar_resumo(novo_resumo)

        # Reconstroi conversa: system + resumo + ultimas N mensagens integrais
        system_msg = conversa[0] if conversa and conversa[0].get("role") == "system" else {"role": "system", "content": ""}
        msgs_sem_sistema = [m for m in conversa if m.get("role") != "system"]
        ultimas = msgs_sem_sistema[-LIMITE_MENSAGENS_INTEGRAS:]

        nova_conversa = [system_msg]
        if novo_resumo:
            nova_conversa.append({
                "role": "system",
                "content": f"Resumo do historico anterior:\n{novo_resumo}"
            })
        nova_conversa.extend(ultimas)
        return nova_conversa

    except Exception:
        # Falha silenciosa -> descarte antigo (podar)
        return podar_antigo(conversa)


def podar_antigo(conversa: list[dict]) -> list[dict]:
    """Metodo original de poda (descarte simples)."""
    if len(conversa) <= LIMITE_HISTORICO + 1:
        return conversa
    cabeca = [conversa[0]]
    corpo = [m for m in conversa[1:] if m.get("role") != "system"]
    return cabeca + corpo[-(LIMITE_HISTORICO - 1):]


def limpar_resumo():
    """Limpa o resumo salvo (nova sessao)."""
    _salvar_resumo("")


def obter_resumo_atual() -> str:
    return _carregar_resumo()
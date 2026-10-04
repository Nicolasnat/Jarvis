"""Memoria ativa: busca semantica de fatos sobre o usuario via embeddings locais.

Usa nomic-embed-text do Ollama. Cacheia vetores em dados/memoria_vetores.json
para so vetorizar a pergunta a cada consulta. Fallback para busca por palavras.
"""
import json
import os
from datetime import datetime
from pathlib import Path

import ollama

from comum import PASTA_DADOS, ler_json, salvar_json, chave_nome

ARQUIVO_MEMORIA = PASTA_DADOS / "memoria.json"
ARQUIVO_VETORES = PASTA_DADOS / "memoria_vetores.json"
MODELO_EMBED = "nomic-embed-text"
MAX_FATOS_CONTEXTO = 5
MAX_CARACTERES_BLOCO = 1200


def _get_vetores() -> dict:
    """Carrega cache de vetores (fato_id -> vetor)."""
    return ler_json(ARQUIVO_VETORES, {})


def _salvar_vetores(vetores: dict):
    """Salva cache de vetores."""
    salvar_json(ARQUIVO_VETORES, vetores)


def _embedding(texto: str) -> list[float] | None:
    """Gera embedding via Ollama. Retorna None se falhar."""
    try:
        r = ollama.embeddings(model=MODELO_EMBED, prompt=texto)
        return r["embedding"]
    except Exception:
        return None


def _similaridade_cosseno(a: list[float], b: list[float]) -> float:
    """Similaridade de cosseno entre dois vetores."""
    if not a or not b or len(a) != len(b):
        return 0.0
    dot = sum(x * y for x, y in zip(a, b))
    norm_a = sum(x * x for x in a) ** 0.5
    norm_b = sum(y * y for y in b) ** 0.5
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return dot / (norm_a * norm_b)


def _gerar_e_cachear_vetor(fato_id: str, texto: str) -> list[float] | None:
    """Gera embedding do fato e cacheia. Retorna vetor ou None se falhar."""
    vetores = _get_vetores()
    if fato_id in vetores:
        return vetores[fato_id]
    vetor = _embedding(texto)
    if vetor:
        vetores[fato_id] = vetor
        _salvar_vetores(vetores)
    return vetor


def _remover_vetor(fato_id: str):
    """Remove vetor do cache (quando fato e apagado)."""
    vetores = _get_vetores()
    if fato_id in vetores:
        del vetores[fato_id]
        _salvar_vetores(vetores)


def _buscar_por_palavras_chave(busca: str, fatos: list[dict], limite: int) -> list[dict]:
    """Fallback: busca simples por palavras-chave normalizadas."""
    termos = set(chave_nome(busca).split())
    if not termos:
        return fatos[:limite]
    pontuados = []
    for f in fatos:
        texto = (f.get("fato", "") or "").lower()
        score = sum(1 for t in termos if t in texto)
        if score > 0:
            pontuados.append((score, f))
    pontuados.sort(key=lambda x: x[0], reverse=True)
    return [f for _, f in pontuados[:limite]]


def _contem_credencial(texto: str) -> bool:
    """Verifica se o texto parece conter credencial (usa logica de seguranca)."""
    from seguranca import CREDENCIAIS_REGEX
    for _, solto in CREDENCIAIS_REGEX:
        if solto.search(texto):
            return True
    return False


def obter_fatos_relevantes(busca: str, modo_privado: bool = False, cerebro_nuvem: bool = False) -> list[dict]:
    """
    Retorna ate MAX_FATOS_CONTEXTO fatos mais relevantes para a busca.
    - modo_privado: so usa busca por palavras (nao manda nada pra nuvem)
    - cerebro_nuvem: se True, filtra fatos que parecem credenciais
    """
    fatos = ler_json(ARQUIVO_MEMORIA, [])
    if not fatos:
        return []

    # Se modo privado ou busca vazia, usa fallback simples (recentes ou palavras)
    if modo_privado or not busca.strip():
        return fatos[-MAX_FATOS_CONTEXTO:]

    # Tenta embedding semantico
    vetor_busca = _embedding(busca)
    if vetor_busca:
        vetores = _get_vetores()
        pontuados = []
        for f in fatos:
            fato_id = f.get("id") or f.get("quando") or ""
            if not fato_id:
                continue
            vetor_fato = vetores.get(fato_id)
            if not vetor_fato:
                # Gera e cacheia se nao tem
                vetor_fato = _gerar_e_cachear_vetor(fato_id, f.get("fato", ""))
            if vetor_fato:
                sim = _similaridade_cosseno(vetor_busca, vetor_fato)
                if sim > 0.1:  # threshold minimo
                    pontuados.append((sim, f))
        if pontuados:
            pontuados.sort(key=lambda x: x[0], reverse=True)
            relevantes = [f for _, f in pontuados[:MAX_FATOS_CONTEXTO]]
            # Filtrar credenciais se vai pra nuvem
            if cerebro_nuvem:
                relevantes = [f for f in relevantes if not _contem_credencial(f.get("fato", ""))]
            return relevantes

    # Fallback: busca por palavras-chave
    return _buscar_por_palavras_chave(busca, fatos, MAX_FATOS_CONTEXTO)


def formatar_bloco_memoria(fatos: list[dict]) -> str:
    """Formata lista de fatos para injetar no prompt. Limita tamanho total."""
    if not fatos:
        return ""
    linhas = [f"- {f.get('fato', '')}" for f in fatos if f.get("fato")]
    if not linhas:
        return ""
    bloco = "\n\nFatos relevantes sobre o usuario:\n" + "\n".join(linhas)
    if len(bloco) > MAX_CARACTERES_BLOCO:
        bloco = bloco[:MAX_CARACTERES_BLOCO] + "\n...[memoria truncada]"
    return bloco


def atualizar_vetor_fato(fato_id: str, texto: str):
    """Chamado ao salvar/editar um fato: gera e cacheia o vetor."""
    _gerar_e_cachear_vetor(fato_id, texto)


def remover_vetor_fato(fato_id: str):
    """Chamado ao apagar um fato: remove do cache."""
    _remover_vetor(fato_id)


def reindexar_todos_vetores() -> int:
    """Regenera todos os vetores (útil se modelo de embedding mudou). Retorna qtd processados."""
    fatos = ler_json(ARQUIVO_MEMORIA, [])
    vetores = {}
    for f in fatos:
        fato_id = f.get("id") or f.get("quando") or ""
        if fato_id and f.get("fato"):
            vetor = _embedding(f["fato"])
            if vetor:
                vetores[fato_id] = vetor
    _salvar_vetores(vetores)
    return len(vetores)
"""RAG local: indexa documentos e responde com base neles.

Usa ChromaDB como banco vetorial persistente (em dados/rag) e o modelo de
embeddings 'nomic-embed-text' do Ollama. Nada sai da maquina.
"""
import hashlib
from pathlib import Path

import ollama

from comum import BASE_PROJETO, PASTA_DADOS

PASTA_INDICE = PASTA_DADOS / "rag"
MODELO_EMBED = "nomic-embed-text"
MODELO_RESPOSTA = "llama3.1:8b"
NOME_COLECAO = "documentos"
EXTENSOES = {".txt", ".md", ".markdown", ".pdf", ".docx"}
TAMANHO_TRECHO = 1000
SOBREPOSICAO = 200
PASTAS_PROIBIDAS = {".ssh", ".aws", ".gnupg", ".kube", ".docker", ".config", ".gnome"}

_cliente = None


def _get_cliente():
    global _cliente
    if _cliente is None:
        import chromadb
        from chromadb.config import Settings
        PASTA_INDICE.mkdir(parents=True, exist_ok=True)
        _cliente = chromadb.PersistentClient(
            path=str(PASTA_INDICE),
            settings=Settings(anonymized_telemetry=False),
        )
    return _cliente


def _colecao():
    return _get_cliente().get_or_create_collection(NOME_COLECAO)


def _embed(textos):
    return [ollama.embeddings(model=MODELO_EMBED, prompt=texto)["embedding"] for texto in textos]


def _ler(caminho: Path) -> str:
    extensao = caminho.suffix.lower()
    if extensao == ".pdf":
        from pypdf import PdfReader
        leitor = PdfReader(str(caminho))
        return "\n".join((pagina.extract_text() or "") for pagina in leitor.pages)
    if extensao == ".docx":
        import docx
        return "\n".join(paragrafo.text for paragrafo in docx.Document(str(caminho)).paragraphs)
    return caminho.read_text(encoding="utf-8", errors="ignore")


def _dividir(texto: str):
    texto = " ".join(texto.split())
    if not texto:
        return []
    passo = TAMANHO_TRECHO - SOBREPOSICAO
    return [texto[i:i + TAMANHO_TRECHO] for i in range(0, len(texto), passo)]


def _caminho_seguro(caminho: str):
    alvo = Path(caminho).expanduser()
    if not alvo.is_absolute():
        alvo = BASE_PROJETO / alvo
    alvo = alvo.resolve()
    home = Path.home().resolve()
    if alvo != home and home not in alvo.parents:
        return None, "So posso indexar arquivos dentro da sua pasta pessoal."
    if any(parte in PASTAS_PROIBIDAS for parte in alvo.parts):
        return None, "Pasta de credenciais ou configuracao bloqueada para indexacao."
    if alvo.name.startswith(".env"):
        return None, "Arquivos .env sao bloqueados."
    return alvo, None


def indexar(caminho: str) -> str:
    alvo, erro = _caminho_seguro(caminho)
    if erro:
        return erro
    if not alvo.exists():
        return f"Nao encontrei '{alvo}'."

    if alvo.is_file():
        arquivos = [alvo]
    else:
        arquivos = [
            item for item in alvo.rglob("*")
            if item.is_file() and item.suffix.lower() in EXTENSOES and not item.name.startswith(".")
        ]
    if not arquivos:
        return f"Nenhum documento suportado (txt, md, pdf, docx) em {alvo}."

    colecao = _colecao()
    total = 0
    usados = 0
    for arquivo in arquivos:
        try:
            trechos = _dividir(_ler(arquivo))
        except Exception as erro_leitura:
            print(f"[rag] ignorando {arquivo}: {erro_leitura}")
            continue
        if not trechos:
            continue
        ids = [hashlib.md5(f"{arquivo}:{i}".encode()).hexdigest() for i in range(len(trechos))]
        colecao.upsert(
            ids=ids,
            documents=trechos,
            embeddings=_embed(trechos),
            metadatas=[{"arquivo": str(arquivo)} for _ in trechos],
        )
        total += len(trechos)
        usados += 1

    return f"Indexados {total} trechos de {usados} arquivo(s) em {alvo}."


def perguntar(pergunta: str) -> str:
    pergunta = (pergunta or "").strip()
    if not pergunta:
        return "Faca uma pergunta sobre os documentos indexados."

    colecao = _colecao()
    if colecao.count() == 0:
        return "Nenhum documento indexado. Use 'indexar_documentos' primeiro."

    vetor = _embed([pergunta])[0]
    resultado = colecao.query(query_embeddings=[vetor], n_results=4)
    documentos = resultado.get("documents", [[]])[0]
    if not documentos:
        return "Nao encontrei nada relevante nos documentos indexados."

    metadados = resultado.get("metadatas", [[]])[0]
    fontes = sorted({item.get("arquivo", "") for item in metadados if item})
    contexto = "\n\n---\n\n".join(documentos)

    resposta = ollama.chat(model=MODELO_RESPOSTA, messages=[
        {"role": "system", "content": (
            "Responda em portugues do Brasil usando SOMENTE o contexto fornecido. "
            "Se a resposta nao estiver no contexto, diga que nao encontrou nos documentos."
        )},
        {"role": "user", "content": f"Contexto:\n{contexto}\n\nPergunta: {pergunta}"},
    ])
    texto = resposta["message"]["content"].strip()
    return f"{texto}\n\nFontes: {', '.join(fontes)}"

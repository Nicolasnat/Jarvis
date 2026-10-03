"""Plugin: toca musica no Spotify a partir do que o usuario fala.

O backend e o Spotify Web API (ver _spotify.py): a busca acha a faixa exata e
o player do proprio Spotify e quem toca, com audio no Spotify Connect.

Requer uma vez so: spotify acao=conectar (abre o navegador para autorizar).
Nota do Spotify: tocar pelo Web API exige conta Premium.

O campo 'dispositivo' NAO aparece no schema de proposito. O modelo passou a
inventar valores para ele ('Web Player', 'realme') e o playback ia parar no
aparelho errado. O destino e escolhido pelo proprio plugin, preferindo o PC.
"""
from concurrent.futures import ThreadPoolExecutor

from . import _spotify
from ._spotify import ErroSpotify
from comum import chave_nome, esquema

NOME = "spotify"
DESCRICAO = (
    "Controla o Spotify pelo nome da musica ou playlist. Use para "
    "'tocar <musica>', 'tocar a playlist <nome>', 'pausar', 'proxima musica', "
    "'o que esta tocando', 'volume do spotify 40'. Nao informe o aparelho: "
    "o som sai no computador."
)
PARAMETROS = esquema(
    {
        "acao": {
            "type": "string",
            "description": (
                "O que fazer: tocar, pausar, retomar, proxima, anterior, tocando, "
                "volume ou conectar."
            ),
            "enum": ["tocar", "pausar", "retomar", "proxima", "anterior", "tocando", "volume", "conectar"],
        },
        "musica": {
            "type": "string",
            "description": (
                "Nome da musica, do artista ou da playlist. Se o usuario citar "
                "playlist, album ou 'minha playlist X', escreva o nome aqui."
            ),
        },
        "valor": {"type": "integer", "description": "Volume de 0 a 100. Usado so na acao 'volume'."},
    },
    ["acao"],
)
SEGURANCA = "detectar"

# Palavras que indicam que o usuario quer uma colecao, nao uma faixa solta.
COLECAO = ("playlist", "playlists", "minha playlist", "album", "álbum")


def _quer_colecao(pedido: str) -> bool:
    return any(marcador in (pedido or "").lower() for marcador in COLECAO)


def _outros(itens, campos=("nome", "artista")):
    """Lista as alternativas sem repetir a mesma faixa duas vezes."""
    vistas, texto = set(), []
    for item in itens:
        chave = tuple(str(item.get(c) or "").strip().lower() for c in campos)
        if chave in vistas:
            continue
        vistas.add(chave)
        nome = item.get("nome") or "?"
        artista = item.get("artista")
        texto.append(f"{nome} - {artista}" if artista else nome)
    return " | ".join(texto[:3])


def _outros_playlists(itens):
    """Playlists alternativas: 'Seila (fulano)' para nao parecer repetida."""
    vistas, texto = set(), []
    for item in itens:
        nome = item.get("nome") or "?"
        dono = (item.get("dono") or "").strip()
        chave = (chave_nome(nome), chave_nome(dono))
        if chave in vistas:
            continue
        vistas.add(chave)
        texto.append(f"{nome} ({dono})" if dono else nome)
    return " | ".join(texto[:3])


def _tocar_playlist(pedido: str):
    resultados = _spotify.buscar_playlists(pedido)
    if not resultados:
        return f"Nao achei a playlist '{pedido}' na sua conta nem no Spotify."

    escolhida = resultados[0]
    _spotify.tocar_contexto(escolhida["uri"], lista=_spotify.garantir_desktop())

    extras = ""
    if len(resultados) > 1:
        outros = _outros_playlists(resultados[1:])
        if outros:
            extras = f" Outras opcoes: {outros}."
    return (
        f"Tocando a playlist {escolhida['nome']} "
        f"({escolhida['total']} musica{'s' if escolhida['total'] != 1 else ''}).{extras}"
    )


def funcao(acao: str, musica: str = "", valor: int = None):
    try:
        acao = (acao or "").strip().lower()

        if acao == "conectar":
            _spotify.conectar()
            return "Conectado ao Spotify. Agora posso tocar musica."

        if acao == "tocar":
            pedido = (musica or "").strip()
            if not pedido:
                return "Diga o nome da musica: 'tocar <musica>'."

            if _spotify.sem_token():
                return (
                    "O Spotify ainda nao foi conectado. Rode spotify acao=conectar "
                    "uma vez para autorizar o Jarvis."
                )

            if _quer_colecao(pedido):
                return _tocar_playlist(pedido)

            # Abrir o app e buscar a musica nao dependem uma da outra, entao
            # uma coisa roda enquanto a outra acontece.
            with ThreadPoolExecutor(max_workers=1) as fila:
                futuro_app = fila.submit(_spotify.garantir_desktop)
                resultados = _spotify.buscar(pedido)
                bons = _spotify.relevantes(pedido, resultados)
                lista = futuro_app.result()

                if not bons:
                    # Ou o pedido era o nome de uma playlist, ou nao existe
                    # essa musica. Na duvida perguntamos em vez de tocar lixo.
                    colecoes = _spotify.buscar_playlists(pedido)
                    if colecoes:
                        return _tocar_playlist(pedido)
                    if resultados:
                        perto = resultados[0]
                        return (
                            f"Nao achei '{pedido}' no Spotify. O mais parecido foi "
                            f"'{perto['nome']}' - {perto['artista']}. Quer que eu toque?"
                        )
                    return f"Nao achei '{pedido}' no Spotify."

                escolhida = bons[0]
                _spotify.tocar(escolhida["uri"], lista=lista)

            outros = _outros(bons[1:])
            return f"Tocando {escolhida['nome']} - {escolhida['artista']}." + (
                f" Outras opcoes: {outros}." if outros else ""
            )

        if acao == "tocando":
            atual = _spotify.tocando()
            if not atual:
                return "Nada tocando no Spotify."
            estado = "tocando" if atual["tocando"] else "pausado"
            return f"{atual['nome']} - {atual['artista']} ({estado})."

        if acao == "volume":
            if valor is None:
                atual = _spotify.comando("volume")
                return f"Volume do Spotify em {atual.get('volume_percent')} por cento."
            _spotify.comando("volume", max(0, min(100, int(valor))))
            return f"Volume do Spotify em {valor} por cento."

        if acao in {"pausar", "retomar", "proxima", "anterior"}:
            _spotify.comando(acao)
            rotulos = {
                "pausar": "Pausado.",
                "retomar": "Voltando a tocar.",
                "proxima": "Proxima musica.",
                "anterior": "Musica anterior.",
            }
            return rotulos[acao]

        return (
            "Acao de Spotify invalida. Use: tocar, pausar, retomar, proxima, "
            "anterior, tocando, volume ou conectar."
        )

    except ErroSpotify as erro:
        return erro.mensagem
    except Exception as erro:  # noqa: BLE001 - erro de rede/libero vira texto
        return f"Falha no Spotify: {erro}"
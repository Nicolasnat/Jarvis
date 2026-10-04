"""Cliente da API do Spotify (Web API) para o plugin de musica.

Usa Authorization Code com PKCE, que dispensa 'client secret' e funciona com
app de escritorio. O token fica em dados/spotify_token.json e e renovado
sozinhos ate dar erro de refreshing, momento em que o usuario precisa
reconectar.

so a stdlib, para nao adicionar dependencia ao projeto.
"""
import base64
import difflib
import hashlib
import json
import os
import secrets
import shutil
import subprocess
import time
import urllib.error
import urllib.parse
import urllib.request
import webbrowser
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

from comum import ARQUIVO_APPS, PASTA_CONFIG, chave_nome, ler_json, salvar_json

ARQUIVO_CLIENTE = PASTA_CONFIG / "spotify.json"
ARQUIVO_TOKEN = PASTA_CONFIG.parent / "dados" / "spotify_token.json"

AUTORIZAR = "https://accounts.spotify.com/authorize"
TOKEN = "https://accounts.spotify.com/api/token"
API = "https://api.spotify.com/v1"

REDIRECIONAMENTO = "http://127.0.0.1:8898/callback"
PORTA = 8898

ESCOPOS = " ".join([
    "user-read-playback-state",
    "user-modify-playback-state",
    "user-read-currently-playing",
    "playlist-read-private",
    "playlist-modify-private",
])


class ErroSpotify(Exception):
    """Erro com mensagem ja pronta para o usuario ler."""

    def __init__(self, mensagem, reconectar=False, codigo=None):
        super().__init__(mensagem)
        self.mensagem = mensagem
        self.reconectar = reconectar
        self.codigo = codigo


def _pedido(metodo, url, token=None, dados=None, corpo=None):
    headers = {"Accept": "application/json"}
    if corpo is not None:
        headers["Content-Type"] = "application/json"
        dados = json.dumps(corpo).encode()
    if token:
        headers["Authorization"] = f"Bearer {token}"

    requisicao = urllib.request.Request(url, data=dados, headers=headers, method=metodo)
    try:
        with urllib.request.urlopen(requisicao, timeout=20) as resposta:
            bruto = resposta.read().decode("utf-8")
            return json.loads(bruto) if bruto.strip() else {}
    except urllib.error.HTTPError as erro:
        detalhe = ""
        try:
            erro_json = json.loads(erro.read().decode("utf-8"))
            erro_desc = erro_json.get("error") or {}
            detalhe = erro_desc.get("message") or erro_json.get("error_description") or ""
        except Exception:
            pass
        if erro.code == 401:
            raise ErroSpotify("A autorizacao do Spotify expirou.", reconectar=True, codigo=401) from erro
        if erro.code == 403:
            raise ErroSpotify(
                "O Spotify recusou a acao (403). Tocar pelo Web API e usar o "
                "dispositivo ativo exige Spotify Premium.", codigo=403,
            ) from erro
        if erro.code == 404 and "active device" in detalhe.lower():
            raise ErroSpotify(
                "Nenhum aparelho do Spotify estava ativo. Abra o Spotify no "
                "computador e tente de novo.", codigo=404,
            ) from erro
        raise ErroSpotify(f"Spotify respondeu {erro.code}: {detalhe or erro.reason}", codigo=erro.code) from erro
    except urllib.error.URLError as erro:
        raise ErroSpotify(f"Nao consegui falar com o Spotify: {erro.reason}") from erro


def client_id() -> str:
    dados = ler_json(ARQUIVO_CLIENTE, {})
    return str((dados or {}).get("client_id") or "").strip()


def sem_token():
    return not ler_json(ARQUIVO_TOKEN, {}).get("refresh_token")


def _token_formulario(campos):
    dados = urllib.parse.urlencode(campos).encode()
    requisicao = urllib.request.Request(
        TOKEN, data=dados,
        headers={"Content-Type": "application/x-www-form-urlencoded"}, method="POST",
    )
    try:
        with urllib.request.urlopen(requisicao, timeout=20) as resposta:
            return json.loads(resposta.read().decode("utf-8"))
    except urllib.error.HTTPError as erro:
        raise ErroSpotify(
            "O Spotify recusou a autenticacao. confira o client_id em "
            f"{ARQUIVO_CLIENTE} e o redirect URI '{REDIRECIONAMENTO}' no painel do Spotify.",
            reconectar=True,
        ) from erro
    except urllib.error.URLError as erro:
        raise ErroSpotify(f"Nao consegui falar com o Spotify: {erro.reason}") from erro


def _desafio():
    verificador = base64.urlsafe_b64encode(secrets.token_bytes(64)).decode().rstrip("=")
    desafio = base64.urlsafe_b64encode(
        hashlib.sha256(verificador.encode()).digest()
    ).decode().rstrip("=")
    return verificador, desafio


class _Coletor(BaseHTTPRequestHandler):
    codigo = None

    def do_GET(self):
        consulta = urllib.parse.urlparse(self.path).query
        parametros = urllib.parse.parse_qs(consulta)
        _Coletor.codigo = (parametros.get("code") or [None])[0]
        erro = (parametros.get("error") or [None])[0]

        if erro:
            corpo = "<h1>Falha na autorizacao do Spotify.</h1><p>Feche esta aba.</p>"
            status = 400
        else:
            corpo = "<h1>Nexus conectado ao Spotify!</h1><p>Pode fechar esta aba.</p>"
            status = 200

        self.send_response(status)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.end_headers()
        self.wfile.write(corpo.encode("utf-8"))

    def log_message(self, *_):
        return


def conectar():
    """Abre o navegador para o usuario autorizar o Nexus. Bloqueia ate o callback."""
    identificador = client_id()
    if not identificador:
        raise ErroSpotify(
            f"Falta o client_id. Crie um arquivo {ARQUIVO_CLIENTE} com "
            '{"client_id": "SEU_CLIENT_ID"}.'
        )

    verificador, desafio = _desafio()
    url = AUTORIZAR + "?" + urllib.parse.urlencode({
        "client_id": identificador,
        "response_type": "code",
        "redirect_uri": REDIRECIONAMENTO,
        "scope": ESCOPOS,
        "code_challenge_method": "S256",
        "code_challenge": desafio,
    })

    webbrowser.open(url)
    print(f"[spotify] Autorize aqui (ou no navegador): {url}")

    servidor = HTTPServer(("127.0.0.1", PORTA), _Coletor)
    servidor.timeout = 180
    try:
        servidor.handle_request()
    finally:
        servidor.server_close()

    if not _Coletor.codigo:
        raise ErroSpotify("A autorizacao do Spotify nao foi concluida.")

    tokens = _token_formulario({
        "client_id": identificador,
        "grant_type": "authorization_code",
        "code": _Coletor.codigo,
        "redirect_uri": REDIRECIONAMENTO,
        "code_verifier": verificador,
    })
    salvar_json(ARQUIVO_TOKEN, tokens)
    return tokens


def token():
    """Devolve um access token valido, renovando pelo refresh_token se precisar."""
    salvos = ler_json(ARQUIVO_TOKEN, {})
    if not salvos:
        raise ErroSpotify(
            "O Spotify ainda nao foi conectado. Rode spotify acao=conectar uma vez "
            "para autorizar o Nexus.",
            reconectar=True,
        )

    if not salvos.get("refresh_token"):
        raise ErroSpotify(
            "A autorizacao do Spotify expirou. Rode spotify acao=conectar de novo.",
            reconectar=True,
        )

    return _token_formulario({
        "client_id": client_id(),
        "grant_type": "refresh_token",
        "refresh_token": salvos["refresh_token"],
    })["access_token"]


def buscar(termo: str, limite=5):
    """Busca faixas e devolve [{uri, nome, artista, album}]."""
    url = API + "/search?" + urllib.parse.urlencode({
        "q": termo, "type": "track", "limit": max(1, min(limite, 20)),
    })
    dados = _pedido("GET", url, token=token())
    resultados = []
    for item in dados.get("tracks", {}).get("items", []):
        resultados.append({
            "uri": item.get("uri"),
            "nome": item.get("name"),
            "artista": ", ".join(a["name"] for a in item.get("artists", []) if a.get("name")),
            "album": (item.get("album") or {}).get("name"),
        })
    return resultados


_CACHE_PLAYLISTS = {"ate": 0.0, "itens": []}
CACHE_PLAYLISTS_SEGUNDOS = 300


def minhas_playlists():
    """Playlists da conta, com cache de 5 minutos.

    A lista muda quase nunca e buscar todo pedido custava ~1s de rede.
    """
    agora = time.time()
    if agora - _CACHE_PLAYLISTS["ate"] < CACHE_PLAYLISTS_SEGUNDOS:
        return _CACHE_PLAYLISTS["itens"]

    itens = _pedido("GET", API + "/me/playlists", token=token()).get("items", [])
    _CACHE_PLAYLISTS["ate"] = agora
    _CACHE_PLAYLISTS["itens"] = itens
    return itens


def _resumo_playlist(item):
    # A API trocou 'tracks' por 'items' na versao nova; aceitamos os dois.
    # A busca publica as vezes devolve entradas nulas, entamo de pe.
    item = item or {}
    contagem = item.get("items") or item.get("tracks") or {}
    return {
        "uri": item.get("uri"),
        "id": (item.get("id") or ""),
        "nome": item.get("name") or "",
        "dono": (item.get("owner") or {}).get("display_name") or "",
        "total": contagem.get("total", 0),
    }


PARADAS_PLAYLIST = {
    "playlist", "playlists", "minha", "minhas", "meu", "meus", "a", "o", "as", "os",
    "um", "uma", "uns", "umas", "de", "do", "da", "dos", "das", "no", "na", "nos",
    "nas", "e", "pra", "pro", "que", "me",
}

# Conectivos que aparecem na fala mas nunca no titulo da faixa.
PARADAS_FALA = PARADAS_PLAYLIST | {
    "toca", "tocar", "tou", "vai", "va", "queria", "quer", "coloca", "bota",
    "manda", "telegrama", "som", "musica", "musicas", "faixa", "algo", "coisa",
    "alguma", "algum", "the", "y", "pra", "por", "com",
}

# Verbos de comando que o modelo costuma incluir junto do nome da playlist.
# Ao contrario de PARADAS_FALA, aqui mantemos 'musica': uma playlist pode ate
# se chamar 'Musicas'. Sem tirar o verbo, 'toque estou a fim' nao casaria com
# 'To afim'.
PARADAS_COLECAO = PARADAS_PLAYLIST | {
    "toca", "tocar", "toque", "toquem", "tocando", "coloca", "coloque", "bota",
    "bote", "manda", "poe", "poem", "abre", "abra", "abrir", "play", "start",
    "spotify", "quero", "queria", "favor", "ai", "aqui",
}


def _tokens(texto):
    return [t for t in chave_nome(texto or "").split() if t not in PARADAS_PLAYLIST]


def _fonemas_playlist(texto):
    """Palavras uteis do pedido de playlist, sem verbos nem conectivos."""
    return [t for t in chave_nome(texto or "").split() if t not in PARADAS_COLECAO]


def _tokens_fala(texto):
    """Palavras do pedido, sem conectivos: 'toca a do enigma' -> ['enigma']."""
    return [t for t in chave_nome(texto or "").split() if t not in PARADAS_FALA]


def relevantes(termo: str, resultados):
    """Filtra e ORDENA o que a busca devolveu, tirando as coincidencias furadas.

    A busca do Spotify e por relevancia e sempre devolve alguma coisa: pedir
    'tragedia do enigma' traz 'Abencado - Filipe Ret'. Tocar isso e pior do que
    avisar que nao achou. So passa o que compartilha palavra com o pedido.

    A ordem da API muda entre chamadas, entao nao confiamos nela: o que decide
    e quanto do pedido aparece no TITULO. Empate vai para o titulo mais curto
    ('Robin Hood' ganha de 'Overture - From Robin Hood: Prince of Thieves').
    """
    termos = _tokens_fala(termo)
    if not termos:
        return resultados

    pontuadas = []
    for item in resultados:
        nome = set(chave_nome(item.get("nome") or "").split())
        artista = set(chave_nome(item.get("artista") or "").split())

        if not any(t in nome or t in artista for t in termos):
            continue

        no_titulo = len([t for t in termos if t in nome])
        na_artista = len([t for t in termos if t in artista])
        pontuadas.append((-(no_titulo / len(termos)), len(nome), -na_artista, item))

    pontuadas.sort(key=lambda linha: linha[:3])
    return [linha[3] for linha in pontuadas]


LIMIAR_PLAYLIST = 0.6


def _similaridade(consulta: str, nome: str) -> float:
    """Quao perto o pedido falado esta do nome da playlist (0 a 1).

    Comparamos o texto sem espacos, entao 'estou a fim' casa com 'To afim' e
    'mpb' casa com 'MPB' mesmo com o reconhecimento fragmentando as palavras.
    """
    alvo = chave_nome(nome or "").replace(" ", "")
    if not consulta:
        return 0.0
    if not alvo:
        return 0.0
    if consulta in alvo or alvo in consulta:
        return 1.0
    return difflib.SequenceMatcher(None, consulta, alvo).ratio()


def _consulta_playlist(termo: str) -> str:
    return "".join(_fonemas_playlist(termo))


def _casar_playlist(termo: str, nome: str) -> bool:
    return _similaridade(_consulta_playlist(termo), nome) >= LIMIAR_PLAYLIST


def buscar_playlists(termo: str, limite=10):
    """Procura playlists pelo nome, com as do usuario em primeiro lugar.

    'minha playlist do afim', 'a playlist do afim' e 'afim' precisam achar a
    mesma coisa, entao as playlists salvas na conta vem antes das publicas. A
    ordem final e por semelhanca com o que foi falado: pedir 'estou afim' leva
    a 'To afim'.
    """
    termo = termo or ""
    encontradas, vistas = [], set()

    def add(item, prioritise):
        if not item:
            return
        resumo = _resumo_playlist(item)
        if not resumo["id"] or resumo["id"] in vistas:
            return
        if not resumo["uri"]:
            return
        resumo["_pontos"] = _similaridade(_consulta_playlist(termo), resumo["nome"])
        if resumo["_pontos"] < LIMIAR_PLAYLIST:
            return
        vistas.add(resumo["id"])
        resumo["_preferida"] = prioritise
        encontradas.append(resumo)

    for item in minhas_playlists():
        add(item, True)

    url = API + "/search?" + urllib.parse.urlencode({
        "q": " ".join(_fonemas_playlist(termo)), "type": "playlist",
        "limit": max(1, min(limite, 20)),
    })
    try:
        publicas = _pedido("GET", url, token=token()).get("playlists", {}).get("items", [])
    except ErroSpotify:
        publicas = []

    for item in publicas:
        add(item, False)

    # Da conta primeiro; dentro de cada grupo, o nome mais parecido com o pedido.
    encontradas.sort(key=lambda r: (not r["_preferida"], -r["_pontos"], len(r["nome"])))
    for resumo in encontradas:
        resumo.pop("_preferida", None)
        resumo.pop("_pontos", None)
    return encontradas


def playlists_para_prompt(limite=40) -> str:
    """Lista as playlists do usuario para o modelo escolher o nome certo."""
    try:
        itens = minhas_playlists()
    except Exception:  # noqa: BLE001 - sem internet/token o prompt segue sem a lista
        return ""
    nomes = [(_resumo_playlist(i)["nome"] or "").strip() for i in itens if i]
    nomes = [nome for nome in nomes if nome]
    if not nomes:
        return ""
    return (
        "\n\nPlaylists do usuario no Spotify (para 'tocar a playlist', use o nome "
        "exato como aparece aqui):\n" + ", ".join(nomes[:limite])
    )


def dispositivos():
    dados = _pedido("GET", API + "/me/player/devices", token=token())
    return dados.get("devices", [])


def comando_desktop():
    """Como abrir o Spotify do PC, com o truque que ele exige nesta maquina."""
    apps = ler_json(ARQUIVO_APPS, {})
    comando = apps.get("spotify") or apps.get("spotify.desktop")
    if not comando:
        achado = shutil.which("spotify")
        comando = [achado] if achado else ["/snap/bin/spotify"]
    comando = [str(item) for item in comando]

    # O snap do Spotify morre na inicializacao da GPU (sai com codigo 1 e sem
    # mensagem nenhuma) em maquinas com drivers mais novos. Desligar a GPU faz
    # ele subir normalmente.
    if any("snap" in item for item in comando):
        comando = comando + ["--disable-gpu"]
    return comando


def garantir_desktop(espera=30):
    """Abre o Spotify do PC se ele nao estiver na lista de dispositivos.

    Devolve a lista de dispositivos ja com o app do PC presente, ou a lista
    original se nao houver como subir (ex.: Spotify nao instalado).
    """
    lista = dispositivos()
    if any(a.get("type") == "Computer" for a in lista):
        return lista

    comando = comando_desktop()
    if not (os.path.isabs(comando[0]) or shutil.which(comando[0])):
        return lista

    subprocess.Popen(
        comando,
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        stdin=subprocess.DEVNULL, start_new_session=True,
    )

    limite = time.time() + espera
    while time.time() < limite:
        time.sleep(3)
        lista = dispositivos()
        if any(a.get("type") == "Computer" for a in lista):
            return lista
    return lista


def _escolher_dispositivo(lista, pedido=None):
    """Descobre em qual aparelho tocar.

    A API so aceita 'device_id' quando o aparelho esta aberto no momento. Como
    o Nexus roda no computador, ele prefere o PC: depois o que estiver ativo e,
    por ultimo, o primeiro da lista.
    """
    if pedido:
        for aparelho in lista:
            if pedido.lower() in (aparelho.get("name") or "").lower():
                return aparelho
        raise ErroSpotify(
            f"Nao achei o dispositivo '{pedido}'. Disponiveis: "
            + ", ".join(a.get("name", "?") for a in lista)
        )

    computador = [a for a in lista if a.get("type") == "Computer"]
    if computador:
        ativos = [a for a in computador if a.get("is_active")]
        return (ativos or computador)[0]

    ativos = [a for a in lista if a.get("is_active")]
    if ativos:
        return ativos[0]

    computador = [a for a in lista if a.get("type") == "Computer"]
    if computador:
        return computador[0]

    if lista:
        return lista[0]

    raise ErroSpotify(
        "Nenhum dispositivo Spotify disponivel. Abra o Spotify no celular ou no "
        "navegador e tente de novo."
    )


def _ativar(dispositivo_id):
    """Transfere o player para o aparelho, acordando-o.

    A API recusa 'play' com 404 'No active device' quando o aparelho esta na
    lista mas ocioso (Spotify aberto sem tocar). Transferir para ele primeiro
    o torna ativo.
    """
    _pedido("PUT", API + "/me/player", token=token(), corpo={"device_ids": [dispositivo_id]})


def _executar_play(corpo):
    """Manda tocar; se o aparelho nao estiver ativo, ativa e tenta uma vez."""
    try:
        _pedido("PUT", API + "/me/player/play", token=token(), corpo=corpo)
    except ErroSpotify as erro:
        if erro.codigo != 404:
            raise
        _ativar(corpo["device_id"])
        _pedido("PUT", API + "/me/player/play", token=token(), corpo=corpo)


def tocar(uri: str, dispositivo=None, lista=None):
    aparelho = _escolher_dispositivo(lista if lista is not None else dispositivos(), dispositivo)
    _executar_play({"uris": [uri], "device_id": aparelho["id"]})


def tocar_contexto(context_uri: str, dispositivo=None, lista=None, offset=None):
    """Toca uma playlist/album inteiro (context_uri), em vez de uma faixa solta."""
    aparelho = _escolher_dispositivo(lista if lista is not None else dispositivos(), dispositivo)
    corpo = {"context_uri": context_uri, "device_id": aparelho["id"]}
    if offset is not None:
        corpo["offset"] = {"position": int(offset)}
    _executar_play(corpo)


def comando(acao: str, valor=None):
    """Acoes do player. 'volume' sem valor consulta; com valor, define."""
    if acao == "volume":
        if valor is None:
            return _pedido("GET", API + "/me/player/volume", token=token())
        return _pedido("PUT", API + "/me/player/volume", token=token(),
                       corpo={"volume_percent": max(0, min(100, int(valor)))})

    rotas = {"proxima": "next", "anterior": "previous", "pausar": "pause", "retomar": "play"}
    if acao not in rotas:
        raise ErroSpotify(f"Acao de player desconhecida: {acao}")

    metodo = "POST" if acao in {"proxima", "anterior"} else "PUT"
    url = API + "/me/player/" + rotas[acao]
    try:
        return _pedido(metodo, url, token=token())
    except ErroSpotify as erro:
        if erro.codigo != 404:
            raise
        # 'retomar' sem aparelho ativo cai no mesmo 404 do play.
        aparelho = _escolher_dispositivo(dispositivos())
        _ativar(aparelho["id"])
        return _pedido(metodo, url, token=token())


def tocando():
    dados = _pedido("GET", API + "/me/player/currently-playing", token=token())
    item = dados.get("item")
    if not item:
        return None
    return {
        "nome": item.get("name"),
        "artista": ", ".join(a["name"] for a in item.get("artists", []) if a.get("name")),
        "tocando": (dados.get("is_playing") or False),
    }
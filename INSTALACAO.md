# Instalacao

## Python (obrigatorio)

```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

## Programas do sistema (apt)

Estes pacotes **nao** sao instalados automaticamente. Instale os que quiser usar,
quando quiser (rode o comando voce mesmo):

| Pacote | Para que serve | Etapa |
|---|---|---|
| `xdg-utils` | abrir pastas no gerenciador de arquivos (`xdg-open`) | 1 |
| `libnotify-bin` | notificacoes de lembretes (`notify-send`) | 2 |
| `pulseaudio-utils` | controlar volume (`pactl`) | 3 |
| `brightnessctl` | controlar brilho da tela | 3 |
| `xclip` ou `wl-clipboard` | area de transferencia | 3 |
| `alsa-utils` | captura de audio da voz (`arecord`) | 4 |
| `espeak-ng` | voz sintetizada de reserva (fallback do Piper) | 4 |

Comando unico (opcional):

```bash
sudo apt install xdg-utils libnotify-bin pulseaudio-utils brightnessctl xclip alsa-utils espeak-ng
```

## Voz neural (Piper)

A voz natural em portugues do Brasil usa o Piper (`piper-tts`, instalado pelo
`requirements.txt`). Baixe o modelo de voz uma unica vez:

```bash
./venv/bin/python -m piper.download_voices pt_BR-faber-medium --download-dir dados/voz
```

Sem esse modelo, o Nexus cai automaticamente para espeak-ng/spd-say (mais robotico).

## Microfone (importante)

### A wakeword e "Nexus", "Hey Nexus" ou "Nexus iniciar"

O reconhecimento e por palavras-chave, feito pelo Vosk (`vosk`, no
`requirements.txt`) — nao ha mais um modelo acustico de frase fixa. As frases
aceitas ficam em `config/voz.json` (`wake_frases`); por padrao: `nexus`, `nexo`,
`nexus iniciar`, `oi nexus` e `hey nexus`. Basta dizer "Nexus" para acordar.

O modelo do Vosk nao vem no repositorio; baixe uma unica vez:

```bash
mkdir -p dados/vosk && cd dados/vosk
curl -LO https://alphacephei.com/vosk/models/vosk-model-small-pt-0.3.zip
unzip vosk-model-small-pt-0.3.zip && rm vosk-model-small-pt-0.3.zip
```

Sem esse modelo, o modo voz fica indisponivel (o erro aponta o caminho esperado).

### Ganho

O reconhecimento (Vosk no wakeword e Whisper na transcricao) so funciona bem se o audio chegar em um nivel
sane. Em notebooks com DMIC (controlado pelo `sof-hda-dsp`) o ganho vem de
fabrica no maximo e o sinal **estoura**; com audio estourado nem a wakeword
nem o Whisper funcionam. O servico ja corrige isso sozinho ao iniciar
(`ExecStartPre`), mas voce pode conferir ou ajustar na mao:

```bash
./ajustar_microfone.sh              # ajusta Dmic0 e Capture
./ajustar_microfone.sh 35 42         # ou informe os niveis (0-63 / 0-70)
```

### Calibrando o limiar

`config/voz.json` guarda os ajustes do microfone, sem precisar editar codigo:

```json
{
  "wake_frases": ["nexus", "nexo", "nexus iniciar", "oi nexus", "hey nexus"],
  "wake_confirmacao": 2,
  "wake_debug": false,
  "barge_limiar": 0.010,
  "barge_limiar_falando": 0.035,
  "barge_duracao": 0.45
}
```

Com `"wake_debug": true` o servico volta a logar a cada 10s o nivel do som e o
que o Vosk ouviu (`ouvido: ...`). Acrescente ou tire frases de `wake_frases`
conforme quiser; `wake_confirmacao` e quantos blocos de 100 ms a palavra deve
persistir para valer (evita acordar com um ruido isolado). Deixe `wake_debug` em
`false` depois: enche o journal.

### Interrompendo o que o Nexus esta fazendo

Enquanto o Nexus responde, toca uma musica, ou tem um agente de codigo
trabalhando, o microfone fica aberto e qualquer frase sua cancela a acao: basta
um "para" com meio segundo de fala. Durante a
propria fala do Nexus o limiar e mais alto (`barge_limiar_falando`), senao a
caixa de som devolve a voz dele no microfone e ele se cala sozinho.

Para testar a deteccao sem o servico no meio:

```bash
./venv/bin/python nexus.py --voz
```

Se ele responder "Nao entendi" logo apos ativar a wakeword, o problema nao e
a wakeword: e o Whisper. Se nao responder a voz nenhuma, confira os logs.

Para testar a deteccao sem o servico no meio:

```bash
./venv/bin/python nexus.py --voz
```

Se ele responder "Nao entendi" logo apos ativar a wakeword, o problema nao e
a wakeword: e o Whisper. Se nao responder a voz nenhuma, confira os logs.

## Musica no Spotify

O plugin `spotify` usa a **Web API do Spotify**: ele busca a faixa pelo nome e
manda o player do proprio Spotify tocar (com audio no Spotify Connect).

Duas coisas do lado do Spotify sao obrigatorias:

1. **Conta Premium.** Tocar pelo Web API nao funciona em conta gratuita.
2. **Um app seu no painel.** Em <https://developer.spotify.com/dashboard>:
   - crie um app e pegue o **Client ID**;
   - em *Settings*, adicione o Redirect URI exato:
     `http://127.0.0.1:8898/callback`;
   - em *User management*, adicione o seu proprio e-mail (o Spotify exige isso
     para apps novos).

Depois cole o Client ID em `config/spotify.json`:

```json
{ "client_id": "SEU_CLIENT_ID" }
```

E autorize uma vez (abre o navegador e mostra um "Nexus conectado"):

```bash
./venv/bin/python -c "from ferramentas import spotify; print(spotify.funcao('conectar'))"
```

O plugin escolhe onde tocar: **prefere o computador**. Se o Spotify não
estiver aberto, o próprio Nexus sobe o aplicativo antes de dar play.

> **Se o Spotify do PC não abre** (some e volta na hora, sem mensagem): o snap
> morre na inicialização da GPU com drivers novos. O contorno é rodar com
> `--disable-gpu`:
>
> ```bash
> snap run spotify --disable-gpu
> ```
>
> Isso já é automático no plugin, mas vale saber caso você abrir o Spotify
> na mão pelo menu de aplicativos.

Depois disso e so falar:

- "toca bohemian rhapsody"
- "toca alguma coisa do Charlie Brown Jr"
- "pausa o spotify", "proxima musica", "o que esta tocando"
- "volume do spotify 40"

O plugin prefere tocar **no computador**: se o Spotify não estiver aberto, ele
sobe o aplicativo sozinho antes de dar play.

## Servico em segundo plano (systemd --user)

Para o Nexus rodar sempre, sem abrir terminal, instale-o como servico de usuario:

```bash
./instalar_servico.sh
```

Ele inicia sozinho no login e fica ouvindo a wakeword. Comandos uteis:

```bash
systemctl --user status nexus
journalctl --user -u nexus -f
systemctl --user stop nexus
systemctl --user disable --now nexus
```

Para iniciar tambem sem login (apos ligar o notebook), rode uma vez:

```bash
sudo loginctl enable-linger $USER
```

## Modelos do Ollama

```bash
ollama pull llama3.1:8b
ollama pull qwen2.5:7b
ollama pull nomic-embed-text   # usado na busca em documentos (Etapa 5)
```

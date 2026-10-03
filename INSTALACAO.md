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

Sem esse modelo, o Jarvis cai automaticamente para espeak-ng/spd-say (mais robotico).

## Servico em segundo plano (systemd --user)

Para o Jarvis rodar sempre, sem abrir terminal, instale-o como servico de usuario:

```bash
./instalar_servico.sh
```

Ele inicia sozinho no login e fica ouvindo a wakeword. Comandos uteis:

```bash
systemctl --user status jarvis
journalctl --user -u jarvis -f
systemctl --user stop jarvis
systemctl --user disable --now jarvis
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

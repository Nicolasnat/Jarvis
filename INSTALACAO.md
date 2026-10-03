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
| `espeak-ng` | voz sintetizada (alternativa ao Piper) | 4 |

Comando unico (opcional):

```bash
sudo apt install xdg-utils libnotify-bin pulseaudio-utils brightnessctl xclip espeak-ng
```

## Modelos do Ollama

```bash
ollama pull llama3.1:8b
ollama pull qwen2.5:7b
ollama pull nomic-embed-text   # usado na busca em documentos (Etapa 5)
```

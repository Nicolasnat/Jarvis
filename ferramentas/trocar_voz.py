"""Troca a voz do Nexus sem precisar editar codigo.

O Piper tem poucas vozes em portugues: sao 3 alternativas para o pt-BR alem da
que ja vem instalada. Este script lista as opcoes, deixa voce ouvir uma amostra
e grava a escolha em config/voz.json.

    python -m ferramentas.trocar_voz --listar
    python -m ferramentas.trocar_voz --ouvir pt_BR-cadu-medium
    python -m ferramentas.trocar_voz --usar pt_BR-jeff-medium
    python -m ferramentas.trocar_voz --atual
    python -m ferramentas.trocar_voz --velocidade 1.15 --profundidade 1.1

Cada voz nova baixa ~60 MB na primeira vez que ela e usada.
"""
import argparse
import sys

from comum import PASTA_CONFIG

import voz

FALLBACK = dict(voz.VOZES_PADRAO)


def _catalogo():
    """Baixa (e guarda em cache) o catalogo de vozes do piper.

    O piper busca isso na HuggingFace toda vez. Sem rede, caimos no cache local
    para o comando --listar continuar funcionando offline.
    """
    import json
    import urllib.request
    from piper.download_voices import VOICES_JSON

    cache = voz.PASTA_VOZES / "voices.json"
    try:
        return json.loads(cache.read_text())
    except (OSError, ValueError):
        pass

    try:
        with urllib.request.urlopen(VOICES_JSON, timeout=20) as resposta:
            dados = json.loads(resposta.read().decode("utf-8"))
    except Exception as erro:
        print(f"Nao consegui baixar o catalogo de vozes: {erro}", file=sys.stderr)
        return {}

    try:
        cache.parent.mkdir(parents=True, exist_ok=True)
        cache.write_text(json.dumps(dados))
    except OSError:
        pass
    return dados


def _disponiveis():
    """Vozes do piper que servem para o Nexus falar portugues."""
    return sorted(k for k in _catalogo() if k.lower().startswith("pt"))


def _baixar(nome):
    """Garante o .onnx da voz em dados/voz, baixando se faltar."""
    caminho = voz.PASTA_VOZES / f"{nome}.onnx"
    if caminho.exists():
        return caminho
    print(f"Baixando a voz {nome} (~60 MB)...")
    import subprocess
    subprocess.run(
        [sys.executable, "-m", "piper.download_voices", nome,
         "--download-dir", str(voz.PASTA_VOZES)],
        check=True,
    )
    return caminho


def main(argv=None):
    ap = argparse.ArgumentParser(description="Troca a voz do Nexus")
    ap.add_argument("--listar", action="store_true", help="mostra as voces em portugues")
    ap.add_argument("--atual", action="store_true", help="mostra a voz em uso")
    ap.add_argument("--ouvir", metavar="VOZ", help="fala uma amostra com essa voz")
    ap.add_argument("--usar", metavar="VOZ", help="deixa essa voz como padrao")
    ap.add_argument("--velocidade", type=float, help="1.0 normal, 1.2 mais rapido")
    ap.add_argument("--profundidade", type=float, help="1.0 normal, maior = mais expressivo")
    args = ap.parse_args(argv)

    config = voz.carregar_config_voz()

    if args.listar or not (args.atual or args.ouvir or args.usar
                           or args.velocidade is not None
                           or args.profundidade is not None):
        print("Vozes em portugues disponiveis:\n")
        for nome in _disponiveis():
            marca = "  <- em uso" if nome == config["modelo"] else ""
            tem = " (instalada)" if (voz.PASTA_VOZES / f"{nome}.onnx").exists() else ""
            print(f"  {nome}{tem}{marca}")
        print("\nTrocar:  python -m ferramentas.trocar_voz --usar <voz>")
        return 0

    if args.atual:
        print(f"Voz     : {config['modelo']}")
        print(f"Velocidade: {config['velocidade']}")
        print(f"Profundidade: {config['profundidade']}")
        print(f"Arquivo : {voz.PASTA_VOZES / (config['modelo'] + '.onnx')}")
        return 0

    if args.ouvir:
        _baixar(args.ouvir)
        from piper import PiperVoice
        tom = PiperVoice.load(str(voz.PASTA_VOZES / f"{args.ouvir}.onnx"))
        import tempfile
        import wave
        from pathlib import Path

        saida = Path(tempfile.mkdtemp()) / "amostra.wav"
        with wave.open(str(saida), "wb") as wav:
            tom.synthesize_wav(
                "Nexus online. Tudo pronto para ouvir voce.",
                wav,
                syn_config=voz._config_sintese(),
            )
        print(f"Reproduzindo amostra de {args.ouvir}...")
        subprocess_run_player(saida)
        return 0

    if args.usar:
        disponiveis = _disponiveis()
        if disponiveis and args.usar not in disponiveis:
            print(f"'{args.usar}' nao e uma voz de portugues do piper.", file=sys.stderr)
            print("Use --listar para ver as opcoes.", file=sys.stderr)
            return 1
        _baixar(args.usar)
        config["modelo"] = args.usar
        print(f"Voz trocada para {args.usar}. Reinicie o servico para valer.")

    if args.velocidade is not None:
        config["velocidade"] = max(0.5, min(2.0, args.velocidade))
        print(f"Velocidade: {config['velocidade']}")
    if args.profundidade is not None:
        config["profundidade"] = max(0.5, min(2.0, args.profundidade))
        print(f"Profundidade: {config['profundidade']}")

    voz.salvar_config_voz(config)
    print(f"Salvo em {voz.ARQUIVO_VOZ}")
    if not args.usar:
        print("Reinicie o servico para valer.")
    return 0


def subprocess_run_player(arquivo):
    import shutil
    import subprocess

    for toca in (["paplay"], ["aplay", "-q"], ["ffplay", "-nodisp", "-autoexit", "-loglevel", "quiet"]):
        if shutil.which(toca[0]):
            subprocess.run(toca + [str(arquivo)])
            return
    print(f"Amostra em {arquivo} (nenhum player encontrado para tocar)")


if __name__ == "__main__":
    sys.exit(main())

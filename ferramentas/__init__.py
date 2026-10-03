"""Pacote de plugins do Jarvis.

Cada modulo em ferramentas/ exporta NOME, DESCRICAO, PARAMETROS, funcao e,
opcionalmente, BINARIO e SEGURANCA. O carregador monta o CATALOGO.
"""
from .carregador import carregar_plugins

__all__ = ["carregar_plugins"]

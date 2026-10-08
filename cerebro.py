"""Modulo de cerebro do Nexus: interface unificada para provedores de LLM.

Implementa a cadeia de cerebros (nuvem_gratis -> local) com
failover automatico, circuit breaker, contadores de uso e historico neutro.
"""

import json
import os
import time
import threading
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from comum import PASTA_DADOS, ler_json, salvar_json
from eventos import registrar_evento


# Configuraveis globais do loop de agente
MAX_PASSOS = 6
MAX_PASSOS_LOCAL = 4
TEMPO_MAX_TURNO = 120  # segundos
TOKENS_MAX_TURNO = 8000


class TipoProvedor(Enum):
    NUVEM_PAGO = "nuvem_pago"
    NUVEM_GRATIS = "nuvem_gratis"
    LOCAL = "local"
    OPENAI = "openai"


class EstadoProvedor(Enum):
    ATIVO = "ativo"
    ESGOTADO = "esgotado"
    ERRO = "erro"
    DESCANSO = "descanso"
    INATIVO = "inativo"


@dataclass
class ConfigProvedor:
    nome: str
    tipo: TipoProvedor
    modelo: str
    chave_ref: str = ""
    limite_mensal_tokens: int = 0
    ativo: bool = True
    prioridade: int = 0
    max_passos: int = 0  # 0 = usa global
    rede_seguranca_palavra_chave: bool = False  # so para local


@dataclass
class EstadoProvedorData:
    estado: EstadoProvedor = EstadoProvedor.ATIVO
    tokens_mes: int = 0
    tokens_dia: int = 0
    ultima_renovacao_dia: str = ""
    ultima_renovacao_mes: str = ""
    erros_consecutivos: int = 0
    ultimo_erro: str = ""
    entrou_descanso_em: float = 0
    descanso_ate: float = 0
    chamada_teste_ok: bool = False


@dataclass
class ResultadoChat:
    conteudo: str
    tool_calls: list = field(default_factory=list)
    tokens_entrada: int = 0
    tokens_saida: int = 0
    modelo_usado: str = ""
    provedor_usado: str = ""
    erro: str = ""


@dataclass
class MensagemNeutra:
    role: str
    content: str
    tool_calls: list = field(default_factory=list)
    tool_call_id: str = ""
    name: str = ""


class CerebroBase(ABC):
    @abstractmethod
    def chat(self, mensagens: list[MensagemNeutra], ferramentas: list[dict] | None = None) -> ResultadoChat:
        pass

    @abstractmethod
    def listar_modelos(self) -> list[str]:
        pass

    @abstractmethod
    def testar_function_calling(self) -> bool:
        pass

    @property
    @abstractmethod
    def config(self) -> ConfigProvedor:
        pass


class CerebroLocal(CerebroBase):
    def __init__(self, config: ConfigProvedor):
        self._config = config
        import ollama
        self._ollama = ollama

    @property
    def config(self) -> ConfigProvedor:
        return self._config

    def chat(self, mensagens: list[MensagemNeutra], ferramentas: list[dict] | None = None) -> ResultadoChat:
        msgs_ollama = []
        for m in mensagens:
            msg = {"role": m.role, "content": m.content}
            if m.tool_calls:
                msg["tool_calls"] = m.tool_calls
            if m.tool_call_id:
                msg["tool_call_id"] = m.tool_call_id
            if m.name:
                msg["name"] = m.name
            msgs_ollama.append(msg)

        try:
            r = self._ollama.chat(
                model=self._config.modelo,
                messages=msgs_ollama,
                tools=ferramentas or [],
                options={"num_ctx": 8192},
            )
            msg = r["message"]
            return ResultadoChat(
                conteudo=msg.get("content") or "",
                tool_calls=msg.get("tool_calls") or [],
                modelo_usado=self._config.modelo,
                provedor_usado=self._config.nome,
            )
        except Exception as e:
            return ResultadoChat(conteudo="", erro=str(e), provedor_usado=self._config.nome)

    def listar_modelos(self) -> list[str]:
        try:
            return [m["name"] for m in self._ollama.list()["models"]]
        except Exception:
            return []

    def testar_function_calling(self) -> bool:
        try:
            r = self._ollama.chat(
                model=self._config.modelo,
                messages=[{"role": "user", "content": "Teste function calling"}],
                tools=[{"type": "function", "function": {"name": "teste", "description": "teste", "parameters": {"type": "object", "properties": {}}}}],
            )
            return True
        except Exception:
            return False


class CerebroGemini(CerebroBase):
    def __init__(self, config: ConfigProvedor):
        self._config = config
        self._client = None
        self._types = None

    def _ensure_client(self):
        if self._client is not None:
            return True
        if not self._obter_chave():
            return False
        from google import genai
        from google.genai import types
        self._client = genai.Client(api_key=self._obter_chave())
        self._types = types
        return True

    def _obter_chave(self) -> str:
        if self._config.chave_ref:
            chave = os.environ.get(self._config.chave_ref)
            if chave:
                return chave
            from comum import BASE_PROJETO, ler_json
            arquivo_chaves = BASE_PROJETO / "config" / "gemini.json"
            chaves = ler_json(arquivo_chaves, {})
            if self._config.chave_ref in chaves:
                return chaves[self._config.chave_ref]
        return ""

    @property
    def config(self) -> ConfigProvedor:
        return self._config

    def _converter_mensagens(self, mensagens: list[MensagemNeutra]) -> list:
        resultado = []
        for m in mensagens:
            if m.role == "system":
                resultado.append(self._types.Content(role="user", parts=[self._types.Part(text=f"[SISTEMA] {m.content}")]))
            elif m.role == "user":
                resultado.append(self._types.Content(role="user", parts=[self._types.Part(text=m.content)]))
            elif m.role == "assistant":
                partes = []
                if m.content:
                    partes.append(self._types.Part(text=m.content))
                if m.tool_calls:
                    for tc in m.tool_calls:
                        partes.append(self._types.Part(function_call=self._types.FunctionCall(
                            name=tc["function"]["name"],
                            args=tc["function"].get("arguments", {}),
                        )))
                if partes:
                    resultado.append(self._types.Content(role="model", parts=partes))
            elif m.role == "tool":
                if m.tool_call_id and m.name:
                    resultado.append(self._types.Content(role="user", parts=[self._types.Part(function_response=self._types.FunctionResponse(
                        name=m.name,
                        response={"result": m.content},
                    ))]))
        return resultado

    def _converter_ferramentas(self, ferramentas: list[dict] | None) -> list | None:
        if not ferramentas:
            return None
        resultado = []
        for f in ferramentas:
            if f.get("type") == "function":
                fn = f["function"]
                resultado.append(self._types.FunctionDeclaration(
                    name=fn["name"],
                    description=fn.get("description", ""),
                    parameters=fn.get("parameters", {}),
                ))
        return resultado if resultado else None

    def chat(self, mensagens: list[MensagemNeutra], ferramentas: list[dict] | None = None) -> ResultadoChat:
        if not self._ensure_client():
            return ResultadoChat(conteudo="", erro="Chave da API nao configurada", provedor_usado=self._config.nome)

        msgs = self._converter_mensagens(mensagens)
        tools = self._converter_ferramentas(ferramentas)

        try:
            # Tenta desativar o AFC (Automatic Function Calling) para evitar aviso "AFC is not recommended"
            config_kwargs = {
                "tools": [self._types.Tool(function_declarations=tools)] if tools else None,
                "temperature": 0.7,
            }
            try:
                config_kwargs["automatic_function_calling"] = self._types.AutomaticFunctionCallingConfig(disable=True)
            except (AttributeError, TypeError):
                pass  # SDK nao suporta, ignora silenciosamente
            config = self._types.GenerateContentConfig(**config_kwargs)
            r = self._client.models.generate_content(
                model=self._config.modelo,
                contents=msgs,
                config=config,
            )

            conteudo = ""
            tool_calls = []
            tokens_entrada = 0
            tokens_saida = 0

            if r.usage_metadata:
                tokens_entrada = r.usage_metadata.prompt_token_count or 0
                tokens_saida = r.usage_metadata.candidates_token_count or 0

            for cand in r.candidates or []:
                if cand.content:
                    for part in cand.content.parts or []:
                        if part.text:
                            conteudo += part.text
                        if part.function_call:
                            tool_calls.append({
                                "function": {
                                    "name": part.function_call.name,
                                    "arguments": part.function_call.args or {},
                                }
                            })

            return ResultadoChat(
                conteudo=conteudo,
                tool_calls=tool_calls,
                tokens_entrada=tokens_entrada,
                tokens_saida=tokens_saida,
                modelo_usado=self._config.modelo,
                provedor_usado=self._config.nome,
            )
        except Exception as e:
            return ResultadoChat(conteudo="", erro=str(e), provedor_usado=self._config.nome)

    def listar_modelos(self) -> list[str]:
        if not self._ensure_client():
            return []
        try:
            modelos = []
            for m in self._client.models.list():
                if "generateContent" in (m.supported_actions or []):
                    modelos.append(m.name.replace("models/", ""))
            return modelos
        except Exception:
            return []

    def testar_function_calling(self) -> bool:
        if not self._ensure_client():
            return False
        try:
            tools = [self._types.FunctionDeclaration(
                name="teste",
                description="teste",
                parameters={"type": "object", "properties": {}},
            )]
            config = self._types.GenerateContentConfig(
                tools=[self._types.Tool(function_declarations=tools)],
            )
            r = self._client.models.generate_content(
                model=self._config.modelo,
                contents=[self._types.Content(role="user", parts=[self._types.Part(text="Teste function calling")])],
                config=config,
            )
            for cand in r.candidates or []:
                if cand.content:
                    for part in cand.content.parts or []:
                        if part.function_call:
                            return True
            return False
        except Exception:
            return False


class CerebroOpenAI(CerebroBase):
    def __init__(self, config: ConfigProvedor):
        self._config = config
        self._client = None

    def _obter_chave(self) -> str:
        if self._config.chave_ref:
            chave = os.environ.get(self._config.chave_ref)
            if chave:
                return chave
            from comum import BASE_PROJETO, ler_json
            arquivo_chaves = BASE_PROJETO / "config" / "openai.json"
            chaves = ler_json(arquivo_chaves, {})
            if self._config.chave_ref in chaves:
                return chaves[self._config.chave_ref]
        return ""

    def _ensure_client(self):
        if self._client is not None:
            return True
        chave = self._obter_chave()
        if not chave:
            return False
        from openai import OpenAI
        self._client = OpenAI(api_key=chave)
        return True

    @property
    def config(self) -> ConfigProvedor:
        return self._config

    def _converter_mensagens(self, mensagens: list[MensagemNeutra]) -> list:
        resultado = []
        for m in mensagens:
            if m.role == "system":
                resultado.append({"role": "system", "content": m.content})
            elif m.role == "user":
                resultado.append({"role": "user", "content": m.content})
            elif m.role == "assistant":
                if m.tool_calls:
                    for tc in m.tool_calls:
                        resultado.append({
                            "role": "assistant",
                            "tool_calls": [{
                                "id": tc["function"].get("id", "call_" + str(hash(str(tc))))[:24],
                                "type": "function",
                                "function": {
                                    "name": tc["function"]["name"],
                                    "arguments": json.dumps(tc["function"].get("arguments", {})),
                                }
                            }]
                        })
                elif m.content:
                    resultado.append({"role": "assistant", "content": m.content})
            elif m.role == "tool":
                if m.tool_call_id and m.name:
                    resultado.append({
                        "role": "tool",
                        "tool_call_id": m.tool_call_id,
                        "name": m.name,
                        "content": m.content,
                    })
        return resultado

    def _converter_ferramentas(self, ferramentas: list[dict] | None) -> list | None:
        if not ferramentas:
            return None
        resultado = []
        for f in ferramentas:
            if f.get("type") == "function":
                fn = f["function"]
                resultado.append({
                    "type": "function",
                    "function": {
                        "name": fn["name"],
                        "description": fn.get("description", ""),
                        "parameters": fn.get("parameters", {}),
                    }
                })
        return resultado if resultado else None

    def chat(self, mensagens: list[MensagemNeutra], ferramentas: list[dict] | None = None) -> ResultadoChat:
        if not self._ensure_client():
            return ResultadoChat(conteudo="", erro="Chave da API OpenAI nao configurada", provedor_usado=self._config.nome)

        msgs = self._converter_mensagens(mensagens)
        tools = self._converter_ferramentas(ferramentas)

        try:
            kwargs = {
                "model": self._config.modelo,
                "messages": msgs,
                "temperature": 0.7,
            }
            if tools:
                kwargs["tools"] = tools
                kwargs["tool_choice"] = "auto"

            r = self._client.chat.completions.create(**kwargs)

            choice = r.choices[0]
            message = choice.message

            conteudo = message.content or ""
            tool_calls = []
            if message.tool_calls:
                for tc in message.tool_calls:
                    tool_calls.append({
                        "function": {
                            "name": tc.function.name,
                            "arguments": json.loads(tc.function.arguments or "{}"),
                        }
                    })

            tokens_entrada = r.usage.prompt_tokens if r.usage else 0
            tokens_saida = r.usage.completion_tokens if r.usage else 0

            return ResultadoChat(
                conteudo=conteudo,
                tool_calls=tool_calls,
                tokens_entrada=tokens_entrada,
                tokens_saida=tokens_saida,
                modelo_usado=self._config.modelo,
                provedor_usado=self._config.nome,
            )
        except Exception as e:
            return ResultadoChat(conteudo="", erro=str(e), provedor_usado=self._config.nome)

    def listar_modelos(self) -> list[str]:
        if not self._ensure_client():
            return []
        try:
            modelos = []
            for m in self._client.models.list():
                modelos.append(m.id)
            return modelos
        except Exception:
            return []

    def testar_function_calling(self) -> bool:
        if not self._ensure_client():
            return False
        try:
            tools = [{
                "type": "function",
                "function": {
                    "name": "teste",
                    "description": "teste",
                    "parameters": {"type": "object", "properties": {}},
                }
            }]
            r = self._client.chat.completions.create(
                model=self._config.modelo,
                messages=[{"role": "user", "content": "Teste function calling"}],
                tools=tools,
                tool_choice="auto",
            )
            return bool(r.choices[0].message.tool_calls)
        except Exception:
            return False


class GerenciadorCerebros:
    ARQUIVO_CEREBRO = PASTA_DADOS / "cerebro.json"
    ARQUIVO_USO = PASTA_DADOS / "uso_cerebro.json"
    ARQUIVO_HISTORICO = PASTA_DADOS / "historico_neutro.json"

    def __init__(self):
        self._lock = threading.RLock()
        self._provedores: list[CerebroBase] = []
        self._configs: list[ConfigProvedor] = []
        self._estados: dict[str, EstadoProvedorData] = {}
        self._historico_neutro: list[MensagemNeutra] = []
        self._ultimo_provedor_ativo: str | None = None
        self._carregar_config()
        self._carregar_estados()
        self._carregar_historico()
        self._inicializar_provedores()

    def _carregar_config(self):
        padrao = {
            "provedores": [
                {"nome": "gemini-flash-gratis", "tipo": "nuvem_gratis", "modelo": "", "chave_ref": "GEMINI_API_KEY_GRATIS", "limite_mensal_tokens": 100000, "ativo": True, "prioridade": 1, "max_passos": 0, "rede_seguranca_palavra_chave": False},
                {"nome": "ollama-local", "tipo": "local", "modelo": "llama3.1:8b", "chave_ref": "", "limite_mensal_tokens": 0, "ativo": True, "prioridade": 2, "max_passos": 4, "rede_seguranca_palavra_chave": True},
            ]
        }
        dados = ler_json(self.ARQUIVO_CEREBRO, padrao)
        self._configs = []
        for p in dados["provedores"]:
            self._configs.append(ConfigProvedor(
                nome=p["nome"],
                tipo=TipoProvedor(p["tipo"]),
                modelo=p["modelo"],
                chave_ref=p.get("chave_ref", ""),
                limite_mensal_tokens=p.get("limite_mensal_tokens", 0),
                ativo=p.get("ativo", True),
                prioridade=p.get("prioridade", 0),
                max_passos=p.get("max_passos", 0),
                rede_seguranca_palavra_chave=p.get("rede_seguranca_palavra_chave", False),
            ))
        self._configs.sort(key=lambda c: c.prioridade)
        if not self.ARQUIVO_CEREBRO.exists():
            self._salvar_config()

    def _salvar_config(self):
        dados = {"provedores": []}
        for c in self._configs:
            dados["provedores"].append({
                "nome": c.nome,
                "tipo": c.tipo.value,
                "modelo": c.modelo,
                "chave_ref": c.chave_ref,
                "limite_mensal_tokens": c.limite_mensal_tokens,
                "ativo": c.ativo,
                "prioridade": c.prioridade,
                "max_passos": c.max_passos,
                "rede_seguranca_palavra_chave": c.rede_seguranca_palavra_chave,
            })
        salvar_json(self.ARQUIVO_CEREBRO, dados)

    def _carregar_estados(self):
        dados = ler_json(self.ARQUIVO_USO, {"provedores": {}})
        for nome, ed in dados.get("provedores", {}).items():
            self._estados[nome] = EstadoProvedorData(
                estado=EstadoProvedor(ed.get("estado", "ativo")),
                tokens_mes=ed.get("tokens_mes", 0),
                tokens_dia=ed.get("tokens_dia", 0),
                ultima_renovacao_dia=ed.get("ultima_renovacao_dia", ""),
                ultima_renovacao_mes=ed.get("ultima_renovacao_mes", ""),
                erros_consecutivos=ed.get("erros_consecutivos", 0),
                ultimo_erro=ed.get("ultimo_erro", ""),
                entrou_descanso_em=ed.get("entrou_descanso_em", 0),
                descanso_ate=ed.get("descanso_ate", 0),
                chamada_teste_ok=ed.get("chamada_teste_ok", False),
            )
        if not self.ARQUIVO_USO.exists():
            self._salvar_estados()

    def _salvar_estados(self):
        dados = {"provedores": {}}
        for nome, ed in self._estados.items():
            dados["provedores"][nome] = {
                "estado": ed.estado.value,
                "tokens_mes": ed.tokens_mes,
                "tokens_dia": ed.tokens_dia,
                "ultima_renovacao_dia": ed.ultima_renovacao_dia,
                "ultima_renovacao_mes": ed.ultima_renovacao_mes,
                "erros_consecutivos": ed.erros_consecutivos,
                "ultimo_erro": ed.ultimo_erro,
                "entrou_descanso_em": ed.entrou_descanso_em,
                "descanso_ate": ed.descanso_ate,
                "chamada_teste_ok": ed.chamada_teste_ok,
            }
        salvar_json(self.ARQUIVO_USO, dados)

    def _carregar_historico(self):
        dados = ler_json(self.ARQUIVO_HISTORICO, {"mensagens": []})
        self._historico_neutro = []
        for m in dados.get("mensagens", []):
            self._historico_neutro.append(MensagemNeutra(
                role=m["role"],
                content=m["content"],
                tool_calls=m.get("tool_calls", []),
                tool_call_id=m.get("tool_call_id", ""),
                name=m.get("name", ""),
            ))
        if not self.ARQUIVO_HISTORICO.exists():
            self._salvar_historico()

    def _salvar_historico(self):
        dados = {"mensagens": []}
        for m in self._historico_neutro:
            dados["mensagens"].append({
                "role": m.role,
                "content": m.content,
                "tool_calls": m.tool_calls,
                "tool_call_id": m.tool_call_id,
                "name": m.name,
            })
        salvar_json(self.ARQUIVO_HISTORICO, dados)

    def _inicializar_provedores(self):
        self._provedores = []
        for cfg in self._configs:
            if not cfg.ativo:
                continue
            if cfg.tipo == TipoProvedor.LOCAL:
                self._provedores.append(CerebroLocal(cfg))
            elif cfg.tipo in (TipoProvedor.NUVEM_PAGO, TipoProvedor.NUVEM_GRATIS):
                self._provedores.append(CerebroGemini(cfg))
            elif cfg.tipo == TipoProvedor.OPENAI:
                self._provedores.append(CerebroOpenAI(cfg))

    def obter_provedor_ativo(self) -> CerebroBase | None:
        with self._lock:
            for p in self._provedores:
                ed = self._estados.get(p.config.nome)
                if ed and ed.estado == EstadoProvedor.ATIVO:
                    return p
            return self._provedores[-1] if self._provedores else None

    def chat(self, mensagens: list[MensagemNeutra], ferramentas: list[dict] | None = None) -> ResultadoChat:
        self.tentar_recuperar_provedores()

        provedores_ativos = [p for p in self._provedores
                             if self._estados.get(p.config.nome, EstadoProvedorData()).estado == EstadoProvedor.ATIVO]

        if not provedores_ativos:
            provedores_ativos = list(self._provedores)

        # Notificar mudanca de cerebro ativo
        provedor_atual = provedores_ativos[0].config.nome if provedores_ativos else None
        if provedor_atual != self._ultimo_provedor_ativo:
            self._ultimo_provedor_ativo = provedor_atual
            self._notificar_mudanca_cerebro(provedor_atual)

        print(f"[cerebro] Modelo ativo: {provedores_ativos[0].config.nome} ({provedores_ativos[0].config.modelo})", flush=True)

        ultimo_erro = ""
        for provedor in provedores_ativos:
            if not self.verificar_limites(provedor.config.nome):
                continue

            inicio = time.time()
            resultado = provedor.chat(mensagens, ferramentas)
            duracao = time.time() - inicio

            if resultado.erro:
                erro_lower = resultado.erro.lower()
                if any(x in erro_lower for x in ["429", "quota", "cota"]):
                    # Verifica se e cota diaria
                    if any(x in erro_lower for x in ["perday", "per day", "daily"]):
                        self._colocar_descanso_diario(provedor.config.nome)
                        registrar_evento("cerebro", f"{provedor.config.nome} falhou (cota diaria)", f"proximo: {provedores_ativos[provedores_ativos.index(provedor)+1].config.nome if provedores_ativos.index(provedor)+1 < len(provedores_ativos) else 'nenhum'}", ok=False, duracao_ms=int(duracao * 1000))
                    else:
                        self._colocar_descanso_curto(provedor.config.nome)
                        registrar_evento("cerebro", f"{provedor.config.nome} falhou (limite por minuto)", f"proximo: {provedores_ativos[provedores_ativos.index(provedor)+1].config.nome if provedores_ativos.index(provedor)+1 < len(provedores_ativos) else 'nenhum'}", ok=False, duracao_ms=int(duracao * 1000))
                    self.registrar_erro(provedor.config.nome, resultado.erro)
                    ultimo_erro = f"{provedor.config.nome}: {resultado.erro}"
                    continue
                elif any(x in erro_lower for x in ["401", "403", "invalid", "unauthorized", "permission"]):
                    registrar_evento("cerebro", f"{provedor.config.nome} falhou (chave invalida)", resultado.erro, ok=False, duracao_ms=int(duracao * 1000))
                    return ResultadoChat(
                        conteudo="",
                        erro=f"Chave invalida para {provedor.config.nome}: {resultado.erro}. Verifique a chave no Google AI Studio.",
                        provedor_usado=provedor.config.nome
                    )
                elif any(x in erro_lower for x in ["billing", "faturamento", "503", "500", "timeout", "network"]):
                    self.registrar_erro(provedor.config.nome, resultado.erro)
                    ultimo_erro = f"{provedor.config.nome}: {resultado.erro}"
                    continue

            if resultado.tokens_entrada or resultado.tokens_saida:
                self.registrar_uso(provedor.config.nome, resultado.tokens_entrada, resultado.tokens_saida)
                self.verificar_limites(provedor.config.nome)

            self.registrar_sucesso(provedor.config.nome)
            registrar_evento("cerebro", f"{provedor.config.nome} respondeu em {duracao:.1f}s", f"tokens_in={resultado.tokens_entrada} tokens_out={resultado.tokens_saida}", ok=True, duracao_ms=int(duracao * 1000))
            return resultado

        registrar_evento("cerebro", "Todos os provedores falharam", ultimo_erro, ok=False)
        return ResultadoChat(conteudo="", erro=f"Todos os provedores falharam: {ultimo_erro}", provedor_usado="")

    def _proxima_meia_noite_la(self) -> float:
        """Retorna timestamp da proxima meia-noite no fuso America/Los_Angeles."""
        agora = datetime.now(ZoneInfo("America/Los_Angeles"))
        proxima = agora.replace(hour=0, minute=0, second=0, microsecond=0)
        if proxima <= agora:
            from datetime import timedelta
            proxima += timedelta(days=1)
        return proxima.timestamp()

    def _colocar_descanso_diario(self, provedor_nome: str):
        with self._lock:
            ed = self._estados.setdefault(provedor_nome, EstadoProvedorData())
            ed.estado = EstadoProvedor.DESCANSO
            ed.descanso_ate = self._proxima_meia_noite_la()
            ed.entrou_descanso_em = time.time()
            self._salvar_estados()

    def _colocar_descanso_curto(self, provedor_nome: str):
        with self._lock:
            ed = self._estados.setdefault(provedor_nome, EstadoProvedorData())
            ed.estado = EstadoProvedor.DESCANSO
            ed.descanso_ate = time.time() + 60
            ed.entrou_descanso_em = time.time()
            self._salvar_estados()

    def _notificar_mudanca_cerebro(self, novo_provedor: str | None):
        """Chama callback registrado quando o cerebro ativo muda."""
        global _g_callback_cerebro_mudou
        if _g_callback_cerebro_mudou and novo_provedor:
            try:
                _g_callback_cerebro_mudou(novo_provedor)
            except Exception:
                pass

    def _extrair_retry_after(self, erro: str) -> int:
        """Extrai segundos de retry-after do erro (se disponivel). Retorna 0 se nao encontrar."""
        import re
        # Padroes comuns: "retry_after: 30", "retry-after: 30s", "wait 30 seconds"
        padroes = [
            r"retry[_\s-]?after[:\s]+(\d+)",
            r"wait\s+(\d+)\s*seconds?",
            r"try again in (\d+)",
        ]
        for p in padroes:
            m = re.search(p, erro, re.IGNORECASE)
            if m:
                try:
                    return int(m.group(1))
                except ValueError:
                    pass
        return 0

    def adicionar_historico(self, mensagens: list[MensagemNeutra]):
        with self._lock:
            self._historico_neutro.extend(mensagens)
            if len(self._historico_neutro) > 50:
                self._historico_neutro = self._historico_neutro[-50:]
            self._salvar_historico()

    def obter_historico(self) -> list[MensagemNeutra]:
        return list(self._historico_neutro)

    def limpar_historico(self):
        with self._lock:
            self._historico_neutro.clear()
            self._salvar_historico()

    def registrar_uso(self, provedor_nome: str, tokens_entrada: int, tokens_saida: int):
        with self._lock:
            ed = self._estados.setdefault(provedor_nome, EstadoProvedorData())
            total = tokens_entrada + tokens_saida
            ed.tokens_mes += total
            ed.tokens_dia += total
            hoje = datetime.now().strftime("%Y-%m-%d")
            mes_atual = datetime.now().strftime("%Y-%m")
            if ed.ultima_renovacao_dia != hoje:
                ed.tokens_dia = total
                ed.ultima_renovacao_dia = hoje
            if ed.ultima_renovacao_mes != mes_atual:
                ed.tokens_mes = total
                ed.ultima_renovacao_mes = mes_atual
            self._salvar_estados()

    def verificar_limites(self, provedor_nome: str) -> bool:
        ed = self._estados.get(provedor_nome)
        cfg = next((c for c in self._configs if c.nome == provedor_nome), None)
        if not ed or not cfg or cfg.limite_mensal_tokens <= 0:
            return True
        if ed.tokens_mes >= cfg.limite_mensal_tokens:
            ed.estado = EstadoProvedor.ESGOTADO
            self._salvar_estados()
            return False
        if ed.tokens_mes >= cfg.limite_mensal_tokens * 0.8:
            print(f"[cerebro] Aviso: {provedor_nome} atingiu 80% do limite mensal ({ed.tokens_mes}/{cfg.limite_mensal_tokens})")
        return True

    def registrar_erro(self, provedor_nome: str, erro: str):
        with self._lock:
            ed = self._estados.setdefault(provedor_nome, EstadoProvedorData())
            ed.erros_consecutivos += 1
            ed.ultimo_erro = erro
            if ed.erros_consecutivos >= 3:
                ed.estado = EstadoProvedor.DESCANSO
                ed.entrou_descanso_em = time.time()
            self._salvar_estados()

    def registrar_sucesso(self, provedor_nome: str):
        with self._lock:
            ed = self._estados.setdefault(provedor_nome, EstadoProvedorData())
            ed.erros_consecutivos = 0
            ed.ultimo_erro = ""
            if ed.estado in (EstadoProvedor.ERRO, EstadoProvedor.DESCANSO):
                ed.estado = EstadoProvedor.ATIVO
            self._salvar_estados()

    def tentar_recuperar_provedores(self):
        with self._lock:
            agora = time.time()
            for ed in self._estados.values():
                if ed.estado == EstadoProvedor.DESCANSO:
                    if ed.descanso_ate and agora >= ed.descanso_ate:
                        ed.estado = EstadoProvedor.ATIVO
                        ed.erros_consecutivos = 0
                        ed.descanso_ate = 0
                    elif not ed.descanso_ate and agora - ed.entrou_descanso_em > 300:
                        ed.estado = EstadoProvedor.ATIVO
                        ed.erros_consecutivos = 0
            self._salvar_estados()

    def status(self) -> dict:
        with self._lock:
            return {
                "provedor_ativo": self.obter_provedor_ativo().config.nome if self.obter_provedor_ativo() else "nenhum",
                "provedores": [
                    {
                        "nome": c.nome,
                        "tipo": c.tipo.value,
                        "modelo": c.modelo,
                        "ativo": c.ativo,
                        "estado": self._estados.get(c.nome, EstadoProvedorData()).estado.value,
                        "tokens_mes": self._estados.get(c.nome, EstadoProvedorData()).tokens_mes,
                        "limite_mensal": c.limite_mensal_tokens,
                    }
                    for c in self._configs
                ],
            }

    def obter_config_ativa(self) -> ConfigProvedor | None:
        """Retorna a config do provedor ativo (para max_passos, rede_seguranca, etc)."""
        prov = self.obter_provedor_ativo()
        return prov.config if prov else None

    def forcar_local(self, forcar: bool = True):
        """Modo privado: forca uso do provedor local."""
        with self._lock:
            for p in self._provedores:
                ed = self._estados.get(p.config.nome)
                if not ed:
                    ed = EstadoProvedorData()
                    self._estados[p.config.nome] = ed
                if p.config.tipo == TipoProvedor.LOCAL:
                    if forcar:
                        ed.estado = EstadoProvedor.ATIVO
                else:
                    if forcar:
                        ed.estado = EstadoProvedor.INATIVO
                    else:
                        if ed and ed.estado == EstadoProvedor.INATIVO:
                            ed.estado = EstadoProvedor.ATIVO
            self._salvar_estados()


_g_cerebros: GerenciadorCerebros | None = None
_g_callback_cerebro_mudou = None


def get_gerenciador() -> GerenciadorCerebros:
    global _g_cerebros
    if _g_cerebros is None:
        _g_cerebros = GerenciadorCerebros()
    return _g_cerebros


def set_callback_cerebro_mudou(callback):
    """Registra callback chamado quando o cerebro ativo muda."""
    global _g_callback_cerebro_mudou
    _g_callback_cerebro_mudou = callback


def chat(mensagens: list[MensagemNeutra], ferramentas: list[dict] | None = None) -> ResultadoChat:
    return get_gerenciador().chat(mensagens, ferramentas)


def adicionar_historico(mensagens: list[MensagemNeutra]):
    get_gerenciador().adicionar_historico(mensagens)


def obter_historico() -> list[MensagemNeutra]:
    return get_gerenciador().obter_historico()


def limpar_historico():
    get_gerenciador().limpar_historico()


def status_cerebros() -> dict:
    return get_gerenciador().status()


def obter_provedor_ativo():
    """Retorna o provedor ativo (instancia) ou None."""
    return get_gerenciador().obter_provedor_ativo()


def obter_config_ativa() -> ConfigProvedor | None:
    return get_gerenciador().obter_config_ativa()


def forcar_modo_local(forcar: bool = True):
    get_gerenciador().forcar_local(forcar)
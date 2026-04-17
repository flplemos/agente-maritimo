import os
import datetime
import json
import re
import time
from concurrent.futures import ThreadPoolExecutor, TimeoutError
from typing import Iterable
from urllib.parse import urlparse

from langchain.agents import AgentExecutor, create_tool_calling_agent
from langchain_core.messages import AIMessage, HumanMessage
from langchain_openai import ChatOpenAI

from core.prompts import build_agent_prompt
from tools.geocoding import geocoding_tool
from tools.tide_tool import tide_tool

KNOWN_SPOTS = {
    "rio doce": "Rio Doce, Búzios, Nísia Floresta, Rio Grande do Norte",
    "rio doce buzios": "Rio Doce, Búzios, Nísia Floresta, Rio Grande do Norte",
    "rio doce búzios": "Rio Doce, Búzios, Nísia Floresta, Rio Grande do Norte",
    "buzios": "Búzios, Nísia Floresta, Rio Grande do Norte",
    "búzios": "Búzios, Nísia Floresta, Rio Grande do Norte",
    "pipa": "Pipa, Tibau do Sul, Rio Grande do Norte",
    "ponta negra": "Ponta Negra, Natal, Rio Grande do Norte",
    "tabatinga": "Barra de Tabatinga, Nísia Floresta, Rio Grande do Norte",
    "barra de tabatinga": "Barra de Tabatinga, Nísia Floresta, Rio Grande do Norte",
    "gostoso": "São Miguel do Gostoso, Rio Grande do Norte",
    "sao miguel do gostoso": "São Miguel do Gostoso, Rio Grande do Norte",
    "são miguel do gostoso": "São Miguel do Gostoso, Rio Grande do Norte",
    "tourinhos": "Tourinhos, São Miguel do Gostoso, Rio Grande do Norte",
    "cunhau": "Barra do Cunhaú, Canguaretama, Rio Grande do Norte",
    "cunhaú": "Barra do Cunhaú, Canguaretama, Rio Grande do Norte",
    "pirangi": "Pirangi do Norte, Parnamirim, Rio Grande do Norte",
}


def _normalizar_base_url_azure_ai(endpoint: str) -> str:
    if not endpoint:
        return endpoint

    endpoint = endpoint.strip().rstrip("/")
    parsed = urlparse(endpoint)

    if parsed.scheme and parsed.netloc:
        return f"{parsed.scheme}://{parsed.netloc}/openai/v1"

    return endpoint


def criar_llm(max_tokens_override: int | None = None) -> ChatOpenAI:
    endpoint = os.getenv("AZURE_DEEPSEEK_ENDPOINT", "")
    api_key = os.getenv("AZURE_DEEPSEEK_API_KEY")
    model = os.getenv("AZURE_DEEPSEEK_MODEL", "DeepSeek-V3.2")
    connect_timeout = float(os.getenv("AZURE_DEEPSEEK_CONNECT_TIMEOUT", "10"))
    read_timeout = float(os.getenv("AZURE_DEEPSEEK_READ_TIMEOUT", "300"))
    max_tokens = max_tokens_override or int(os.getenv("AZURE_DEEPSEEK_MAX_TOKENS", "700"))

    if not endpoint:
        raise ValueError("Defina AZURE_DEEPSEEK_ENDPOINT no .env.")

    if not api_key:
        raise ValueError("Defina AZURE_DEEPSEEK_API_KEY no .env.")

    return ChatOpenAI(
        model=model,
        base_url=_normalizar_base_url_azure_ai(endpoint),
        api_key=api_key,
        temperature=0,
        timeout=(connect_timeout, read_timeout),
        max_retries=1,
        max_tokens=max_tokens,
        disable_streaming=True,
    )


class AgenteMaritimo:
    def __init__(self) -> None:
        self.tools = [geocoding_tool, tide_tool]
        self.prompt = build_agent_prompt()
        self.llm = criar_llm()
        self.summary_llm = criar_llm(max_tokens_override=320)
        self.agent = create_tool_calling_agent(self.llm, self.tools, self.prompt)
        self.executor = AgentExecutor(
            agent=self.agent,
            tools=self.tools,
            verbose=False,
            max_iterations=6,
            early_stopping_method="force",
        )
        self.summary_timeout = float(os.getenv("AZURE_DEEPSEEK_SUMMARY_TIMEOUT", "35"))

    def _datas_consulta(self, pergunta: str) -> list[str]:
        hoje = datetime.date.today()
        texto = pergunta.strip().lower()
        if "fim de semana" in texto or "final de semana" in texto:
            dias_ate_sabado = (5 - hoje.weekday()) % 7
            sabado = hoje + datetime.timedelta(days=dias_ate_sabado)
            domingo = sabado + datetime.timedelta(days=1)
            return [sabado.isoformat(), domingo.isoformat()]

        if "amanhã" in texto or "amanha" in texto:
            return [(hoje + datetime.timedelta(days=1)).isoformat()]

        if "hoje" in texto:
            return [hoje.isoformat()]

        match = re.search(r"\b(\d{2})/(\d{2})(?:/(\d{4}))?\b", texto)
        if match:
            dia, mes, ano = match.groups()
            ano = int(ano) if ano else hoje.year
            return [datetime.date(ano, int(mes), int(dia)).isoformat()]

        return [hoje.isoformat()]

    def _consultar_regiao_ampla(self, pergunta: str) -> str | None:
        texto = pergunta.strip().lower()
        if not texto:
            return None

        spots = None
        nome_regiao = None
        consulta_previsao = any(
            chave in texto for chave in [
                "swell",
                "previsão",
                "previsao",
                "vento",
                "maré",
                "mare",
                "melhor horário",
                "melhor horario",
                "qual horário",
                "qual horario",
                "hoje",
                "amanhã",
                "amanha",
                "fim de semana",
                "final de semana",
                "sábado",
                "sabado",
                "domingo",
                "sexta",
            ]
        )

        for chave, spot in KNOWN_SPOTS.items():
            if chave in texto:
                nome_regiao = spot
                spots = [spot]
                break

        if not spots and re.search(r"\blitoral norte\b|\bnorte do rn\b|\bnorte do rio grande do norte\b", texto):
            nome_regiao = "Litoral Norte do RN"
            spots = [
                "São Miguel do Gostoso, Rio Grande do Norte",
                "Tourinhos, São Miguel do Gostoso, Rio Grande do Norte",
                "Ponta do Santo Cristo, São Miguel do Gostoso, Rio Grande do Norte",
            ]
        elif not spots and re.search(r"\blitoral sul\b|\bsul do rn\b|\bsul do rio grande do norte\b", texto):
            nome_regiao = "Litoral Sul do RN"
            spots = [
                "Pipa, Tibau do Sul, Rio Grande do Norte",
                "Búzios, Nísia Floresta, Rio Grande do Norte",
                "Barra de Tabatinga, Nísia Floresta, Rio Grande do Norte",
            ]
        elif not spots and re.search(r"\brio grande do norte\b|\brn\b", texto) and any(
            chave in texto for chave in ["melhor pico", "onde surfar", "melhor lugar", "qual pico", "melhor praia"]
        ):
            nome_regiao = "Rio Grande do Norte"
            spots = [
                "Ponta Negra, Natal, Rio Grande do Norte",
                "Pipa, Tibau do Sul, Rio Grande do Norte",
                "São Miguel do Gostoso, Rio Grande do Norte",
            ]
        elif not spots and re.search(r"\brio grande do norte\b|\brn\b", texto) and consulta_previsao:
            nome_regiao = "Rio Grande do Norte (referência costeira: Ponta Negra/Natal)"
            spots = [
                "Ponta Negra, Natal, Rio Grande do Norte",
            ]

        if not spots:
            return None

        return self._consultar_spots(spots, pergunta, nome_regiao)

    def _consultar_spots(self, spots: list[str], pergunta: str, nome_regiao: str | None) -> str | None:
        datas = self._datas_consulta(pergunta)
        consultas = []

        def _rodar_consulta(spot: str, data: str):
            geo = geocoding_tool.invoke(spot)
            if not geo.get("sucesso"):
                return {
                    "spot": spot,
                    "data": data,
                    "erro_geocoding": geo.get("erro") or "Não foi possível localizar esse ponto.",
                }
            previsao = tide_tool.invoke({
                "latitude": geo["latitude"],
                "longitude": geo["longitude"],
                "target_date": data,
            })
            return {
                "spot": spot,
                "local_encontrado": geo.get("local_encontrado"),
                "data": data,
                "previsao": previsao,
            }

        with ThreadPoolExecutor(max_workers=min(6, max(1, len(spots) * len(datas)))) as executor:
            futures = [
                executor.submit(_rodar_consulta, spot, data)
                for spot in spots
                for data in datas
            ]
            for future in futures:
                resultado = future.result()
                if resultado:
                    consultas.append(resultado)

        consultas_validas = [item for item in consultas if "previsao" in item]
        if not consultas_validas:
            spots_falhos = ", ".join(item["spot"] for item in consultas) or (nome_regiao or "o local pedido")
            return (
                f"Não consegui localizar com segurança {spots_falhos} para consultar onda, vento e maré. "
                "Pode me passar o nome da praia com cidade/estado ou um ponto de referência mais próximo?"
            )

        def _tem_dados_essenciais(previsao: dict) -> bool:
            ondas = previsao.get("resumo_ondas", {}) or {}
            vento = previsao.get("resumo_vento", {}) or {}
            mares = previsao.get("tabua_de_mares", []) or []
            tem_mares = any("não disponíveis" not in str(item).lower() and "erro" not in str(item).lower() for item in mares)
            return bool(ondas.get("dados_disponiveis") or vento.get("dados_disponiveis") or tem_mares)

        if not any(_tem_dados_essenciais(item["previsao"]) for item in consultas_validas):
            spots_sem_dados = ", ".join(sorted({item["spot"] for item in consultas_validas}))
            return (
                f"Consegui localizar {spots_sem_dados}, mas não vieram dados suficientes de onda, vento ou maré para responder com segurança. "
                "Quer tentar uma praia vizinha específica ou me mandar outro ponto de referência?"
            )

        consultas = consultas_validas

        if not consultas:
            return None

        consultas_compactas = []
        for item in consultas:
            previsao = item["previsao"]
            consultas_compactas.append({
                "spot": item["spot"],
                "data": item["data"],
                "resumo_ondas": previsao.get("resumo_ondas"),
                "resumo_vento": previsao.get("resumo_vento"),
                "resumo_chuva": previsao.get("resumo_chuva"),
                "janelas_do_dia": previsao.get("janelas_do_dia"),
                "tabua_de_mares": previsao.get("tabua_de_mares"),
            })

        def _pontuacao(item: dict) -> float:
            previsao = item["previsao"]
            ondas = previsao.get("resumo_ondas", {}) or {}
            vento = previsao.get("resumo_vento", {}) or {}
            altura = ondas.get("altura_max_m") or 0
            periodo = ondas.get("periodo_max_s") or 0
            vento_min = vento.get("vento_min_kmh") or 99
            return (altura * 8) + periodo - (vento_min * 0.35)

        def _hora_curta(valor: str | None) -> str:
            if not valor or "T" not in valor:
                return "horário indefinido"
            return valor.split("T", 1)[1][:5]

        def _data_curta(valor: str) -> str:
            data = datetime.date.fromisoformat(valor)
            return data.strftime("%d/%m/%Y")

        def _sintese_dinamica() -> str:
            ordenadas = sorted(consultas, key=_pontuacao, reverse=True)
            melhor = ordenadas[0]
            previsao = melhor["previsao"]
            ondas = previsao.get("resumo_ondas", {}) or {}
            vento = previsao.get("resumo_vento", {}) or {}
            mares = previsao.get("tabua_de_mares", []) or []
            janela = (previsao.get("janelas_do_dia") or [None])[0]

            if len(ordenadas) == 1:
                partes = [
                    f"Consultando {melhor['spot']} para {_data_curta(melhor['data'])}, a condição parece mais favorável entre {_hora_curta(vento.get('janela_vento_mais_fraco'))} e o começo da manhã.",
                    f"As ondas variam de {ondas.get('altura_min_m', 0)}m a {ondas.get('altura_max_m', 0)}m, com período entre {ondas.get('periodo_min_s', 0)}s e {ondas.get('periodo_max_s', 0)}s.",
                    f"O vento mais limpo aparece perto de {_hora_curta(vento.get('janela_vento_mais_fraco'))}, com pico mínimo de {vento.get('vento_min_kmh', 0)} km/h.",
                ]
                if mares:
                    partes.append("Marés do dia: " + "; ".join(mares[:4]) + ".")
                return " ".join(partes)

            top = ordenadas[:3]
            ranking = ", ".join(
                f"{item['spot']} ({_data_curta(item['data'])})"
                for item in top
            )
            partes = [
                f"Consultando os dados em tempo real para {nome_regiao or 'a região pedida'}, o cenário mais promissor aparece em {melhor['spot']} no dia {_data_curta(melhor['data'])}.",
                f"Lá o mar chega a {ondas.get('altura_max_m', 0)}m com período máximo de {ondas.get('periodo_max_s', 0)}s.",
                f"O vento mais favorável aparece perto de {_hora_curta(vento.get('janela_vento_mais_fraco'))}, em torno de {vento.get('vento_min_kmh', 0)} km/h.",
                f"Ranking consultado: {ranking}.",
            ]
            if mares:
                partes.append("Marés da melhor referência: " + "; ".join(mares[:4]) + ".")
            return " ".join(partes)

        prompt = (
            "Você é um especialista em surf do Rio Grande do Norte.\n"
            "Analise os dados consultados e responda em português do Brasil, de forma objetiva, natural e útil.\n"
            "Use somente os dados consultados para sustentar a resposta.\n"
            "Se a pergunta pedir melhor horário, indique a melhor janela com base em ondas, período, vento e maré.\n"
            "Se a pergunta pedir melhor pico, compare os spots consultados e diga qual parece mais promissor.\n"
            "Responda em no máximo 6 frases curtas.\n"
            "Se houver mais de uma data, compare brevemente.\n"
            "Nunca troque uma praia específica por um pico-base ou referência costeira se houver coordenadas para o local pedido.\n"
            "Se a praia ou localidade pedida estiver ambígua ou os dados essenciais não vierem na consulta, diga exatamente o que falta e peça a informação ao usuário.\n\n"
            f"Pergunta do usuário: {pergunta}\n"
            f"Região analisada: {nome_regiao or 'Consulta local'}\n"
            f"Dados consultados: {json.dumps(consultas_compactas, ensure_ascii=False)}\n"
        )
        executor = ThreadPoolExecutor(max_workers=1)
        try:
            future = executor.submit(self.summary_llm.invoke, prompt)
            resposta = future.result(timeout=self.summary_timeout)
            return resposta.content if isinstance(resposta.content, str) else str(resposta.content)
        except TimeoutError:
            print("[AgenteMaritimo] summary_llm timeout, usando síntese dinâmica baseada nos dados consultados")
            future.cancel()
            return _sintese_dinamica()
        finally:
            executor.shutdown(wait=False, cancel_futures=True)

    def ask(self, pergunta: str, chat_history: Iterable[dict] | None = None) -> str:
        inicio = time.perf_counter()
        resposta_regional = self._consultar_regiao_ampla(pergunta)
        if resposta_regional is not None:
            duracao = time.perf_counter() - inicio
            print(f"[AgenteMaritimo] consulta regional em {duracao:.2f}s")
            return resposta_regional

        mensagens = []
        for item in chat_history or []:
            role = item.get("role")
            content = (item.get("content") or "").strip()
            if not content:
                continue
            if role == "user":
                mensagens.append(HumanMessage(content=content))
            elif role == "assistant":
                mensagens.append(AIMessage(content=content))

        resposta = self.executor.invoke({
            "input": pergunta.strip(),
            "chat_history": mensagens[-4:],
        })
        duracao = time.perf_counter() - inicio
        print(f"[AgenteMaritimo] resposta gerada em {duracao:.2f}s")
        return resposta["output"]

import os
import requests
import datetime
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta # Importamos apenas o timedelta separadamente
from functools import lru_cache
from typing import Optional, Union

from langchain_core.tools import tool

REQUEST_TIMEOUT = (4, 10)
SESSION = requests.Session()


def _resolver_data_alvo(target_date: Optional[str]) -> datetime.date:
    hoje = datetime.date.today()

    if not target_date:
        return hoje

    texto = target_date.strip().lower()
    if texto == "hoje":
        return hoje
    if texto in {"amanha", "amanhã"}:
        return hoje + timedelta(days=1)
    if texto in {"ontem"}:
        return hoje - timedelta(days=1)

    try:
        return datetime.date.fromisoformat(target_date)
    except ValueError:
        pass

    for formato in ("%d/%m/%Y", "%d-%m-%Y"):
        try:
            return datetime.datetime.strptime(target_date, formato).date()
        except ValueError:
            continue

    raise ValueError(
        "target_date deve ser uma data no formato YYYY-MM-DD, DD/MM/YYYY, 'hoje' ou 'amanhã'."
    )


def _resumir_ondas(condicoes: dict) -> dict:
    alturas = condicoes.get("wave_height", []) or []
    periodos = condicoes.get("wave_period", []) or []
    direcoes = condicoes.get("wave_direction", []) or []
    horarios = condicoes.get("time", []) or []

    if not alturas or not horarios:
        return {"dados_disponiveis": False}

    registros_validos = [
        (i, altura)
        for i, altura in enumerate(alturas)
        if altura is not None and i < len(horarios)
    ]
    if not registros_validos:
        return {"dados_disponiveis": False}

    indice_melhor, melhor_altura = max(registros_validos, key=lambda item: item[1])
    alturas_validas = [altura for _, altura in registros_validos]
    periodos_validos = [p for p in periodos if p is not None]
    direcoes_validas = [d for d in direcoes if d is not None]

    return {
        "dados_disponiveis": True,
        "altura_min_m": round(min(alturas_validas), 2),
        "altura_max_m": round(max(alturas_validas), 2),
        "periodo_min_s": round(min(periodos_validos), 2) if periodos_validos else None,
        "periodo_max_s": round(max(periodos_validos), 2) if periodos_validos else None,
        "direcao_predominante_graus": round(sum(direcoes_validas) / len(direcoes_validas)) if direcoes_validas else None,
        "melhor_janela_horario": horarios[indice_melhor],
        "melhor_janela_altura_m": round(melhor_altura, 2),
        "melhor_janela_periodo_s": round(periodos[indice_melhor], 2)
        if indice_melhor < len(periodos) and periodos[indice_melhor] is not None
        else None,
    }


def _resumir_vento(condicoes: dict) -> dict:
    velocidades = condicoes.get("wind_speed_10m", []) or []
    direcoes = condicoes.get("wind_direction_10m", []) or []
    horarios = condicoes.get("time", []) or []

    registros_validos = [
        (i, velocidade)
        for i, velocidade in enumerate(velocidades)
        if velocidade is not None and i < len(horarios)
    ]
    if not registros_validos:
        return {"dados_disponiveis": False}

    indice_melhor, menor_vento = min(registros_validos, key=lambda item: item[1])
    indice_pior, maior_vento = max(registros_validos, key=lambda item: item[1])
    direcoes_validas = [d for d in direcoes if d is not None]

    return {
        "dados_disponiveis": True,
        "vento_min_kmh": round(menor_vento, 1),
        "vento_max_kmh": round(maior_vento, 1),
        "direcao_predominante_graus": round(sum(direcoes_validas) / len(direcoes_validas)) if direcoes_validas else None,
        "janela_vento_mais_fraco": horarios[indice_melhor],
        "janela_vento_mais_forte": horarios[indice_pior],
    }


def _resumir_chuva(condicoes: dict) -> dict:
    chuva = [v for v in (condicoes.get("precipitation", []) or []) if v is not None]
    if not chuva:
        return {"dados_disponiveis": False}
    return {
        "dados_disponiveis": True,
        "chuva_total_mm": round(sum(chuva), 2),
        "chuva_max_hora_mm": round(max(chuva), 2),
    }


def _destacar_janelas(condicoes: dict) -> list[dict]:
    horarios = condicoes.get("time", []) or []
    alturas = condicoes.get("wave_height", []) or []
    periodos = condicoes.get("wave_period", []) or []
    ventos = condicoes.get("wind_speed_10m", []) or []

    destaques = []
    for indice in (6, 9, 12, 15, 18):
        if indice >= len(horarios):
            continue
        altura = alturas[indice] if indice < len(alturas) else None
        periodo = periodos[indice] if indice < len(periodos) else None
        vento = ventos[indice] if indice < len(ventos) else None
        destaques.append({
            "horario": horarios[indice],
            "onda_m": round(altura, 2) if altura is not None else None,
            "periodo_s": round(periodo, 2) if periodo is not None else None,
            "vento_kmh": round(vento, 1) if vento is not None else None,
        })
    return destaques


@lru_cache(maxsize=256)
def _buscar_ondas(latitude: float, longitude: float, data_alvo_str: str) -> dict:
    url_ondas = "https://marine-api.open-meteo.com/v1/marine"
    params_ondas = {
        "latitude": latitude,
        "longitude": longitude,
        "hourly": "wave_height,wave_period,wave_direction",
        "timezone": "auto",
        "start_date": data_alvo_str,
        "end_date": data_alvo_str,
    }
    resp_ondas = SESSION.get(url_ondas, params=params_ondas, timeout=REQUEST_TIMEOUT)
    resp_ondas.raise_for_status()
    return resp_ondas.json().get("hourly", {})


@lru_cache(maxsize=256)
def _buscar_clima(latitude: float, longitude: float, data_alvo_str: str) -> dict:
    url_clima = "https://api.open-meteo.com/v1/forecast"
    params_clima = {
        "latitude": latitude,
        "longitude": longitude,
        "hourly": "wind_speed_10m,wind_direction_10m,precipitation",
        "timezone": "auto",
        "start_date": data_alvo_str,
        "end_date": data_alvo_str,
    }
    resp_clima = SESSION.get(url_clima, params=params_clima, timeout=REQUEST_TIMEOUT)
    resp_clima.raise_for_status()
    return resp_clima.json().get("hourly", {})


@lru_cache(maxsize=256)
def _buscar_mares(latitude: float, longitude: float, data_alvo_str: str, chave_worldtides: str | None) -> tuple[str, ...]:
    url_mares = "https://www.worldtides.info/api/v3"
    params_mares = {
        "lat": latitude,
        "lon": longitude,
        "key": chave_worldtides,
        "date": data_alvo_str,
        "days": 1,
        "extremes": True,
        "localtime": True,
    }
    resp_mares = SESSION.get(url_mares, params=params_mares, timeout=REQUEST_TIMEOUT)
    resp_mares.raise_for_status()
    dados_mares = resp_mares.json()

    if "extremes" not in dados_mares:
        return ("Dados de marés não disponíveis para esta localização.",)

    tabua_mares = []
    for extremo in dados_mares["extremes"]:
        tipo = "Alta" if extremo["type"] == "High" else "Baixa"
        hora_local_str = extremo.get("date", "")
        if hora_local_str:
            hora_formatada = datetime.datetime.fromisoformat(
                hora_local_str.replace("Z", "+00:00")
            ).strftime("%H:%M")
        else:
            hora_utc = datetime.datetime.fromtimestamp(
                extremo["dt"], tz=datetime.timezone.utc
            )
            hora_formatada = hora_utc.strftime("%H:%M")
        altura = round(extremo["height"], 2)
        tabua_mares.append(f"Maré {tipo} às {hora_formatada} ({altura}m)")
    return tuple(tabua_mares)


@tool
def tide_tool(
    latitude: Union[float, str],
    longitude: Union[float, str],
    target_date: Optional[str] = None,
) -> dict:
    """
    Consulta condições marítimas completas e gratuitas: ondas (altura, período, direção), vento (velocidade, direção), precipitação (chuva) e horários exatos da tábua de marés.
    Se o usuário pedir amanhã ou uma data específica, informe target_date no formato YYYY-MM-DD.
    """
    data_alvo = _resolver_data_alvo(target_date)
    data_alvo_str = data_alvo.isoformat()
    latitude = float(latitude)
    longitude = float(longitude)
    dados_ondas_filtrados = {}
    dados_clima_filtrados = {}
    chave_worldtides = os.getenv("WORLDTIDES_API_KEY")  # Obtenha uma key gratuita em https://www.worldtides.info/
    tabua_mares = []

    with ThreadPoolExecutor(max_workers=3) as executor:
        futuro_ondas = executor.submit(_buscar_ondas, latitude, longitude, data_alvo_str)
        futuro_clima = executor.submit(_buscar_clima, latitude, longitude, data_alvo_str)
        futuro_mares = executor.submit(_buscar_mares, latitude, longitude, data_alvo_str, chave_worldtides)

        try:
            for chave, valores in futuro_ondas.result().items():
                dados_ondas_filtrados[chave] = valores
        except Exception as e:
            print(f"Aviso: Falha ao buscar ondas: {e}")

        try:
            for chave, valores in futuro_clima.result().items():
                dados_clima_filtrados[chave] = valores
        except Exception as e:
            print(f"Aviso: Falha ao buscar clima: {e}")

        try:
            tabua_mares = list(futuro_mares.result())
        except Exception as e:
            tabua_mares.append(f"Erro ao consultar tábua de marés: {e}")

    condicoes_completas = {**dados_ondas_filtrados, **dados_clima_filtrados}
    return {
        "sucesso": True,
        "data_consultada": data_alvo_str,
        "resumo_ondas": _resumir_ondas(condicoes_completas),
        "resumo_vento": _resumir_vento(condicoes_completas),
        "resumo_chuva": _resumir_chuva(condicoes_completas),
        "janelas_do_dia": _destacar_janelas(condicoes_completas),
        "tabua_de_mares": tabua_mares
    }

# Teste isolado para debuggar a API
if __name__ == "__main__":
    from dotenv import load_dotenv
    import json

    # Carrega o .env localmente para o teste
    load_dotenv()

    print("Testando a conexão com as APIs gratuitas em Ponta Negra...\n")
    # Coordenadas de Ponta Negra
    resultado = tide_tool.invoke({
        "latitude": -5.8736046,
        "longitude": -35.1766302,
        "target_date": "amanhã",
    })

    # Imprime o dicionário formatado para facilitar a leitura do erro
    print(json.dumps(resultado, indent=2, ensure_ascii=False))

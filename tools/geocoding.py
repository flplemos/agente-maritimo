from functools import lru_cache
import unicodedata

from langchain_core.tools import tool
from geopy.geocoders import Nominatim

SURF_ALIASES = {
    "rio grande do norte": "Ponta Negra, Natal, Rio Grande do Norte",
    "rn": "Ponta Negra, Natal, Rio Grande do Norte",
}

SURF_COORDINATES = {
    "rio doce": {
        "local_encontrado": "Rio Doce, Praia de Búzios, Nísia Floresta, Rio Grande do Norte",
        "latitude": -6.0185,
        "longitude": -35.1097,
    },
    "rio doce buzios": {
        "local_encontrado": "Rio Doce, Praia de Búzios, Nísia Floresta, Rio Grande do Norte",
        "latitude": -6.0185,
        "longitude": -35.1097,
    },
    "rio doce buzios nisia floresta rio grande do norte": {
        "local_encontrado": "Rio Doce, Praia de Búzios, Nísia Floresta, Rio Grande do Norte",
        "latitude": -6.0185,
        "longitude": -35.1097,
    },
    "buzios": {
        "local_encontrado": "Praia de Búzios, Nísia Floresta, Rio Grande do Norte",
        "latitude": -6.0185,
        "longitude": -35.1097,
    },
    "buzios nisia floresta rio grande do norte": {
        "local_encontrado": "Praia de Búzios, Nísia Floresta, Rio Grande do Norte",
        "latitude": -6.0185,
        "longitude": -35.1097,
    },
    "praia de buzios": {
        "local_encontrado": "Praia de Búzios, Nísia Floresta, Rio Grande do Norte",
        "latitude": -6.0185,
        "longitude": -35.1097,
    },
}

GEOCODER = Nominatim(user_agent="agente_maritimo_senac", timeout=5)


def _normalizar_texto(valor: str) -> str:
    texto = unicodedata.normalize("NFKD", valor.strip().lower())
    texto = "".join(caractere for caractere in texto if not unicodedata.combining(caractere))
    return " ".join(texto.replace(",", " ").split())


@lru_cache(maxsize=128)
def _buscar_local(consulta: str):
    return GEOCODER.geocode(consulta, timeout=5)


@tool
def geocoding_tool(nome_local: str) -> dict:
    """
    Converte o nome de uma praia, cidade ou localidade em coordenadas geográficas (latitude e longitude).
    Use esta ferramenta SEMPRE que o usuário mencionar um local e você precisar das coordenadas para consultar o clima ou a maré.
    """
    chave_local = _normalizar_texto(nome_local)
    coordenadas_conhecidas = SURF_COORDINATES.get(chave_local)
    if coordenadas_conhecidas:
        return {
            "sucesso": True,
            "local_encontrado": coordenadas_conhecidas["local_encontrado"],
            "local_consultado": nome_local,
            "latitude": coordenadas_conhecidas["latitude"],
            "longitude": coordenadas_conhecidas["longitude"],
            "fonte": "coordenadas_locais",
        }

    # Inicializa o geolocalizador do OpenStreetMap. 
    # O user_agent precisa ser um nome único para não ser bloqueado por spam.
    consulta = SURF_ALIASES.get(nome_local.strip().lower(), nome_local)
    
    try:
        # Tenta encontrar o local
        location = _buscar_local(consulta)
        
        if location:
            return {
                "sucesso": True,
                "local_encontrado": location.address,
                "local_consultado": consulta,
                "latitude": location.latitude,
                "longitude": location.longitude
            }
        else:
            return {
                "sucesso": False,
                "erro": f"Não foi possível encontrar as coordenadas para '{nome_local}'."
            }
    except Exception as e:
        return {
            "sucesso": False,
            "erro": str(e)
        }


    # Teste isolado da ferramenta
if __name__ == "__main__":
    print("Testando a Geocoding Tool...\n")
    
    # Repare que chamamos .invoke() pois ela é uma ferramenta LangChain, não apenas uma função comum
    resultado = geocoding_tool.invoke("Praia de Ponta Negra, Natal")
    
    print(resultado)

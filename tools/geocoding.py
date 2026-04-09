from functools import lru_cache

from langchain_core.tools import tool
from geopy.geocoders import Nominatim

SURF_ALIASES = {
    "rio grande do norte": "Ponta Negra, Natal, Rio Grande do Norte",
    "rn": "Ponta Negra, Natal, Rio Grande do Norte",
}

GEOCODER = Nominatim(user_agent="agente_maritimo_senac", timeout=5)


@lru_cache(maxsize=128)
def _buscar_local(consulta: str):
    return GEOCODER.geocode(consulta, timeout=5)


@tool
def geocoding_tool(nome_local: str) -> dict:
    """
    Converte o nome de uma praia, cidade ou localidade em coordenadas geográficas (latitude e longitude).
    Use esta ferramenta SEMPRE que o usuário mencionar um local e você precisar das coordenadas para consultar o clima ou a maré.
    """
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

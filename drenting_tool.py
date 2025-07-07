import os
from typing import List, Dict
from pymongo import MongoClient
import openai
from dotenv import load_dotenv

load_dotenv()

# Configuración de claves y clientes
openai.api_key = os.getenv("OPENAI_API_KEY")
MONGO_URI = os.getenv("MONGO_URI")

mongo_client = MongoClient(MONGO_URI)
db = mongo_client["vehiculos"]
collection = db["vehiculos"]

# Obtener embedding
def get_embedding(text: str) -> List[float]:
    response = openai.embeddings.create(input=text, model="text-embedding-3-small")
    return response.data[0].embedding

# Buscar vehículos usando vector search + filtros
def buscar_vehiculos(consulta: str, limite: int = 5, filtro_tipo: str = None,
                     filtro_color: str = None, filtro_plazas: int = None,
                     filtro_traccion: str = None, filtro_precio_max: int = None,
                     filtro_precio_min: int = None, filtro_duracion: int = None,
                     filtro_kms: int = None, filtro_transmision: str = None,
                     filtro_combustible: str = None, filtro_consumo_max: float = None,
                     filtro_consumo_min: float = None, filtro_año_min: int = None) -> List[Dict]:
    embedding = get_embedding(consulta)
    pipeline = []

    match_conditions = {}

    if filtro_tipo:
        match_conditions["tipo"] = {"$regex": filtro_tipo, "$options": "i"}
    if filtro_color:
        match_conditions["color"] = {"$regex": filtro_color, "$options": "i"}
    if filtro_plazas:
        match_conditions["plazas"] = filtro_plazas
    if filtro_traccion:
        match_conditions["tracción"] = {"$regex": filtro_traccion, "$options": "i"}
    if filtro_transmision:
        match_conditions["transmisión"] = {"$regex": filtro_transmision, "$options": "i"}
    if filtro_combustible:
        match_conditions["combustible"] = {"$regex": filtro_combustible, "$options": "i"}
    if filtro_año_min:
        match_conditions["año"] = {"$gte": filtro_año_min}
    if filtro_consumo_max or filtro_consumo_min:
        consumo_filter = {}
        if filtro_consumo_max:
            consumo_filter["$lte"] = filtro_consumo_max
        if filtro_consumo_min:
            consumo_filter["$gte"] = filtro_consumo_min
        match_conditions["consumo_litros"] = consumo_filter  # este campo debe existir en documentos

    if match_conditions:
        pipeline.append({"$match": match_conditions})

    pipeline.append({
        "$vectorSearch": {
            "queryVector": embedding,
            "path": "embedding",
            "numCandidates": 100,
            "limit": limite,
            "index": "vector_index"
        }
    })

    pipeline.append({
        "$project": {
            "_id": 0,
            "nombre": 1,
            "url": 1,
            "precios": 1
        }
    })

    results = list(collection.aggregate(pipeline))

    processed_results = []
    for veh in results:
        precios = veh.get("precios", [])

        if filtro_duracion:
            precios = [p for p in precios if p["duracion"] == filtro_duracion]
        if filtro_kms:
            precios = [p for p in precios if p["kms"] == filtro_kms]

        if not precios:
            continue

        precios_validos = []
        for p in precios:
            if filtro_precio_min and p["importe"] < filtro_precio_min:
                continue
            if filtro_precio_max and p["importe"] > filtro_precio_max:
                continue
            precios_validos.append(p)

        if not precios_validos:
            continue

        precio_min = min(precios_validos, key=lambda p: p["importe"])

        vehiculo_info = {
            "nombre": veh["nombre"],
            "url": veh["url"],
            "precio": precio_min["importe"],
            "duracion": precio_min["duracion"],
            "kms": precio_min["kms"]
        }
        processed_results.append(vehiculo_info)

    processed_results.sort(key=lambda x: x["precio"])

    return processed_results[:limite]



# Formato simple para mostrar vehículos
def format_vehicle_summary(vehicle: Dict) -> str:
    return f"- {vehicle.get('nombre', 'N/A')} | {vehicle.get('precio', 'N/A')} | {vehicle.get('url', 'N/A')}"

# Función para tool call
def handle_buscar_vehiculos(consulta, limite=5, filtro_tipo=None, filtro_color=None,
                            filtro_plazas=None, filtro_traccion=None, filtro_precio_max=None,
                            filtro_precio_min=None, filtro_duracion=None, filtro_kms=None,
                            filtro_transmision=None, filtro_combustible=None,
                            filtro_consumo_max=None, filtro_consumo_min=None,
                            filtro_año_min=None):
    try:
        vehicles = buscar_vehiculos(
            consulta, limite, filtro_tipo, filtro_color,
            filtro_plazas, filtro_traccion, filtro_precio_max, filtro_precio_min,
            filtro_duracion, filtro_kms, filtro_transmision, filtro_combustible,
            filtro_consumo_max, filtro_consumo_min, filtro_año_min
        )
        if not vehicles:
            return "No se encontraron vehículos que coincidan con tu consulta."

        return "\n".join(
            f"- {v['nombre']} | {v['precio']}€/mes ({v['duracion']} meses / {v['kms']} km/año) | {v['url']}"
            for v in vehicles
        )

    except Exception as e:
        return f"❌ Error procesando la consulta: {e}"


if __name__ == "__main__":
    print("Este archivo está diseñado para funcionar como Tool Function de Assistant API.")

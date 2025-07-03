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
    response = openai.embeddings.create(input=text, model="text-embedding-ada-002")
    return response.data[0].embedding

# Buscar vehículos usando vector search + filtros
def buscar_vehiculos(consulta: str, limite: int = 5, filtro_tipo: str = None,
                     filtro_color: str = None, filtro_plazas: int = None,
                     filtro_traccion: str = None, filtro_precio_max: int = None) -> List[Dict]:
    embedding = get_embedding(consulta)
    pipeline = []

    match_conditions = {}

    if filtro_tipo:
        match_conditions["tipo"] = {"$regex": filtro_tipo, "$options": "i"}
    if filtro_color:
        match_conditions["color"] = {"$regex": filtro_color, "$options": "i"}
    if filtro_plazas:
        match_conditions["plazas"] = str(filtro_plazas)
    if filtro_traccion:
        match_conditions["tracción"] = {"$regex": filtro_traccion, "$options": "i"}
    if filtro_precio_max:
        match_conditions["precio"] = {"$regex": r"\d+"}  # Puedes añadir parsing numérico si quieres filtrar numéricamente

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
            "precio": 1,
            "url": 1
        }
    })

    results = list(collection.aggregate(pipeline))
    return results

# Formato simple para mostrar vehículos
def format_vehicle_summary(vehicle: Dict) -> str:
    return f"- {vehicle.get('nombre', 'N/A')} | {vehicle.get('precio', 'N/A')} | {vehicle.get('url', 'N/A')}"

# Función para tool call
def handle_buscar_vehiculos(consulta, limite=5, filtro_tipo=None, filtro_color=None,
                            filtro_plazas=None, filtro_traccion=None, filtro_precio_max=None):
    try:
        vehicles = buscar_vehiculos(
            consulta, limite, filtro_tipo, filtro_color,
            filtro_plazas, filtro_traccion, filtro_precio_max
        )
        if not vehicles:
            return "No se encontraron vehículos que coincidan con tu consulta."

        return "\n".join(format_vehicle_summary(v) for v in vehicles)

    except Exception as e:
        return f"❌ Error procesando la consulta: {e}"

if __name__ == "__main__":
    print("Este archivo está diseñado para funcionar como Tool Function de Assistant API.")

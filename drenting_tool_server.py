from fastapi import FastAPI, Request
from drenting_tool import handle_buscar_vehiculos

app = FastAPI()

@app.post("/buscar_vehiculos")
async def buscar_vehiculos_endpoint(request: Request):
    body = await request.json()
    params = body.get("arguments", {})

    response = handle_buscar_vehiculos(
        consulta=params.get("consulta"),
        limite=params.get("limite", 5),
        filtro_tipo=params.get("filtro_tipo"),
        filtro_color=params.get("filtro_color"),
        filtro_plazas=params.get("filtro_plazas"),
        filtro_traccion=params.get("filtro_traccion"),
        filtro_precio_max=params.get("filtro_precio_max"),
        filtro_precio_min=params.get("filtro_precio_min"),
        filtro_duracion=params.get("filtro_duracion"),
        filtro_kms=params.get("filtro_kms"),
        filtro_transmision=params.get("filtro_transmision"),
        filtro_combustible=params.get("filtro_combustible"),
        filtro_consumo_max=params.get("filtro_consumo_max"),
        filtro_consumo_min=params.get("filtro_consumo_min"),
        filtro_año_min=params.get("filtro_año_min")
    )
    return {"output": response}

import os
import json
import uuid
import requests
from datetime import datetime
from qdrant_client import QdrantClient
from qdrant_client.models import Distance, VectorParams, PointStruct

OLLAMA_URL = os.getenv("OLLAMA_URL", "http://host.docker.internal:11434")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "phi3:latest")
OLLAMA_EMBED_MODEL = os.getenv("OLLAMA_EMBED_MODEL", "nomic-embed-text")
QDRANT_URL = os.getenv("QDRANT_URL", "http://qdrant:6333")
COLLECTION_NAME = "noc_memoria"

qdrant = QdrantClient(url=QDRANT_URL)


def inicializar_qdrant():
    """Crea la colección vectorial (768 dimensiones para nomic-embed-text) si no existe."""
    colecciones = [c.name for c in qdrant.get_collections().collections]
    if COLLECTION_NAME not in colecciones:
        qdrant.create_collection(
            collection_name=COLLECTION_NAME,
            vectors_config=VectorParams(size=768, distance=Distance.COSINE),
        )


def get_embedding(texto: str) -> list:
    r = requests.post(
        f"{OLLAMA_URL}/api/embeddings",
        json={"model": OLLAMA_EMBED_MODEL, "prompt": texto},
        timeout=30,
    )
    r.raise_for_status()
    return r.json()["embedding"]


def guardar_memoria(texto: str, tipo: str = "ticket", etiqueta: str = "general"):
    """Guarda una resolución de ticket, nota de usuario o informe en Qdrant."""
    inicializar_qdrant()
    vector = get_embedding(texto)
    punto = PointStruct(
        id=str(uuid.uuid4()),
        vector=vector,
        payload={
            "texto": texto,
            "tipo": tipo,
            "etiqueta": etiqueta,
            "fecha": datetime.now().isoformat(timespec="minutes"),
        },
    )
    qdrant.upsert(collection_name=COLLECTION_NAME, points=[punto])


def buscar_memoria(consulta: str, limite: int = 4) -> list:
    """Busca notas o resoluciones previas por similitud semántica."""
    inicializar_qdrant()
    vector = get_embedding(consulta)
    resultados = qdrant.query_points(
        collection_name=COLLECTION_NAME,
        query=vector,
        limit=limite,
    ).points
    return [r.payload for r in resultados]


def extraer_datos_migracion(texto_correo: str) -> dict:
    """Pide a Ollama extraer datos estructurados de un correo del proveedor en formato JSON."""
    prompt = f"""Eres un asistente técnico de NOC. Extrae los datos del siguiente correo de migración de enlaces.
Devuelve ÚNICAMENTE un objeto JSON válido con estas claves exactas (usa null si un dato no aparece):
{{
  "codigo_sucursal": "código corto o sigla en mayúsculas, ej: CONCE-01",
  "nombre_sucursal": "nombre de la sucursal o ciudad",
  "fase_actual": "Factibilidad Técnica | Instalación FO | Pruebas | Producción",
  "fecha_visita": "YYYY-MM-DD HH:MM o null",
  "estado_visita": "Tentativa | Confirmada | Realizada",
  "observaciones": "resumen breve de requisitos, bloqueos o notas"
}}

Correo:
{texto_correo}
"""
    r = requests.post(
        f"{OLLAMA_URL}/api/generate",
        json={
            "model": OLLAMA_MODEL,
            "prompt": prompt,
            "format": "json",
            "stream": False,
        },
        timeout=60,
    )
    r.raise_for_status()
    raw = r.json().get("response", "{}").strip()
    return json.loads(raw)


def responder_asistente(pregunta: str, contexto_sql: str, contexto_qdrant: list) -> str:
    """Responde combinando la memoria estructurada (Postgres) y la semántica (Qdrant)."""
    notas = "\n".join(
        [f"- [{m.get('fecha')}] ({m.get('tipo')}): {m.get('texto')}" for m in contexto_qdrant]
    ) or "Sin antecedentes previos en memoria."

    prompt = f"""Eres la secretaria técnica del NOC de FONASA. Responde de forma directa, clara y útil en español.
Usa únicamente la información disponible abajo; si falta un dato, dilo claramente sin inventarlo.

=== DATOS ESTRUCTURADOS (PostgreSQL) ===
{contexto_sql}

=== EXPERIENCIA Y NOTAS PREVIAS (Qdrant) ===
{notas}

=== CONSULTA DEL USUARIO ===
{pregunta}
"""
    r = requests.post(
        f"{OLLAMA_URL}/api/generate",
        json={"model": OLLAMA_MODEL, "prompt": prompt, "stream": False},
        timeout=90,
    )
    r.raise_for_status()
    return r.json().get("response", "").strip()
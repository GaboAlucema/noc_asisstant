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


def extraer_datos_migracion(texto_correo: str) -> list:
    """Extrae una o múltiples sucursales desde un correo o tabla pegada."""
    prompt = f"""Eres un asistente técnico del NOC de FONASA. Analiza el siguiente texto o tabla de correo.
Puede contener UNA o VARIAS sucursales (una por línea o párrafo). Extrae TODAS las sucursales mencionadas.

REGLAS ESTRICTAS:
1. El "codigo_sucursal" es el Código MINSAL, que tiene formato de 7 u 8 dígitos, un guion y 3 dígitos (ejemplos: 0403601-001, 13101001-006, 1011810-118).
2. Si aparece dirección, nombre de contacto o teléfono de la sucursal, colócalos en sus campos respectivos.
3. Si se mencionan códigos de servicio de enlaces, switches, equipos o anexos telefónicos, guárdalos en "datos_tecnicos".
4. Convierte fechas como "16-nov-26" al formato "2026-11-16".

Devuelve ÚNICAMENTE un JSON válido con esta estructura exacta:
{{
  "sucursales": [
    {{
      "codigo_sucursal": "ej: 0403601-001",
      "nombre_sucursal": "nombre completo de la sucursal",
      "direccion": "dirección física o null",
      "contacto_nombre": "nombre del contacto local o null",
      "contacto_fono": "teléfono o anexo o null",
      "fase_actual": "Factibilidad Técnica | Instalación FO | Pruebas | Producción",
      "fecha_visita": "YYYY-MM-DD o YYYY-MM-DD HH:MM o null",
      "estado_visita": "Pendiente | Tentativa | Confirmada | Realizada",
      "observaciones": "estado operativo, requisitos de acceso o bloqueos",
      "datos_tecnicos": "códigos de servicio, switches, enlaces o anexos mencionados (o null)"
    }}
  ]
}}

Texto a analizar:
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
        timeout=120,
    )
    r.raise_for_status()
    data = json.loads(r.json().get("response", "{}").strip())

    # Normaliza la salida para asegurar SIEMPRE una lista de diccionarios
    if isinstance(data, list):
        return data
    if isinstance(data, dict):
        # Si existe la clave "sucursales"
        if "sucursales" in data:
            val = data["sucursales"]
            return val if isinstance(val, list) else [val]
        # Si el modelo inventó otra clave que contiene una lista (ej: "data", "items")
        for v in data.values():
            if isinstance(v, list) and v and isinstance(v[0], dict):
                return v
        # Si devolvió un solo objeto directo
        return [data]
    return []


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
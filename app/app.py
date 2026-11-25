import os
import requests
import psycopg2
import streamlit as st
from qdrant_client import QdrantClient

st.set_page_config(page_title="NOC Assistant", layout="wide")
st.title("NOC Assistant — Verificación de Entorno")

col1, col2, col3 = st.columns(3)

# 1. Test PostgreSQL
with col1:
    try:
        conn = psycopg2.connect(os.getenv("DATABASE_URL"))
        conn.close()
        st.success("PostgreSQL: Conectado")
    except Exception as e:
        st.error(f"PostgreSQL Error: {e}")

# 2. Test Qdrant
with col2:
    try:
        client = QdrantClient(url=os.getenv("QDRANT_URL"))
        client.get_collections()
        st.success("Qdrant: Conectado")
    except Exception as e:
        st.error(f"Qdrant Error: {e}")

# 3. Test Ollama Local
with col3:
    try:
        r = requests.get(f"{os.getenv('OLLAMA_URL')}/api/tags", timeout=3)
        if r.status_code == 200:
            modelos = [m["name"] for m in r.json().get("models", [])]
            st.success(f"Ollama: Conectado ({len(modelos)} modelos)")
        else:
            st.warning("Ollama respondió con error")
    except Exception as e:
        st.error(f"Ollama Error: {e}")
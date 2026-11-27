import time
import sys
import os

sys.path.append(os.path.abspath("app"))
import ai_engine

TEXTO_PRUEBA = """
Fecha VISITA	Horario autorizado	Estado Visita	Código MINSAL	Región	Dependencia Administrativa	Sitio	Ciudad / Comuna	Dirección	Contacto en Sitio	Número Telefónico	Observacion
16-nov-26		Realizada	0403601-001	4	FONASA	FONASA CENTRO DE ATENCIÓN COQUIMBO	COQUIMBO	ALDUNATE 1354	Susana Olivares Lopez	51-2333120	Sucursal Operativa
17-nov-26		Realizada	0404304-004	4	FONASA	FONASA ILLAPEL	ILLAPEL	CONSTITUCIÓN 132	Ximena Cortes Bustamante	53-2663140	Sucursal Operativa
"""

MODELOS = ["phi3:latest", "qwen2.5:3b"]  # Agrega "qwen2.5:7b" si lo descargas

for modelo in MODELOS:
    ai_engine.OLLAMA_MODEL = modelo
    inicio = time.perf_counter()
    try:
        res = ai_engine.extraer_datos_migracion(TEXTO_PRUEBA)
        duracion = time.perf_counter() - inicio
        print(f"\n=== MODELO: {modelo} ({duracion:.2f}s) | Filas: {len(res)} ===")
        for fila in res:
            print(f"  - {fila['codigo_sucursal']} | Dir: {fila['direccion']} | Fecha: {fila['fecha_visita']} | Estado: {fila['estado_visita']} | Obs: {fila['observaciones']}")
    except Exception as e:
        print(f"\n=== MODELO: {modelo} FALLÓ: {e} ===")
import os
import psycopg2
from psycopg2.extras import RealDictCursor

DATABASE_URL = os.getenv("DATABASE_URL")


def get_conn():
    return psycopg2.connect(DATABASE_URL, cursor_factory=RealDictCursor)


# --- SUCURSALES ---
def upsert_sucursal(codigo, nombre, direccion=None, ip_enlace=None,
                    contacto_nombre=None, contacto_fono=None, notas_extra=None):
    """Inserta una sucursal o actualiza solo los campos nuevos si el código ya existe."""
    sql = """
        INSERT INTO sucursales (codigo, nombre, direccion, ip_enlace, contacto_nombre, contacto_fono, notas_extra)
        VALUES (%s, %s, %s, %s, %s, %s, %s)
        ON CONFLICT (codigo) DO UPDATE SET
            nombre = COALESCE(EXCLUDED.nombre, sucursales.nombre),
            direccion = COALESCE(EXCLUDED.direccion, sucursales.direccion),
            ip_enlace = COALESCE(EXCLUDED.ip_enlace, sucursales.ip_enlace),
            contacto_nombre = COALESCE(EXCLUDED.contacto_nombre, sucursales.contacto_nombre),
            contacto_fono = COALESCE(EXCLUDED.contacto_fono, sucursales.contacto_fono),
            notas_extra = COALESCE(EXCLUDED.notas_extra, sucursales.notas_extra),
            actualizado_en = CURRENT_TIMESTAMP
        RETURNING id;
    """
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, (codigo.upper().strip(), nombre, direccion, ip_enlace,
                              contacto_nombre, contacto_fono, notas_extra))
            return cur.fetchone()["id"]


def buscar_sucursales(termino=""):
    with get_conn() as conn:
        with conn.cursor() as cur:
            if termino:
                like = f"%{termino}%"
                cur.execute("""
                    SELECT * FROM sucursales
                    WHERE nombre ILIKE %s OR codigo ILIKE %s OR contacto_nombre ILIKE %s
                    ORDER BY nombre;
                """, (like, like, like))
            else:
                cur.execute("SELECT * FROM sucursales ORDER BY nombre;")
            return cur.fetchall()


# --- MIGRACIÓN NACIONAL ---
def registrar_avance_migracion(codigo_sucursal, nombre_sucursal, fase_actual=None,
                               fecha_visita=None, estado_visita="Tentativa", observaciones=None,
                               direccion=None, contacto_nombre=None, contacto_fono=None,
                               notas_extra=None):
    """Asegura que la sucursal exista (actualizando contacto/dirección/técnicos) y registra su avance."""
    sucursal_id = upsert_sucursal(
        codigo=codigo_sucursal,
        nombre=nombre_sucursal,
        direccion=direccion,
        contacto_nombre=contacto_nombre,
        contacto_fono=contacto_fono,
        notas_extra=notas_extra
    )

    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT id FROM migracion_nacional WHERE sucursal_id = %s;", (sucursal_id,))
            existente = cur.fetchone()

            if existente:
                cur.execute("""
                    UPDATE migracion_nacional SET
                        fase_actual = COALESCE(%s, fase_actual),
                        fecha_visita = COALESCE(%s, fecha_visita),
                        estado_visita = COALESCE(%s, estado_visita),
                        observaciones = COALESCE(%s, observaciones),
                        actualizado_en = CURRENT_TIMESTAMP
                    WHERE sucursal_id = %s;
                """, (fase_actual, fecha_visita, estado_visita, observaciones, sucursal_id))
            else:
                cur.execute("""
                    INSERT INTO migracion_nacional (sucursal_id, fase_actual, fecha_visita, estado_visita, observaciones)
                    VALUES (%s, %s, %s, %s, %s);
                """, (sucursal_id, fase_actual or "Factibilidad Técnica",
                      fecha_visita, estado_visita, observaciones))


def get_migracion():
    sql = """
        SELECT m.id, s.codigo, s.nombre AS sucursal, m.fase_actual,
               m.fecha_visita, m.estado_visita, m.observaciones,
               s.contacto_nombre, s.contacto_fono, m.actualizado_en
        FROM migracion_nacional m
        JOIN sucursales s ON m.sucursal_id = s.id
        ORDER BY m.fecha_visita ASC NULLS LAST, s.nombre ASC;
    """
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(sql)
            return cur.fetchall()


# --- TAREAS (NOC Y PERSONALES) ---
def agregar_tarea(titulo, categoria="NOC", descripcion="", fecha_limite=None):
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                INSERT INTO tareas (categoria, titulo, descripcion, fecha_limite)
                VALUES (%s, %s, %s, %s) RETURNING id;
            """, (categoria, titulo, descripcion, fecha_limite))
            return cur.fetchone()["id"]


def get_tareas(categoria=None):
    with get_conn() as conn:
        with conn.cursor() as cur:
            if categoria:
                cur.execute("SELECT * FROM tareas WHERE categoria = %s ORDER BY estado DESC, fecha_limite ASC NULLS LAST;", (categoria,))
            else:
                cur.execute("SELECT * FROM tareas ORDER BY estado DESC, fecha_limite ASC NULLS LAST;")
            return cur.fetchall()
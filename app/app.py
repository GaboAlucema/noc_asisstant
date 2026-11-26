import pandas as pd
import streamlit as st
import db
import ai_engine

st.set_page_config(page_title="NOC Assistant", page_icon="🛠️", layout="wide")
st.title("🛠️ NOC Assistant — FONASA")

tab1, tab2, tab3 = st.tabs([
    "💬 Secretaria y Memoria",
    "🌐 Migración Nacional",
    "📋 Directorio y Tareas"
])

# ==========================================
# PESTAÑA 1: SECRETARIA (CHAT + MEMORIA)
# ==========================================
with tab1:
    col_chat, col_nota = st.columns([2, 1])

    with col_nota:
        st.subheader("Guardar en Memoria (Qdrant)")
        st.caption("Guarda resoluciones de tickets, ubicaciones de usuarios o informes técnicos.")
        with st.form("form_memoria", clear_on_submit=True):
            tipo_nota = st.selectbox("Tipo", ["ticket", "usuario", "procedimiento", "proveedor"])
            etiqueta = st.text_input("Etiqueta / Sucursal", placeholder="Ej: Contabilidad, CONCE-01")
            texto_nota = st.text_area("Detalle o resolución", height=140,
                                      placeholder="Ej: María de Contabilidad (piso 24) tenía enlace caído, se cambió patchcord.")
            if st.form_submit_button("Guardar nota", use_container_width=True):
                if texto_nota.strip():
                    with st.spinner("Guardando en memoria semántica..."):
                        ai_engine.guardar_memoria(texto_nota.strip(), tipo=tipo_nota, etiqueta=etiqueta or "general")
                    st.success("Guardado en Qdrant.")
                else:
                    st.warning("Escribe una nota antes de guardar.")

    with col_chat:
        st.subheader("Consulta a tu Secretaria")
        if "mensajes" not in st.session_state:
            st.session_state.mensajes = []

        for msg in st.session_state.mensajes:
            with st.chat_message(msg["role"]):
                st.markdown(msg["content"])

        if pregunta := st.chat_input("Ej: ¿Qué sabemos de Juan Pérez o cómo va la sucursal Concepción?"):
            st.session_state.mensajes.append({"role": "user", "content": pregunta})
            with st.chat_message("user"):
                st.markdown(pregunta)

            with st.chat_message("assistant"):
                with st.spinner("Consultando PostgreSQL, Qdrant y Ollama..."):
                    # 1. Contexto estructurado desde PostgreSQL
                    sucs = db.buscar_sucursales()
                    migs = db.get_migracion()
                    contexto_sql = "SUCURSALES:\n" + "\n".join(
                        [f"- {s['codigo']} ({s['nombre']}): IP={s['ip_enlace']}, Contacto={s['contacto_nombre']} ({s['contacto_fono']})" for s in sucs]
                    )
                    contexto_sql += "\n\nMIGRACIÓN NACIONAL:\n" + "\n".join(
                        [f"- {m['codigo']} ({m['sucursal']}): Fase={m['fase_actual']}, Visita={m['fecha_visita']} ({m['estado_visita']}), Obs={m['observaciones']}" for m in migs]
                    )

                    # 2. Contexto semántico desde Qdrant
                    contexto_qdrant = ai_engine.buscar_memoria(pregunta, limite=4)

                    # 3. Respuesta de Ollama
                    respuesta = ai_engine.responder_asistente(pregunta, contexto_sql, contexto_qdrant)
                    st.markdown(respuesta)

                    if contexto_qdrant:
                        with st.expander("Antecedentes encontrados en Qdrant"):
                            for item in contexto_qdrant:
                                st.markdown(f"- **[{item.get('tipo')}]** ({item.get('fecha')}): {item.get('texto')}")

            st.session_state.mensajes.append({"role": "assistant", "content": respuesta})


# ==========================================
# PESTAÑA 2: MIGRACIÓN NACIONAL
# ==========================================
with tab2:
    st.subheader("Seguimiento de Cambio de Proveedor")

    # Bloque de ingesta asistida por IA (Humano en el bucle)
    with st.expander("📩 Procesar correo de proveedor con IA", expanded=False):
        correo_raw = st.text_area("Pega aquí el correo del proveedor:", height=130,
                                  placeholder="Ej: Estimados, confirmamos visita de instalación de fibra para Sucursal Valparaíso el 10/12/2026 a las 09:30...")
        if st.button("Analizar correo con Ollama"):
            if correo_raw.strip():
                with st.spinner("Extrayendo datos con phi3..."):
                    try:
                        st.session_state.propuesta_mig = ai_engine.extraer_datos_migracion(correo_raw)
                    except Exception as e:
                        st.error(f"Error al interpretar JSON de Ollama: {e}")
            else:
                st.warning("Pega un correo primero.")

        if "propuesta_mig" in st.session_state:
            prop = st.session_state.propuesta_mig
            st.info("Revisa y corrige los datos extraídos antes de guardar:")
            with st.form("form_confirmar_mig"):
                c1, c2 = st.columns(2)
                cod = c1.text_input("Código Sucursal", value=prop.get("codigo_sucursal") or "")
                nom = c2.text_input("Nombre Sucursal", value=prop.get("nombre_sucursal") or "")

                fases = ["Factibilidad Técnica", "Instalación FO", "Pruebas", "Producción"]
                fase_idx = fases.index(prop.get("fase_actual")) if prop.get("fase_actual") in fases else 0
                fase = c1.selectbox("Fase Actual", fases, index=fase_idx)

                estados = ["Pendiente", "Tentativa", "Confirmada", "Realizada"]
                est_idx = estados.index(prop.get("estado_visita")) if prop.get("estado_visita") in estados else 1
                estado = c2.selectbox("Estado Visita", estados, index=est_idx)

                fecha_v = st.text_input("Fecha Visita (YYYY-MM-DD HH:MM o vacío)", value=prop.get("fecha_visita") or "")
                obs = st.text_area("Observaciones", value=prop.get("observaciones") or "")

                if st.form_submit_button("✅ Confirmar y Guardar en PostgreSQL"):
                    if cod.strip() and nom.strip():
                        db.registrar_avance_migracion(
                            codigo_sucursal=cod,
                            nombre_sucursal=nom,
                            fase_actual=fase,
                            fecha_visita=fecha_v.strip() or None,
                            estado_visita=estado,
                            observaciones=obs.strip() or None
                        )
                        del st.session_state.propuesta_mig
                        st.success(f"Sucursal {cod} actualizada correctamente.")
                        st.rerun()
                    else:
                        st.error("Código y Nombre de sucursal son obligatorios.")

    # Métricas y tabla en vivo
    datos_mig = db.get_migracion()
    if datos_mig:
        df_mig = pd.DataFrame(datos_mig)
        m1, m2, m3, m4 = st.columns(4)
        m1.metric("Total Sucursales", len(df_mig))
        m2.metric("Factibilidad", int((df_mig["fase_actual"] == "Factibilidad Técnica").sum()))
        m3.metric("Instalación FO", int((df_mig["fase_actual"] == "Instalación FO").sum()))
        m4.metric("En Producción", int((df_mig["fase_actual"] == "Producción").sum()))

        filtro_fase = st.multiselect("Filtrar por fase", df_mig["fase_actual"].unique().tolist())
        if filtro_fase:
            df_mig = df_mig[df_mig["fase_actual"].isin(filtro_fase)]

        st.dataframe(
            df_mig[["codigo", "sucursal", "fase_actual", "fecha_visita", "estado_visita", "contacto_nombre", "observaciones"]],
            use_container_width=True,
            hide_index=True
        )
    else:
        st.info("Aún no hay sucursales en seguimiento de migración.")


# ==========================================
# PESTAÑA 3: DIRECTORIO Y TAREAS
# ==========================================
with tab3:
    col_dir, col_tar = st.columns(2)

    with col_dir:
        st.subheader("Directorio de Sucursales")
        with st.expander("➕ Agregar / Actualizar Sucursal"):
            with st.form("form_sucursal", clear_on_submit=True):
                s_cod = st.text_input("Código (ej: CONCE-01)")
                s_nom = st.text_input("Nombre Sucursal")
                s_ip = st.text_input("IP Enlace")
                s_con = st.text_input("Contacto Local")
                s_fon = st.text_input("Teléfono / Anexo")
                s_not = st.text_area("Notas extra")
                if st.form_submit_button("Guardar Sucursal"):
                    if s_cod.strip() and s_nom.strip():
                        db.upsert_sucursal(s_cod, s_nom, ip_enlace=s_ip or None,
                                           contacto_nombre=s_con or None, contacto_fono=s_fon or None,
                                           notas_extra=s_not or None)
                        st.success("Sucursal guardada.")
                        st.rerun()

        busqueda = st.text_input("Buscar sucursal, código o contacto")
        sucursales = db.buscar_sucursales(busqueda)
        if sucursales:
            st.dataframe(
                pd.DataFrame(sucursales)[["codigo", "nombre", "ip_enlace", "contacto_nombre", "contacto_fono"]],
                use_container_width=True,
                hide_index=True
            )

    with col_tar:
        st.subheader("Tareas (NOC y Personales)")
        with st.expander("➕ Nueva Tarea"):
            with st.form("form_tarea", clear_on_submit=True):
                t_cat = st.selectbox("Categoría", ["NOC", "Personal"])
                t_tit = st.text_input("Título")
                t_desc = st.text_area("Descripción")
                t_fec = st.date_input("Fecha límite", value=None)
                if st.form_submit_button("Agregar Tarea"):
                    if t_tit.strip():
                        db.agregar_tarea(t_tit.strip(), t_cat, t_desc.strip(), t_fec)
                        st.success("Tarea agregada.")
                        st.rerun()

        cat_filtro = st.radio("Ver:", ["Todas", "NOC", "Personal"], horizontal=True)
        tareas = db.get_tareas(None if cat_filtro == "Todas" else cat_filtro)
        for t in tareas:
            c_txt, c_btn = st.columns([4, 1])
            estado_icon = "✅" if t["estado"] == "Completada" else "⏳"
            c_txt.markdown(f"{estado_icon} **[{t['categoria']}]** {t['titulo']} *(Límite: {t['fecha_limite'] or 'Sin fecha'})*")
            if t["estado"] != "Completada":
                if c_btn.button("Listo", key=f"done_{t['id']}"):
                    with db.get_conn() as conn:
                        with conn.cursor() as cur:
                            cur.execute("UPDATE tareas SET estado = 'Completada' WHERE id = %s;", (t["id"],))
                    st.rerun()
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

    # Bloque de ingesta asistida por IA (Múltiples sucursales con tabla editable)
    with st.expander("📩 Procesar correo o tabla de proveedor con IA", expanded=True):
        correo_raw = st.text_area("Pega aquí el correo o tabla del proveedor:", height=130,
                                  placeholder="Puedes pegar una o varias líneas con código MINSAL, contacto, fecha, etc.")
        if st.button("Analizar correo con Ollama"):
            if correo_raw.strip():
                with st.spinner("Extrayendo sucursales con Ollama..."):
                    try:
                        lista_extraida = ai_engine.extraer_datos_migracion(correo_raw)
                        st.session_state.propuesta_mig = pd.DataFrame(lista_extraida)
                    except Exception as e:
                        st.error(f"Error al interpretar JSON de Ollama: {e}")
            else:
                st.warning("Pega un correo o tabla primero.")

        if "propuesta_mig" in st.session_state and not st.session_state.propuesta_mig.empty:
            st.info(f"Se detectaron **{len(st.session_state.propuesta_mig)} sucursal(es)**. Revisa o edita cualquier celda antes de guardar:")
            df_editado = st.data_editor(
                st.session_state.propuesta_mig,
                num_rows="dynamic",
                use_container_width=True,
                key="editor_migracion"
            )

            c_ok, c_cancel = st.columns([2, 1])
            if c_ok.button("✅ Confirmar y Guardar todas en PostgreSQL", use_container_width=True):
                guardadas = 0
                for _, row in df_editado.iterrows():
                    cod = str(row.get("codigo_sucursal") or "").strip()
                    nom = str(row.get("nombre_sucursal") or "").strip()
                    if not cod or not nom:
                        continue

                    fecha_raw = str(row.get("fecha_visita") or "").strip()
                    fecha_val = fecha_raw if fecha_raw and fecha_raw.lower() != "none" else None
                    datos_tec = str(row.get("datos_tecnicos") or "").strip()
                    datos_tec = datos_tec if datos_tec and datos_tec.lower() != "none" else None

                    db.registrar_avance_migracion(
                        codigo_sucursal=cod,
                        nombre_sucursal=nom,
                        fase_actual=row.get("fase_actual") or "Factibilidad Técnica",
                        fecha_visita=fecha_val,
                        estado_visita=row.get("estado_visita") or "Tentativa",
                        observaciones=row.get("observaciones") or None,
                        direccion=row.get("direccion") or None,
                        contacto_nombre=row.get("contacto_nombre") or None,
                        contacto_fono=row.get("contacto_fono") or None,
                        notas_extra=datos_tec
                    )

                    # Si hay códigos de servicio, switches o anexos, también se guardan en Qdrant
                    if datos_tec:
                        ai_engine.guardar_memoria(
                            f"Sucursal {nom} ({cod}): {datos_tec}",
                            tipo="infraestructura",
                            etiqueta=cod
                        )
                    guardadas += 1

                del st.session_state.propuesta_mig
                st.success(f"Se guardaron {guardadas} sucursal(es) correctamente.")
                st.rerun()

            if c_cancel.button("Descartar", use_container_width=True):
                del st.session_state.propuesta_mig
                st.rerun()

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
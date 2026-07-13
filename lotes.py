import streamlit as st
import pandas as pd  
import CRUDs.crud_lotes_entradas as crud_l  # Conexión directa con nuestro controlador de lotes
from datetime import date
import time

# Define las cadenas de texto autorizadas para alterar datos del inventario médico
ROLES_AUTORIZADOS = ["Administrador", "Encargado del area"]

def usuario_tiene_permiso_escritura() -> bool:
    """Evalúa si el usuario en sesión cuenta con credenciales administrativas."""
    es_autenticado = st.session_state.get("usuario_autenticado", False)
    rol_usuario = st.session_state.get("user_rol", None)
    return es_autenticado and (rol_usuario in ROLES_AUTORIZADOS)

def Vista_Control_Lotes()
    """
    Renderiza la perspectiva analítica de inventarios clasificada por lotes de fábrica.
    """
    # 1. Recupera el histórico mapeado desde el backend en memoria RAM
    tuplas_lotes = crud_l.obtener_todos_lotes_con_relaciones()
    puede_editar = usuario_tiene_permiso_escritura()

    # 📌 TRUCO MAESTRO: Reservamos el espacio exacto del título para inyectarlo después de filtrar
    contenedor_titulo = st.empty()
    
    total_lotes_bd = len(tuplas_lotes) #hola

    # ==============================================================================
    # 🧠 EXTRACCIÓN DINÁMICA DE OPCIONES PARA LOS SELECTBOXES FILTRADORES
    # ==============================================================================
    opciones_insumos_set = set()
    opciones_lotes_set = set()
    opciones_ubicaciones_set = set()

    for tupla in tuplas_lotes:
        lote_obj, insumo_obj, _ = tupla
        if insumo_obj:
            opciones_insumos_set.add(insumo_obj.nombre.upper())
        if lote_obj:
            opciones_lotes_set.add(lote_obj.codigo_lote.upper())
            if lote_obj.ubicacion_fisica:
                opciones_ubicaciones_set.add(lote_obj.ubicacion_fisica.upper())

    lista_insumos = [""] + sorted(list(opciones_insumos_set))
    lista_lotes = [""] + sorted(list(opciones_lotes_set))
    lista_ubicaciones = [""] + sorted(list(opciones_ubicaciones_set))

    # ==============================================================================
    # 🎛️ FILTROS AVANZADOS PREDICTIVOS (Mismo layout de Entradas)
    # ==============================================================================
    c_med, c_lote, c_ubica, c_venc = st.columns([1.5, 1.2, 1.2, 1.6])
    
    with c_med:
        f_med = st.selectbox("Filtrar por Medicamento", options=lista_insumos, index=0)
    with c_lote:
        f_lote = st.selectbox("Filtrar por Código de Lote", options=lista_lotes, index=0)
    with c_ubica:
        f_ubica = st.selectbox("Filtrar por Ubicación", options=lista_ubicaciones, index=0)
    with c_venc:
        f_limite_venc = st.date_input("Vencimientos anteriores a:", value=date(2030, 12, 31), format="DD/MM/YYYY")


    # ==============================================================================
    # 🧠 MOTOR DE FILTRADO CONCURRENTE
    # ==============================================================================
    lotes_filtrados = []
    for tupla in tuplas_lotes:
        lote_obj, insumo_obj, _ = tupla
        
        nombre_insumo = insumo_obj.nombre.upper() if insumo_obj else ""
        cod_lote = lote_obj.codigo_lote.upper() if lote_obj else ""
        ubica_txt = lote_obj.ubicacion_fisica.upper() if lote_obj else ""
        
        match_med = not f_med or (f_med == nombre_insumo)
        match_lote = not f_lote or (f_lote == cod_lote)
        match_ubica = not f_ubica or (f_ubica == ubica_txt)
        
        match_fecha = True
        if lote_obj and lote_obj.fecha_vencimiento:
            match_fecha = lote_obj.fecha_vencimiento <= f_limite_venc

        if match_med and match_lote and match_ubica and match_fecha:
            lotes_filtrados.append(tupla)

    # ==============================================================================
    # 📊 INYECCIÓN DEL TÍTULO DINÁMICO CON EL FORMATO SOLICITADO
    # ==============================================================================
    total_filtrados_lotes = len(lotes_filtrados)
    
    # Inyectamos el título en formato exacto al solicitado en la parte superior
    contenedor_titulo.markdown(
        f"<h2 style='margin-bottom: 0;'>📦 Control de Lotes ({total_filtrados_lotes} / {total_lotes_bd})</h2>"
        f"<p style='color: gray; margin-top: 0;'>Inspección detallada de cargamentos y vencimientos en el almacén del <b>Destacamento 134</b>.</p>", 
        unsafe_allow_html=True
    )

    if not puede_editar:
        st.info("🔒 Modo Lectura: No tiene privilegios para alterar las propiedades de los lotes.")

    # 🛠️ PASO 1: Aquí reservamos el espacio en la pantalla (todavía está invisible)
    contenedor_guardar_modificacion = st.empty()

    # ==============================================================================
    # 📈 RENDERIZADOR INTERACTIVO CON DATAFRAME EDITABLE (Look Limpio)
    # ==============================================================================
    st.write("")
    if not lotes_filtrados:
        st.info("💡 No se encontraron lotes registrados que coincidan con los filtros.")
    else:
        filas_raw = []
        hoy = date.today()

        for tupla in lotes_filtrados:
            lote_obj, insumo_obj, entrada_obj = tupla
            
            # Semáforo visual simple incorporado al texto de la alerta
            venc_status = "⚠️ VENCIDO" if lote_obj.fecha_vencimiento and lote_obj.fecha_vencimiento <= hoy else "🟢 ACTIVO"
            stock_disp = lote_obj.stock_disponible  # @property dinámica de tu modelo
            
            filas_raw.append({
                "ID": lote_obj.id_lote,
                "INSUMO MÉDICO": insumo_obj.nombre.upper() if insumo_obj else "SIN INSUMO",
                "CÓD. LOTE": lote_obj.codigo_lote.upper() if lote_obj else "N/A",
                "UBICACIÓN": lote_obj.ubicacion_fisica.upper() if lote_obj.ubicacion_fisica else "SIN ASIGNAR",
                "CANT. INICIAL": entrada_obj.cantidad if entrada_obj else 0,
                "STOCK DISP.": "AGOTADO" if stock_disp == 0 else stock_disp,
                "F. VENCIMIENTO": lote_obj.fecha_vencimiento,
                "ESTADO": venc_status
            })

        df_lotes = pd.DataFrame(filas_raw)

        if puede_editar:
            st.caption("💡 **Modo Editor Activo:** Haga doble clic en *Cód. Lote*, *Ubicación* o *F. Vencimiento* para enmendar registros de forma directa.")

        # Invocación de la grilla de alto rendimiento enlazada al búfer de sesión
        grilla_lotes = st.data_editor(
            df_lotes,
            use_container_width=True,
            hide_index=True,
            height=400,
            key="editor_lotes",  # Permite atrapar las mutaciones en caliente
            # 📌 REQUISITO REFINADO: Bloqueamos ID, Insumo, Cantidad Inicial, Stock Calculado y Estado
            disabled=["ID", "INSUMO MÉDICO", "CANT. INICIAL", "STOCK DISP.", "ESTADO"] if puede_editar else True,
            column_config={
                "ID": st.column_config.NumberColumn(label="ID", format="%d"),
                "INSUMO MÉDICO": st.column_config.TextColumn(label="INSUMO MÉDICO"),
                "CÓD. LOTE": st.column_config.TextColumn(label="CÓD. LOTE (Editable)"),
                "UBICACIÓN": st.column_config.TextColumn(label="UBICACIÓN (Editable)"),
                "CANT. INICIAL": st.column_config.NumberColumn(label="CANT. INICIAL", format="%d unds."),
                # Si el stock tiene texto ("AGOTADO") o números, el TextColumn genérico se adapta sin romper formatos numéricos rígidos
                "STOCK DISP.": st.column_config.TextColumn(label="STOCK DISP."),
                "F. VENCIMIENTO": st.column_config.DateColumn(label="F. VENCIMIENTO (Editable)", format="DD/MM/YYYY"),
                "ESTADO": st.column_config.TextColumn(label="ESTADO")
            }
        )

        # ==============================================================================
        # 💾 DETECTOR DE CAMBIOS Y SINCRONIZACIÓN ATÓMICA CON SQLITE
        # ==============================================================================
        if puede_editar:
            estado_edicion = st.session_state.get("editor_lotes", {})
            cambios_detectados = estado_edicion.get("edited_rows", {}) if isinstance(estado_edicion, dict) else {}
            
            if cambios_detectados:
                with contenedor_guardar_modificacion:
                    st.warning("⚠️ Se detectaron modificaciones locales en las propiedades de los lotes.")
                    
                    # Traducimos las filas modificadas de la pantalla a IDs de la base de datos
                    diccionario_cambios_bd = {}
                    for indice_fila, modificaciones in cambios_detectados.items():
                        id_real_bd = df_lotes.iloc[int(indice_fila)]["ID"]
                        diccionario_cambios_bd[str(id_real_bd)] = modificaciones
                    
                    c_save, _ = st.columns([1.5, 4])
                    with c_save:
                        if st.button("💾 GUARDAR CAMBIOS DE LOTES", use_container_width=True, type="primary"):
                            # 🚀 Ejecutamos la función en el backend y guardamos su respuesta
                            resultado = crud_l.actualizar_registros_lotes_masivo(diccionario_cambios_bd)              
                            # 🔍 EVALUAMOS QUÉ NOS DEVOLVIÓ EL BACKEND:
                            if resultado == "DUPLICADO":
                                # 🛑 Si devolvió "DUPLICADO", pintamos el mensaje de error en pantalla
                                with _:
                                    st.error("🛑 Error: El código de lote que ingresaste ya existe en el sistema.")
                            elif resultado is True:
                                # ✔️ Si todo salió bien, guardamos con éxito y recargamos
                                st.success("¡Propiedades de lotes actualizadas con éxito!")
                                time.sleep(1.5)
                                st.rerun()
                            else:
                                # 🚨 Por si ocurre cualquier otro error imprevisto
                                with _:
                                    st.error(f"Fallo operativo insospechado: {resultado}")
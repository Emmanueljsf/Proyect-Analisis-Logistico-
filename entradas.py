import streamlit as st
import pan as pd  
import CRUDs.crud_lotes_entradas as crud_le  
from datetime import date  
import time  

# Define las cadenas de texto autorizadas para alterar datos del inventario médico
ROLES_AUTORIZADOS = ["Administrador", "Encargado del area"]

def usuario_tiene_permiso_escritura() -> bool:
    """
    Evalúa si las credenciales cargadas en la sesión activa otorgan
    privilegios de escritura y modificación sobre el inventario médico.
    """
    es_autenticado = st.session_state.get("usuario_autenticado", False)
    rol_usuario = st.session_state.get("user_rol", None)
    return es_autenticado and (rol_usuario in ROLES_AUTORIZADOS)

@st.dialog("📥 Registrar Entrada de Cargamento")
def modal_registro_entrada():
    """
    Ventana flotante institucional encargada de recolectar los metadatos
    de las actas de ingreso y las propiedades del lote del fabricante.
    """
    st.markdown("<p style='color:gray;'>Ingrese los datos del acta de recepción y el lote del fabricante.</p>", unsafe_allow_html=True)
    
    if not usuario_tiene_permiso_escritura():
        st.error("🛑 Acceso denegado. No tiene permisos para realizar esta acción.")
        return

    lista_insumos = crud_le.obtener_todos_insumos()
    if not lista_insumos:
        st.error("⚠️ No hay insumos registrados en el catálogo base.")
        return

    dict_insumos = {f"{i.nombre} [{i.clasificacion_ved}]".upper(): i.id_insumo for i in lista_insumos}
    insumo_seleccionado = st.selectbox("Seleccione el Insumo Médico *", list(dict_insumos.keys()))
    id_insumo_target = dict_insumos[insumo_seleccionado]
    
    c1, c2 = st.columns(2)
    with c1:
        txt_lote = st.text_input("Código de Lote *", placeholder="Ej: LOT-2026A")
        f_pedido = st.date_input("Fecha de Pedido Militar *", value=date.today(), format="DD/MM/YYYY")
        f_vence = st.date_input("Fecha de Vencimiento del Lote *", min_value=date.today(), format="DD/MM/YYYY")
    with c2:
        txt_ubica = st.text_input("Ubicación Física *", placeholder="Ej: Estante B")
        num_cantidad = st.number_input("Cantidad Recibida *", min_value=1, step=1, value=1)
        
    st.divider()
    c_btn1, c_btn2 = st.columns(2)
    with c_btn1:
        if st.button("GUARDAR INGRESO", use_container_width=True, type="primary"):
            if not txt_lote.strip() or not txt_ubica.strip():
                st.warning("⚠️ Campos marcados con (*) son obligatorios.")
            else:
                exito = crud_le.registrar_ingreso_inventario(
                    id_insumo=id_insumo_target,
                    codigo_lote=txt_lote.strip().upper(),
                    fecha_vencimiento=f_vence,
                    ubicacion_fisica=txt_ubica.strip().upper(),
                    cantidad=num_cantidad,
                    id_usuario=st.session_state.get("user_id", 1), 
                    fecha_pedido=f_pedido
                )
                if exito:
                    st.success("✔️ Entrada y lote registrados exitosamente.")
                    time.sleep(1.5)
                    st.rerun()
                else:
                    st.error("🛑 Error: Verifique si el código de lote ya está registrado.")
    with c_btn2:
        if st.button("CANCELAR", use_container_width=True): 
            st.rerun()

def Vista_Registrar_Entradas():
    """
    Punto de entrada principal para el módulo de recepción de cargamentos.
    """
    # 1. Recupera el histórico desde la base de datos
    historial_completo = crud_le.obtener_historial_entradas()
    puede_editar = usuario_tiene_permiso_escritura()

    # 📌 TRUCO MAESTRO: Reservamos el espacio exacto del título para inyectarlo después de filtrar
    contenedor_titulo = st.empty()
    total_registros_bd = len(historial_completo)

    # ==============================================================================
    # 🧠 EXTRACCIÓN DINÁMICA DE OPCIONES PARA LOS SELECTBOXES FILTRADORES
    # ==============================================================================
    opciones_insumos_set = set()      
    opciones_lotes_set = set()        
    opciones_usuarios_set = set()     

    for tupla in historial_completo:
        entrada_obj, lote_obj, insumo_obj, usuario_obj = tupla
        
        if not lote_obj:
            continue                  

        if insumo_obj:
            opciones_insumos_set.add(insumo_obj.nombre.upper())
            
        opciones_lotes_set.add(lote_obj.codigo_lote.upper())
            
        if usuario_obj:
            nombre_corto = f"{usuario_obj.nombres.split()[0]} {usuario_obj.apellidos.split()[0]}".upper()
            opciones_usuarios_set.add(nombre_corto)

    lista_insumos = [""] + sorted(list(opciones_insumos_set))
    lista_lotes = [""] + sorted(list(opciones_lotes_set))
    lista_usuarios = [""] + sorted(list(opciones_usuarios_set))

    # ==============================================================================
    # 🎛️ FILTROS AVANZADOS PREDICTIVOS
    # ==============================================================================
    c_med, c_lote, c_user, c_dates = st.columns([1.5, 1.2, 1.5, 1.8])
    
    with c_med:
        f_med = st.selectbox("Filtrar por Medicamento", options=lista_insumos, index=0)
    with c_lote:
        f_lote = st.selectbox("Filtrar por Código de Lote", options=lista_lotes, index=0)
    with c_user:
        f_user = st.selectbox("Filtrar por Operador", options=lista_usuarios, index=0)
    with c_dates:
        rango_fechas = st.date_input("Rango de Recepción", value=[date(2024, 1, 1), date.today()], format="DD/MM/YYYY")

    

    # ==============================================================================
    # 🧠 MOTOR DE FILTRADO CONCURRENTE
    # ==============================================================================
    entradas_filtradas = []
    for tupla in historial_completo:
        entrada_obj, lote_obj, insumo_obj, usuario_obj = tupla
        
        nombre_insumo = insumo_obj.nombre.upper() if insumo_obj else ""
        codigo_lote_txt = lote_obj.codigo_lote.upper() if lote_obj else ""
        
        if usuario_obj:
            nombre_corto_reg = f"{usuario_obj.nombres.split()[0]} {usuario_obj.apellidos.split()[0]}".upper()
        else:
            nombre_corto_reg = f"ID: {entrada_obj.id_usuario}"
        
        match_med = not f_med or (f_med == nombre_insumo)
        match_lote = not f_lote or (f_lote == codigo_lote_txt)
        match_user = not f_user or (f_user == nombre_corto_reg)
        
        match_fecha = True
        if isinstance(rango_fechas, (list, tuple)) and len(rango_fechas) == 2:
            dt_recepcion = entrada_obj.fecha_recepcion
            if dt_recepcion:
                fecha_reg = dt_recepcion.date() if hasattr(dt_recepcion, "date") else dt_recepcion
                match_fecha = rango_fechas[0] <= fecha_reg <= rango_fechas[1]
            else:
                match_fecha = False
            
        if match_med and match_lote and match_user and match_fecha:
            entradas_filtradas.append(tupla)

    # ==============================================================================
    # 📊 INYECCIÓN DEL TÍTULO DINÁMICO CON EL FORMATO SOLICITADO
    # ==============================================================================
    total_filtrados = len(entradas_filtradas)
    
    # Inyectamos el título con los contadores en vivo en el espacio reservado arriba
    contenedor_titulo.markdown(
        f"<h2 style='margin-bottom: 0;'>📥 Historial de Entradas ({total_filtrados} / {total_registros_bd})</h2>"
        f"<p style='color: gray; margin-top: 0;'>Historial cronológico de actas de ingreso al almacén del <b>Destacamento 134</b>.</p>", 
        unsafe_allow_html=True
    )

    # Botón de registro acoplado abajo
    c_vacia, c_btn_reg = st.columns([4, 1.2])
    with c_btn_reg:
        if puede_editar:
            if st.button("➕ REGISTRAR ENTRADA", use_container_width=True, type="primary"): 
                modal_registro_entrada()
        else:
            st.info("🔒 Modo Lectura")

    # 🛠️ PASO 1: Aquí reservamos el espacio en la pantalla (todavía está invisible)
    contenedor_guardar_modificacion = st.empty()

    # ==============================================================================
    # 📈 RENDERIZADOR INTERACTIVO CON EDICIÓN MASIVA EN BASE DE DATOS
    # ==============================================================================
    st.write("")
    if not entradas_filtradas:
        st.info("💡 No se encontraron registros de entradas logísticas.")
    else:
        filas_raw = []
        for tupla in entradas_filtradas:
            entrada_obj, lote_obj, insumo_obj, usuario_obj = tupla
            
            filas_raw.append({
                "ID": entrada_obj.id_entrada,
                "INSUMO MÉDICO": insumo_obj.nombre.upper() if insumo_obj else "SIN INSUMO",
                "CÓD. LOTE": lote_obj.codigo_lote.upper() if lote_obj else "N/A",
                "CANTIDAD": entrada_obj.cantidad,
                "FECHA PEDIDO": entrada_obj.fecha_pedido,
                "L. TIME": entrada_obj.tiempo_entrega_dias,
                "FECHA RECEPCIÓN": entrada_obj.fecha_recepcion,
                "OPERADOR LOGÍSTICO": f"{usuario_obj.nombres.split()[0]} {usuario_obj.apellidos.split()[0]}".upper() if usuario_obj else f"ID: {entrada_obj.id_usuario}"
            })
        
        df_entradas = pd.DataFrame(filas_raw)
        
        if puede_editar:
            st.caption("💡 **Modo Editor Activo:** Haga doble clic en *Cantidad* o *Fecha Pedido* para corregir errores. El código de lote se modifica en el módulo de lotes.")
            
            # Menú de eliminación masiva por ID
            with st.expander("🗑️ Menú de Eliminación de Actas"):
                c_del_id, c_del_btn = st.columns([3, 1])
                with c_del_id:
                    id_para_eliminar = st.number_input("Ingrese el ID exacto del acta a eliminar:", min_value=1, step=1)
                with c_del_btn:
                    st.markdown("<div style='padding-top:24px;'></div>", unsafe_allow_html=True)
                    if st.button("🔴 ELIMINAR REGISTRO DEFINITIVAMENTE", use_container_width=True, type="primary"):
                        if crud_le.eliminar_registro_entrada(id_para_eliminar):
                            st.success(f"Acta ID {id_para_eliminar} y su lote eliminados de la BD.")
                            time.sleep(1)
                            st.rerun()
                        else:
                            st.error("No se encontró ningún registro con ese ID.")

        # 📌 SOLUCIÓN PRINCIPAL: Añadimos 'key="editor_entradas"' fijo para enlazar los cambios en tiempo real
        grilla_editada = st.data_editor(
            df_entradas,
            use_container_width=True,
            hide_index=True,
            height=400,
            key="editor_entradas",  # 👈 Súper clave para el monitoreo de estado estable
            # 📌 CORRECCIÓN: Agregamos "CÓD. LOTE" a la lista de columnas bloqueadas (disabled)
            disabled=["ID", "INSUMO MÉDICO", "CÓD. LOTE", "L. TIME", "FECHA RECEPCIÓN", "OPERADOR LOGÍSTICO"] if puede_editar else True,
            column_config={
                "ID": st.column_config.NumberColumn(label="ID", format="%d"),
                "INSUMO MÉDICO": st.column_config.TextColumn(label="INSUMO MÉDICO"),
                "CÓD. LOTE": st.column_config.TextColumn(label="CÓD. LOTE"),
                "CANTIDAD": st.column_config.NumberColumn(label="CANTIDAD (Editable)", format="%d unds.", min_value=1),
                "FECHA PEDIDO": st.column_config.DateColumn(label="FECHA PEDIDO (Editable)", format="DD/MM/YYYY"),
                "L. TIME": st.column_config.NumberColumn(label="L. TIME", format="%d días"),
                "FECHA RECEPCIÓN": st.column_config.DatetimeColumn(label="FECHA RECEPCIÓN", format="DD/MM/YYYY HH:mm"),
                "OPERADOR LOGÍSTICO": st.column_config.TextColumn(label="OPERADOR LOGÍSTICO")
            }
        )
        
        # ==============================================================================
        # 💾 DETECTOR DE CAMBIOS FIABLE (CONSOLIDACIÓN EN BD)
        # ==============================================================================
        if puede_editar:
            # Apuntamos directamente al estado de la llave asignada al componente
            estado_edicion = st.session_state.get("editor_entradas", {})
            cambios_detectados = estado_edicion.get("edited_rows", {}) if isinstance(estado_edicion, dict) else {}
            
            # Si el diccionario de filas editadas contiene datos, renderizamos inmediatamente el botón de guardado
            if cambios_detectados:
                with contenedor_guardar_modificacion:
                    st.warning("⚠️ Hay modificaciones locales en la tabla pendientes por subir a la Base de Datos.")
                    
                    # Traducimos los índices visuales del DataFrame a los IDs reales de la clave primaria SQL
                    diccionario_cambios_bd = {}
                    for indice_fila, modificaciones in cambios_detectados.items():
                        id_real_bd = df_entradas.iloc[int(indice_fila)]["ID"]
                        diccionario_cambios_bd[str(id_real_bd)] = modificaciones
                    
                    c_save, _ = st.columns([1.5, 4])
                    with c_save:
                        if st.button("💾 GUARDAR CAMBIOS", use_container_width=True, type="primary"):
                            if crud_le.actualizar_registros_entradas_masivo(diccionario_cambios_bd):
                                st.success("¡Registro modificado de forma exitosa!")
                                time.sleep(1.6)
                                st.rerun()
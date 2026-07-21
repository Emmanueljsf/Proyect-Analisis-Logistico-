import streamlit as st
import pandas as pd  # Manejo matricial a alta velocidad
import CRUDs.crud_insumos as crud_insumos  # Controlador backend SQL
from models import Rol
import time  # Control de pausas para confirmaciones visuales
import math
from datetime import datetime
import io
from seguridad import es_administrador, usuario_tiene_permiso_escritura
from reportes import generar_reporte_insumos_excel, generar_reporte_insumos_pdf
import uuid
import logging



# FUNCIÓN PARA PINTAR EL FONDO DE LA PALABRA
def colorear_celda_ved(valor):
    """Pinta el fondo de la celda según la clasificación VED (Estilo Etiqueta)."""
    if valor == "V":
        return "background-color: #ffcccc; color: #cc0000; font-weight: bold; text-align: center;"  # 🔴 Fondo Rojo suave
    elif valor == "E":
        return "background-color: #fff3cd; color: #856404; font-weight: bold; text-align: center;"  # 🟡 Fondo Amarillo suave
    elif valor == "D":
        return "background-color: #d4edda; color: #155724; font-weight: bold; text-align: center;"  # 🟢 Fondo Verde suave
    return "text-align: center;"


@st.dialog("📦 Registrar Nuevo Insumo")
def modal_registro_insumo():
    """
    Ventana flotante simplificada para añadir un artículo de forma limpia.
    Implementa logs estructurados y manejo seguro de errores mediante UUID.
    """
    # PROTECCIÓN: Contenedor para mensajes de error de UI
    contenedor_msg = st.empty()
    
    try:
        if not usuario_tiene_permiso_escritura():
            st.error("❌ Acceso restringido: No tienes el permiso para acceder a este formulario.")
        else:
            st.markdown("<p style='color:gray;'>Ingrese los datos básicos para el catálogo general.</p>", unsafe_allow_html=True)
            
            txt_nombre = st.text_input("Nombre del Insumo / Medicamento *", placeholder="Ej: AMOXICILINA 500MG")
            opc_ved = st.selectbox("Clasificación VED *", ["V", "E", "D"], help="V: Vital, E: Esencial, D: Diario")
            
            st.write("")
            c_save, c_cancel = st.columns(2)
            with c_save:
                if st.button("💾 REGISTRAR", use_container_width=True, type="primary"):
                    if not txt_nombre.strip():
                        contenedor_msg.error("🛑 El nombre es obligatorio.")
                    else:
                        try:
                            # Registro en base de datos protegido
                            crud_insumos.crear_insumo(txt_nombre, opc_ved)
                            st.success("¡Insumo creado con éxito!")
                            time.sleep(1.2)
                            st.rerun()
                        except Exception as e:
                            # Trazabilidad Avanzada al fallar la persistencia
                            correlation_id = str(uuid.uuid4())
                            logging.error(f'{{"correlation_id": "{correlation_id}", "error": "{str(e)}", "modulo": "modal_registro_insumo_bd"}}')
                            contenedor_msg.error(f"Error al guardar. Reporte el código: [{correlation_id}]")
            with c_cancel:
                if st.button("CANCELAR", use_container_width=True):
                    st.rerun()

    except Exception as e:
        # 🔍 CAPA EXTERNA DE PROTECCIÓN DEL DIÁLOGO
        correlation_id = str(uuid.uuid4())
        logging.error(f'{{"correlation_id": "{correlation_id}", "error": "{str(e)}", "modulo": "modal_registro_insumo_ui"}}')
        st.error(f"Error fatal en el formulario. Reporte el código: [{correlation_id}]")

def Insumos():
    try:
        tiene_permisos = usuario_tiene_permiso_escritura()  # Valida privilegios de rol
        
        """Componente maestro del catálogo estructurado en un dataframe con control de cambios masivos."""
        contenedor_titulo = st.empty()
        st.caption("Gestión integral con filtro de stock por rango de texto único, colores de fondo VED y edición masiva.")

    # 1. OBLIGATORIO: Inicializar la variable al principio del todo para que exista en RAM
        if "pagina_insumos" not in st.session_state:
            st.session_state["pagina_insumos"] = 1

    # ==============================================================================
        # PANEL DE FILTROS UNIVERSALES 
        # ==============================================================================
        with st.expander("🔍 Buscador Universal de Catálogo", expanded=True):
            # Reducimos a 4 columnas unificando la barra de Nombre y VED
            f_col_buscar, f_col_stock, f_col_estado = st.columns([2.2, 1.4, 1.2])
            
            with f_col_buscar:
                # Una sola barra para Nombre o palabras clave: "Vital", "Esencial", "Deseable"
                txt_buscar = st.text_input("Buscar por Nombre o VED:", placeholder="Ej: Paracetamol o Vital...", key="f_txt_buscar").strip()
            with f_col_stock:
                txt_rango_stock = st.text_input("Rango de Stock (Min-Max):", placeholder="Ej: 30-50 o 50", key="f_txt_stock").strip()
            with f_col_estado:
                opt_estado = st.selectbox("Estado:", ["ACTIVOS", "INACTIVOS", "TODOS"], index=0, key="f_opt_estado")
            

        # Creamos dos columnas visuales elegantes
        col_excel, col_pdf, _, f_col_btn = st.columns([2,2,1,1.2])

        # BOTON DE REGISTRO
        with f_col_btn:
                if tiene_permisos and st.button("➕ NUEVO INSUMO", use_container_width=True, type="primary"):
                    modal_registro_insumo()

        if es_administrador():
            usuario_actual = st.session_state.get("user_nombre_completo", "OPERADOR SIAL-MED")
            
            # SECCIÓN: REPORTE EN EXCEL
            with col_excel:
                # 1. Creamos el botón disparador para evitar consultas automáticas
                if st.button("📊 Generar Reporte en Excel (.xlsx)", use_container_width=True, key="btn_trigger_excel"):
                    with st.spinner("Procesando Excel..."):
                        
                        # 2. La consulta a la BD SOLO ocurre AQUÍ tras hacer clic
                        datos_excel = generar_reporte_insumos_excel(txt_buscar, opt_estado, usuario_actual)
                        
                        if datos_excel:
                            # 3. Si hay datos, habilitamos el botón nativo de descarga
                            st.download_button(
                                label="⬇️ Descargar Archivo Excel",
                                data=datos_excel,
                                file_name=f"SIALMED_Reporte_Insumos_{opt_estado}.xlsx",
                                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                                use_container_width=True
                            )
                        else:
                            st.warning("No hay datos para el filtro seleccionado.")

            # SECCIÓN: REPORTE EN PDF
            with col_pdf:
                # 1. Creamos el botón disparador para evitar consultas automáticas
                if st.button("📄 Generar Reporte en PDF", use_container_width=True, key="btn_trigger_pdf"):
                    with st.spinner("Procesando PDF..."):
                        
                        # 2. La consulta a la BD SOLO ocurre AQUÍ tras hacer clic
                        datos_pdf = generar_reporte_insumos_pdf(txt_buscar, opt_estado, usuario_actual)   
                        if datos_pdf:
                            # 3. Si hay datos, habilitamos el botón nativo de descarga      
                            st.download_button(
                                label="⬇️ Descargar Archivo PDF",
                                data=datos_pdf,
                                file_name=f"SIALMED_Reporte_Insumos_{opt_estado}.pdf",
                                mime="application/pdf",
                                use_container_width=True
                            )
                        else:
                            st.warning("No hay datos para el filtro seleccionado.")

        # ==============================================================================
        # EJECUCIÓN DEL BACKEND (Trae todo de un solo viaje)
        # ==============================================================================
        lista_insumos = crud_insumos.obtener_insumos(
            solo_activos=False,
            opt_estado=opt_estado,
            txt_buscar=txt_buscar
        )
        
        # 1. CONSTRUCCIÓN DE LA MATRIZ BASE EN MEMORIA RAM
        datos_matriz = []
        
        if lista_insumos:
            for ins in lista_insumos:
                ved = ins.clasificacion_ved.value if hasattr(ins.clasificacion_ved, "value") else ins.clasificacion_ved
                datos_matriz.append({
                    "ID": ins.id_insumo,  
                    "NOMBRE DEL INSUMO": ins.nombre, 
                    "CLASIFICACIÓN VED": 'VITAL' if ved=='V' else 'ESENCIAL' if ved=='E' else 'DESEABLE',
                    "STOCK DISPONIBLE": ins.total_stock,  # Corre fluido porque la RAM tiene los lotes cargados
                    "ESTADO": "ACTIVO" if ins.activo else "INACTIVO"
                })
                
        # Construye el DataFrame original con las columnas explícitas
        df_filtrado = pd.DataFrame(datos_matriz, columns=["ID", "NOMBRE DEL INSUMO", "CLASIFICACIÓN VED", "STOCK DISPONIBLE", "ESTADO"])

        # Renderizado dinámico de títulos informativos basados en la respuesta del backend
        total_filtrados = len(df_filtrado)
        contenedor_titulo.markdown(
            f"<h2 style='margin-bottom: 0;'>📦 Catálogo Maestro de Insumos Médicos ({total_filtrados} registros filtrados)</h2>", 
            unsafe_allow_html=True
        )

        # 2. FILTRO DE STOCK AD-HOC (Ocurre al instante sobre el DataFrame de Pandas)
        if txt_rango_stock and not df_filtrado.empty:
            try:
                if "-" in txt_rango_stock:
                    partes = txt_rango_stock.split("-")
                    val_min = int(partes[0].strip()) if partes[0].strip() else 0
                    val_max = int(partes[1].strip()) if partes[1].strip() else 999999
                else:
                    val_min = int(txt_rango_stock)
                    val_max = 999999
                df_filtrado = df_filtrado[(df_filtrado["STOCK DISPONIBLE"] >= val_min) & (df_filtrado["STOCK DISPONIBLE"] <= val_max)]
            except ValueError:
                st.sidebar.error("⚠️ Formato de rango incorrecto (Ej: 30-50)")

        # ==============================================================================
        # 📟 MOTOR DE PAGINACIÓN LOCAL (Segmentación de 50 en 50 desde la RAM)
        # ==============================================================================
        REGISTROS_POR_PAGINA = 50
        total_registros = len(df_filtrado)
        total_paginas = math.ceil(total_registros / REGISTROS_POR_PAGINA) if total_registros > 0 else 1

        # Evitamos que la página actual quede fuera de rango tras un filtro muy estricto
        if st.session_state["pagina_insumos"] > total_paginas:
            st.session_state["pagina_insumos"] = 1

        # Slicing (rebanado) del DataFrame para extraer solo las 50 filas de la página actual
        inicio = (st.session_state["pagina_insumos"] - 1) * REGISTROS_POR_PAGINA
        fin = inicio + REGISTROS_POR_PAGINA
        df_pagina_actual = df_filtrado.iloc[inicio:fin]


        st.write("")
        contenedor_guardar_cambios = st.empty()  # Slot para confirmaciones visuales

        # Aplicamos estilos a las celdas VED sobre la página actual (solo si no está vacía)
        if not df_pagina_actual.empty:
            df_estilizado = df_pagina_actual.style.applymap(colorear_celda_ved, subset=["CLASIFICACIÓN VED"])
        else:
            df_estilizado = df_pagina_actual
        
        # ==============================================================================
        # 4. RENDERIZADO DEL DATAFRAME EDITABLE / SOLO LECTURA
        # ==============================================================================
        if tiene_permisos:
            st.data_editor(
                df_estilizado,  
                use_container_width=True,
                hide_index=True,
                key="editor_cat_insumos",  
                disabled=["ID", "STOCK DISPONIBLE"],  
                column_config={
                    "ID": st.column_config.NumberColumn(width="small"),
                    "NOMBRE DEL INSUMO": st.column_config.TextColumn(width='big'),
                    "CLASIFICACIÓN VED": st.column_config.SelectboxColumn(options=["VITAL", "ESENCIAL", "DESEABLE"], required=True, width="medium"),
                    "STOCK DISPONIBLE": st.column_config.NumberColumn(format="%d unds.", width="medium"),
                    "ESTADO": st.column_config.SelectboxColumn(options=["ACTIVO", "INACTIVO"], width="small", required=True)
                }
            )
            
            # Procesamiento de cambios masivos sobre la página en pantalla
            estado_edicion = st.session_state.get("editor_cat_insumos", {})
            cambios_detectados = estado_edicion.get("edited_rows", {}) if isinstance(estado_edicion, dict) else {}
            
            if cambios_detectados and not df_pagina_actual.empty:
                with contenedor_guardar_cambios:
                    st.warning("⚠️ Hay cambios locales en la tabla pendientes por subir a la Base de Datos.")
                    
                    diccionario_cambios_bd = {}
                    for indice_fila, modificaciones in cambios_detectados.items():
                        id_real_bd = df_pagina_actual.iloc[int(indice_fila)]["ID"]
                        diccionario_cambios_bd[str(id_real_bd)] = modificaciones
                    
                    c_save, mensaje, _ = st.columns([1.5, 3.3, 0.7])
                    with c_save:
                        if st.button("💾 GUARDAR CAMBIOS DETECTADOS", use_container_width=True, type="primary"):
                            resultado = crud_insumos.actualizar_catalogo_insumos_masivo(diccionario_cambios_bd)
                            with mensaje:
                                if resultado == True:
                                    st.success("¡Datos actualizados con éxito!")  
                                    time.sleep(1.1)  
                                    st.rerun()  
                                else:
                                    st.error(resultado)
        else:
            st.dataframe(
                df_estilizado,  
                use_container_width=True,
                hide_index=True,
                column_config={
                    "STOCK DISPONIBLE": st.column_config.NumberColumn(format="%d u.")
                }
            )

        # Mensaje informativo si no hay filas que mostrar
        if df_pagina_actual.empty:
            st.info("ℹ️ La consulta no arrojó resultados con los criterios seleccionados. La grilla se encuentra vacía.")

        # ==============================================================================
        # 📟 CONTROLADOR VISUAL DE PAGINACIÓN INTERACTIVO (BOTONES)
        # ==============================================================================
        st.write("")
        c_pag1, c_pag2, c_pag3 = st.columns([1.5, 2, 1.5])
        
        with c_pag2:
            pag_vis = st.session_state["pagina_insumos"]
            st.markdown(f"<p style='text-align:center; color:gray;'>Página <b>{pag_vis}</b> de {total_paginas}</p>", unsafe_allow_html=True)
            
        with c_pag1:
            # Botón para retroceder (Deshabilitado si está en la primera página)
            if st.button("⬅️ Anterior", use_container_width=True, disabled=(st.session_state["pagina_insumos"] == 1)):
                st.session_state["pagina_insumos"] -= 1
                st.rerun()
                
        with c_pag3:
            # Botón para avanzar (Deshabilitado si llegó a la última página calculada)
            if st.button("Siguiente ➡️", use_container_width=True, disabled=(st.session_state["pagina_insumos"] >= total_paginas)):
                st.session_state["pagina_insumos"] += 1
                st.rerun()


    except Exception as e:
        # Observabilidad (Trazabilidad Avanzada)
        correlation_id = str(uuid.uuid4())
        logging.error(f'{{"correlation_id": "{correlation_id}", "error": "{str(e)}", "modulo": "nombre_modulo"}}')
        st.error(f"Ocurrió un error inesperado. Reporte el código: [{correlation_id}]")
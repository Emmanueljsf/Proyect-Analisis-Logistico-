import streamlit as st
import pandas as pd  
import CRUDs.crud_lotes as crud_l  
import CRUDs.crud_insumos as crud_ins  # Importamos para obtener la lista de opciones de insumos
from insumos1 import usuario_tiene_permiso_escritura
from reportes import generar_reporte_lotes_excel, generar_reporte_lotes_pdf
from datetime import date, timedelta
import time
import math

def Vista_Control_Lotes():
    """
    Renderiza el control de lotes con filtros procesados en el backend
    y paginación local de 50 en 50 para alto rendimiento.
    """
    try:
        # Inicialización obligatoria del estado de la página para evitar KeyErrors
        if "pagina_lotes" not in st.session_state:
            st.session_state["pagina_lotes"] = 1

        puede_editar = usuario_tiene_permiso_escritura()
        contenedor_titulo = st.empty()

        # ==============================================================================
        #  BARRAS DE BÚSQUEDA 
        # ==============================================================================
        with st.expander("🔍 Panel de Filtros Centralizado", expanded=True):
            f_col1, f_col2, f_col3, f_col4 = st.columns([2.5, 1.2, 1.8, 1.2])
            
            with f_col1:
                txt_universal = st.text_input(
                    "Buscador Universal:", 
                    placeholder="Nombre insumo, VED, código lote o ubicación...", 
                    key="fl_universal"
                ).strip()
                
            with f_col2:
                txt_rango_stock = st.text_input(
                    "Rango Stock (Min-Max):", 
                    placeholder="Ej: 10-50 o 10", 
                    key="fl_stock"
                ).strip()
                
            with f_col3:
                rango_vencimiento = st.date_input(
                    "Ventana de Vencimiento:", 
                    value=[date.today()-timedelta(days=30), date.today()+timedelta(days=365)],
                    format="DD/MM/YYYY", 
                    key="fl_fecha"
                )
                
            with f_col4:
                opt_estado = st.selectbox(
                    "Disponibilidad:", 
                    ["ACTIVOS", "INACTIVOS", "TODOS"], 
                    index=0, 
                    key="fl_estado"
                )

        # ==============================================================================
        # 🚀 CONSULTA DIRECTA AL BACKEND FILTRADO
        # ==============================================================================
        tuplas_lotes = crud_l.obtener_lotes_filtrados(
            txt_universal=txt_universal,
            txt_rango_stock=txt_rango_stock,
            rango_vencimiento=rango_vencimiento,
            opt_estado=opt_estado
        )

        # Construcción de la matriz con los registros ya filtrados por el servidor SQL
        filas_raw = []
        if tuplas_lotes:
            for lote_obj, insumo_obj in tuplas_lotes:
                ved = insumo_obj.clasificacion_ved.value if hasattr(insumo_obj.clasificacion_ved, "value") else insumo_obj.clasificacion_ved
                ved_txt = 'VITAL' if ved=='V' else 'ESENCIAL' if ved=='E' else 'DESEABLE'
                
                # Recuperamos el motivo de desactivación real del objeto de la BD
                motivo = lote_obj.motivo_desactivacion if lote_obj.motivo_desactivacion else ""
                
                registro = {
                    "ID": lote_obj.id_lote,
                    "INSUMO ASOCIADO": insumo_obj.nombre,
                    "CÓDIGO DE LOTE": lote_obj.codigo_lote,
                    "CLASIFICACIÓN VED": ved_txt,
                    "STOCK DISPONIBLE": lote_obj.stock_disponible,  
                    "FECHA VENCIMIENTO": lote_obj.fecha_vencimiento, 
                    "UBICACIÓN FÍSICA": lote_obj.ubicacion_fisica,
                    "ESTADO": "ACTIVO" if lote_obj.activo else "INACTIVO"
                }
                
                # CONDICIÓN: Se añade la columna al diccionario si el estado no es meramente "ACTIVOS"
                if opt_estado != "ACTIVOS":
                    registro["MOTIVO DESACTIVACIÓN"] = motivo
                    
                filas_raw.append(registro)

        # Si no hay datos, creamos las columnas base limpias respetando el filtro dinámico
        if filas_raw:
            df_lotes = pd.DataFrame(filas_raw)
        else:
            columnas_base = ["ID", "INSUMO ASOCIADO", "CÓDIGO DE LOTE", "CLASIFICACIÓN VED", "STOCK DISPONIBLE", "FECHA VENCIMIENTO", "UBICACIÓN FÍSICA", "ESTADO"]
            if opt_estado != "ACTIVOS":
                columnas_base.append("MOTIVO DESACTIVACIÓN")
            df_lotes = pd.DataFrame(columns=columnas_base)

        # Renderizado dinámico de títulos informativos basados en la respuesta del backend
        total_filtrados = len(df_lotes) if filas_raw else 0
        contenedor_titulo.markdown(
            f"<h2 style='margin-bottom: 0;'>📦 Control de Existencias por Lotes ({total_filtrados} registros filtrados)</h2>", 
            unsafe_allow_html=True
        )


        # BOTONES DE REPORTES
        if st.session_state.get("user_rol") == "Administrador":
            usuario_actual = st.session_state.get("user_nombre_completo", "ADMINISTRADOR SIAL-MED")
            
            f_stock = txt_rango_stock if 'txt_rango_stock' in locals() else ""
            f_vencimiento = rango_vencimiento if 'rango_vencimiento' in locals() else None
            f_estado = opt_estado if 'opt_estado' in locals() else "ACTIVOS"
            
            col_excel, col_pdf, _ = st.columns([2, 2, 2])
            
            with col_excel:
                # 1. Creamos el botón disparador para evitar consultas automáticas
                if st.button("📊 Generar Reporte en Excel (.xlsx)", use_container_width=True, key="btn_trigger_excel"):
                    with st.spinner("Procesando Excel..."):
                        
                        # 2. La consulta a la BD SOLO ocurre AQUÍ tras hacer clic
                        datos_l_excel = generar_reporte_lotes_excel(txt_universal, f_stock, f_vencimiento, f_estado, usuario_actual)
                        
                        if datos_l_excel:
                            # 3. Si hay datos, habilitamos el botón nativo de descarga
                            st.download_button(
                                label="⬇️ Descargar Archivo Excel (.xlsx)",
                                data=datos_l_excel,
                                file_name=f"SIALMED_Inventario_Lotes_{f_estado}.xlsx",
                                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                                use_container_width=True,
                                key="btn_download_lotes_excel"
                            )
                        else:
                            st.warning("No hay datos para el filtro seleccionado.")
            
            # SECCIÓN: REPORTE EN PDF
            with col_pdf:
                # 1. Creamos el botón disparador para evitar consultas automáticas
                if st.button("📄 Generar Reporte en PDF", use_container_width=True, key="btn_trigger_pdf"):
                    with st.spinner("Procesando PDF..."):
                        
                        # 2. La consulta a la BD SOLO ocurre AQUÍ tras hacer clic
                        datos_l_pdf = generar_reporte_lotes_pdf(txt_universal, f_stock, f_vencimiento, f_estado, usuario_actual)
                        
                        if datos_l_pdf:
                            # 3. Si hay datos, habilitamos el botón nativo de descarga
                            st.download_button(
                                label="⬇️ Descargar Archivo PDF",
                                data=datos_l_pdf,
                                file_name=f"SIALMED_Inventario_Lotes_{f_estado}.pdf",
                                mime="application/pdf",
                                use_container_width=True,
                                key="btn_download_lotes_pdf"
                            )
                        else:
                            st.warning("No hay datos para el filtro seleccionado.")
        

        contenedor_guardar_modificacion = st.empty()

        # ==============================================================================
        # 📟 MOTOR DE PAGINACIÓN LOCAL (De 50 en 50)
        # ==============================================================================
        REGISTROS_POR_PAGINA = 50
        total_paginas = math.ceil(total_filtrados / REGISTROS_POR_PAGINA) if total_filtrados > 0 else 1

        if st.session_state["pagina_lotes"] > total_paginas:
            st.session_state["pagina_lotes"] = 1

        inicio = (st.session_state["pagina_lotes"] - 1) * REGISTROS_POR_PAGINA
        fin = inicio + REGISTROS_POR_PAGINA
        df_pagina_actual = df_lotes.iloc[inicio:fin]

        # Traemos los nombres de insumos disponibles en la BD para el Selectbox editable
        lista_insumos_bd = crud_ins.obtener_insumos(solo_activos=False, opt_estado='TODOS') # <<- ACORDATE DE VERIFICAR ESTO
        nombres_insumos_opciones = [ins.nombre for ins in lista_insumos_bd] if lista_insumos_bd else []

        # ==============================================================================
        # 📉 RENDIMIENTO EN PANTALLA (GRID CONFIGURADO)
        # ==============================================================================
        st.write("")
        
        if puede_editar:
            st.caption("💡 **Modo Operador:** Puede corregir el código de lote, reasignar el insumo base, ajustar estanterías.")

            # Base de configuración de columnas para st.data_editor
            config_columnas = {
                "ID": st.column_config.NumberColumn(format="%d", width=40),
                "INSUMO ASOCIADO": st.column_config.SelectboxColumn(options=nombres_insumos_opciones, width="medium", required=True),
                "CÓDIGO DE LOTE": st.column_config.TextColumn(width="medium", required=True),
                "CLASIFICACIÓN VED": st.column_config.TextColumn(label='VED', width="small"),
                "STOCK DISPONIBLE": st.column_config.NumberColumn(label='STOCK DISP.', format="%d unds.", width="small"),
                "FECHA VENCIMIENTO": st.column_config.DateColumn(label="F. VENCIMIENTO", format="DD/MM/YYYY", width=120),
                "UBICACIÓN FÍSICA": st.column_config.TextColumn(width="medium"),
                "ESTADO": st.column_config.TextColumn(width='small'),
            }

            # Si estamos visualizando registros de baja, añadimos la configuración para la columna de motivos
            if opt_estado != "ACTIVOS":
                config_columnas["MOTIVO DESACTIVACIÓN"] = st.column_config.TextColumn(label="MOTIVO DE DESACTIVACION", width="medium")

            grilla_editada = st.data_editor(
                df_pagina_actual,
                use_container_width=True,
                hide_index=True,
                height=380,
                key="editor_lotes_grilla",
                disabled=["ID", "CLASIFICACIÓN VED", "STOCK DISPONIBLE", 'ESTADO'],
                column_config=config_columnas
            )

            # Sincronización y persistencia de ediciones masivas utilizando los IDs reales
            estado_edicion = st.session_state.get("editor_lotes_grilla", {})
            cambios_detectados = estado_edicion.get("edited_rows", {}) if isinstance(estado_edicion, dict) else {}
            
            if cambios_detectados and not df_pagina_actual.empty:
                with contenedor_guardar_modificacion:
                    st.warning("⚠️ Hay modificaciones de lotes en la grilla pendientes por subir.")
                    
                    diccionario_cambios_bd = {}
                    for indice_fila, modificaciones in cambios_detectados.items():
                        id_real_bd = df_pagina_actual.iloc[int(indice_fila)]["ID"]
                        
                        # Mapeamos internamente el nombre de la grilla ("MOTIVO DESACTIVACIÓN") 
                        # al atributo real del modelo de SQLModel ("motivo_desactivacion")
                        if "MOTIVO DESACTIVACIÓN" in modificaciones:
                            modificaciones["motivo_desactivacion"] = modificaciones.pop("MOTIVO DESACTIVACIÓN")
                            
                        diccionario_cambios_bd[str(id_real_bd)] = modificaciones
                    
                    c_save, _ = st.columns([1.5, 4])
                    with c_save:
                        if st.button("💾 GUARDAR CAMBIOS DE LOTES", use_container_width=True, type="primary"):
                            resultado = crud_l.actualizar_registros_lotes_masivo(diccionario_cambios_bd)              
                            if resultado == True:
                                st.success("✔️ ¡Lotes actualizados con éxito!")
                                time.sleep(1.2)
                                st.rerun()
                            st.error(resultado)
        else:
            # Configuración de solo lectura
            config_lectura = {
                "ID": st.column_config.NumberColumn(format="%d"),
                "STOCK DISPONIBLE": st.column_config.NumberColumn(format="%d u.")
            }
            if opt_estado != "ACTIVOS":
                config_lectura["MOTIVO DESACTIVACIÓN"] = st.column_config.TextColumn(label="MOTIVO DE BAJA")

            st.dataframe(
                df_pagina_actual,
                use_container_width=True,
                hide_index=True,
                height=380,
                column_config=config_lectura
            )

        if df_pagina_actual.empty:
            st.info("ℹ️ No existen lotes en la base de datos que coincidan con los filtros aplicados.")

        # ==============================================================================
        # 📟 BOTONES DE CONTROL DE PÁGINAS (LOTES)
        # ==============================================================================
        st.write("")
        c_pag1, c_pag2, c_pag3 = st.columns([1.5, 2, 1.5])
        
        with c_pag2:
            pag_vis = st.session_state["pagina_lotes"]
            st.markdown(f"<p style='text-align:center; color:gray;'>Página <b>{pag_vis}</b> de {total_paginas}</p>", unsafe_allow_html=True)
            
        with c_pag1:
            if st.button("⬅️ Anterior", use_container_width=True, key="btn_l_ant", disabled=(st.session_state["pagina_lotes"] == 1)):
                st.session_state["pagina_lotes"] -= 1
                st.rerun()
                
        with c_pag3:
            if st.button("Siguiente ➡️", use_container_width=True, key="btn_l_sig", disabled=(st.session_state["pagina_lotes"] >= total_paginas)):
                st.session_state["pagina_lotes"] += 1
                st.rerun()

        

    except Exception as e:
            print(f"Error crítico en la vista de Lotes: {e}")
            st.error(f"Error crítico en la vista de Lotes: {e}")
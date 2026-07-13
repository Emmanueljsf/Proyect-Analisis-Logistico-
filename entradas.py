import streamlit as st
import pandas as pd  
import CRUDs.crud_lotes_entradas as crud_le  
import CRUDs.crud_insumos as crud_i  # 💡 Importamos para alimentar las opciones de insumos en la celda
from insumos1 import usuario_tiene_permiso_escritura
from models import Rol
from reportes import generar_reporte_entradas_excel, generar_reporte_entradas_pdf
from datetime import date, timedelta
import time
import math

@st.dialog("📥 Registrar Entrada de Cargamento")
def modal_registro_entrada():
    """
    Ventana flotante institucional encargada de recolectar los metadatos
    de las actas de ingreso y las propiedades del lote del fabricante.
    """
    try:
        st.markdown("<p style='color:gray;'>Ingrese los datos del acta de recepción y el lote del fabricante.</p>", unsafe_allow_html=True)
        
        if not usuario_tiene_permiso_escritura():
            st.error("🛑 Acceso denegado. No tiene permisos para realizar esta acción.")
            return

        lista_insumos = crud_i.obtener_insumos(solo_activos=True)
        if not lista_insumos:
            st.error("⚠️ No hay insumos registrados en el catálogo base.")
            return

        dict_insumos = {f"{i.nombre} [{i.clasificacion_ved}]".upper(): i.id_insumo for i in lista_insumos}
        insumo_seleccionado = st.selectbox("Seleccione el Insumo Médico *", list(dict_insumos.keys()))
        id_insumo_target = dict_insumos[insumo_seleccionado]
        
        c1, c2 = st.columns(2)
        with c1:
            txt_lote = st.text_input("Código de Lote *", placeholder="Ej: LOT-2026A")
            f_pedido = st.date_input("Fecha de Pedido *", max_value=date.today(), format="DD/MM/YYYY")
            f_vence = st.date_input("Fecha de Vencimiento del Lote *", min_value=date.today()+timedelta(days=1), format="DD/MM/YYYY")
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
                        codigo_lote=txt_lote,
                        fecha_vencimiento=f_vence,
                        ubicacion_fisica=txt_ubica,
                        cantidad=num_cantidad,
                        id_usuario=st.session_state.get("user_id", 1), 
                        fecha_pedido=f_pedido
                    )
                    if exito==True:
                        st.success("✔️ Entrada y lote registrados exitosamente.")
                        time.sleep(1.5)
                        st.rerun()
                    else:
                        st.error(exito)
        with c_btn2:
            if st.button("CANCELAR", use_container_width=True): 
                st.rerun()

    except Exception as e:
            print(f"🛑 Error crítico en el formulario de registro de entradas: {e}")


def Vista_Entradas():
    """
    Renderiza el historial de actas de entrada de SIAL-MED.
    Aplica las variables exactas del modelo (fecha_recepcion, VALIDO/ANULADO, username)
    """
    try:
        if "pagina_entradas" not in st.session_state:
            st.session_state["pagina_entradas"] = 1

        puede_editar = usuario_tiene_permiso_escritura()
        contenedor_titulo = st.empty()

        # ==============================================================================
        # LAS 4 BARRAS DE BÚSQUEDA CORREGIDAS
        # ==============================================================================
        with st.expander("🔍 Historial y Auditoría de Entradas (Filtros en Backend)", expanded=True):
            f_col1, f_col2, f_col3, f_col4 = st.columns([2.5, 1.2, 1.8, 1.2])
            
            with f_col1:
                txt_universal = st.text_input(
                    "Buscador Universal:", 
                    placeholder="Insumo, VED o código de lote...", 
                    key="fe_universal"
                ).strip()
                
            with f_col2:
                txt_rango_cantidad = st.text_input(
                    "Cantidad (Min-Max):", 
                    placeholder="Ej: 100-500 o 50", 
                    key="fe_cantidad"
                ).strip()
                
            with f_col3:
                # Filtrado basado en la propiedad fecha_recepcion
                rango_fechas = st.date_input(
                    "Fecha de Recepción:", 
                    value=[date.today()-timedelta(days=121), date.today()],
                    format="DD/MM/YYYY", 
                    key="fe_fecha"
                )
                
            with f_col4:
                # Los estados reales mapeados del modelo
                opt_estado = st.selectbox(
                    "Estado Acta:", 
                    ["VALIDO", "ANULADO", "TODOS"], 
                    index=0, 
                    key="fe_estado"
                )

        # ==============================================================================
        # CONSULTA AL BACKEND 
        # ==============================================================================
        REGISTROS_POR_PAGINA = 100
        
        tuplas_entradas, total_registros_bd = crud_le.obtener_entradas_filtradas_paginadas(
            txt_universal=txt_universal,
            txt_rango_cantidad=txt_rango_cantidad,
            rango_fechas=rango_fechas,
            opt_estado=opt_estado,
            pagina_actual=st.session_state["pagina_entradas"],
            registros_por_pagina=REGISTROS_POR_PAGINA
        )

        filas_raw = []
        if tuplas_entradas:
            for entrada_obj, lote_obj, insumo_obj in tuplas_entradas:
                ved = insumo_obj.clasificacion_ved.value if hasattr(insumo_obj.clasificacion_ved, "value") else insumo_obj.clasificacion_ved
                ved_txt = 'VITAL' if ved=='V' else 'ESENCIAL' if ved=='E' else 'DESEABLE'
                nombre_completo = f"{entrada_obj.usuario.nombres.split()[0]} {entrada_obj.usuario.apellidos.split()[0]}"
                
                filas_raw.append({
                    "ID": entrada_obj.id_entrada,
                    "INSUMO MÉDICO": insumo_obj.nombre,
                    "CÓDIGO LOTE": lote_obj.codigo_lote,
                    "CLASIFICACIÓN VED": ved_txt,
                    "CANTIDAD": entrada_obj.cantidad,
                    "FECHA PEDIDO": entrada_obj.fecha_pedido,
                    "FECHA RECEPCIÓN": entrada_obj.fecha_recepcion,
                    'TIEMPO ENTREGA': entrada_obj.tiempo_entrega_dias, 
                    "RESPONSABLE": nombre_completo,
                    "ESTADO": entrada_obj.estado
                })

        # Construcción exacta para que si está vacío no pinte registros fantasmas
        if filas_raw:
            df_entradas = pd.DataFrame(filas_raw)
        else:
            df_entradas = pd.DataFrame(columns=["ID", "INSUMO MÉDICO", "CÓDIGO DE LOTE", "CLASIFICACIÓN VED", "CANTIDAD", "FECHA RECEPCIÓN", "RESPONSABLE", "ESTADO"])

        # Renderizado del título informando el universo total histórico coincidente
        contenedor_titulo.markdown(
            f"<h2 style='margin-bottom: 0;'>📥 Control de Entradas de Inventario ({total_registros_bd} registros filtrados)</h2>", 
            unsafe_allow_html=True
        )

    # BOTONES DE REPORTE Y FORMULARIO DE REGISTRO
        col_excel, col_pdf, _, col_btn = st.columns([2, 2, 1, 2])
        with col_btn:
            if puede_editar and st.button("📥 NUEVA ENTRADA", use_container_width=True, type="primary"):
                modal_registro_entrada()

        if st.session_state.get("user_rol") == Rol.Administrador:
            usuario_actual = st.session_state.get("user_nombre_completo", "ADMINISTRADOR SIAL-MED")
            
            f_cantidad = txt_rango_cantidad if 'txt_rango_cantidad' in locals() else ""
            f_fechas = rango_fechas if 'rango_fechas' in locals() else None
            f_estado = opt_estado if 'opt_estado' in locals() else "VALIDO"
                        
            # SECCIÓN: REPORTE EN EXCEL
            with col_excel:
                # 1. Creamos el botón disparador para evitar consultas automáticas
                if st.button("📊 Generar Reporte en Excel (.xlsx)", use_container_width=True, key="btn_trigger_excel"):
                    with st.spinner("Procesando Excel..."):
                        
                        # 2. La consulta a la BD SOLO ocurre AQUÍ tras hacer clic
                        datos_l_excel = generar_reporte_entradas_excel(txt_universal, f_cantidad, f_fechas, f_estado, usuario_actual)
                        
                        if datos_l_excel:
                            # 3. Si hay datos, habilitamos el botón nativo de descarga
                            st.download_button(
                                label="⬇️ Descargar Archivo Excel",
                                data=datos_l_excel,
                                file_name=f"SIALMED_Inventario_Entradas_{f_estado}_{date.today()}.xlsx",
                                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                                use_container_width=True,
                                key="btn_download_entradas_excel"
                            )
                        else:
                            st.warning("No hay datos para el filtro seleccionado.")

            # SECCIÓN: REPORTE EN PDF
            with col_pdf:
                # 1. Creamos el botón disparador para evitar consultas automáticas
                if st.button("📄 Generar Reporte en PDF", use_container_width=True, key="btn_trigger_pdf"):
                    with st.spinner("Procesando PDF..."):
                        
                        # 2. La consulta a la BD SOLO ocurre AQUÍ tras hacer clic
                        datos_l_pdf = generar_reporte_entradas_pdf(txt_universal, f_cantidad, f_fechas, f_estado, usuario_actual)
                        
                        if datos_l_pdf:
                            # 3. Si hay datos, habilitamos el botón nativo de descarga
                            st.download_button(
                                label="⬇️ Descargar Archivo PDF",
                                data=datos_l_pdf,
                                file_name=f"SIALMED_Inventario_Entradas_{f_estado}_{date.today()}.pdf",
                                mime="application/pdf",
                                use_container_width=True,
                                key="btn_download_entradas_pdf"
                            )
                        else:
                            st.warning("No hay datos para el filtro seleccionado.")
        
        
        st.write("")
        contenedor_guardar_modificacion = st.empty()

        total_paginas = math.ceil(total_registros_bd / REGISTROS_POR_PAGINA) if total_registros_bd > 0 else 1

        lista_insumos_bd = crud_i.obtener_insumos(solo_activos=False, opt_estado='TODOS')
        nombres_insumos_opciones = [ins.nombre for ins in lista_insumos_bd] if lista_insumos_bd else []

        # ==============================================================================
        # 📉 RENDERIZADO DE LA GRILLA (EDICIÓN AMPLIA)
        # ==============================================================================
        if df_entradas.empty:
            st.info("ℹ️ No existen entradas registradas que coincidan con los criterios seleccionados.")
        else:
            if puede_editar:
                st.caption("💡 **Modo Operador:** Puede modificar las cantidades, reasignar el insumo o cambiar el estado del acta directamente en la grilla.")

                grilla_editada = st.data_editor(
                    df_entradas,
                    use_container_width=True,
                    hide_index=True,
                    height=380,
                    key="editor_entradas_grilla",
                    disabled=["ID", "CLASIFICACIÓN VED", "RESPONSABLE", "FECHA RECEPCIÓN", 'TIEMPO ENTREGA'], 
                    column_config={
                        "ID": st.column_config.NumberColumn(format="%d", width="small"),
                        "INSUMO MÉDICO": st.column_config.SelectboxColumn(options=nombres_insumos_opciones, width="medium", required=True),
                        "CÓDIGO LOTE": st.column_config.TextColumn(label='CÓD. DE LOTE', width=150),
                        "CLASIFICACIÓN VED": st.column_config.TextColumn(label='VED', width="small"),
                        "CANTIDAD": st.column_config.NumberColumn(label='CANT.', format="%d unds.", width="small", required=True, min_value=1),
                        "FECHA PEDIDO": st.column_config.DateColumn(label="F. PEDIDO", format="DD-MM-YYYY", width=110),
                        "FECHA RECEPCIÓN": st.column_config.DateColumn(label="F. RECEPCIÓN", format="DD-MM-YYYY HH:MM", width=120),
                        "TIEMPO ENTREGA": st.column_config.NumberColumn(label='T. ENTREGA.', format="%d días.", width="small"),
                        "RESPONSABLE": st.column_config.TextColumn(width="medium"),
                        "ESTADO": st.column_config.SelectboxColumn(options=["VALIDO", "ANULADO"], width="small", required=True)
                    }
                )

                estado_edicion = st.session_state.get("editor_entradas_grilla", {})
                cambios_detectados = estado_edicion.get("edited_rows", {}) if isinstance(estado_edicion, dict) else {}
                
                if cambios_detectados:
                    with contenedor_guardar_modificacion:
                        st.warning("⚠️ Hay modificaciones locales en la tabla de entradas pendientes por subir a la Base de Datos.")
                        
                        diccionario_cambios_bd = {}
                        for indice_fila, modificaciones in cambios_detectados.items():
                            id_real_bd = df_entradas.iloc[int(indice_fila)]["ID"]                        
                            diccionario_cambios_bd[str(id_real_bd)] = modificaciones
                        
                        c_save, _ = st.columns([1.5, 4])
                        with c_save:
                            if st.button("💾 GUARDAR CAMBIOS DE ENTRADAS", use_container_width=True, type="primary"):
                                resultado = crud_le.actualizar_registros_entradas_masivo(diccionario_cambios_bd)
                                if resultado == True:
                                    st.success("✔️ ¡Historial de actas actualizado con éxito!")
                                    time.sleep(1.2)
                                    st.rerun()
                                st.error(resultado)
            else:
                st.dataframe(
                    df_entradas,
                    use_container_width=True,
                    hide_index=True,
                    height=380,
                    column_config={
                        "ID": st.column_config.NumberColumn(format="%d"),
                        "CANTIDAD": st.column_config.NumberColumn(format="%d u.")
                    }
                )

        # ==============================================================================
        # 📟 BOTONES DE CONTROL DE PÁGINAS
        # ==============================================================================
        st.write("")
        _, c_pag1, c_pag2, c_pag3, _ = st.columns([2, 1.5, 2, 1.5, 2])
        
        with c_pag2:
            pag_vis = st.session_state["pagina_entradas"]
            st.markdown(f"<p style='text-align:center; color:gray;'>Pág <b>{pag_vis}</b> de {total_paginas}</p>", unsafe_allow_html=True)
            
        with c_pag1:
            if st.button("⬅️ Anterior", use_container_width=True, key="btn_e_ant", disabled=(st.session_state["pagina_entradas"] == 1)):
                st.session_state["pagina_entradas"] -= 1
                st.rerun()
                
        with c_pag3:
            if st.button("Siguiente ➡️", use_container_width=True, key="btn_e_sig", disabled=(st.session_state["pagina_entradas"] >= total_paginas)):
                st.session_state["pagina_entradas"] += 1
                st.rerun()
    
    except Exception as e:
            print(f"Error crítico en la vista de entradas: {e}")
            return [], 0
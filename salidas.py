import streamlit as st
import pandas as pd
import CRUDs.crud_salidas as crud_salidas
from registro_salidas import modal_registro_salida_fefo
from reportes_salidas import generar_reporte_salidas_excel, generar_reporte_salidas_pdf
from bd.models import Rol
from insumos1 import usuario_tiene_permiso_escritura
from datetime import date, timedelta
import time
import math
import base64

def Vista_Salidas():
    try:
        """
        PANEL DE CONTROL DE DESPACHOS DE SALIDAS - SIAL-MED
        Doble Grilla Editora Interactiva (Maestra-Detalle) optimizada para st.data_editor.
        """
        if "pagina_salidas" not in st.session_state:
            st.session_state["pagina_salidas"] = 1
        if "hoja_ruta_despacho" not in st.session_state:
            st.session_state["hoja_ruta_despacho"] = None

        # Interceptor de Guía de recolección FEFO (Mantenido intacto)
        if st.session_state["hoja_ruta_despacho"] is not None:
            st.title("📦 Guía de Extracción en Almacén (Ruta FEFO)")
            st.success("🎉 ¡Movimiento de Inventario Consolidado Exitosamente!")
            
            # DESCARGA DEL REPORTE DE VENCIMIENTO
            acta_pdf = st.session_state.get("acta_perdida_pendiente_pdf")
            if acta_pdf is not None:
                orden_pdf = st.session_state.get("acta_perdida_pendiente_orden", "acta_perdida")
                
                
                # Inyección de Script HTML para forzar descarga automática en el navegador
                b64_pdf = base64.b64encode(acta_pdf).decode('utf-8')
                js_download_script = f"""
                    <a id="download_link" href="data:application/pdf;base64,{b64_pdf}" download="acta_perdida_lote_{orden_pdf}.pdf" style="display:none;"></a>
                    <script>
                        document.getElementById('download_link').click();
                    </script>
                """
                st.components.v1.html(js_download_script, height=0)
                st.success("✔️ Se ha descargado el Acta Oficial de Pérdida y ha sido enviada automáticamente a tu carpeta de descargas.")
                st.info("Por favor, verifique su barra de descargas, proceda a imprimirla y recabar las firmas correspondientes.")
                st.write("---")

            with st.container(border=True):
                st.markdown("### 📋 GUÍA DE EXTRACCIÓN EN ESTANTES PARA EL OPERARIO")
                df_ruta = pd.DataFrame(st.session_state["hoja_ruta_despacho"])
                st.dataframe(df_ruta, use_container_width=True, hide_index=True)
                
                if st.button("🏁 CONFIRMAR EXTRACCIÓN Y VOLVER", use_container_width=True):
                    st.session_state["hoja_ruta_despacho"] = None
                    st.session_state["acta_perdida_pendiente_pdf"] = None
                    st.session_state["acta_perdida_pendiente_orden"] = None
                    st.rerun()
            return

        puede_editar = usuario_tiene_permiso_escritura()
        contenedor_titulo = st.empty()

        # ==============================================================================
        # 🎛️ PANEL DE FILTROS
        # ==============================================================================
        with st.expander("🔍 Historial y Auditoría de Salidas (Filtros en Backend)", expanded=True):
            f_col1, f_col2, f_col3 = st.columns([3, 1.5, 1])
            
            with f_col1:
                txt_universal = st.text_input(
                    "Buscador Universal:", 
                    placeholder="Paciente, Destino o N° de Orden...", 
                    key="fs_universal"
                ).strip()
                
            with f_col2:
                rango_fechas = st.date_input(
                    "Fecha de Salida:", 
                    value=[date.today()-timedelta(days=15), date.today()], 
                    format="DD/MM/YYYY", 
                    key="fs_fecha"
                )
                
            with f_col3:
                opt_estado = st.selectbox(
                    "Estado salida:", 
                    ["VALIDO", "ANULADO", "TODOS"], 
                    index=0, 
                    key="fs_estado"
                )


        # ==============================================================================
        # CONSULTA MAESTRA AL BACKEND PAGINADA
        # ==============================================================================
        REGISTROS_POR_PAGINA = 100
        
        lista_salidas, total_registros = crud_salidas.obtener_salidas_filtradas_paginadas(
            txt_universal=txt_universal,
            rango_fechas=rango_fechas,
            opt_estado=opt_estado,
            pagina_actual=st.session_state["pagina_salidas"],
            registros_por_pagina=REGISTROS_POR_PAGINA
        )

        filas_maestro = []
        for salida in lista_salidas:
            nombre_completo = f"{salida.usuario.nombres.split()[0]} {salida.usuario.apellidos.split()[0]}"
            
            filas_maestro.append({
                "VER": False,  # Tu columna exacta de la captura de pantalla
                "ID": salida.id_salida,
                "ORDEN DE SALIDA": salida.orden_salida,
                "RAZÓN DE SALIDA": salida.razon_salida,
                "FECHA": salida.fecha,
                "DESTINO / PACIENTE": salida.paciente_destino,
                "RESPONSABLE": nombre_completo,
                "ESTADO": salida.estado.value if hasattr(salida.estado, "value") else salida.estado
            })

        if filas_maestro:
            df_maestro_final = pd.DataFrame(filas_maestro)
        else:
            df_maestro_final = pd.DataFrame(columns=["VER", "ID", "ORDEN DE SALIDA", "FECHA", "DESTINO / PACIENTE", "RAZÓN DE SALIDA", "RESPONSABLE", "ESTADO"])

        contenedor_titulo.markdown(
            f"<h2 style='margin-bottom: 0;'>📦 Control de Órdenes y Salidas ({total_registros} registros filtrados)</h2>", 
            unsafe_allow_html=True
        )

        col_rep1, col_rep2, _, f_col_btn = st.columns([2, 2, 1, 2])

        with f_col_btn:
                if puede_editar and st.button("📤 NUEVA SALIDA (FEFO)", use_container_width=True, type="primary"):
                    modal_registro_salida_fefo()

        if st.session_state.get("user_rol") == Rol.Administrador:
            
            usuario_actual = st.session_state.get("user_nombre_completo", "OPERADOR SIAL-MED")
            with col_rep1:
                if st.button("📊 Generar Reporte en Excel (.xlsx)", use_container_width=True):
                    with st.spinner("Procesando Excel..."):
                        # La consulta a la BD SOLO ocurre AQUÍ, tras hacer clic
                        data_xlsx = generar_reporte_salidas_excel(
                            txt_universal, rango_fechas, opt_estado, 
                            usuario_actual
                        )
                        
                        if data_xlsx:
                            st.download_button(
                                label="⬇️ Descargar Archivo Excel",
                                data=data_xlsx,
                                file_name=f"salidas_estructuradas_{date.today()}.xlsx",
                                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                                use_container_width=True
                            )
                        else:
                            st.warning("No hay datos para el filtro seleccionado.")

            with col_rep2:
                if st.button("📄 Generar Reporte en PDF", use_container_width=True):
                    with st.spinner("Procesando PDF..."):
                        # La consulta a la BD SOLO ocurre AQUÍ, tras hacer clic
                        data_pdf = generar_reporte_salidas_pdf(
                            txt_universal, rango_fechas, opt_estado, 
                            usuario_actual
                        )
                        
                        if data_pdf:
                            st.download_button(
                                label="⬇️ Descargar Archivo PDF",
                                data=data_pdf,
                                file_name=f"auditoria_salidas_{date.today()}.pdf",
                                mime="application/pdf",
                                use_container_width=True
                            )
                        else:
                            st.warning("No hay datos para el filtro seleccionado.")

        st.write("")
        contenedor_guardar_modificacion = st.empty()

        # ==============================================================================
        # 📝 TABLA MAESTRA CON LA COLUMNA 'VER' 
        # ==============================================================================
        st.markdown("##### 🧾 Actas de Salidas Registradas (Marque la casilla 'VER' para inspeccionar medicamentos)")
        
        # 1. Recuperamos el ID que está activo actualmente en el sistema
        if "id_salida_activa" not in st.session_state:
            st.session_state["id_salida_activa"] = None

        # 2. Sincronizamos el DataFrame visual: forzamos True SOLO en la fila que coincide con el ID activo
        if not df_maestro_final.empty:
            df_maestro_final["VER"] = df_maestro_final["ID"] == st.session_state["id_salida_activa"]

        grilla_maestra_editada = st.data_editor(
            df_maestro_final,
            use_container_width=True,
            hide_index=True,
            height=370,
            key="editor_maestro_salidas",
            disabled=["ID", "FECHA", "RAZÓN DE SALIDA", "RESPONSABLE"] if puede_editar else df_maestro_final.columns.tolist(),
            column_config={
                "VER": st.column_config.CheckboxColumn(width="small", help="Marque para cargar medicamentos"),
                "ID": st.column_config.NumberColumn(label='ID', format="%d", width="small"),
                "FECHA": st.column_config.DatetimeColumn(format="DD/MM/YYYY HH:mm", width="medium"),
                "ORDEN DE SALIDA": st.column_config.TextColumn(width="medium", required=True),
                "DESTINO / PACIENTE": st.column_config.TextColumn(width="medium", required=True),
                "RAZÓN DE SALIDA": st.column_config.TextColumn(width="medium", required=True),
                "RESPONSABLE": st.column_config.TextColumn(width="medium"),
                "ESTADO": st.column_config.SelectboxColumn(options=["VALIDO", "ANULADO"], width="small", required=True)
            }
        )

        # ==============================================================================
        # 🔄 INTERCEPTOR DE CLIC: GARANTIZA SELECCIÓN ÚNICA Y CONTROL FLUJO
        # ==============================================================================
        cambios_maestro_raw = st.session_state.get("editor_maestro_salidas", {}).get("edited_rows", {})

        id_salida_target = st.session_state["id_salida_activa"]

        for indice_str, diccionario_cambios in cambios_maestro_raw.items():
            if "VER" in diccionario_cambios:
                idx = int(indice_str)
                if idx < len(df_maestro_final):
                    # CASO A: El usuario marcó una casilla nueva como True
                    if diccionario_cambios["VER"] is True:
                        nuevo_id = df_maestro_final.iloc[idx]["ID"]
                        if nuevo_id != st.session_state["id_salida_activa"]:
                            st.session_state["id_salida_activa"] = nuevo_id
                            st.rerun()  # Reinicia para limpiar cualquier otra casilla marcada
                    
                    # CASO B: El usuario desmarcó la casilla que ya estaba activa (vuelve a False)
                    elif diccionario_cambios["VER"] is False:
                        if df_maestro_final.iloc[idx]["ID"] == st.session_state["id_salida_activa"]:
                            st.session_state["id_salida_activa"] = None
                            st.rerun()

        # Vinculamos la variable de extracción de detalles al estado oficial consolidado
        id_salida_target = st.session_state["id_salida_activa"]

        # Paginación
        total_paginas = math.ceil(total_registros / REGISTROS_POR_PAGINA) if total_registros > 0 else 1
        c_pag1, c_pag2, c_pag3 = st.columns([1.5, 2, 1.5])
        with c_pag2:
            st.markdown(f"<p style='text-align:center; color:gray; font-size:12px;'>Pág <b>{st.session_state['pagina_salidas']}</b> de {total_paginas}</p>", unsafe_allow_html=True)
        with c_pag1:
            if st.button("⬅️ Anterior", use_container_width=True, key="btn_s_ant", disabled=(st.session_state["pagina_salidas"] == 1)):
                st.session_state["pagina_salidas"] -= 1
                st.rerun()
        with c_pag3:
            if st.button("Siguiente ➡️", use_container_width=True, key="btn_s_sig", disabled=(st.session_state["pagina_salidas"] >= total_paginas)):
                st.session_state["pagina_salidas"] += 1
                st.rerun()

        st.write("---")

        

        df_para_editar = pd.DataFrame() 
        
        if id_salida_target is not None:
            st.markdown(f"##### 💊 Insumos Médicos Despachados en la Aalida seleccionada: `#{id_salida_target}`")
            print(id_salida_target)
            
            # Invocamos la función de tu backend
            tuplas_detalles = crud_salidas.obtener_detalles_insumos_por_acta(id_salida_target)
            
            filas_detalle = []
            for tupla in tuplas_detalles:
                # tupla[0] = id_detalle
                # tupla[1] = id_salida
                # tupla[2] = nombre insumo
                # tupla[3] = VED (str)
                # tupla[4] = codigo_lote (str)
                # tupla[5] = cantidad (int)
                
                ved = tupla[3] 
                
                filas_detalle.append({
                    "ID DETALLE": tupla[0],
                    "INSUMO MÉDICO": tupla[2],
                    "CÓDIGO DE LOTE": tupla[4], # Corregido de tupla[3] a tupla[4]
                    'VED': 'VITAL' if ved == 'V' else 'ESENCIAL' if ved == 'E' else 'DESEABLE',
                    "CANTIDAD": tupla[5]       # Corregido de tupla[4] a tupla[5]
                })
            
            if filas_detalle:
                df_para_editar = pd.DataFrame(filas_detalle)
                
                grilla_detalles_editada = st.data_editor(
                    df_para_editar,
                    use_container_width=True,
                    hide_index=True,
                    key="editor_detalles",
                    disabled=["ID DETALLE", "INSUMO MÉDICO", 'VED', "CÓDIGO DE LOTE"] if puede_editar else df_para_editar.columns.tolist(),
                    column_config={
                        "ID DETALLE": st.column_config.NumberColumn(format="%d", width="small"),
                        "CANTIDAD": st.column_config.NumberColumn(format="%d unds.", width="small", required=True, min_value=0)
                    }
                )
            else:
                st.info("ℹ️ Esta orden de salida no contiene renglones de insumos registrados.")
        else:
            st.info("💡 Por favor, marque la casilla de la columna 'VER' en cualquier fila de la tabla superior para inspeccionar y auditar sus insumos correspondientes.")

        # ==============================================================================
        # 💾 FILTRADO AUTOMÁTICO (Evita que la columna 'VER' active el botón de guardar)
        # ==============================================================================
        estado_detalle_widget = st.session_state.get("editor_detalles", {})
        cambios_detalle = estado_detalle_widget.get("edited_rows", {}) if isinstance(estado_detalle_widget, dict) else {}

        # Filtramos limpiando la columna "VER" para no enviarla al CRUD y que no levante alertas falsas
        cambios_maestro_reales = {}
        for idx_m, modifs in cambios_maestro_raw.items():
            modifs_sin_virtual = {k: v for k, v in modifs.items() if k != "VER"}
            if modifs_sin_virtual:  # Si de verdad editó campos como Oficio, Paciente o Estado
                cambios_maestro_reales[idx_m] = modifs_sin_virtual

        # El botón se renderiza ÚNICAMENTE ante ediciones reales en base de datos
        if puede_editar and (cambios_maestro_reales or cambios_detalle):
            with contenedor_guardar_modificacion:
                st.warning("⚠️ Modificaciones locales detectadas en la información. Guarde para consolidar la orden y stock.")
                
                c_save, _ = st.columns([1.5, 4])
                with c_save:
                    if st.button("💾 GUARDAR CAMBIOS DE SALIDAS", use_container_width=True, type="primary"):
                        resultado = crud_salidas.actualizar_registros_salidas_masivo(
                            cambios_cabecera=cambios_maestro_reales,
                            cambios_detalle=cambios_detalle,
                            df_maestro=df_maestro_final,
                            df_detalle=df_para_editar
                        )
                        
                        if resultado is True:
                            st.success("✔️ ¡Datos actualizados con éxito!")
                            time.sleep(1.3)
                            st.rerun()
                        else:
                            st.error(resultado)

    except Exception as e:
        print(f"Error crítico en la vista de salidas: {e}")
        return st.error(f"Error crítico en la vista de salidas: {e}")
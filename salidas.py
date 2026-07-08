import streamlit as st
import pandas as pd
import CRUDs.crud_salidas as crud_salidas
from registro_salidas import modal_registro_salida_fefo
from insumos1 import usuario_tiene_permiso_escritura
from datetime import date
import time
import math

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
            with st.container(border=True):
                st.markdown("### 📋 GUÍA DE EXTRACCIÓN EN ESTANTES PARA EL OPERARIO")
                df_ruta = pd.DataFrame(st.session_state["hoja_ruta_despacho"])
                st.dataframe(df_ruta, use_container_width=True, hide_index=True)
                if st.button("🏁 CONFIRMAR EXTRACCIÓN Y VOLVER", use_container_width=True):
                    st.session_state["hoja_ruta_despacho"] = None
                    st.rerun()
            return

        puede_editar = usuario_tiene_permiso_escritura()
        contenedor_titulo = st.empty()

        # ==============================================================================
        # 🎛️ PANEL DE FILTROS CENTRALIZADOS (Backend)
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
                    "Fecha de Despacho:", 
                    value=[date(2024, 1, 1), date(2030, 12, 31)], 
                    format="DD/MM/YYYY", 
                    key="fs_fecha"
                )
                
            with f_col3:
                opt_estado = st.selectbox(
                    "Estado Acta:", 
                    ["VALIDO", "ANULADO", "TODOS"], 
                    index=0, 
                    key="fs_estado"
                )


        # ==============================================================================
        # CONSULTA MAESTRA AL BACKEND PAGINADA
        # ==============================================================================
        REGISTROS_POR_PAGINA = 50
        
        lista_actas_bd, total_registros_bd = crud_salidas.obtener_salidas_filtradas_paginadas(
            txt_universal=txt_universal,
            rango_fechas=rango_fechas,
            opt_estado=opt_estado,
            pagina_actual=st.session_state["pagina_salidas"],
            registros_por_pagina=REGISTROS_POR_PAGINA
        )

        filas_maestro = []
        for acta in lista_actas_bd:
            responsable = acta.usuario.username if acta.usuario else "Sistema"
            
            filas_maestro.append({
                "VER": False,  # Tu columna exacta de la captura de pantalla
                "ID": acta.id_salida,
                "ORDEN DE SALIDA": acta.orden_salida,
                "FECHA": acta.fecha,
                "DESTINO / PACIENTE": acta.paciente_destino,
                "RAZÓN LOGÍSTICA": acta.razon_salida,
                "RESPONSABLE": responsable,
                "ESTADO": acta.estado.value if hasattr(acta.estado, "value") else acta.estado
            })

        if filas_maestro:
            df_maestro_final = pd.DataFrame(filas_maestro)
        else:
            df_maestro_final = pd.DataFrame(columns=["VER", "ID", "ORDEN DE SALIDA", "FECHA", "DESTINO / PACIENTE", "RAZÓN LOGÍSTICA", "RESPONSABLE", "ESTADO"])

        contenedor_titulo.markdown(
            f"<h2 style='margin-bottom: 0;'>📦 Control de Órdenes y Salidas ({total_registros_bd} registros históricos)</h2>", 
            unsafe_allow_html=True
        )

        _, col_btn = st.columns([4, 1.2])
        with col_btn:
            if puede_editar and st.button("📦 NUEVO DESPACHO (FEFO)", use_container_width=True, type="primary"):
                modal_registro_salida_fefo()

        st.write("")
        contenedor_guardar_modificacion = st.empty()

        # ==============================================================================
        # 📝 TABLA MAESTRA CON LA COLUMNA 'VER' 
        # ==============================================================================
        st.markdown("##### 🧾 Actas de Despacho Registradas (Marque la casilla 'VER' para inspeccionar medicamentos)")
        
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
            height=220,
            key="editor_maestro_salidas",
            disabled=["ID", "FECHA", "RESPONSABLE"] if puede_editar else df_maestro_final.columns.tolist(),
            column_config={
                "VER": st.column_config.CheckboxColumn(width="small", help="Marque para cargar medicamentos"),
                "ID": st.column_config.NumberColumn(label='ID', format="%d", width="small"),
                "FECHA": st.column_config.DatetimeColumn(format="DD/MM/YYYY HH:mm", width="medium"),
                "ORDEN DE SALIDA": st.column_config.TextColumn(width="medium", required=True),
                "DESTINO / PACIENTE": st.column_config.TextColumn(width="medium", required=True),
                "RAZÓN LOGÍSTICA": st.column_config.SelectboxColumn(options=["CONSUMO CLÍNICO", "TRASLADO PREVENTIVO", "PERDIDA POR CADUCIDAD"], width="medium", required=True),
                "RESPONSABLE": st.column_config.TextColumn(width="small"),
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
        total_paginas = math.ceil(total_registros_bd / REGISTROS_POR_PAGINA) if total_registros_bd > 0 else 1
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
            st.markdown(f"##### 💊 Insumos Médicos Despachados en el Acta seleccionada: `#{id_salida_target}`")
            print(id_salida_target)
            
            # Invocamos la función de tu backend
            tuplas_detalles = crud_salidas.obtener_detalles_insumos_por_acta(id_salida_target)
            
            filas_detalle = []
            for tupla in tuplas_detalles:
                # tupla[0] = id_detalle_salida (int)
                # tupla[1] = id_salida (int)
                # tupla[2] = nombre del insumo (str)
                # tupla[3] = codigo_lote (str)
                # tupla[4] = cantidad (int)
                
                filas_detalle.append({
                    "ID DETALLE": tupla[0],
                    "INSUMO MÉDICO": tupla[2],
                    "CÓDIGO DE LOTE": tupla[3],
                    "CANTIDAD": tupla[4]
                })
            
            if filas_detalle:
                df_para_editar = pd.DataFrame(filas_detalle)
                
                grilla_detalles_editada = st.data_editor(
                    df_para_editar,
                    use_container_width=True,
                    hide_index=True,
                    height=180,
                    key="editor_detalles",
                    disabled=["ID DETALLE", "INSUMO MÉDICO", "CÓDIGO DE LOTE"] if puede_editar else df_para_editar.columns.tolist(),
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
import streamlit as st
import pandas as pd
import CRUDs.crud_salidas as crud_s
import CRUDs.crud_insumos as crud_i 
from datetime import datetime
from reportes_salidas import generar_reporte_salida_caducidad_pdf
from seguridad import usuario_tiene_permiso_escritura
from analisis_logistico import calcular_metricas_analiticas_sialmed
import uuid
import logging

@st.dialog("📤 Registrar Despacho y Movimientos de Inventario", width="large")
def modal_registro_salida_fefo():
    """
    FORMULARIO LOGÍSTICO TRANSACCIONAL COMPACTO - SISTEMA SIAL-MED
    =============================================================================
    OBJETIVO DE INGENIERÍA:
    Asegurar la persistencia del estado síncrono de la sesión en RAM para impedir 
    el cierre abrupto del componente @st.dialog al consolidar transacciones.
    
    MATRIZ DE OPERACIONES LOGÍSTICAS COMPILADA:
      - CONSUMO CLÍNICO / TRASLADO PREVENTIVO: FEFO Automatizado (Lotes Vigentes).
      - TRASLADO INSTITUCIONAL: Selección Manual en Estantes (Lotes Vigentes).
      - PERDIDA POR CADUCIDAD: Selección Manual de Aislamiento (Lotes Vencidos).
      - OTRO (ESPECIFICAR): Selección Manual Operativa (Lotes Vigentes).
    =============================================================================
    """
    try:
        if not usuario_tiene_permiso_escritura():
            st.error("❌ Acceso restringido: No tienes el permiso para acceder a este formulario.")
        else:
            # Área aislada para el despliegue de excepciones de integridad UNIQUE de SQLite
            contenedor_errores = st.empty()

            # 1. Asegurar el estado
            if "carrito_insumos" not in st.session_state:
                st.session_state["carrito_insumos"] = []

            # --- ⚙️ SECCION 1: CLASIFICACION DE CAMPOS MAESTROS (LAYOUT HORIZONTAL FILA 1) ---
            st.markdown("##### ⚙️ 1. Parámetros Generales de la Transacción")
            
            f1_c1, f1_c2, f1_c3 = st.columns([1.8, 1.6, 1.6])
            
            # 🌟 CONTROL ESTRICTO EN RAM: Evaluamos si el carrito tiene elementos
            carrito_tiene_items = len(st.session_state.carrito_insumos) > 0

            # Si hay elementos en el carrito, congelamos el valor de la razón en el Session State
            if carrito_tiene_items and "razon_fijada" in st.session_state:
                st.session_state["sel_razon_salida"] = st.session_state["razon_fijada"]

            with f1_c1:
                opciones_razon = ["Consumo Clínico", "Traslado Preventivo", "Perdida por Caducidad", "Otro (especificar)"]
                razon_seleccionada = st.selectbox(
                    "Razón de Salida: *", 
                    opciones_razon, 
                    key="sel_razon_salida",
                    disabled=carrito_tiene_items  # Se bloquea visualmente si hay artículos
                )
                # Si el carrito está vacío, guardamos la última selección válida como la "fijada"
                if not carrito_tiene_items:
                    st.session_state["razon_fijada"] = razon_seleccionada
            
            with f1_c2:
                txt_orden = st.text_input("Orden de salida / : *", placeholder="Ej: OFI-134-2026").strip()
                
            with f1_c3:
                txt_destino = st.text_input("Destino / Paciente : *", placeholder="Ej: Felix Hernandez").strip()

            # Entrada abierta condicional estandarizada en mayúsculas (.upper)
            txt_razon = razon_seleccionada
            if razon_seleccionada == "Otro (especificar)":
                txt_razon = st.text_input("Especifique la Razón Extraordinaria: *", placeholder="Ej: REQUERIMIENTO ESPECIAL").strip()

            st.write("") # Espaciador simétrico


            # --- ➕ MÓDULO 4: PANEL COLECTOR DE RENGLONES (LAYOUT HORIZONTAL FILA 2) ---
            st.markdown("##### ➕ Agregar Medicamento a la Cola de Despacho")
            
            # Obtener métricas de caducidad para evaluar riesgos si la razón lo exige[cite: 2]
            _, df_caducidad_metrica = calcular_metricas_analiticas_sialmed()

            # Consumo síncrono del catálogo de medicamentos activos en el sistema[cite: 1]
            lista_insumos = crud_i.obtener_insumos(solo_activos=True) 

            # Filtrado inteligente de insumos según la Razón de Salida seleccionada
            if razon_seleccionada == "Traslado Preventivo" and not df_caducidad_metrica.empty:
                ids_insumos_riesgo = df_caducidad_metrica[
                    df_caducidad_metrica["alerta_vencimiento"].isin(["⚠️ CRÍTICO (MENOS DE 20 DÍAS)", "🔄 ALERTA: RIESGO DE MERMA"])
                ]["id_insumo"].unique()
                lista_insumos = [ins for ins in lista_insumos if ins.id_insumo in ids_insumos_riesgo]

            elif razon_seleccionada == "Perdida por Caducidad" and not df_caducidad_metrica.empty:
                ids_insumos_vencidos = df_caducidad_metrica[
                    df_caducidad_metrica["alerta_vencimiento"] == "🚨 LOTE VENCIDO (AISLAR)"
                ]["id_insumo"].unique()
                lista_insumos = [ins for ins in lista_insumos if ins.id_insumo in ids_insumos_vencidos]

            dict_insumos = {ins.nombre: ins.id_insumo for ins in lista_insumos}
            
            f2_c1, f2_c2, f2_c3 = st.columns([2.5, 1.5, 1.0])
            
            with f2_c1:
                medicina_sel = st.selectbox("Insumo / Medicamento:", [""] + list(dict_insumos.keys()), key="sel_med_salida")

            lote_manual_id = None
            lotes_compatibles = []
            modo_extraccion = "SELECCIÓN MANUAL"
            stock_total_disponible = 0
            cantidad_sugerida_inicial = 1

            # Bloque evaluador cuando un insumo es seleccionado en la interfaz
            if medicina_sel != "":
                id_insumo_sel = dict_insumos[medicina_sel]
                # Invocación al CRUD inyectando la razón para filtrar vigentes vs vencidos por fechas
                lotes_compatibles = crud_s.obtener_lotes_disponibles_fefo(id_insumo_sel, razon_salida=txt_razon)
                
                if lotes_compatibles:
                    # Sumamos el stock de todos los lotes disponibles para el límite global del insumo
                    stock_total_disponible = sum(l.stock_disponible for l in lotes_compatibles)
                    
                    # ⚡ CASO A: TRASLADO PREVENTIVO (Lote automático en riesgo y cantidad recomendada)
                    if razon_seleccionada == "Traslado Preventivo":
                        modo_extraccion = "Traslado Preventivo Automático"
                        
                        lote_en_riesgo = None
                        if not df_caducidad_metrica.empty:
                            lotes_riesgo_df = df_caducidad_metrica[
                                (df_caducidad_metrica["id_insumo"] == id_insumo_sel) & 
                                (df_caducidad_metrica["alerta_vencimiento"].isin(["⚠️ CRÍTICO (MENOS DE 20 DÍAS)", "🔄 ALERTA: RIESGO DE MERMA"]))
                            ]
                            if not lotes_riesgo_df.empty:
                                id_lote_en_riesgo = lotes_riesgo_df.iloc[0]["id_lote"]
                                cantidad_sugerida_inicial = int(lotes_riesgo_df.iloc[0]["cantidad_riesgo"])
                                lote_en_riesgo = next((l for l in lotes_compatibles if l.id_lote == id_lote_en_riesgo), None)

                        primer_lote = lote_en_riesgo if lote_en_riesgo else lotes_compatibles[0]
                        lote_manual_id = primer_lote.id_lote
                        cantidad_sugerida_inicial = max(1, min(cantidad_sugerida_inicial, stock_total_disponible))
                        
                        with f2_c2:
                            st.text_input("Lote Seleccionado (Preventivo):", value=f"🎯 {primer_lote.codigo_lote}", disabled=True)
                        
                        st.info(
                            f"⚠️ **TRASLADO PREVENTIVO (RIESGO DETECTADO):**\n\n"
                            f"* 📦 **Lote Asignado:** `{primer_lote.codigo_lote}` (Vence el {primer_lote.fecha_vencimiento.strftime('%d/%m/%Y') if primer_lote.fecha_vencimiento else 'N/A'}).\n"
                            f"* 💡 **Cantidad Recomendada a Retirar:** `{cantidad_sugerida_inicial} unidades` (basado en análisis de merma)."
                        )

                    # ⚡ CASO B: CONSUMO CLÍNICO (FEFO Automático Estándar con stock total sumado)
                    elif razon_seleccionada == "Consumo Clínico":
                        modo_extraccion = "FEFO Autómatico"
                        primer_lote = lotes_compatibles[0] # Lote con vencimiento más crítico en estantes
                        lote_manual_id = primer_lote.id_lote
                        cantidad_sugerida_inicial = 1
                        
                        with f2_c2:
                            st.text_input("Lote Asignado (FEFO Auto):", value=f"🎯 {primer_lote.codigo_lote} (Vigente)", disabled=True)
                        
                        st.info(
                            f"📊 **ESTADO DE INVENTARIO PARA {medicina_sel}:**\n\n"
                            f"* 📦 **Stock TOTAL en Almacén:** `{stock_total_disponible} unidades` (Sumando todos los lotes disponibles).\n"
                            f"* 🎯 **Lote de Consumo Prioritario (FEFO):** `{primer_lote.codigo_lote}` (Vence el {primer_lote.fecha_vencimiento.strftime('%d/%m/%Y') if primer_lote.fecha_vencimiento else 'N/A'}).\n"
                            f"* 📍 **Ubicación Física en Estante:** **{primer_lote.ubicacion_fisica}** (Hay {primer_lote.stock_disponible} u. en este lote prioritario)."
                        )
                    
                    # CASO C: PÉRDIDA POR CADUCIDAD (Lotes vencidos, por default todo el stock del lote)
                    elif razon_seleccionada == "Perdida por Caducidad":
                        modo_extraccion = "Purga Vencidos Manual"
                        dict_lotes_manuales = {
                            f"LOTE VENCIDO: {l.codigo_lote} | STOCK: {l.stock_disponible} unds. | VENCE: {l.fecha_vencimiento.strftime('%d/%m/%Y') if l.fecha_vencimiento else 'N/A'}": l.id_lote
                            for l in lotes_compatibles
                        }
                        with f2_c2:
                            lote_texto_sel = st.selectbox("Seleccione Lote Vencido: *", list(dict_lotes_manuales.keys()), key="sel_lote_vencido_salida")
                            lote_manual_id = dict_lotes_manuales[lote_texto_sel]
                        
                        lote_objeto_sel = next(l for l in lotes_compatibles if l.id_lote == lote_manual_id)
                        stock_total_disponible = lote_objeto_sel.stock_disponible
                        cantidad_sugerida_inicial = stock_total_disponible  # Por default todo el lote
                        
                        st.warning(
                            f"🚨 **MODO PURGA ACTIVO (SÓLO LOTES VENCIDOS):**\n\n"
                            f"* 📦 **Stock Vencido en este Lote:** `{stock_total_disponible} unidades`.\n"
                            f"* 🎯 **Lote Aislado para Desincorporar:** `{lote_objeto_sel.codigo_lote}`.\n"
                            f"* 💡 **Debe retirar todo el lote (`{cantidad_sugerida_inicial} u.`)."
                        )

                    # CASO D: SELECCIÓN MANUAL (Otros)
                    else:
                        modo_extraccion = "SELECCIÓN MANUAL"
                        dict_lotes_manuales = {
                            f"LOTE: {l.codigo_lote} | STOCK: {l.stock_disponible} unds. | UBICACIÓN: {l.ubicacion_fisica} | VENCIMIENTO: {l.fecha_vencimiento.strftime('%d/%m/%Y') if l.fecha_vencimiento else 'N/A'}": l.id_lote
                            for l in lotes_compatibles
                        }
                        with f2_c2:
                            lote_texto_sel = st.selectbox("Seleccione Lote Físico: *", list(dict_lotes_manuales.keys()), key="sel_lote_manual_salida")
                            lote_manual_id = dict_lotes_manuales[lote_texto_sel]
                        
                        lote_objeto_sel = next(l for l in lotes_compatibles if l.id_lote == lote_manual_id)
                        stock_total_disponible = lote_objeto_sel.stock_disponible
                        cantidad_sugerida_inicial = 1
                        
                        st.info(
                            f"🔓 **OPERACIÓN MANUAL ACTIVA (SÓLO LOTES VIGENTES):**\n\n"
                            f"* 📦 **Stock Disponible en este Lote:** `{stock_total_disponible} unidades`.\n"
                            f"* 🎯 **Lote Seleccionado para Transferir:** `{lote_objeto_sel.codigo_lote}`.\n"
                            f"* 📍 **Ubicación en Estante:** **{lote_objeto_sel.ubicacion_fisica}**."
                        )
                else:
                    with f2_c2:
                        st.text_input("Estado del Lote:", value="❌ Sin Existencias Aptas", disabled=True)
                    st.error(f"❌ No se localizan lotes aptos en el almacén militar bajo la modalidad de '{txt_razon}'.")
            else:
                with f2_c2:
                    st.text_input("Lote:", value="💡 Seleccione Insumo", disabled=True)

            with f2_c3:
                max_unidades_permitidas = stock_total_disponible if (medicina_sel != "" and lotes_compatibles) else 99999
                cant_solicitada = st.number_input(
                    "Cantidad:", 
                    min_value=1, 
                    max_value=int(max_unidades_permitidas), 
                    value=int(cantidad_sugerida_inicial), 
                    step=1, 
                    key="num_cant_salida"
                )


            c_anexar, _, c_limpiar = st.columns([2, 0.6, 1.4])
            with c_anexar:
                # --- BOTÓN INTERMEDIO DE ENTRADA AL BUFFER (ANEXAR) ---
                if st.button("➕ Anexar Medicamento a la cola", use_container_width=True):
                    if medicina_sel == "" or not lotes_compatibles:
                        st.toast("⚠️ Verifique el insumo seleccionado y su disponibilidad real.")
                    elif cant_solicitada > stock_total_disponible:
                        st.error(f"🛑 Error de Stock: Intentó ingresar {cant_solicitada} u. pero el límite disponible es {stock_total_disponible} u.")
                    elif razon_seleccionada == "OTRO (ESPECIFICAR)" and not txt_razon.strip():
                        st.error("🛑 Operación rechazada: La descripción de la razón extraordinaria no puede estar vacía.")
                    else:
                        id_insumo_sel = dict_insumos[medicina_sel]
                        
                        # Algoritmo de acumulación continua para impedir la duplicación de filas idénticas
                        existe = False
                        for item in st.session_state.carrito_insumos:
                            if item["id_insumo"] == id_insumo_sel and item["lote_especifico_id"] == lote_manual_id:
                                if (item["cantidad"] + int(cant_solicitada)) <= stock_total_disponible:
                                    item["cantidad"] += int(cant_solicitada)
                                    st.toast("¡Cantidad actualizada en el renglón de forma conforme!")
                                else:
                                    st.error("🛑 Error: La acumulación supera el stock físico de este lote.")
                                existe = True
                                break
                        
                        if not existe:
                            st.session_state.carrito_insumos.append({
                                "id_insumo": id_insumo_sel,
                                "nombre_insumo": medicina_sel,
                                "cantidad": int(cant_solicitada),
                                "lote_especifico_id": lote_manual_id,
                                "modo_extraccion": modo_extraccion
                            })
                            st.toast(f"Anexado: {medicina_sel}")
                        
                        # Refresco de estado controlado (Mantiene el diálogo abierto renderizando la grilla)
                        st.empty()

            # BOTON DE LIMPIAR CARRITO
            with c_limpiar:
                if st.session_state.carrito_insumos:
                    if st.button("🗑️ Vaciar Lista de Insumos", type="secondary", use_container_width=True):
                            st.session_state.carrito_insumos = []
                            st.rerun()


            # --- MÓDULO 5: GRILLA INTERACTIVA DE EDICIÓN EN VIVO ---
            if st.session_state.carrito_insumos:
                st.write("")
                st.markdown("##### 🛒 Resumen de Insumos Cargados en la Tanda Actual")
                
                df_carrito = pd.DataFrame(st.session_state.carrito_insumos)
                
                carrito_editado = st.data_editor(
                    df_carrito,
                    use_container_width=True,
                    hide_index=True,
                    column_config={
                        "id_insumo": None, 
                        "lote_especifico_id": None,
                        "nombre_insumo": st.column_config.TextColumn("MEDICAMENTO / INSUMO VINCULADO", disabled=True),
                        "modo_extraccion": st.column_config.TextColumn("MECANISMO DE FLUJO", disabled=True),
                        "cantidad": st.column_config.NumberColumn("CANTIDAD A DESPACHAR", min_value=1, step=1, required=True) # Celda editable
                    },
                    key="editor_carrito_salidas"
                )
                
                # Sincronizador de la grilla interactiva hacia el Session State de Streamlit
                if st.session_state.get("editor_carrito_salidas"):
                    cambios = st.session_state["editor_carrito_salidas"]["edited_rows"]
                    for indice, modificaciones in cambios.items():
                        if "cantidad" in modificaciones:
                            st.session_state.carrito_insumos[indice]["cantidad"] = int(modificaciones["cantidad"])


            # --- MÓDULO 6: PROTOCOLO DE PERSISTENCIA FINAL TRASLADADO AL ENGINE ---
            c_save, c_cancel = st.columns(2)
            
            with c_save:
                if st.button("💾 CONSOLIDAR SALIDA", use_container_width=True, type="primary"):
                    if not txt_orden.strip() or not txt_destino.strip():
                        contenedor_errores.error("⚠️ Los campos 'Orden de salida' y 'Paciente/Destino' son de carácter obligatorio.")
                    elif not st.session_state.carrito_insumos:
                        contenedor_errores.error("⚠️ El carrito de despachos se encuentra vacío.")
                    else:
                        id_usuario_ram = st.session_state.get("user_id")
                        id_usuario_final = int(id_usuario_ram) if id_usuario_ram is not None else 1

                        # Clonamos el carrito en RAM para asegurar que no se pierdan cantidades ni datos al borrarlo
                        copia_carrito_auditoria = list(st.session_state.carrito_insumos)

                        try:
                            resultado = crud_s.registrar_despacho_combinado_fefo(
                                orden_salida=txt_orden,
                                paciente_destino=txt_destino,
                                razon_salida=txt_razon,
                                id_usuario=id_usuario_final,
                                lista_pedidos=st.session_state.carrito_insumos
                            )
                            
                            
                            if isinstance(resultado, dict) and resultado.get("status") is True:
                                if txt_razon == "Perdida por Caducidad":
                                    datos_cabecera = {
                                        "orden_salida": txt_orden,
                                        "paciente_destino": txt_destino,
                                        "fecha": datetime.now()
                                    }
                                    
                                    # Reconstrucción de insumos con las cantidades reales del carrito en memoria
                                    insumos_reporte = []
                                    for item in copia_carrito_auditoria:
                                        # Buscamos el código de lote asignado consultando los lotes compatibles
                                        id_insumo_sel = item["id_insumo"]
                                        lotes = crud_s.obtener_lotes_disponibles_fefo(id_insumo_sel, razon_salida=txt_razon)
                                        obj_lote = next((l for l in lotes if l.id_lote == item["lote_especifico_id"]), None)
                                        cod_lote_txt = obj_lote.codigo_lote if obj_lote else "LOTE"

                                        insumos_reporte.append({
                                            "nombre_insumo": item["nombre_insumo"],
                                            "codigo_lote": cod_lote_txt,
                                            "cantidad": int(item["cantidad"]) # Fijación de cantidad real
                                        })
                                    
                                    usuario_actual = st.session_state.get("user_nombre_completo", "OPERADOR SIAL-MED")
                                    pdf_bytes = generar_reporte_salida_caducidad_pdf(datos_cabecera, insumos_reporte, usuario_actual)
                                    
                                    # Almacenamos los bytes del PDF en el estado global
                                    st.session_state["acta_perdida_pendiente_pdf"] = pdf_bytes
                                    st.session_state["acta_perdida_pendiente_orden"] = txt_orden
                                else:
                                    st.session_state["acta_perdida_pendiente_pdf"] = None

                                st.session_state["hoja_ruta_despacho"] = resultado["despacho"]
                                st.session_state.carrito_insumos = []
                                if "editor_carrito_salidas" in st.session_state:
                                    del st.session_state["editor_carrito_salidas"]
                                st.rerun()
                            else:
                                contenedor_errores.error(resultado)
                        
                        except Exception as e:
                            correlation_id = str(uuid.uuid4())
                            logging.error(f'{{"correlation_id": "{correlation_id}", "error": "{str(e)}", "modulo": "modal_salida_consolidacion"}}')
                            contenedor_errores.error(f"Error crítico consolidando despacho. Reporte el código: [{correlation_id}]")    
            
            with c_cancel:
                if st.button("CANCELAR Y SALIR", use_container_width=True):
                    st.session_state.carrito_insumos = []
                    st.session_state.hoja_ruta_despacho = None
                    if "editor_carrito_salidas" in st.session_state:
                        del st.session_state["editor_carrito_salidas"]
                    st.rerun()

    except Exception as e:
        # CAPA EXTERNA DE PROTECCIÓN
        correlation_id = str(uuid.uuid4())
        logging.error(f'{{"correlation_id": "{correlation_id}", "error": "{str(e)}", "modulo": "modal_registro_salida"}}')
        st.error(f"Error inesperado en el formulario de salidas. Reporte el código: [{correlation_id}]")
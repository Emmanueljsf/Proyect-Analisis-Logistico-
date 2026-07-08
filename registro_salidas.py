import streamlit as st
import pandas as pd
import CRUDs.crud_salidas as crud_s
import CRUDs.crud_insumos as crud_i 
from datetime import datetime

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
        # Área aislada para el despliegue de excepciones de integridad UNIQUE de SQLite
        contenedor_errores = st.empty()
        
        # ---  MÓDULO 1: BUFFERING DE VARIABLES EN MEMORIA VOLÁTIL (RAM) ---
        if "carrito_insumos" not in st.session_state:
            st.session_state.carrito_insumos = []
        if "hoja_ruta_despacho" not in st.session_state:
            st.session_state.hoja_ruta_despacho = None

        # ---  MÓDULO 2: INTERCEPTOR DE ÉXITO POST-TRANSACCIONAL (RESUMEN FINAL) ---
        if st.session_state.hoja_ruta_despacho is not None:
            st.success("🎉 ¡Movimiento de Inventario Consolidado Exitosamente en SQLite!")
            st.markdown("### 📋 GUÍA DE RECOLECCIÓN EN ESTANTES PARA EL OPERARIO:")
            
            df_ruta = pd.DataFrame(st.session_state.hoja_ruta_despacho)
            st.dataframe(df_ruta, use_container_width=True, hide_index=True)
            
            st.warning("⚠️ Registre estas ubicaciones físicas en el almacén antes de cerrar esta ventana.")
            
            # 🏁 Botón de cierre controlado
            if st.button("🏁 FINALIZAR Y CERRAR VENTANA", use_container_width=True, type="primary"):
                st.session_state.carrito_insumos = []
                st.session_state.hoja_ruta_despacho = None
                if "editor_carrito_salidas" in st.session_state:
                    del st.session_state["editor_carrito_salidas"]
                st.rerun()

            return # Cortafuegos de UI absoluto

        # --- ⚙️ MÓDULO 3: CLASIFICACIÓN DE CAMPOS MAESTROS (LAYOUT HORIZONTAL FILA 1) ---
        st.markdown("##### ⚙️ 1. Parámetros Generales de la Transacción")
        
        f1_c1, f1_c2, f1_c3 = st.columns([1.8, 1.6, 1.6])
        
        with f1_c1:
            opciones_razon = ["Consumo Clínico", "Traslado Preventivo", "Perdida por Caducidad", "Otro (especificar)"]
            razon_seleccionada = st.selectbox("Razón de Salida: *", opciones_razon, key="sel_razon_salida")
        
        with f1_c2:
            txt_orden = st.text_input("Orden de salida / : *", placeholder="Ej: OFI-134-2026").strip()
            
        with f1_c3:
            txt_destino = st.text_input("Destino / Paciente : *", placeholder="Ej: Felix Hernandez").strip()

        # Entrada abierta condicional estandarizada en mayúsculas (.upper)
        txt_razon = razon_seleccionada
        if razon_seleccionada == "OTRO (ESPECIFICAR)":
            txt_razon = st.text_input("Especifique la Razón Extraordinaria: *", placeholder="Ej: REQUERIMIENTO ESPECIAL").strip()

        st.write("") # Espaciador simétrico

        # --- ➕ MÓDULO 4: PANEL COLECTOR DE RENGLONES (LAYOUT HORIZONTAL FILA 2) ---
        st.markdown("##### ➕ Agregar Medicamento a la Cola de Despacho")
        
        # Consumo síncrono del catálogo de medicamentos activos en el sistema
        lista_insumos = crud_i.obtener_insumos(solo_activos=True) 
        dict_insumos = {ins.nombre: ins.id_insumo for ins in lista_insumos}
        
        f2_c1, f2_c2, f2_c3 = st.columns([2.5, 1.5, 1.0])
        
        with f2_c1:
            medicina_sel = st.selectbox("Insumo / Medicamento:", [""] + list(dict_insumos.keys()), key="sel_med_salida")

        lote_manual_id = None
        lotes_compatibles = []
        modo_extraccion = "SELECCIÓN MANUAL"
        stock_total_disponible = 0

        # Bloque evaluador cuando un insumo es seleccionado en la interfaz
        if medicina_sel != "":
            id_insumo_sel = dict_insumos[medicina_sel]
            # Invocación al CRUD inyectando la razón para filtrar vigentes vs vencidos por fechas
            lotes_compatibles = crud_s.obtener_lotes_disponibles_fefo(id_insumo_sel, razon_salida=txt_razon)
            
            if lotes_compatibles:
                stock_total_disponible = sum(l.stock_disponible for l in lotes_compatibles)
                
                # ⚡ CASO A: CRITERIO FEFO AUTOMÁTICO (Consumo Clínico y Donaciones)
                if razon_seleccionada in ["Consumo Clínico", "Traslado Preventivo"]:
                    modo_extraccion = "FEFO Autómatico"
                    primer_lote = lotes_compatibles[0] # Lote con vencimiento más crítico en estantes
                    lote_manual_id = primer_lote.id_lote
                    
                    with f2_c2:
                        st.text_input("Lote Asignado (FEFO Auto):", value=f"🎯 {primer_lote.codigo_lote} (Vigente)", disabled=True)
                    
                    # RESTABLECIDO: Cuadro informativo original del estado del inventario para automatismo
                    st.info(
                        f"📊 **ESTADO DE INVENTARIO PARA {medicina_sel}:**\n\n"
                        f"* 📦 **Stock TOTAL en Almacén:** `{stock_total_disponible} unidades` (Sumando lotes disponibles).\n"
                        f"* 🎯 **Lote de Consumo Prioritario (FEFO):** `{primer_lote.codigo_lote}` (Vence el {primer_lote.fecha_vencimiento.strftime('%d/%m/%Y') if primer_lote.fecha_vencimiento else 'N/A'}).\n"
                        f"* 📍 **Ubicación Física en Estante:** **{primer_lote.ubicacion_fisica}** (Hay {primer_lote.stock_disponible} u. en este lote)."
                    )
                
                # 🔓 CASO B: SELECCIÓN MANUAL (Traslados, Perdidas por caducidad y Otros)
                else:
                    modo_extraccion = "SELECCIÓN MANUAL"
                    dict_lotes_manuales = {
                        f"LOTE: {l.codigo_lote} | STOCK: {l.stock_disponible} unds. | UBICACIÓN: {l.ubicacion_fisica} | VENCIMIENTO: {l.fecha_vencimiento.strftime('%d/%m/%Y') if l.fecha_vencimiento else 'N/A'}": l.id_lote
                        for l in lotes_compatibles
                    }
                    with f2_c2:
                        lote_texto_sel = st.selectbox("Seleccione Lote Físico: *", list(dict_lotes_manuales.keys()), key="sel_lote_manual_salida")
                        lote_manual_id = dict_lotes_manuales[lote_texto_sel]
                    
                    # Reajuste de la cota máxima del stock al lote específico amarrado por el operador
                    lote_objeto_sel = next(l for l in lotes_compatibles if l.id_lote == lote_manual_id)
                    stock_total_disponible = lote_objeto_sel.stock_disponible
                    
                    # RESTABLECIDO: Cuadro informativo original del estado del inventario para control manual
                    if razon_seleccionada == "Perdida por Caducidad":
                        st.warning(
                            f"🚨 **MODO PURGA ACTIVO (SÓLO LOTES VENCIDOS):**\n\n"
                            f"* 📦 **Stock Vencido en este Lote:** `{stock_total_disponible} unidades`.\n"
                            f"* 🎯 **Lote Aislado para Desincorporar:** `{lote_objeto_sel.codigo_lote}`.\n"
                            f"* 📍 **Ubicación en Estante:** **{lote_objeto_sel.ubicacion_fisica}**."
                        )
                    else:
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
            # Botones de + y - liberados operativamente fijando límites genéricos seguros
            max_unidades_permitidas = stock_total_disponible if (medicina_sel != "" and lotes_compatibles) else 99999
            cant_solicitada = st.number_input("Cantidad:", min_value=1, max_value=int(max_unidades_permitidas), value=1, step=1, key="num_cant_salida")

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

        # --- MÓDULO 5: GRILLA INTERACTIVA DE EDICIÓN EN VIVO ---
        if st.session_state.carrito_insumos:
            st.write("")
            st.markdown("##### 🛒 Resumen de Insumos Cargados en la Tanda Actual")
            st.caption("💡 Puede hacer doble clic sobre la celda de **CANTIDAD** para realizar correcciones numéricas rápidas.")
            
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

            if st.button("🗑️ Vaciar Lista de Insumos", type="secondary", use_container_width=True):
                st.session_state.carrito_insumos = []
                st.rerun()

        # --- MÓDULO 6: PROTOCOLO DE PERSISTENCIA FINAL TRASLADADO AL ENGINE ---
        st.divider()
        c_save, c_cancel = st.columns(2)
        
        with c_save:
            if st.button("💾 CONSOLIDAR ACTA DE DESPACHO", use_container_width=True, type="primary"):
                if not txt_orden.strip() or not txt_orden.strip():
                    contenedor_errores.error("⚠️ Los campos 'Orden de salida' y 'Paciente/Destino' son de carácter obligatorio.")
                elif not st.session_state.carrito_insumos:
                    contenedor_errores.error("⚠️ El carrito de despachos se encuentra vacío.")
                else:
                    # 🛡️ CORTAFUEGOS PYTHON 3.8: Forzar un entero válido si user_id es None o no existe
                    id_usuario_ram = st.session_state.get("user_id")
                    id_usuario_final = int(id_usuario_ram) if id_usuario_ram is not None else 1

                    # Ejecutamos la persistencia en lote hacia el backend
                    resultado = crud_s.registrar_despacho_combinado_fefo(
                        orden_salida=txt_orden,
                        paciente_destino=txt_destino,
                        razon_salida=txt_razon,
                        id_usuario=id_usuario_final,  # Pasamos la variable blindada
                        lista_pedidos=st.session_state.carrito_insumos
                    )
                    
                    # Evaluación atómica de la respuesta emitida por el motor SQLite bajo modo WAL
                    if resultado == "ORDEN_DUPLICADA":
                        contenedor_errores.error(f"🛑 Falla de Restricción UNIQUE: El Identificador/Oficio '{txt_orden}' ya existe en el kárdex.")
                    
                    elif isinstance(resultado, dict) and resultado.get("status") is True:
                        # SOLUCIÓN MAESTRA: Forzamos la persistencia en el estado global de la aplicación
                        st.session_state["hoja_ruta_despacho"] = resultado["despacho"]
                        # Limpiamos el carrito en RAM de forma segura post-guardado exitoso
                        st.session_state.carrito_insumos = []
                        # Destruimos el estado del widget editor para que no colisione en la recarga
                        if "editor_carrito_salidas" in st.session_state:
                            del st.session_state["editor_carrito_salidas"]
                        # 🔄 Cerramos el modal forzando el refresco de la pantalla principal
                        st.rerun()
                    else:
                        # Captura quiebres de stock o bloqueos de negocio detectados
                        contenedor_errores.error(resultado)
                        
        with c_cancel:
            if st.button("CANCELAR Y SALIR", use_container_width=True):
                st.session_state.carrito_insumos = []
                st.session_state.hoja_ruta_despacho = None
                if "editor_carrito_salidas" in st.session_state:
                    del st.session_state["editor_carrito_salidas"]
                st.rerun()

    except Exception as e:
            print(f"Error crítico en el formulario de registro de entradas: {e}")
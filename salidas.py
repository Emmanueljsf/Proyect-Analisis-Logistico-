import streamlit as st
import pandas as pd
import CRUDs.crud_salidas as crud_s
import CRUDs.crud_insumos as crud_i 
from datetime import datetime
import time

@st.dialog("📤 Registrar Despacho (FIFO)", width="large")
def modal_registro_salida_fifo():
    """
    Formulario dinámico que permite acumular múltiples medicamentos en una misma
    orden médica, calculando las ubicaciones FIFO en tiempo real.
    """
    contenedor_alertas = st.empty()
    
    # Inicializadores de la memoria temporal de la sesión (RAM de la vista)
    if "carrito_insumos" not in st.session_state:
        st.session_state.carrito_insumos = []
    if "hoja_ruta_despacho" not in st.session_state:
        st.session_state.hoja_ruta_despacho = None

    # --- PANTALLA DE ÉXITO: MOSTRAR ALERTA FINAL DE RETIRO ---
    if st.session_state.hoja_ruta_despacho:
        st.success("🎉 ¡Orden Médica Registrada con Éxito en el Sistema!")
        st.markdown("### 📋 GUÍA DE RECOLECCIÓN EN ESTANTES PARA EL OPERARIO:")
        st.dataframe(pd.DataFrame(st.session_state.hoja_ruta_despacho), use_container_width=True, hide_index=True)
        
        if st.button("FINALIZAR Y CERRAR VENTANA", use_container_width=True, type="primary"):
            st.session_state.hoja_ruta_despacho = None
            st.session_state.carrito_insumos = []
            st.rerun()
        return

    # --- DATOS GENERALES (SE ESCRIBEN UNA SOLA VEZ) ---
    c1, c2 = st.columns(2)
    with c1:
        txt_orden = st.text_input("Código de Orden Médica (Único) *", placeholder="Ej: ORD-2026-A")
    with c2:
        txt_paciente = st.text_input("Nombre Completo del Paciente *", placeholder="Ej: Teniente Carlos Gómez")

    st.divider()

    # --- PANEL COLECTOR DE RENGLONES ---
    st.markdown("##### ➕ Agregar Medicamento a la Receta")
    
    lista_insumos = crud_i.obtener_todos_insumos() 
    dict_insumos = {ins.nombre.upper(): ins.id_insumo for ins in lista_insumos}
    
    col_sel_med, col_cant, col_btn_add = st.columns([2.5, 1.2, 1])
    
    with col_sel_med:
        medicina_sel = st.selectbox("Seleccione el Medicamento:", [""] + list(dict_insumos.keys()), key="sel_med_salida")
    
    with col_cant:
        cant_solicitada = st.number_input("Cantidad:", min_value=1, value=1, step=1, key="num_cant_salida")

    # Muestra dinámicamente la ubicación del lote que se afectará justo antes de añadirlo
    if medicina_sel != "":
        id_insumo_sel = dict_insumos[medicina_sel]
        # Obtenemos los lotes para informarle la ubicación al operador en vivo
        lotes_compatibles = crud_s.obtener_lotes_disponibles_fifo(id_insumo_sel)
        if lotes_compatibles:
            primer_lote = lotes_compatibles[0] # El lote que se consumirá primero por FEFO/FIFO
            
            # 🧠 Calculamos en caliente la suma de existencias de todos los lotes juntos
            stock_total_en_almacen = sum(l.stock_disponible for l in lotes_compatibles)
            
            # Dibujamos un contenedor con la información unificada y súper visible
            st.info(
                f"📊 **ESTADO DE INVENTARIO PARA {medicina_sel}:**\n\n"
                f"* 📦 **Stock TOTAL en Almacén:** `{stock_total_en_almacen} unidades` (Sumando todos los lotes disponibles).\n"
                f"* 🎯 **Lote de Consumo Prioritario (FIFO):** `{primer_lote.codigo_lote}` (Vence el {primer_lote.fecha_vencimiento.strftime('%d/%m/%Y')}).\n"
                f"* 📍 **Ubicación Física en Estante:** **{primer_lote.ubicacion_fisica.upper()}** (Hay {primer_lote.stock_disponible} u. en este lote)."
            )
        else:
            st.error("❌ No hay existencias de este insumo en el almacén.")

    with col_btn_add:
        st.markdown("<div style='padding-top:24px;'></div>", unsafe_allow_html=True)
        if st.button("➕ ANEXAR", use_container_width=True):
            if medicina_sel == "":
                st.toast("⚠️ Seleccione un medicamento primero.")
            else:
                # Verificar si ya metió el mismo medicamento para consolidar la cantidad
                id_insumo_sel = dict_insumos[medicina_sel]
                existe = False
                for item in st.session_state.carrito_insumos:
                    if item["id_insumo"] == id_insumo_sel:
                        item["cantidad"] += int(cant_solicitada)
                        existe = True
                        break
                
                if not existe:
                    st.session_state.carrito_insumos.append({
                        "id_insumo": id_insumo_sel,
                        "nombre_insumo": medicina_sel,
                        "cantidad": int(cant_solicitada)
                    })
                st.toast(f"Anexado: {medicina_sel}")

    # --- LISTA VISUAL DEL CARRITO ACTUAL ---
    if st.session_state.carrito_insumos:
        st.markdown("##### 🛒 Resumen de Medicamentos en esta Orden:")
        df_visual = pd.DataFrame(st.session_state.carrito_insumos)
        st.dataframe(df_visual[["nombre_insumo", "cantidad"]], column_config={"nombre_insumo": "MEDICAMENTO", "cantidad": "CANTIDAD TOTAL"}, use_container_width=True, hide_index=True)
        
        if st.button("🗑️ Vaciar Lista de Insumos", type="secondary"):
            st.session_state.carrito_insumos = []
            st.rerun()

    # --- ACCIONES PRINCIPALES DE GUARDADO ---
    st.divider()
    c_save, c_cancel = st.columns(2)
    with c_save:
        if st.button("💾 CONSOLIDAR DESPACHO", use_container_width=True, type="primary"):
            contenedor_alertas.empty()
            
            if not txt_orden.strip() or not txt_paciente.strip():
                contenedor_alertas.warning("⚠️ Complete el Código de la Orden y el Paciente.")
            elif not st.session_state.carrito_insumos:
                contenedor_alertas.warning("⚠️ Debe anexar al menos un medicamento a la receta.")
            else:
                # Enviamos el paquete agrupado al backend inteligente
                resultado = crud_s.registrar_despacho_combinado_fifo(
                    orden_medica=txt_orden,
                    paciente=txt_paciente,
                    id_usuario=st.session_state.get("user_id", 1),
                    lista_pedidos=st.session_state.carrito_insumos
                )
                
                # Gestión y control de la regla UNIQUE de la base de datos
                if resultado == "ORDEN_DUPLICADA":
                    contenedor_alertas.error(f"🛑 Error de Integridad: El Código de Orden Médica '{txt_orden.upper()}' ya fue registrado anteriormente. Ingrese un código único válido.")
                elif isinstance(resultado, dict) and resultado.get("status") is True:
                    # Guardamos la hoja de ruta total e invocamos el refresco
                    st.session_state.hoja_ruta_despacho = resultado["despacho"]
                    st.rerun()
                else:
                    contenedor_alertas.error(resultado) # Imprime alertas si falta stock en algún renglón
                    
    with c_cancel:
        if st.button("CANCELAR Y SALIR", use_container_width=True):
            st.session_state.carrito_insumos = []
            st.rerun()

import streamlit as st
import pandas as pd
import plotly.express as px
from analisis_logistico import calcular_metricas_analiticas_sialmed
from reportes_analisis import generar_reporte_rop_excel, generar_reporte_caducidad_excel, generar_reporte_rop_pdf, generar_reporte_caducidad_pdf
from bd.models import Rol

# --------------------------------------------------------------------------
# 🛠️ OPTIMIZACIÓN 4: FUNCIÓN DE ESTILIZADO DEFINIDA FUERA DEL BUCLE
# --------------------------------------------------------------------------
def destacar_excedentes(val):
    """Aplica estilo visual a las celdas con cantidades en riesgo."""
    if val > 0:
        return "background-color: rgba(214, 39, 40, 0.2); color: #ff7f7f; font-weight: bold;"
    return "color: #888888;"


def Vista_Dashboard_Logistico():
    """
    Renderiza el Panel de Inteligencia Logística y Control de Stock Preventivo del SIAL-MED.
    Consume las métricas analíticas del backend para estructurar la capa de presentación 
    del Destacamento 134 mediante componentes visuales interactivos de Streamlit y Plotly Express.
    """
    try:
        st.title("📊 Panel de Inteligencia Logística y Análisis de Stock")
        st.markdown(
            "Módulo analítico predictivo para optimizar el reabastecimiento "
            "y mitigar mermas por caducidad en el Destacamento 134 (Dabajuro)."
        )

        # --------------------------------------------------------------------------
        # ⚡ EXTRACCIÓN DE DATOS PROCESADOS POR EL BACKEND
        # --------------------------------------------------------------------------
        with st.spinner("Ejecutando algoritmos logísticos en tiempo real..."):
            df_rop, df_caducidad = calcular_metricas_analiticas_sialmed()

        # CONTROL DE SEGURIDAD EXPLICITO
        if df_rop.empty or "semaforo" not in df_rop.columns:
            st.info("💡 Actualmente no existen lotes de insumos registrados o activos en el inventario para procesar el análisis logístico.")
            return

        # --------------------------------------------------------------------------
        # BLOQUE 1: TARJETAS DE MÉTRICAS LOGÍSTICAS
        # --------------------------------------------------------------------------
        total_insumos_distintos = len(df_rop)
        insumos_en_reorden = len(df_rop[df_rop["semaforo"].str.contains("ADVERTENCIA|REORDEN", case=False, na=False)])
        insumos_criticos = len(df_rop[df_rop["semaforo"].str.contains("CRÍTICO|CRITICO|CERO", case=False, na=False)])
        
        if not df_caducidad.empty:
            lotes_vencidos = len(df_caducidad[df_caducidad["alerta_vencimiento"].str.contains("VENCIDO", case=False, na=False)])
            lotes_riesgo_merma = len(df_caducidad[
                df_caducidad["alerta_vencimiento"].str.contains("MERMA|TRASLADAR|CRÍTICO|CRITICO", case=False, na=False)
            ])
        else:
            lotes_vencidos = 0
            lotes_riesgo_merma = 0

        # Renderizado de Tarjetas Métricas
        c1, c2, c3, c4, c5 = st.columns(5)
        with c1:
            st.metric(label="📋 Insumos Catalogados", value=total_insumos_distintos)
        with c2:
            st.metric(label="🚨 Stock en Cero", value=insumos_criticos)
        with c3:
            st.metric(label="🚨 Lotes Vencidos", value=lotes_vencidos, delta="Aislar", delta_color="inverse")
        with c4:
            st.metric(label="⚠️ Alertas de Reorden", value=insumos_en_reorden)
        with c5:
            st.metric(label="🔄 Lotes en Riesgo / Donar", value=lotes_riesgo_merma, delta="Acción Prev.", delta_color="off")

        st.write("")

        # --------------------------------------------------------------------------
        # BLOQUE 2: PESTAÑAS DE DISTRIBUCIÓN ANALÍTICA
        # --------------------------------------------------------------------------
        tab_abastecimiento, tab_caducidad = st.tabs([
            "📦 Control de Abastecimiento (ROP / VED)", 
            "⏳ Gestión Preventiva de Caducidad"
        ])

        # ==========================================================================
        # PESTAÑA 1: PUNTO DE REORDEN Y SEMÁFORO DE STOCK (OPTIMIZADA PARA MÓVIL)
        # ==========================================================================
        with tab_abastecimiento:
            st.subheader("📋 Estado General de Abastecimiento de Medicamentos")
            st.caption(
                "El Punto de Reorden (ROP) se calcula con un modelo estadístico que considera: "
                "consumo promedio diario (CPD), lead time promedio, nivel de servicio según criticidad VED "
                "(Vital 99.9%, Esencial 97.5%, Deseable 90%) y la variabilidad real de la demanda. "
                "El stock de seguridad (SS) protege contra fluctuaciones durante el tiempo de reposición."
            )

            # --------------------------------------------------------------------------
            # 📱 FILTRADO LOGÍSTICO AVANZADO (BUENAS PRÁCTICAS)
            # --------------------------------------------------------------------------
            # Filtro inteligente: Mostrar solo productos bajo el ROP o muy cerca (hasta un 20% por encima del ROP)
            df_criticos_grafico = df_rop[df_rop["stock_disponible"] <= (df_rop["rop"] * 1.2)].copy()
            
            # solucion rapida de la imprecicion del mensaje: solo es para el mensaje
            df_criticos_mensaje = df_rop[df_rop["stock_disponible"] <= (df_rop["rop"])].copy()
            
            # Ordenamos de menor a mayor stock para priorizar lo crítico visualmente
            df_criticos_grafico = df_criticos_grafico.sort_values(by="stock_disponible", ascending=True)

            # Cálculo de la fracción del inventario en alerta (Porcentaje)
            total_insumos = len(df_rop)
            insumos_en_alerta = len(df_criticos_mensaje)
            print(df_criticos_grafico)
            porcentaje_alerta = (insumos_en_alerta / total_insumos * 100) if total_insumos > 0 else 0

            # --------------------------------------------------------------------------
            # 📊 SECCIÓN DE GRÁFICOS RESPONSIVOS (ST.COLUMNS SE APILA EN MÓVILES)
            # --------------------------------------------------------------------------
            st.write("---")
            col_g1, col_g2 = st.columns([1, 1]) # Proporción equitativa para pantallas anchas. En celular se apilará verticalmente.

            with col_g1:
                # GRÁFICO 1: Salud General del Inventario (Donut)
                df_semaforo = df_rop.groupby("semaforo").size().reset_index(name="cantidad")
                color_map_semaforo = {
                    "🟢 ÓPTIMO": "#2ecc71",
                    "🌕 ADVERTENCIA (REORDEN)": "#f1c40f",
                    "🔴 CRÍTICO (SIN STOCK)": "#e74c3c"
                }
                
                fig_donut = px.pie(
                    df_semaforo,
                    values="cantidad",
                    names="semaforo",
                    hole=0.5,
                    color="semaforo",
                    color_discrete_map=color_map_semaforo,
                    title="<b>Estado del Inventario</b>"
                )
                fig_donut.update_layout(
                    height=300, # Altura compacta ideal para pantallas de teléfonos
                    margin=dict(t=40, b=10, l=10, r=10),
                    legend=dict(orientation="h", yanchor="bottom", y=-0.2, xanchor="center", x=0.5)
                )
                st.plotly_chart(fig_donut, use_container_width=True)

            with col_g2:
                # ⚠️ GRÁFICO 2: Productos Críticos: Stock vs. ROP (Barras Horizontales)
                # La orientación horizontal evita que los nombres se pisen en pantallas angostas de celulares
                if not df_criticos_grafico.empty:
                    fig_comparativo = px.bar(
                        df_criticos_grafico.head(12), # Mostramos un top de los 12 más urgentes para no saturar el móvil
                        y="nombre_insumo",
                        x=["stock_disponible", "rop"],
                        barmode="group",
                        orientation="h",
                        labels={"value": "Cantidad (unds)", "variable": "Métrica", "nombre_insumo": ""},
                        title="<b>Productos Críticos: Stock Disponible vs. ROP</b>",
                        color_discrete_sequence=["#e74c3c", "#f39c12"] # Rojo (Stock Real) vs Naranja (Punto de Reorden)
                    )
                    
                    # Ajuste de altura responsivo dinámico según la cantidad de registros
                    altura_dinamica = max(280, len(df_criticos_grafico.head(12)) * 32)
                    
                    fig_comparativo.update_layout(
                        height=altura_dinamica,
                        margin=dict(t=40, b=10, l=10, r=10),
                        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1)
                    )
                    st.plotly_chart(fig_comparativo, use_container_width=True)
                else:
                    st.success("🎉 ¡Excelente! No hay insumos por debajo o cerca de su Punto de Reorden (ROP) en este momento.")

            # --------------------------------------------------------------------------
            # 🎯 MÉTRICA DE FRACCIÓN DE INVENTARIO (BUENAS PRÁCTICAS)
            # --------------------------------------------------------------------------
            # Alerta informativa justo debajo de los gráficos indicando el porcentaje del inventario representado
            st.info(
                f"📊 **Análisis de Cobertura:** El gráfico de criticidad representa al **{porcentaje_alerta:.1f}%** "
                f"({insumos_en_alerta} de {total_insumos} insumos) del inventario total que se encuentra actualmente en "
                f"situación de alerta o desabastecimiento inminente."
            )
            st.write("---")

            # Filtros y Reportes de la Tabla Detallada
            opciones_semaforo = ["TODOS"] + list(df_rop["semaforo"].unique())
            col_filtro_rop, col_excel_rop, col_pdf_rop = st.columns([1.6, 1.3, 1.1])
            
            with col_filtro_rop:
                filtro_sem = st.selectbox("Filtrar por Estado de Alerta (Tabla Completa):", opciones_semaforo, label_visibility="visible")

            df_rop_render = df_rop.copy()
            if filtro_sem != "TODOS":
                df_rop_render = df_rop_render[df_rop_render["semaforo"] == filtro_sem]

            filtros_rop_aplicados = {"Estado de Alerta Semáforo": filtro_sem}

            # BOTONES DE REPORTE
            if st.session_state.get("user_rol") == Rol.Administrador:
                usuario_actual = st.session_state.get("user_nombre_completo", "OPERADOR SIAL-MED")
                with col_excel_rop:
                    st.write('')
                    # 1. Creamos el botón disparador para evitar consultas automáticas
                    if st.button("📊 Generar Reporte en Excel (.xlsx)", use_container_width=True, key="btn_trigger_excel_rop"):
                        with st.spinner("Procesando Excel..."):
                        # 2. La consulta a la BD SOLO ocurre AQUÍ tras hacer clic
                            st.write("") # Espaciador para alinear el botón verticalmente con el selectbox
                            excel_data_rop = generar_reporte_rop_excel(df_rop_render, filtros_rop_aplicados, usuario_actual)
                            if excel_data_rop:
                                # 3. Si hay datos, habilitamos el botón nativo de descarga
                                st.download_button(
                                    label="📊 Descargar Excel",
                                    data=excel_data_rop,
                                    file_name=f"Reporte_ROP_{filtro_sem}.xlsx",
                                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                                    use_container_width=True
                                )
                # REPORTE PDF
                with col_pdf_rop:
                    st.write('')
                    # 1. Creamos el botón disparador para evitar consultas automáticas
                    if st.button("📄 Generar Reporte en PDF", use_container_width=True, key="btn_trigger_pdf_rop"):
                        with st.spinner("Procesando PDF..."):
                        # 2. La consulta a la BD SOLO ocurre AQUÍ tras hacer clic
                            pdf_data_rop = generar_reporte_rop_pdf(df_rop_render, filtros_rop_aplicados, usuario_actual)
                            if pdf_data_rop:
                                # 3. Si hay datos, habilitamos el botón nativo de descarga
                                st.download_button(
                                    label="📄 Descargar archivo PDF",
                                    data=pdf_data_rop,
                                    file_name="Reporte_ROP.pdf",
                                    mime="application/pdf"
                                )

            st.write("")

            # Renderizado de Tabla ROP
            st.data_editor(
                df_rop_render[[
                    "nombre_insumo", "clasificacion_ved", "stock_disponible", "cpd", 
                    "lead_time_promedio", "rop", "semaforo"
                ]],
                use_container_width=True,
                hide_index=True,
                disabled=True, 
                column_config={
                    "nombre_insumo": st.column_config.TextColumn("MEDICAMENTO / INSUMO"),
                    "clasificacion_ved": st.column_config.TextColumn("VED"),
                    "stock_disponible": st.column_config.NumberColumn("STOCK REAL", format="%d unds."),
                    "cpd": st.column_config.NumberColumn("CONS. DIARIO (CPD)", format="%.2f unds./día"),
                    "lead_time_promedio": st.column_config.NumberColumn("ESPERA PROM.", format="%.1f días"),
                    "rop": st.column_config.NumberColumn("PUNTO REORDEN (ROP)", format="%d unds."),
                    "semaforo": st.column_config.TextColumn("SEMÁFORO DE ALERTA")
                }
            )
            


        # ==========================================================================
        # PESTAÑA 2: GESTIÓN PREVENTIVA DE CADUCIDAD (GRÁFICOS VERTICALES)
        # ==========================================================================
        with tab_caducidad:
            st.subheader("🔬 Análisis de Ciclo de Vida e Índice de Mermas por Lote")
            st.caption(
                "Alerta de Merma: Se dispara si la velocidad de consumo (CPD) proyecta que "
                "el stock durará más días que el tiempo que le queda de vida física al lote."
            )

            # --------------------------------------------------------------------------
            # 📱 FILTRADO LOGÍSTICO Y MÉTRICAS DE CADUCIDAD
            # --------------------------------------------------------------------------
            # 1. Filtro para Gráfico 1: Lotes que NO están seguros (Solo alertas, mermas o vencidos)
            df_lotes_alerta = df_caducidad[
                ~df_caducidad["alerta_vencimiento"].str.contains("SEGURO", case=False, na=False)
            ].copy()
            # Ordenamos de menor a mayor vida útil (el más crítico primero)
            df_lotes_alerta = df_lotes_alerta.sort_values(by="dias_para_vencer", ascending=True)

            # 2. Filtro para Gráfico 2: Lotes con cantidad de riesgo real
            df_mermas_reales = df_caducidad[df_caducidad["cantidad_riesgo"] > 0].copy()
            df_mermas_reales = df_mermas_reales.sort_values(by="cantidad_riesgo", ascending=False)

            # 3. Métricas de cobertura para el banner informativo
            total_lotes = len(df_caducidad)
            lotes_comprometidos = len(df_lotes_alerta)
            porcentaje_comprometido = (lotes_comprometidos / total_lotes * 100) if total_lotes > 0 else 0

            # --------------------------------------------------------------------------
            # 📊 SECCIÓN DE GRÁFICOS RESPONSIVOS (VERTICALES)
            # --------------------------------------------------------------------------
            st.write("---")
            col_g3, col_g4 = st.columns([1, 1])

            with col_g3:
                # 📊 GRÁFICO 1: Próximos Vencimientos (Vertical)
                if not df_lotes_alerta.empty:
                    df_lotes_alerta["insumo_lote"] = df_lotes_alerta["nombre_insumo"] + "<br>(" + df_lotes_alerta["codigo_lote"] + ")"
                    
                    fig_proximos = px.bar(
                        df_lotes_alerta.head(8), # Limitamos a 8 para que las columnas respiren bien en celular
                        x="insumo_lote",
                        y="dias_para_vencer",
                        orientation="v", # v para Vertical
                        text="dias_para_vencer",
                        title="<b>Lotes con más Riesgo de Vencer (Días de Vida)</b>",
                        labels={"dias_para_vencer": "Días restantes de vida", "insumo_lote": ""},
                    )
                    
                    fig_proximos.update_traces(
                        marker_color="#e74c3c",          # Rojo de alerta
                        marker_line_color="#ffffff",
                        marker_line_width=1,
                        texttemplate='%{text} d',        # Texto dinámico abreviado para móvil
                        textposition='outside',          # Texto arriba de la barra
                        cliponaxis=False
                    )
                    
                    fig_proximos.update_layout(
                        height=360, # Altura fija óptima para gráficos verticales
                        margin=dict(t=50, b=110, l=10, r=10), # Margen inferior amplio para las etiquetas rotadas
                        bargap=0.4, # Espacio controlado para evitar barras excesivamente anchas
                        xaxis=dict(
                            tickangle=-45, # Inclinación para perfecta lectura en celulares
                            showgrid=False
                        ),
                        yaxis=dict(showgrid=True, gridcolor="rgba(255,255,255,0.1)")
                    )
                    st.plotly_chart(fig_proximos, use_container_width=True)
                else:
                    st.success("🎉 Todos los lotes en el depósito tienen un ciclo de vida óptimo y seguro.")

            with col_g4:
                # 📊 GRÁFICO 2: Pérdidas Proyectadas en Unidades (Vertical)
                if not df_mermas_reales.empty:
                    df_mermas_reales["insumo_lote"] = df_mermas_reales["nombre_insumo"] + "<br>(" + df_mermas_reales["codigo_lote"] + ")"
                    
                    fig_perdidas = px.bar(
                        df_mermas_reales.head(8), # Limitamos a 8 elementos por usabilidad
                        x="insumo_lote",
                        y="cantidad_riesgo",
                        orientation="v", # Vertical
                        text="cantidad_riesgo",
                        title="<b>Mermas Proyectadas (Unidades en Riesgo)</b>",
                        labels={"cantidad_riesgo": "Unidades estimadas a perder", "insumo_lote": ""},
                    )
                    
                    fig_perdidas.update_traces(
                        marker_color="#d62728",          # Rojo carmín uniforme
                        marker_line_color="#ffffff",
                        marker_line_width=1,
                        texttemplate='%{text} u',        # 'u' de unidades abreviado para no saturar
                        textposition='outside',          # Texto arriba de la barra
                        cliponaxis=False
                    )
                    
                    fig_perdidas.update_layout(
                        height=360,
                        margin=dict(t=50, b=110, l=10, r=10), # Margen inferior amplio para evitar cortes de texto
                        bargap=0.4,
                        xaxis=dict(
                            tickangle=-45, # Rotación para evitar colisión de nombres
                            showgrid=False
                        ),
                        yaxis=dict(showgrid=True, gridcolor="rgba(255,255,255,0.1)")
                    )
                    st.plotly_chart(fig_perdidas, use_container_width=True)
                else:
                    st.success("🎉 ¡Excelente! No se proyectan pérdidas materiales bajo la tasa de consumo actual.")

            # --------------------------------------------------------------------------
            # 🎯 BANNER INFORMATIVO DE COBERTURA
            # --------------------------------------------------------------------------
            st.warning(
                f"⚠️ **Alerta de Caducidad:** El **{porcentaje_comprometido:.1f}%** de los lotes activos "
                f"({lotes_comprometidos} de {total_lotes} lotes en total) presenta algún grado de riesgo de vencimiento "
                f"o merma acumulada. Se recomienda coordinar jornadas de distribución o traslados."
            )
            st.write("---")

            # Filtros de Caducidad para la Tabla Detallada y botones de reporte en excel y pdf
            col_chk_cad, col_excel_cad, col_pdf_cad = st.columns([1.8, 1.2, 1])

            with col_chk_cad:
                solo_riesgo = st.checkbox("Mostrar únicamente lotes con riesgo de vencimiento o merma")
            
            df_cad_render = df_caducidad.copy()
            if solo_riesgo:
                df_cad_render = df_cad_render[
                    df_cad_render["alerta_vencimiento"].str.contains("ALERTA|CRÍTICO|VENCIDO", case=False, na=False)
                ]

            filtros_cad_aplicados = "Solo Lotes Críticos / Riesgo" if solo_riesgo else "Ninguno"

            if st.session_state.get("user_rol") == Rol.Administrador:
                usuario_actual = st.session_state.get("user_nombre_completo", "OPERADOR SIAL-MED")
                with col_excel_cad:
                    # 1. Creamos el botón disparador para evitar consultas automáticas
                    if st.button("📄 Generar Reporte en Excel (.xlsx)", use_container_width=True, key="btn_trigger_excel"):
                        with st.spinner("Procesando Excel..."):
                        # 2. La consulta a la BD SOLO ocurre AQUÍ tras hacer clic
                            excel_data_cad = generar_reporte_caducidad_excel(df_cad_render, filtros_cad_aplicados, usuario_actual)
                            if excel_data_cad:       
                                st.download_button(
                                    label="📊 Generar Reporte en Excel",
                                    data=excel_data_cad,
                                    file_name="SIALMED_Reporte_Caducidad_Preventivo.xlsx",
                                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                                    use_container_width=True
                                )
                            else:
                                st.warning("No hay datos para el filtro seleccionado.")
                
                with col_pdf_cad:
                    # 1. Creamos el botón disparador para evitar consultas automáticas
                    if st.button("📄 Generar Reporte en PDF", use_container_width=True, key="btn_trigger_pdf"):
                        with st.spinner("Procesando PDF..."):
                        
                        # 2. La consulta a la BD SOLO ocurre AQUÍ tras hacer clic
                            pdf_data_cad = generar_reporte_caducidad_pdf(df_cad_render, filtros_cad_aplicados, usuario_actual)
                            if pdf_data_cad:
                                st.download_button(
                                    label="⬇️ Descargar Archivo PDF",
                                    data=pdf_data_cad,
                                    file_name="SIALMED_Reporte_Caducidad_Preventivo.pdf",
                                    mime="application/pdf"
                                )
                            else:
                                st.warning("No hay datos para el filtro seleccionado.")



            st.write("") 

            # Estilizado Condicional con validación preventiva
            # NOTA: Si migran a pandas >= 2.1, cambiar .applymap() por .map()
            df_estilizado = df_cad_render[[
                "codigo_lote", "nombre_insumo", "stock_disponible", 'cpd',
                "dias_para_vencer", "dias_duracion_stock", "cantidad_riesgo", "alerta_vencimiento"
            ]].style.applymap(destacar_excedentes, subset=["cantidad_riesgo"])


            # Tabla de lotes de caducidad
            st.dataframe(
                df_estilizado,
                use_container_width=True,
                hide_index=True,
                column_config={
                    "codigo_lote": st.column_config.TextColumn("CÓDIGO LOTE"),
                    "nombre_insumo": st.column_config.TextColumn("MEDICAMENTO"),
                    "stock_disponible": st.column_config.NumberColumn("CANT. LOTE", format="%d unds."),
                    "cpd": st.column_config.NumberColumn("CONS. DIARIO (CPD)", format="%.2f unds./día"),
                    "dias_para_vencer": st.column_config.NumberColumn("DÍAS DE VIDA", format="%d días"),
                    "dias_duracion_stock": st.column_config.NumberColumn("DÍAS DE INVENTARIO", format="%d días"),
                    "cantidad_riesgo": st.column_config.NumberColumn("CANT. A DESPACHAR (RIESGO)", format="%d unds."),
                    "alerta_vencimiento": st.column_config.TextColumn("DIAGNÓSTICO LOGÍSTICO")
                }
            )

    except Exception as e:
        st.error(f"Error en la vista de análisis logístico: {e}")
        st.stop()
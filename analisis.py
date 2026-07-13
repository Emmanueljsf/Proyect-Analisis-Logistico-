import streamlit as st
import pandas as pd
import plotly.express as px
from analisis_logistico import calcular_metricas_analiticas_sialmed
# Importación de las funciones de reporte de SIAL-MED
# (Ajusta el path de importación según la estructura de tus archivos)
from reportes_analisis import generar_reporte_rop_excel, generar_reporte_caducidad_excel
from models import Rol


def Vista_Dashboard_Logistico():
    """
    Renderiza el Panel de Inteligencia Logística y Control de Stock Preventivo del SIAL-MED.
    Consume las métricas analíticas del backend para estructurar la capa de presentación 
    del Destacamento 134 mediante componentes visuales interactivos de Streamlit y Plotly Express.
    """
    try:
        # Se asume un usuario emisor en sesión. Ajustar según tu sistema de autenticación.

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
        # BLOQUE 1: TARJETAS DE MÉTRICAS LOGÍSTICAS (Calibración Total)
        # --------------------------------------------------------------------------
        total_insumos_distintos = len(df_rop)
        
        # 1. Alertas de Reorden (Busca "ADVERTENCIA" o "REORDEN")
        insumos_en_reorden = len(df_rop[df_rop["semaforo"].str.contains("ADVERTENCIA|REORDEN", case=False, na=False)])
        
        # 2. Filtro robusto para alertas críticas sin stock
        insumos_criticos = len(df_rop[df_rop["semaforo"].str.contains("CRÍTICO|CRITICO|CERO", case=False, na=False)])
        
        # 3. Conteo de Lotes Vencidos (Busca la palabra "VENCIDO" en la alerta de caducidad)
        if not df_caducidad.empty:
            lotes_vencidos = len(df_caducidad[df_caducidad["alerta_vencimiento"].str.contains("VENCIDO", case=False, na=False)])
        else:
            lotes_vencidos = 0
            
        # 4. Lotes para Donación o en Riesgo Crítico por vencer (Captura ambas alertas de merma/crítico)
        if not df_caducidad.empty:
            lotes_riesgo_merma = len(df_caducidad[
                df_caducidad["alerta_vencimiento"].str.contains("MERMA|TRASLADAR|CRÍTICO|CRITICO", case=False, na=False)
            ])
        else:
            lotes_riesgo_merma = 0

        # Renderizado en la interfaz con una distribución limpia de 4 columnas
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

        # --------------------------------------------------------------------------
        # BLOQUE 2: PESTAÑAS DE DISTRIBUCIÓN ANALÍTICA
        # --------------------------------------------------------------------------
        tab_abastecimiento, tab_caducidad = st.tabs([
            "📦 Control de Abastecimiento (ROP / VED)", 
            "⏳ Gestión Preventiva de Caducidad"
        ])

        # ==========================================================================
        # PESTAÑA 1: PUNTO DE REORDEN Y SEMÁFORO DE STOCK
        # ==========================================================================
        with tab_abastecimiento:
            st.subheader("📋 Estado General de Abastecimiento de Medicamentos")
            #st.caption(
                
            #)

            # Filtro interactivo rápido por estado del semáforo
            opciones_semaforo = ["TODOS"] + list(df_rop["semaforo"].unique())
            
            # Colocamos el filtro y los botones de reportes alineados horizontalmente
            col_filtro_rop, _, col_btn_xls_rop = st.columns([2, 1, 1])
            
            with col_filtro_rop:
                filtro_sem = st.selectbox("Filtrar por Estado de Alerta:", opciones_semaforo, label_visibility="collapsed")

            df_rop_render = df_rop.copy()
            if filtro_sem != "TODOS":
                df_rop_render = df_rop_render[df_rop_render["semaforo"] == filtro_sem]

            # Diccionario con metadatos del filtro actual para inyectar en el reporte
            filtros_rop_aplicados = {"Estado de Alerta Semáforo": filtro_sem}

            
            if st.session_state.get("user_rol") == Rol.Administrador:
            
                usuario_actual = st.session_state.get("user_nombre_completo", "OPERADOR SIAL-MED")
                with col_btn_xls_rop:
                    # Botón de Descargar Excel
                    excel_data_rop = generar_reporte_rop_excel(df_rop_render, filtros_rop_aplicados, usuario_actual)
                    st.download_button(
                        label="📊 Generar reporte en Excel",
                        data=excel_data_rop,
                        file_name=f"Reporte_ROP_{filtro_sem}.xlsx",
                        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                        use_container_width=True
                    )

            st.write("") # Espaciador sutil

            # 🎯 AJUSTE DE INTERFAZ: Añadidas las dos nuevas métricas analíticas al renderizado
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
        # PESTAÑA 2: ÍNDICE DE RIESGO DE CADUCIDAD Y GRÁFICOS
        # ==========================================================================
        with tab_caducidad:
            st.subheader("🔬 Análisis de Ciclo de Vida e Índice de Mermas por Lote")
            st.caption(
                "Alerta de Merma: Se dispara si la velocidad de consumo (CPD) proyecta que "
                "el stock durará más días que el tiempo que le queda de vida física al lote."
            )

            # Estructura horizontal para el Checkbox y los botones de Reporte
            col_chk_cad, _, col_btn_xls_cad = st.columns([2, 1, 1])

            with col_chk_cad:
                solo_riesgo = st.checkbox("Mostrar únicamente lotes con riesgo de vencimiento o merma")
            
            df_cad_render = df_caducidad.copy()
            if solo_riesgo:
                df_cad_render = df_cad_render[
                    df_cad_render["alerta_vencimiento"].str.contains("ALERTA|CRÍTICO|VENCIDO")
                ]

            # Diccionario con metadatos del filtro actual
            filtros_cad_aplicados = {"Solo Lotes Críticos / Riesgo": "SÍ" if solo_riesgo else "NO"}

            if st.session_state.get("user_rol") == Rol.Administrador:
                usuario_actual = st.session_state.get("user_nombre_completo", "OPERADOR SIAL-MED")
                with col_btn_xls_cad:
                    # Botón de Descargar Excel
                    excel_data_cad = generar_reporte_caducidad_excel(df_cad_render, filtros_cad_aplicados, usuario_actual)
                    st.download_button(
                        label="📊 Generar Reporte en Excel",
                        data=excel_data_cad,
                        file_name="Reporte_Caducidad_Preventivo.xlsx",
                        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                        use_container_width=True
                    )

            st.write("") # Espaciador sutil

            #  ESTILIZADO CONDICIONAL DE PANDAS PARA RESALTAR UNIDADES EN RIESGO
            def destacar_excedentes(val):
                if val > 0:
                    return "background-color: rgba(214, 39, 40, 0.2); color: #ff7f7f; font-weight: bold;"
                return "color: #888888;"

            # Aplicamos el estilo únicamente a la columna analítica de riesgo
            df_estilizado = df_cad_render[[
                "codigo_lote", "nombre_insumo", "stock_disponible", 
                "dias_para_vencer", "dias_duracion_stock", "cantidad_riesgo", "alerta_vencimiento"
            ]].style.applymap(destacar_excedentes, subset=["cantidad_riesgo"])

            # Despliegue atómico de la tabla de lotes con la nueva configuración de columnas
            st.dataframe(
                df_estilizado,
                use_container_width=True,
                hide_index=True,
                column_config={
                    "codigo_lote": st.column_config.TextColumn("CÓDIGO LOTE"),
                    "nombre_insumo": st.column_config.TextColumn("MEDICAMENTO"),
                    "stock_disponible": st.column_config.NumberColumn("CANT. LOTE", format="%d unds."),
                    "dias_para_vencer": st.column_config.NumberColumn("DÍAS DE VIDA", format="%d días"),
                    "dias_duracion_stock": st.column_config.NumberColumn("DÍAS COBERTURA STOCK", format="%d días"),
                    "cantidad_riesgo": st.column_config.NumberColumn("CANT. A DESPACHAR (RIESGO)", format="%d unds."),
                    "alerta_vencimiento": st.column_config.TextColumn("DIAGNÓSTICO LOGÍSTICO")
                }
            )

            st.markdown("---")
            st.subheader("📈 Visualización Gráfica de Existencias Críticas")
            
            # ----------------------------------------------------------------------
            # GRÁFICO DE PLOTLY EXPRESS: Stock Disponible por Insumo
            # ----------------------------------------------------------------------
            fig_barras = px.bar(
                df_rop,
                x="nombre_insumo",
                y="stock_disponible",
                color="semaforo",
                title="Suma de Stock Físico Actual por Medicamento",
                labels={"stock_disponible": "Unidades en Almacén", "nombre_insumo": "Insumo Médico"},
                color_discrete_map={
                    "🟢 ÓPTIMO": "#2ca02c",
                    "🟡 ADVERTENCIA (REORDEN)": "#ff7f0e",
                    "🔴 CRÍTICO (SIN STOCK)": "#d62728"
                }
            )
            st.plotly_chart(fig_barras, use_container_width=True)

    except Exception as e:
            print(f"Error crítico en la vista de analisis logistico: {e}")
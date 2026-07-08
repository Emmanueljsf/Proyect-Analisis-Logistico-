import streamlit as st
import pandas as pd
import plotly.express as px
from analisis_logistico import calcular_metricas_analiticas_sialmed

def Vista_Dashboard_Logistico():
    """
    PANEL DE INTELIGENCIA LOGÍSTICA Y CONTROL DE STOCK PREVENTIVO (SIAL-MED)
    ======================================================================
    Capa de Presentación Premium integrada con Pandas y Plotly Express.
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

        # --------------------------------------------------------------------------
        # ⚡ EXTRACCIÓN DE DATOS PROCESADOS POR EL BACKEND
        # --------------------------------------------------------------------------
        with st.spinner("Ejecutando algoritmos logísticos en tiempo real..."):
            df_rop, df_caducidad = calcular_metricas_analiticas_sialmed()

        # 📌 CONTROL DE SEGURIDAD EXPLICITO
        if df_rop.empty or "semaforo" not in df_rop.columns:
            st.info("💡 Actualmente no existen lotes de insumos registrados o activos en el inventario para procesar el análisis logístico.")
            return

        # --------------------------------------------------------------------------
        # 🎛️ BLOQUE 1: TARJETAS DE MÉTRICAS LOGÍSTICAS (Calibración Total)
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
        # 📑 BLOQUE 2: PESTAÑAS DE DISTRIBUCIÓN ANALÍTICA
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
            st.caption(
                "El Punto de Reorden (ROP) se calcula mediante el modelado avanzado de criticidad VED: "
                "Insumos Vitales (Máximo tiempo de espera + 3 días), Esenciales (Máximo tiempo de espera) "
                "y Deseables (Tiempo de espera promedio real)."
            )

            # Filtro interactivo rápido por estado del semáforo
            opciones_semaforo = ["TODOS"] + list(df_rop["semaforo"].unique())
            filtro_sem = st.selectbox("Filtrar por Estado de Alerta:", opciones_semaforo)

            df_rop_render = df_rop.copy()
            if filtro_sem != "TODOS":
                df_rop_render = df_rop_render[df_rop_render["semaforo"] == filtro_sem]

            # 🎯 AJUSTE DE INTERFAZ: Añadidas las dos nuevas métricas analíticas al renderizado
            st.data_editor(
                df_rop_render[[
                    "nombre_insumo", "clasificacion_ved", "stock_disponible", "cpd", 
                    "lead_time_promedio", "lead_time_maximo", "rop", "semaforo"
                ]],
                use_container_width=True,
                hide_index=True,
                disabled=True, 
                column_config={
                    "nombre_insumo": st.column_config.TextColumn("MEDICAMENTO / INSUMO"),
                    "clasificacion_ved": st.column_config.TextColumn("CRITICIDAD VED"),
                    "stock_disponible": st.column_config.NumberColumn("STOCK REAL", format="%d unds."),
                    "cpd": st.column_config.NumberColumn("CONS. DIARIO (CPD)", format="%.2f unds./día"),
                    "lead_time_promedio": st.column_config.NumberColumn("ESPERA PROM.", format="%.1f días"),
                    "lead_time_maximo": st.column_config.NumberColumn("ESPERA MÁX.", format="%d días"),
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

            # Filtro rápido para aislar los lotes que requieren acción inmediata (Donar/Trasladar)
            solo_riesgo = st.checkbox("Mostrar únicamente lotes con riesgo de vencimiento o merma")
            
            df_cad_render = df_caducidad.copy()
            if solo_riesgo:
                df_cad_render = df_cad_render[
                    df_cad_render["alerta_vencimiento"].str.contains("ALERTA|CRÍTICO|VENCIDO")
                ]

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
            # Generamos una gráfica de barras interactiva en una sola línea de código
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
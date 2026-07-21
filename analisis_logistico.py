import uuid
import logging
import streamlit as st
from sqlmodel import Session, select, func
from models import Salidas, DetallesSalida, Entradas, Lotes, Insumos, engine, Estado
from datetime import datetime, date, timedelta
import pandas as pd
import numpy as np

# EXTRACTOR Y PROCESADOR DE MÉTRICAS LOGÍSTICAS CON PANDAS 

def calcular_metricas_analiticas_sialmed(dias_ventana: int = 120):
    """
    Función Maestra de Ingeniería Optimizada: Resuelve el estado del inventario, 
    patrones de consumo y mermas potenciales utilizando agregaciones nativas de SQL.
    Evita cuellos de botella procesando de forma vectorial mediante Pandas y NumPy.

    Parámetros: dias_ventana : int, opcional
        Número de días hacia el pasado para evaluar el historial de consumo real. 
        Por defecto es 120 días.

    Retorna: tuple (pd.DataFrame, pd.DataFrame)
        Una tupla con dos DataFrames de Pandas:
        1. df_rop: Análisis de Punto de Reorden, consumos promedio (CPD) y estado de stock (Semáforo).
        2. df_caducidad: Diagnóstico logístico predictivo de lotes próximos a vencer y cálculo de mermas.
    """
    try:
        hoy = date.today()
        fecha_limite_ventana = hoy - timedelta(days=dias_ventana)
        
        with Session(engine) as session:
            # ----------------------------------------------------------------------
            # PASO 1: Consumo Directo Agrupado por Insumo en SQL
            # ----------------------------------------------------------------------
            stmt_salidas_sql = (
                select(
                    Lotes.id_insumo,
                    func.sum(DetallesSalida.cantidad).label("cantidad_total"),
                    func.min(Salidas.fecha).label("primera_salida")
                )
                .join(DetallesSalida, Lotes.id_lote == DetallesSalida.id_lote)
                .join(Salidas, DetallesSalida.id_salida == Salidas.id_salida)
                .where(Salidas.estado == Estado.VALIDO)
                .where(Salidas.razon_salida == "Consumo Clínico")
                .where(Salidas.fecha >= fecha_limite_ventana)
                .group_by(Lotes.id_insumo)
            )
            resultados_salidas = session.exec(stmt_salidas_sql).all()
            
            if resultados_salidas:
                df_salidas_raw = pd.DataFrame(resultados_salidas, columns=["id_insumo", "cantidad", "primera_salida"])
                
                # Conversión robusta a datetime
                df_salidas_raw["primera_salida"] = pd.to_datetime(df_salidas_raw["primera_salida"], errors='coerce')
                
                # Ciclo operativo dinámico individual para evitar subestimar insumos nuevos
                df_salidas_raw["dias_desde_primera_salida"] = (
                    pd.to_datetime(hoy) - df_salidas_raw["primera_salida"]
                ).dt.days
                
                df_salidas_raw["divisor_por_insumo"] = df_salidas_raw["dias_desde_primera_salida"].clip(lower=1, upper=dias_ventana)
                df_salidas_raw["cpd"] = df_salidas_raw["cantidad"] / df_salidas_raw["divisor_por_insumo"]
                
                df_consumo_total = df_salidas_raw[["id_insumo", "cantidad", "cpd"]].copy()
            else:
                df_consumo_total = pd.DataFrame(columns=["id_insumo", "cantidad", "cpd"])

            # ----------------------------------------------------------------------
            # PASO 2: Cálculo Dinámico Matemático de Inventario por Lote
            # ----------------------------------------------------------------------
            stmt_ent = select(Entradas.id_lote, func.sum(Entradas.cantidad).label("total_entrada")).where(Entradas.estado == Estado.VALIDO).group_by(Entradas.id_lote)
            df_ent = pd.DataFrame(session.exec(stmt_ent).all(), columns=["id_lote", "total_entrada"])
            
            stmt_sal = select(DetallesSalida.id_lote, func.sum(DetallesSalida.cantidad).label("total_salida")).join(Salidas).where(Salidas.estado == Estado.VALIDO).group_by(DetallesSalida.id_lote)
            df_sal = pd.DataFrame(session.exec(stmt_sal).all(), columns=["id_lote", "total_salida"])
            
            stmt_lotes_activos = select(Lotes.id_lote, Lotes.codigo_lote, Lotes.id_insumo, Lotes.fecha_vencimiento).where(Lotes.activo == True)
            df_lotes_base = pd.DataFrame(session.exec(stmt_lotes_activos).all(), columns=["id_lote", "codigo_lote", "id_insumo", "fecha_vencimiento"])
            
            if df_lotes_base.empty:
                return pd.DataFrame(), pd.DataFrame()
                
            df_lotes = pd.merge(df_lotes_base, df_ent, on="id_lote", how="left").fillna(0)
            df_lotes = pd.merge(df_lotes, df_sal, on="id_lote", how="left").fillna(0)
            
            df_lotes["stock_disponible"] = (df_lotes["total_entrada"] - df_lotes["total_salida"]).clip(lower=0).astype(int)
            
            stmt_insumos_lookup = select(Insumos.id_insumo, Insumos.nombre, Insumos.clasificacion_ved)
            df_insumos_lookup = pd.DataFrame(session.exec(stmt_insumos_lookup).all(), columns=["id_insumo", "nombre_insumo", "clasificacion_ved"])
            df_insumos_lookup["nombre_insumo"] = df_insumos_lookup["nombre_insumo"]
            df_insumos_lookup["clasificacion_ved"] = df_insumos_lookup["clasificacion_ved"].str.upper()
            
            df_lotes = pd.merge(df_lotes, df_insumos_lookup, on="id_insumo", how="left")

            # ----------------------------------------------------------------------
            # PASO 3: Algoritmo ROP con Enfoque de Demanda Variable (Fórmula Recomendada)
            # ----------------------------------------------------------------------
            df_stock_general = df_lotes.groupby("id_insumo")["stock_disponible"].sum().reset_index()
            
            # --- 3.1. PROCESAMIENTO DEL LEAD TIME Y FILTRO IQR GRANULAR POR INSUMO ---
            stmt_entradas_lt = (
                select(Entradas.id_lote, Lotes.id_insumo, Entradas.fecha_pedido, Entradas.fecha_recepcion)
                .join(Lotes, Entradas.id_lote == Lotes.id_lote)
                .where(Entradas.estado == Estado.VALIDO)
            )
            resultados_entradas = session.exec(stmt_entradas_lt).all()
            
            if resultados_entradas:
                df_entradas = pd.DataFrame(
                    resultados_entradas, 
                    columns=["id_lote", "id_insumo", "fecha_pedido", "fecha_recepcion"]
                )
                df_entradas["fecha_pedido"] = pd.to_datetime(df_entradas["fecha_pedido"], errors='coerce')
                df_entradas["fecha_recepcion"] = pd.to_datetime(df_entradas["fecha_recepcion"], errors='coerce')
                df_entradas["lead_time"] = (df_entradas["fecha_recepcion"] - df_entradas["fecha_pedido"]).dt.days
                
                # Filtro IQR adaptativo por grupo de insumo
                def filtrar_outliers_por_insumo(grupo, factor=1.5):
                    if len(grupo) >= 4:
                        q1 = grupo["lead_time"].quantile(0.25)
                        q3 = grupo["lead_time"].quantile(0.75)
                        iqr = q3 - q1
                        return grupo[(grupo["lead_time"] >= (q1 - factor * iqr)) & (grupo["lead_time"] <= (q3 + factor * iqr))]
                    return grupo

                df_entradas = df_entradas.groupby("id_insumo", group_keys=False).apply(filtrar_outliers_por_insumo)
                
                df_lead_time_stats = df_entradas.groupby("id_insumo").agg(
                    lead_time_promedio=('lead_time', 'mean')
                ).reset_index()
            else:
                df_lead_time_stats = pd.DataFrame(columns=["id_insumo", "lead_time_promedio"])

            # --- 3.2. VARIABILIDAD DE LA DEMANDA DIARIA REAL ---
            stmt_consumo_diario = (
                select(
                    Lotes.id_insumo,
                    Salidas.fecha,
                    func.sum(DetallesSalida.cantidad).label("consumo_diario")
                )
                .join(DetallesSalida, Lotes.id_lote == DetallesSalida.id_lote)
                .join(Salidas, DetallesSalida.id_salida == Salidas.id_salida)
                .where(Salidas.estado == Estado.VALIDO)
                .where(Salidas.razon_salida == "Consumo Clínico")
                .where(Salidas.fecha >= fecha_limite_ventana)
                .group_by(Lotes.id_insumo, Salidas.fecha)
            )
            resultados_diarios = session.exec(stmt_consumo_diario).all()
            
            if resultados_diarios:
                df_diario_raw = pd.DataFrame(resultados_diarios, columns=["id_insumo", "fecha", "consumo_diario"])
                df_desviacion_real = df_diario_raw.groupby("id_insumo")["consumo_diario"].std().reset_index()
                df_desviacion_real = df_desviacion_real.rename(columns={"consumo_diario": "desviacion_demanda_real"})
            else:
                df_desviacion_real = pd.DataFrame(columns=["id_insumo", "desviacion_demanda_real"])

            # --- 3.3. CONSOLIDACIÓN DEL MAESTRO ROP ---
            df_insumos_meta = df_insumos_lookup.copy()
            
            df_rop_final = pd.merge(df_insumos_meta, df_stock_general, on="id_insumo", how="left")
            df_rop_final = pd.merge(df_rop_final, df_consumo_total[["id_insumo", "cpd"]], on="id_insumo", how="left")
            df_rop_final = pd.merge(df_rop_final, df_lead_time_stats, on="id_insumo", how="left")
            df_rop_final = pd.merge(df_rop_final, df_desviacion_real, on="id_insumo", how="left")
            
            df_rop_final["stock_disponible"] = df_rop_final["stock_disponible"].fillna(0).astype(int)
            df_rop_final["cpd"] = df_rop_final["cpd"].fillna(0)
            df_rop_final["lead_time_promedio"] = df_rop_final["lead_time_promedio"].fillna(0) 
            
            # Respaldo teórico si el historial es muy corto para calcular desviaciones
            df_rop_final["desviacion_demanda"] = df_rop_final["desviacion_demanda_real"].fillna(df_rop_final["cpd"] * 0.20)

            # --- 3.4. CÁLCULO DEL SS MEDIANTE FÓRMULA SIMPLIFICADA PROTEGIDA ---
            def asignar_factor_z(ved):
                if "VITAL" in ved or ved == "V": return 3.09
                if "ESENCIAL" in ved or ved == "E": return 1.96
                return 1.28

            df_rop_final["z"] = df_rop_final["clasificacion_ved"].apply(asignar_factor_z)
            
            # 🎯 Corrección Física Aplicada: SS = Z * σ_d * √LT_promedio
            df_rop_final["ss"] = (
                df_rop_final["z"] 
                * df_rop_final["desviacion_demanda"] 
                * np.sqrt(df_rop_final["lead_time_promedio"])
            ).fillna(0).apply(np.ceil).astype(int)
            
            # Punto de Reorden Final
            df_rop_final["rop"] = (
                (df_rop_final["cpd"] * df_rop_final["lead_time_promedio"]) + df_rop_final["ss"]
            ).apply(np.ceil).astype(int)

            def asignar_semaforo_abastecimiento(row):
                stock = row["stock_disponible"]
                rop = row["rop"]
                if stock == 0:
                    return "🔴 CRÍTICO (SIN STOCK)"
                elif stock <= rop:
                    return "🟡 ADVERTENCIA (REORDEN)"
                return "🟢 ÓPTIMO"

            df_rop_final["semaforo"] = df_rop_final.apply(asignar_semaforo_abastecimiento, axis=1)

            # ----------------------------------------------------------------------
            # PASO 4: Índice de Riesgo de Caducidad (Análisis Atómico por Lote)
            # ----------------------------------------------------------------------
            df_caducidad = df_lotes[["id_lote", "codigo_lote", "id_insumo", "nombre_insumo", "clasificacion_ved", "stock_disponible", "fecha_vencimiento"]].copy()
            df_caducidad = pd.merge(df_caducidad, df_rop_final[["id_insumo", "cpd"]], on="id_insumo", how="left").fillna(0)
            
            df_caducidad["fecha_vencimiento"] = pd.to_datetime(df_caducidad["fecha_vencimiento"]).dt.date
            df_caducidad["dias_para_vencer"] = df_caducidad["fecha_vencimiento"].apply(lambda x: (x - hoy).days if pd.notnull(x) else 0)
            
            df_caducidad["dias_duracion_stock"] = np.where(
                df_caducidad["cpd"] == 0, 
                9999, 
                np.floor(df_caducidad["stock_disponible"] / df_caducidad["cpd"])
            ).astype(int)
            
            def detectar_riesgo_vencimiento(row):
                dias_vencer = row["dias_para_vencer"]
                dias_stock = row["dias_duracion_stock"]
                if dias_vencer <= 0:
                    return "🚨 LOTE VENCIDO (AISLAR)"
                elif dias_vencer <= 20 and dias_stock >= dias_vencer:
                    return "⚠️ CRÍTICO (MENOS DE 20 DÍAS)"
                elif dias_stock >= dias_vencer:
                    return "🔄 ALERTA: RIESGO DE MERMA"
                return "✔️​ SEGURO"
                    
            df_caducidad["alerta_vencimiento"] = df_caducidad.apply(detectar_riesgo_vencimiento, axis=1)

            def calcular_cantidad_en_riesgo(row):
                alerta = row["alerta_vencimiento"]
                stock = row["stock_disponible"]
                cpd = row["cpd"]
                dias_vencer = row["dias_para_vencer"]

                if "VENCIDO" in alerta:
                    return stock
                elif "MERMA" in alerta or "CRÍTICO" in alerta:
                    excedente = stock - (cpd * dias_vencer)
                    return int(np.ceil(max(0, excedente)))
                return 0

            df_caducidad["cantidad_riesgo"] = df_caducidad.apply(calcular_cantidad_en_riesgo, axis=1)*1.20
            
            return df_rop_final, df_caducidad
    
    except Exception as e:
        correlation_id = str(uuid.uuid4())
        # Log estructurado para el Avance #6
        logging.error(f'{{"correlation_id": "{correlation_id}", "error": "{str(e)}", "modulo": "analisis_logistico"}}')
        st.error(f"Error procesando métricas. Reporte el código: [{correlation_id}]")
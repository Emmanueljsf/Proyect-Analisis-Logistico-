from sqlmodel import Session, select, func
from models import Salidas, DetallesSalida, Entradas, Lotes, Insumos, engine, Estado
from datetime import datetime, date, timedelta
import pandas as pd
import numpy as np

# EXTRACTOR Y PROCESADOR DE MÉTRICAS LOGÍSTICAS CON PANDAS 

def calcular_metricas_analiticas_sialmed(dias_ventana: int= 120):
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
            # OPTIMIZACIÓN DEL PASO 1: Consumo Directo Agrupado por Insumo en SQL
            # ----------------------------------------------------------------------
            # Extraemos el consumo y la fecha de la primera salida en una sola operación vectorial
            stmt_salidas_sql = (
                select(
                    Lotes.id_insumo,
                    func.sum(DetallesSalida.cantidad).label("cantidad_total"),
                    func.min(Salidas.fecha).label("primera_salida")
                )
                .join(DetallesSalida, Lotes.id_lote == DetallesSalida.id_lote)
                .join(Salidas, DetallesSalida.id_salida == Salidas.id_salida)
                .where(Salidas.estado == Estado.VALIDO)
                .where(Salidas.razon_salida == "CONSUMO CLÍNICO")
                .where(Salidas.fecha >= fecha_limite_ventana)
                .group_by(Lotes.id_insumo)
            )
            resultados_salidas = session.exec(stmt_salidas_sql).all()
            
            # Mapeamos a DataFrame de consumo indexado por id_insumo
            if resultados_salidas:
                df_salidas_raw = pd.DataFrame(resultados_salidas, columns=["id_insumo", "cantidad", "primera_salida"])
                # Calculamos el divisor general basado en la primera salida global registrada en la ventana
                primera_salida_sistema = pd.to_datetime(df_salidas_raw["primera_salida"]).min().date()
                dias_operacion_real = (hoy - primera_salida_sistema).days
                divisor_efectivo = max(1, min(dias_operacion_real, dias_ventana))
                
                df_consumo_total = df_salidas_raw[["id_insumo", "cantidad"]].copy()
                df_consumo_total["cpd"] = df_consumo_total["cantidad"] / divisor_efectivo
            else:
                df_consumo_total = pd.DataFrame(columns=["id_insumo", "cantidad", "cpd"])

            # ----------------------------------------------------------------------
            # ⚡ OPTIMIZACIÓN DEL PASO 2: Cálculo Dinámico Matemático de Inventario por Lote
            # ----------------------------------------------------------------------
            # En lugar de usar la propiedad @property iterativa, sumamos entradas y restando salidas en SQL.
            
            # 1. Entradas totales agrupadas por Lote
            stmt_ent = select(Entradas.id_lote, func.sum(Entradas.cantidad).label("total_entrada")).where(Entradas.estado == Estado.VALIDO).group_by(Entradas.id_lote)
            df_ent = pd.DataFrame(session.exec(stmt_ent).all(), columns=["id_lote", "total_entrada"])
            
            # 2. Salidas totales agrupadas por Lote
            stmt_sal = select(DetallesSalida.id_lote, func.sum(DetallesSalida.cantidad).label("total_salida")).join(Salidas).where(Salidas.estado == Estado.VALIDO).group_by(DetallesSalida.id_lote)
            df_sal = pd.DataFrame(session.exec(stmt_sal).all(), columns=["id_lote", "total_salida"])
            
            # 3. Metadatos de lotes ACTIVOS
            stmt_lotes_activos = select(Lotes.id_lote, Lotes.codigo_lote, Lotes.id_insumo, Lotes.fecha_vencimiento).where(Lotes.activo == True)
            df_lotes_base = pd.DataFrame(session.exec(stmt_lotes_activos).all(), columns=["id_lote", "codigo_lote", "id_insumo", "fecha_vencimiento"])
            
            if df_lotes_base.empty:
                return pd.DataFrame(), pd.DataFrame()
                
            # Cruzamos matrices en memoria a alta velocidad con Pandas
            df_lotes = pd.merge(df_lotes_base, df_ent, on="id_lote", how="left").fillna(0)
            df_lotes = pd.merge(df_lotes, df_sal, on="id_lote", how="left").fillna(0)
            
            # stock_disponible matemático instantáneo por fila sin colapsar el ORM
            df_lotes["stock_disponible"] = (df_lotes["total_entrada"] - df_lotes["total_salida"]).clip(lower=0).astype(int)
            
            # Traemos datos del insumo para completar los datos que requiere el df_lotes original
            stmt_insumos_lookup = select(Insumos.id_insumo, Insumos.nombre, Insumos.clasificacion_ved)
            df_insumos_lookup = pd.DataFrame(session.exec(stmt_insumos_lookup).all(), columns=["id_insumo", "nombre_insumo", "clasificacion_ved"])
            df_insumos_lookup["nombre_insumo"] = df_insumos_lookup["nombre_insumo"].str.upper()
            df_insumos_lookup["clasificacion_ved"] = df_insumos_lookup["clasificacion_ved"].str.upper()
            
            df_lotes = pd.merge(df_lotes, df_insumos_lookup, on="id_insumo", how="left")

            # ----------------------------------------------------------------------
            # PASO 3: Algoritmo ROP (Punto de Reorden Dinámico por Insumo)
            # ----------------------------------------------------------------------
            df_stock_general = df_lotes.groupby("id_insumo")["stock_disponible"].sum().reset_index()
            
            # ----------------------------------------------------------------------
            # C. Lead Time Promedio y Máximo Real desde SQL (Corregido para @property)
            # ----------------------------------------------------------------------
            # AJUSTE: Traemos las fechas físicas en lugar de la propiedad calculada
            stmt_entradas_lt = (
                select(Entradas.id_lote, Lotes.id_insumo, Entradas.fecha_pedido, Entradas.fecha_recepcion)
                .join(Lotes, Entradas.id_lote == Lotes.id_lote)
                .where(Entradas.estado == Estado.VALIDO)
            )
            resultados_entradas = session.exec(stmt_entradas_lt).all()
            
            if resultados_entradas:
                # Reconstruimos el DataFrame con las fechas físicas
                df_entradas = pd.DataFrame(
                    resultados_entradas, 
                    columns=["id_lote", "id_insumo", "fecha_pedido", "fecha_recepcion"]
                )
                
                # Convertimos a tipo datetime de Pandas por seguridad
                df_entradas["fecha_pedido"] = pd.to_datetime(df_entradas["fecha_pedido"])
                df_entradas["fecha_recepcion"] = pd.to_datetime(df_entradas["fecha_recepcion"])
                
                # ⚡ CÁLCULO MATRICIAL EN PANDAS: Reemplaza al property de forma ultraveloz
                df_entradas["lead_time"] = (df_entradas["fecha_recepcion"] - df_entradas["fecha_pedido"]).dt.days
                
                # Agrupamos para obtener la media y el máximo histórico tal como lo pide tu ROP
                df_lead_time_stats = df_entradas.groupby("id_insumo").agg(
                    lead_time_promedio=('lead_time', 'mean'),
                    lead_time_maximo=('lead_time', 'max')
                ).reset_index()
            else:
                df_lead_time_stats = pd.DataFrame(columns=["id_insumo", "lead_time_promedio", "lead_time_maximo"])

            # D. Catálogo Maestro Base (Mantenemos la solución que rescata el stock 0)
            df_insumos_meta = df_insumos_lookup.copy()
            
            df_rop_final = pd.merge(df_insumos_meta, df_stock_general, on="id_insumo", how="left")
            df_rop_final = pd.merge(df_rop_final, df_consumo_total[["id_insumo", "cpd"]], on="id_insumo", how="left")
            df_rop_final = pd.merge(df_rop_final, df_lead_time_stats, on="id_insumo", how="left")
            
            df_rop_final["stock_disponible"] = df_rop_final["stock_disponible"].fillna(0).astype(int)
            df_rop_final["cpd"] = df_rop_final["cpd"].fillna(0)
            df_rop_final["lead_time_promedio"] = df_rop_final["lead_time_promedio"].fillna(5.0) 
            df_rop_final["lead_time_maximo"] = df_rop_final["lead_time_maximo"].fillna(8.0) 
            
            # Funciones vectorizadas o apply eficientes
            def calcular_rop_fila(row):
                cpd = row["cpd"]
                ved = row["clasificacion_ved"]
                lt_promedio = row["lead_time_promedio"]
                lt_maximo = row["lead_time_maximo"]
                
                if "VITAL" in ved or ved == "V":
                    rop_calculado = cpd * (lt_maximo + 3)
                elif "ESENCIAL" in ved or ved == "E":
                    rop_calculado = cpd * lt_maximo
                else:
                    rop_calculado = cpd * lt_promedio
                return int(np.ceil(rop_calculado))

            def asignar_semaforo_abastecimiento(row):
                stock = row["stock_disponible"]
                rop = row["rop"]
                if stock == 0:
                    return "🔴 CRÍTICO (SIN STOCK)"
                elif stock <= rop:
                    return "🌕 ADVERTENCIA (REORDEN)"
                return "🟢 ÓPTIMO"

            df_rop_final["rop"] = df_rop_final.apply(calcular_rop_fila, axis=1)
            df_rop_final["semaforo"] = df_rop_final.apply(asignar_semaforo_abastecimiento, axis=1)

            # ----------------------------------------------------------------------
            # PASO 4: Índice de Riesgo de Caducidad (Análisis Atómico por Lote)
            # ----------------------------------------------------------------------
            df_caducidad = df_lotes[["id_lote", "codigo_lote", "id_insumo", "nombre_insumo", "clasificacion_ved", "stock_disponible", "fecha_vencimiento"]].copy()
            df_caducidad = pd.merge(df_caducidad, df_rop_final[["id_insumo", "cpd"]], on="id_insumo", how="left").fillna(0)
            
            df_caducidad["dias_para_vencer"] = df_caducidad["fecha_vencimiento"].apply(lambda x: (x - hoy).days)
            
            # Optimización del cálculo de cobertura de stock
            df_caducidad["dias_duracion_stock"] = np.where(
                df_caducidad["cpd"] == 0, 
                9999, 
                np.floor(df_caducidad["stock_disponible"] / df_caducidad["cpd"])
            ).astype(int)
            
            # Semáforos de Vencimiento Analíticos
            def detectar_riesgo_vencimiento(row):
                dias_vencer = row["dias_para_vencer"]
                dias_stock = row["dias_duracion_stock"]
                if dias_vencer <= 0:
                    return "🚨 LOTE VENCIDO (AISLAR)"
                elif dias_vencer <= 20 and dias_stock > dias_vencer:
                    return "⚠️ CRÍTICO (MENOS DE 20 DÍAS)"
                elif dias_stock > dias_vencer:
                    return "🔄 ALERTA: RIESGO DE MERMA (DONAR/TRASLADAR)"
                return "✔️​ SEGURO"
                    
            df_caducidad["alerta_vencimiento"] = df_caducidad.apply(detectar_riesgo_vencimiento, axis=1)

            # Cálculo de merma/excedentes en riesgo
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

            df_caducidad["cantidad_riesgo"] = df_caducidad.apply(calcular_cantidad_en_riesgo, axis=1)
            
            return df_rop_final, df_caducidad
    
    except Exception as e:
            print(f"Error crítico en la función de analisis logistico: {e}")
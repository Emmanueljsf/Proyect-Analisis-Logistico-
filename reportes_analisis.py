import uuid
import logging
import io
import re
import math
from seguridad import es_administrador
import streamlit as st
from datetime import datetime
import pandas as pd
from openpyxl import Workbook
from openpyxl.styles import Font, Alignment, PatternFill
from openpyxl.utils.dataframe import dataframe_to_rows
from openpyxl.utils import get_column_letter

# Importación de la clase base institucional compartida y los estilos de la suite
from reportes import (
    PDFBaseSIALMED,
    aplicar_membrete_excel,
    autoajustar_columnas_excel,
    FUENTE_CABECERA_TABLA,
    FILL_AZUL_MILITAR,
    ALINEAR_CENTRO,
    ALINEAR_IZQ
)

# ==============================================================================
# SECCIÓN: UTILERÍAS DE SANITIZACIÓN
# ==============================================================================

def limpiar_emojis(texto) -> str:
    """
    Remueve de forma estricta cualquier emoji, símbolo del plano suplementario,
    dingbats, caracteres especiales no imprimibles y, de manera crítica, los 
    selectores de variación (como \\ufe0f o \\ufe0e) que rompen la fuente Helvetica de FPDF.
    Returns:
        str: Cadena de texto limpia, decodificada de forma segura en 'latin1' 
            y sin espacios en blanco redundantes en los extremos.
    """
    if texto is None:
        return ""
    texto_str = str(texto)
    
    # 1. Elimina selectores de variación invisible (U+FE00 a U+FE0F) que causan el error
    texto_sin_selectores = re.sub(r'[\ufe00-\ufe0f]', '', texto_str)
    
    # 2. Elimina caracteres del plano suplementario (emojis del plano U+10000 en adelante)
    texto_sin_suplementarios = re.sub(r'[\U00010000-\U0010ffff]', '', texto_sin_selectores)
    
    # 3. Elimina símbolos misceláneos, transporte, marcas y dingbats (U+2600 a U+27BF)
    texto_limpio = re.sub(r'[\u2600-\u27BF]', '', texto_sin_suplementarios)
    
    # 4. Asegura la codificación estándar (reemplaza caracteres incompatibles por un espacio vacío o un fallback seguro)
    texto_limpio_codificado = texto_limpio.encode('latin1', errors='ignore').decode('latin1')
    
    return texto_limpio_codificado.strip()


# ==============================================================================
# SECCIÓN: REPORTE DE PUNTO DE REORDEN (ROP)
# ==============================================================================

def generar_reporte_rop_excel(df_rop: pd.DataFrame, filtros: dict, usuario_emisor: str) -> bytes:
    """Genera el reporte analítico de Punto de Reorden (ROP) en formato Excel (.xlsx).
    Aplica el membrete oficial, formato de colores institucional (Azul Militar),
    alineación adaptativa y autoajuste de columnas.

    Parametros:
        df_rop: DataFrame con las columnas: 'nombre_insumo', 'clasificacion_ved', 
            'stock_disponible', 'cpd', 'lead_time_promedio', 'rop' y 'semaforo'.
        filtros: Diccionario con los parámetros de búsqueda aplicados.
        usuario_emisor: Nombre del usuario que emite el reporte.

    Returns:
        bytes: Stream binario del archivo Excel, o b"" si el DataFrame está vacío.
    """
    # Barrera de seguridad explícita
    if not es_administrador():
        st.error("Acceso denegado: Solo administradores pueden generar este reporte.")
        return b""
    
    try:
        if df_rop.empty:
            return b""

        # Preparación de datos limpia para el archivo Excel (libre de emojis)
        datos_matriz = []
        for _, fila in df_rop.iterrows():
            datos_matriz.append({
                "MEDICAMENTO / INSUMO": limpiar_emojis(fila["nombre_insumo"]),
                "VED": limpiar_emojis(fila["clasificacion_ved"]),
                "STOCK REAL": int(fila["stock_disponible"]),
                "CONS. DIARIO (CPD)": f"{float(fila['cpd']):.2f}",
                "ESPERA PROM.": f"{float(fila['lead_time_promedio']):.2f}",
                "PUNTO REORDEN (ROP)": int(fila["rop"]),
                "SEMÁFORO DE ALERTA": limpiar_emojis(fila["semaforo"])
            })

        df_final = pd.DataFrame(datos_matriz)

        wb = Workbook()
        ws = wb.active
        ws.title = "Análisis ROP"
        
        # Renderizado del membrete oficial adaptado a 7 columnas (Letra G)
        str_filtros = limpiar_emojis(", ".join([f"{k}: {v}" for k, v in filtros.items()]))
        fila_tabla = aplicar_membrete_excel(
            ws, 
            ultima_letra_col="G", 
            titulo_reporte=f"Análisis Logístico de Stock (Filtro: {str_filtros})", 
            usuario_emisor=limpiar_emojis(usuario_emisor)
        )

        # Inyección y formateo de cabeceras de tabla
        for col_num, column_title in enumerate(df_final.columns, 1):
            cell = ws.cell(row=fila_tabla, column=col_num, value=column_title)
            cell.font = FUENTE_CABECERA_TABLA
            cell.fill = FILL_AZUL_MILITAR
            cell.alignment = ALINEAR_CENTRO

        # Inyección de las filas de datos con alineación adaptativa
        for row_num, row_data in enumerate(dataframe_to_rows(df_final, index=False, header=False), fila_tabla + 1):
            for col_num, val in enumerate(row_data, 1):
                cell = ws.cell(row=row_num, column=col_num, value=val)
                # El nombre del insumo (Col 1) se alinea a la izquierda, el resto centrado
                cell.alignment = ALINEAR_IZQ if col_num == 1 else ALINEAR_CENTRO

        # Ajuste dinámico inteligente del ancho de columnas
        autoajustar_columnas_excel(ws, num_columnas=7, fila_inicio_tabla=fila_tabla)

        excel_buffer = io.BytesIO()
        wb.save(excel_buffer)
        excel_buffer.seek(0)
        return excel_buffer.getvalue()
    
    except Exception as e:
        correlation_id = str(uuid.uuid4())
        logging.error(f'{{"correlation_id": "{correlation_id}", "error": "{str(e)}", "modulo": "reporte_rop_excel"}}')
        st.error(f"Error generando PDF. Reporte el código: [{correlation_id}]")
        return b""


def generar_reporte_rop_pdf(df_rop: pd.DataFrame, filtros: dict, usuario_emisor: str) -> bytes:
    """Genera el reporte de Punto de Reorden (ROP) en formato PDF institucional.
    Diseñado en orientación vertical (Carta). Utiliza el motor adaptativo multilínea 
    de la suite para evitar desbordes físicos al procesar insumos con nombres extensos.

    Parametros:
        df_rop: DataFrame con el análisis de stock (mismas columnas que la versión Excel).
        filtros: Parámetros de búsqueda para el membrete superior.
        usuario_emisor: Nombre del emisor del reporte.

    Returns:
        bytes: Flujo binario del archivo PDF listo para su descarga, o b"" si está vacío.
    """
    
    # Barrera de seguridad explícita
    if not es_administrador():
        st.error("Acceso denegado: Solo administradores pueden generar este reporte.")
        return b""
    
    try:
        if df_rop.empty:
            return b""

        # Orientación vertical ('P'), tamaño carta ('letter') para uso administrativo
        pdf = PDFBaseSIALMED(orientation='P', unit='mm', format='letter')
        pdf.alias_nb_pages()
        pdf.set_auto_page_break(True, 35)

        titulo = "Reporte de Análisis: Punto de Reorden (ROP)"
        str_filtros = limpiar_emojis(", ".join([f"{k}: {v}" for k, v in filtros.items()]))
        usuario_limpio = limpiar_emojis(usuario_emisor)

        # Definición exacta del layout físico en la hoja (Suma exacta = 195 mm útiles)
        anchos = [65, 12, 22, 22, 22, 17, 35]
        titulos = ['INSUMO', 'VED', 'STOCK', 'CPD', 'ESPERA', 'ROP', 'ESTADO']
        alineaciones = ['L', 'C', 'C', 'C', 'C', 'C', 'C']

        # Registro de metadatos en la clase base para la reconstrucción automatizada en saltos de página
        pdf.registrar_datos_tabla(titulo, usuario_limpio, str_filtros, anchos, titulos, alineaciones)

        # Inicialización del documento
        pdf.add_page()
        pdf.escribir_subcabecera_pdf(titulo, usuario_limpio, str_filtros)
        pdf._escribir_cabecera_tabla(tamano_fuente=8.5)

        # Renderizado iterativo bajo control del algoritmo de altura unificada
        for _, fila in df_rop.iterrows():
            # Extracción segura, sanitización de emojis y formateo estricto de campos
            nombre_insumo = limpiar_emojis(fila["nombre_insumo"])
            ved = limpiar_emojis(fila["clasificacion_ved"])[0].upper() if fila["clasificacion_ved"] else ""
            stock = f"{int(fila['stock_disponible'])} unds."
            cpd = f"{float(fila['cpd']):.2f} unds./día"
            espera = f"{float(fila['lead_time_promedio']):.1f} días."
            rop = f"{int(fila['rop'])} unds."
            estado = limpiar_emojis(fila["semaforo"])

            fila_datos = [nombre_insumo, ved, stock, cpd, espera, rop, estado]
            
            # Invocación de la celda adaptativa multilínea para prevenir desbordes laterales o de página
            pdf.imprimir_fila_adaptativa(fila_datos, tamano_fuente=7.5)

        return bytes(pdf.output(dest='S'))

    except Exception as e:
        correlation_id = str(uuid.uuid4())
        logging.error(f'{{"correlation_id": "{correlation_id}", "error": "{str(e)}", "modulo": "reporte_rop_pdf"}}')
        st.error(f"Error generando PDF. Reporte el código: [{correlation_id}]")
        return b""

# ==============================================================================
# SECCIÓN: REPORTE DE PREVENCIÓN DE CADUCIDADES
# ==============================================================================

def generar_reporte_caducidad_excel(df_caducidad: pd.DataFrame, filtros: str, usuario_emisor: str) -> bytes:
    """Genera el reporte de ciclo de vida e índice de mermas en formato Excel (.xlsx).
    Estructura la información por lote indicando días de vida remanente, cobertura 
    teórica frente al consumo y la cantidad física proyectada en riesgo de caducar.

    Parametros:
        df_caducidad: DataFrame con las columnas: 'codigo_lote', 'nombre_insumo', 
            'stock_disponible', 'dias_para_vencer', 'dias_duracion_stock', 
            'cantidad_riesgo' y 'alerta_vencimiento'.
        filtros: Parámetros de consulta aplicados.
        usuario_emisor: Nombre del usuario que emite el reporte.

    Returns:
        bytes: Stream binario del archivo Excel, o b"" si el DataFrame está vacío.
    """
    # Barrera de seguridad explícita
    if not es_administrador():
        st.error("Acceso denegado: Solo administradores pueden generar este reporte.")
        return b""

    try:
        if df_caducidad.empty:
            return b""
        
        datos_matriz = []
        for _, fila in df_caducidad.iterrows():
            datos_matriz.append({
                "CÓDIGO LOTE": limpiar_emojis(fila["codigo_lote"]),
                "MEDICAMENTO": limpiar_emojis(fila["nombre_insumo"]),
                "CANT. LOTE": int(fila["stock_disponible"]),
                'CPD': f"{float(fila['cpd']):.2f}",
                "DÍAS DE VIDA": int(fila["dias_para_vencer"]),
                "DÍAS DE INVENTARIO": int(fila["dias_duracion_stock"]),
                "CANT. RIESGO": int(fila["cantidad_riesgo"]),
                "DIAGNÓSTICO LOGÍSTICO": limpiar_emojis(fila["alerta_vencimiento"])
            })

        df_final = pd.DataFrame(datos_matriz)

        wb = Workbook()
        ws = wb.active
        ws.title = "Análisis Caducidad"
        
        fila_tabla = aplicar_membrete_excel(
            ws, 
            ultima_letra_col="H", 
            titulo_reporte=f"Control Preventivo de Mermas (Filtro: {filtros})", 
            usuario_emisor=limpiar_emojis(usuario_emisor)
        )

        # Cabeceras
        for col_num, column_title in enumerate(df_final.columns, 1):
            cell = ws.cell(row=fila_tabla, column=col_num, value=column_title)
            cell.font = FUENTE_CABECERA_TABLA
            cell.fill = FILL_AZUL_MILITAR
            cell.alignment = ALINEAR_CENTRO

        # Datos
        for row_num, row_data in enumerate(dataframe_to_rows(df_final, index=False, header=False), fila_tabla + 1):
            for col_num, val in enumerate(row_data, 1):
                cell = ws.cell(row=row_num, column=col_num, value=val)
                # El nombre del medicamento (Col 2) e indicación (Col 7) van alineados a la izquierda
                cell.alignment = ALINEAR_IZQ if col_num in [2, 7] else ALINEAR_CENTRO

        autoajustar_columnas_excel(ws, num_columnas=7, fila_inicio_tabla=fila_tabla)

        excel_buffer = io.BytesIO()
        wb.save(excel_buffer)
        excel_buffer.seek(0)
        return excel_buffer.getvalue()
    
    except Exception as e:
        correlation_id = str(uuid.uuid4())
        logging.error(f'{{"correlation_id": "{correlation_id}", "error": "{str(e)}", "modulo": "reporte_caducidad_excel"}}')
        st.error(f"Error generando PDF. Reporte el código: [{correlation_id}]")
        return b""


def generar_reporte_caducidad_pdf(df_caducidad: pd.DataFrame, filtros: str, usuario_emisor: str) -> bytes:
    """Genera el reporte de prevención de caducidades por lote en formato PDF.
    Representación tabular vertical restringida a un ancho útil exacto de 195 mm. 
    Aplica saltos de página y redibujado de cabeceras de manera automatizada y limpia.

    Parametros:
        df_caducidad: DataFrame de control de lotes (mismas columnas que la versión Excel).
        filtros: Parámetros de búsqueda para el membrete superior.
        usuario_emisor: Nombre del emisor para firma y auditoría.

    Returns:
        bytes: Flujo binario del archivo PDF, o b"" si el DataFrame está vacío.
    """
    # Barrera de seguridad explícita
    if not es_administrador():
        st.error("Acceso denegado: Solo administradores pueden generar este reporte.")
        return b""

    try:
        if df_caducidad.empty:
            return b""
    
        pdf = PDFBaseSIALMED(orientation='P', unit='mm', format='letter')
        pdf.alias_nb_pages()
        pdf.set_auto_page_break(True, 35)

        titulo = "Análisis de Ciclo de Vida e Índice de Mermas por Lote"

        # Distribución física de columnas (Suma exacta = 195 mm útiles)
        anchos = [22, 48, 18, 16, 20, 20, 22, 31]
        titulos = ['CÓD. LOTE', 'MEDICAMENTO', 'CANT. LOTE', 'CPD', 'DÍAS VIDA', 'DÍAS INVENT', 'CANT. RIESGO', 'DIAGNÓSTICO']
        alineaciones = ['C', 'L', 'C', 'C', 'C', 'C', 'C', 'L']

        # Registro en la clase base para manejo controlado de salto de página
        pdf.registrar_datos_tabla(titulo, usuario_emisor, filtros, anchos, titulos, alineaciones)

        pdf.add_page()
        pdf.escribir_subcabecera_pdf(titulo, usuario_emisor, filtros)
        pdf._escribir_cabecera_tabla(tamano_fuente=8.0)

        for _, fila in df_caducidad.iterrows():
            cod_lote = limpiar_emojis(fila["codigo_lote"])
            nombre_insumo = limpiar_emojis(fila["nombre_insumo"])
            cant_lote = f"{int(fila['stock_disponible'])} unds."
            cpd = f"{float(fila['cpd']):.2f} u/d"
            dias_vida = f"{int(fila['dias_para_vencer'])} días."
            cobertura = f"{int(fila['dias_duracion_stock'])} días." if int(fila['dias_duracion_stock']) >= 0 else "N/A"
            cant_riesgo = f"{int(fila['cantidad_riesgo'])} unds."
            diagnostico = limpiar_emojis(fila["alerta_vencimiento"])

            fila_datos = [cod_lote, nombre_insumo, cant_lote, cpd, dias_vida, cobertura, cant_riesgo, diagnostico]

            # Imprime de forma segura previniendo la dispersión masiva de celdas
            pdf.imprimir_fila_adaptativa(fila_datos, tamano_fuente=7.5)

        return bytes(pdf.output(dest='S'))

    except Exception as e:
        correlation_id = str(uuid.uuid4())
        logging.error(f'{{"correlation_id": "{correlation_id}", "error": "{str(e)}", "modulo": "reporte_caducidad_pdf"}}')
        st.error(f"Error generando PDF. Reporte el código: [{correlation_id}]")
        return b""


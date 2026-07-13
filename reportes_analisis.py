from reportes import *
import io
from datetime import datetime, date
import pandas as pd
import math
import CRUDs.crud_insumos as crud_insumos
import CRUDs.crud_lotes_entradas as crud_le
import CRUDs.crud_salidas as crud_salidas
# Librerías estéticas y estructurales para Excel Nativo
from openpyxl import Workbook
from openpyxl.styles import Font, Alignment, PatternFill, Side, Border
from openpyxl.utils.dataframe import dataframe_to_rows
from openpyxl.utils import get_column_letter
# Librería para documentos inmutables PDF
from fpdf import FPDF

# ==============================================================================
# CAPA DE DISEÑO COMPARTIDA Y REUTILIZABLE (ESTILOS ESTÁNDAR SIAL-MED)
# ==============================================================================

FUENTE_TITULO = Font(name="Arial", size=12, bold=True, color="000000")
FUENTE_SUBTITULO = Font(name="Arial", size=11, bold=True, color="1F497D")
FUENTE_METADATO = Font(name="Arial", size=10, bold=True)
FUENTE_CABECERA_TABLA = Font(name="Arial", size=11, bold=True, color="FFFFFF")

FILL_AZUL_MILITAR = PatternFill(start_color="1F497D", end_color="1F497D", fill_type="solid")

ALINEAR_CENTRO = Alignment(horizontal="center", vertical="center")
ALINEAR_IZQ = Alignment(horizontal="left", vertical="center")
ALINEAR_DER = Alignment(horizontal="right", vertical="center")  # <--- ESTA ERA LA QUE FALTABA


def aplicar_membrete_excel(ws, ultima_letra_col: str, titulo_reporte: str, usuario_emisor: str) -> int:
    """
    Dibuja el encabezado institucional idéntico en cualquier hoja de Excel.
    Retorna el número de fila donde debe comenzar la tabla de datos.
    """
    ws.views.sheetView[0].showGridLines = True
    
    # 1. Títulos combinados dinámicamente según el ancho de la tabla
    ws.merge_cells(f"A1:{ultima_letra_col}1")
    ws["A1"] = "GUARDIA NACIONAL BOLIVARIANA - DESTACAMENTO 134 (DABAJURO)"
    ws["A1"].font = FUENTE_TITULO
    ws["A1"].alignment = ALINEAR_CENTRO

    ws.merge_cells(f"A2:{ultima_letra_col}2")
    ws["A2"] = f"SIAL-MED: {titulo_reporte.upper()}"
    ws["A2"].font = FUENTE_SUBTITULO
    ws["A2"].alignment = ALINEAR_CENTRO

    # 2. Bloque de Metadatos estándar
    fecha_actual = datetime.now().strftime("%d/%m/%Y %I:%M %p")
    ws["A4"] = "Generado por:"
    ws["A4"].font = FUENTE_METADATO
    ws["B4"] = usuario_emisor
    
    # Colocamos la fecha en la penúltima y última columna de forma dinámica
    letra_penultima = chr(ord(ultima_letra_col) - 1)
    ws[f"{letra_penultima}4"] = "Fecha Emisión:"
    ws[f"{letra_penultima}4"].font = FUENTE_METADATO
    ws[f"{ultima_letra_col}4"] = f" {fecha_actual}"
    
    return 6  # La tabla comenzará siempre en la fila 6


def autoajustar_columnas_excel(ws, num_columnas: int, fila_inicio_tabla: int):
    """Algoritmo genérico para ajustar el ancho de las columnas omitiendo el membrete."""
    for col_num in range(1, num_columnas + 1):
        max_len = 0
        col_letter = get_column_letter(col_num)
        for row_num in range(fila_inicio_tabla, ws.max_row + 1):
            cell_value = ws.cell(row=row_num, column=col_num).value
            if cell_value:
                max_len = max(max_len, len(str(cell_value)))
        ws.column_dimensions[col_letter].width = max(max_len + 5, 15)


class PDFBaseSIALMED(FPDF):
    """Clase base unificada para todos los reportes institucionales con soporte modular de tablas."""
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Variables de control para la reimpresión automática en cambios de página
        self.titulo_reporte = ""
        self.usuario_emisor = ""
        self.filtros_str = ""
        self.anchos_columnas = []
        self.titulos_columnas = []
        self.alineaciones_columnas = []

    def header(self):
        """Membrete oficial que se repite automáticamente en cada nueva página."""
        self.set_font('Arial', 'B', 11)
        self.cell(0, 6, 'GUARDIA NACIONAL BOLIVARIANA - DESTACAMENTO 134', 0, 1, 'C')
        self.set_font('Arial', 'B', 10)
        self.cell(0, 6, 'SIAL-MED - CONTROL DE INSUMOS Y LOGÍSTICA MÉDICA', 0, 1, 'C')
        self.ln(4)
        
    def footer(self):
        """Pie de página automático."""
        self.set_y(-15)
        self.set_font('Arial', 'I', 8)
        self.cell(0, 10, f'Página {self.page_no()}/{{nb}}', 0, 0, 'C')

    def escribir_subcabecera_pdf(self, titulo: str, usuario: str, filtros: str):
        """Renderiza los metadatos y filtros del reporte actual."""
        self.set_font('Arial', 'B', 12)
        self.cell(0, 8, titulo.upper(), 0, 1, 'L')
        self.set_font('Arial', '', 9)
        self.cell(0, 5, f'Fecha de Emisión: {datetime.now().strftime("%d/%m/%Y %I:%M %p")}', 0, 1, 'L')
        self.cell(0, 5, f'Generado por: {usuario}', 0, 1, 'L')
        self.cell(0, 5, f'Filtros Aplicados: {filtros}', 0, 1, 'L')
        self.ln(5)

    def _escribir_cabecera_tabla(self, tamano_fuente=8):
        """Pinta la fila azul oscuro con los títulos de las columnas."""
        self.set_fill_color(31, 73, 125)
        self.set_text_color(255, 255, 255)
        self.set_font('Arial', 'B', tamano_fuente)
        
        for idx, titulo in enumerate(self.titulos_columnas):
            # Alineación adaptativa para los títulos
            align_h = 'L' if idx == 1 or titulo in ['UBICACIÓN FÍSICA', 'UBICACIÓN', 'MOTIVO DE BAJA', 'NOMBRE DEL INSUMO'] else 'C'
            self.cell(self.anchos_columnas[idx], 7, titulo, 1, 0, align_h, True)
        
        self.ln(7)
        self.set_text_color(0, 0, 0) # Restaurar color de texto para los datos

    def registrar_datos_tabla(self, titulo: str, usuario: str, filtros: str, anchos: list, titulos: list, alineaciones: list):
        """Inicializa los parámetros de la tabla para que la clase sepa cómo redibujarla al saltar de página."""
        self.titulo_reporte = titulo
        self.usuario_emisor = usuario
        self.filtros_str = filtros
        self.anchos_columnas = anchos
        self.titulos_columnas = titulos
        self.alineaciones_columnas = alineaciones

    
# ==============================================================================
# SECCIÓN 4: REPORTE DE ANÁLISIS LOGÍSTICO (CON MEMBRETE MILITAR Y BLINDAJE UNICODE)
# ==============================================================================

def generar_reporte_rop_excel(df_filtrado: pd.DataFrame, filtros_aplicados: dict, usuario_emisor: str) -> bytes:
    """
    Genera en memoria un archivo Excel (.xlsx) estructurado e institucional para la 
    Planificación de Abastecimiento y Alertas de Puntos de Reorden (ROP) de SIAL-MED.

    Parámetros:
    -----------
    df_filtrado : pd.DataFrame
        Matriz de datos procesados que contiene métricas logísticas: 'nombre_insumo', 
        'clasificacion_ved', 'stock_disponible', 'cpd', 'lead_time_promedio', 'rop' y 'semaforo'.
    filtros_aplicados : dict
        Diccionario asociativo con los parámetros y rangos utilizados en la consulta.
    usuario_emisor : str
        Nombre y rango/cargo del funcionario militar responsable de la emisión del reporte.

    Retorna:
    --------
    bytes
        Stream de datos binarios del archivo Excel listo para transferencia HTTP.
    """
    if df_filtrado.empty:
        return b""
        
    wb = Workbook()
    ws = wb.active
    ws.title = "Alertas de Reorden ROP"
    
    # Renderizar membrete institucional de la Guardia Nacional Bolivariana hasta columna G
    fila_inicio = aplicar_membrete_excel(ws, "G", "PLANIFICACIÓN DE ABASTECIMIENTO Y PUNTOS DE REORDEN", usuario_emisor)
    
    # ---- BLOQUE DE FILTROS APLICADOS ----
    ws.cell(row=fila_inicio, column=1, value="Filtros Aplicados:").font = FUENTE_SUBTITULO
    fila_inicio += 1
    
    filtros_texto = " | ".join([f"{k}: {str(v).upper()}" for k, v in filtros_aplicados.items()]) if filtros_aplicados else "NINGUNO"
    ws.cell(row=fila_inicio, column=1, value=filtros_texto).font = Font(name="Arial", size=10, italic=True)
    fila_inicio += 2  # Separación prudente para la tabla
    
    # ---- CABECERA DE LA TABLA ESTILO SIAL-MED ----
    cabeceras = ["MEDICAMENTO / INSUMO", "VED", "STOCK REAL", "CONS. DIARIO (CPD)", "ESPERA PROM. (DÍAS)", "PUNTO REORDEN (ROP)", "SEMÁFORO DE ALERTA"]
    for col_idx, texto in enumerate(cabeceras, start=1):
        celda = ws.cell(row=fila_inicio, column=col_idx, value=texto)
        celda.font = FUENTE_CABECERA_TABLA
        celda.fill = FILL_AZUL_MILITAR
        celda.alignment = ALINEAR_CENTRO
        celda.border = Border(bottom=Side(style="medium", color="000000"))
    
    fila_actual = fila_inicio + 1
    
    # ---- VOLCADO Y FORMATEO DE FILAS ----
    for _, fila in df_filtrado.iterrows():
        # Limpieza de caracteres de control visual para Excel (Texto limpio en mayúsculas)
        insumo_limpio = str(fila["nombre_insumo"]).replace("✔", "").strip().upper()
        semaforo_limpio = str(fila["semaforo"]).replace("✔", "").strip().upper()
        
        ws.cell(row=fila_actual, column=1, value=insumo_limpio).alignment = ALINEAR_IZQ
        ws.cell(row=fila_actual, column=2, value=str(fila["clasificacion_ved"]).upper()).alignment = ALINEAR_CENTRO
        ws.cell(row=fila_actual, column=3, value=int(fila["stock_disponible"])).alignment = ALINEAR_DER
        ws.cell(row=fila_actual, column=4, value=round(float(fila["cpd"]), 2)).alignment = ALINEAR_DER
        ws.cell(row=fila_actual, column=5, value=round(float(fila["lead_time_promedio"]), 1)).alignment = ALINEAR_DER
        ws.cell(row=fila_actual, column=6, value=round(float(fila["rop"]), 2)).alignment = ALINEAR_DER
        
        celda_alerta = ws.cell(row=fila_actual, column=7, value=semaforo_limpio)
        celda_alerta.alignment = ALINEAR_CENTRO
        celda_alerta.font = Font(name="Arial", size=10, bold=True)
        
        for col_idx in range(1, 8):
            ws.cell(row=fila_actual, column=col_idx).border = Border(
                bottom=Side(style="thin", color="CCCCCC"),
                left=Side(style="thin", color="CCCCCC"),
                right=Side(style="thin", color="CCCCCC")
            )
        fila_actual += 1
        
    autoajustar_columnas_excel(ws, 7, fila_inicio)
    
    buffer = io.BytesIO()
    wb.save(buffer)
    return buffer.getvalue()





def generar_reporte_caducidad_excel(df_filtrado: pd.DataFrame, filtros_aplicados: dict, usuario_emisor: str) -> bytes:
    """
    Construye el libro Excel para la auditoría física de lotes con riesgo de vencimiento, 
    alimentándose de la columna 'alerta_vencimiento' calculada bajo metodología FEFO.

    Parámetros:
    -----------
    df_filtrado : pd.DataFrame
        Lotes sanitarios procesados con métricas de cobertura y cantidad en riesgo.
    filtros_aplicados : dict
        Criterios vigentes aplicados en la consulta del panel SIAL-MED.
    usuario_emisor : str
        Firma textual del analista logístico emisor.

    Retorna:
    --------
    bytes
        Representación en bytes del archivo Excel generado.
    """
    if df_filtrado.empty:
        return b""
        
    wb = Workbook()
    ws = wb.active
    ws.title = "Análisis de Vencimientos"
    
    fila_inicio = aplicar_membrete_excel(ws, "G", "CONTROL PREVENTIVO DE CADUCIDADES Y GESTIÓN DE MERMAS", usuario_emisor)
    
    # ---- BLOQUE DE FILTROS APLICADOS ----
    ws.cell(row=fila_inicio, column=1, value="Filtros Aplicados:").font = FUENTE_SUBTITULO
    fila_inicio += 1
    
    filtros_texto = " | ".join([f"{k}: {str(v).upper()}" for k, v in filtros_aplicados.items()]) if filtros_aplicados else "NINGUNO"
    ws.cell(row=fila_inicio, column=1, value=filtros_texto).font = Font(name="Arial", size=10, italic=True)
    fila_inicio += 2
    
    cabeceras = ["LOTE", "MEDICAMENTO / INSUMO", "CANT. LOTE", "DÍAS VNC.", "COBERTURA", "CANT. RIESGO", "DIAGNÓSTICO LOGÍSTICO"]
    for col_idx, texto in enumerate(cabeceras, start=1):
        celda = ws.cell(row=fila_inicio, column=col_idx, value=texto)
        celda.font = FUENTE_CABECERA_TABLA
        celda.fill = FILL_AZUL_MILITAR
        celda.alignment = ALINEAR_CENTRO
        celda.border = Border(bottom=Side(style="medium", color="000000"))
        
    fila_actual = fila_inicio + 1
    
    for _, fila in df_filtrado.iterrows():
        ws.cell(row=fila_actual, column=1, value=str(fila["codigo_lote"]).upper()).alignment = ALINEAR_CENTRO
        
        insumo_limpio = str(fila["nombre_insumo"]).replace("✔", "").strip().upper()
        ws.cell(row=fila_actual, column=2, value=insumo_limpio).alignment = ALINEAR_IZQ
        
        ws.cell(row=fila_actual, column=3, value=int(fila["stock_disponible"])).alignment = ALINEAR_DER
        ws.cell(row=fila_actual, column=4, value=int(fila["dias_para_vencer"])).alignment = ALINEAR_DER
        
        cob = fila.get("dias_duracion_stock", fila.get("dias_cobertura", 9999))
        val_cob = "INF" if pd.isna(cob) or cob >= 9999 or cob == float('inf') else int(cob)
        ws.cell(row=fila_actual, column=5, value=val_cob).alignment = ALINEAR_DER
        
        ws.cell(row=fila_actual, column=6, value=int(fila["cantidad_riesgo"])).alignment = ALINEAR_DER
        
        # Mapeo unificado y seguro de la alerta analítica del backend
        diag_val = fila.get("alerta_vencimiento", fila.get("diagnostico_logistico", "SIN DIAGNÓSTICO"))
        diag_limpio = str(diag_val).replace("✔", "").strip().upper()
        
        celda_diag = ws.cell(row=fila_actual, column=7, value=diag_limpio)
        celda_diag.alignment = ALINEAR_IZQ
        celda_diag.font = Font(name="Arial", size=10, bold=True)
        
        if int(fila["cantidad_riesgo"]) > 0:
            celda_diag.font = Font(name="Arial", size=10, bold=True, color="9C0006")
            
        for col_idx in range(1, 8):
            ws.cell(row=fila_actual, column=col_idx).border = Border(
                bottom=Side(style="thin", color="CCCCCC"),
                left=Side(style="thin", color="CCCCCC"),
                right=Side(style="thin", color="CCCCCC")
            )
        fila_actual += 1
        
    autoajustar_columnas_excel(ws, 7, fila_inicio)
    
    buffer = io.BytesIO()
    wb.save(buffer)
    return buffer.getvalue()


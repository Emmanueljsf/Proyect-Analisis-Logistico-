import uuid
import logging
from seguridad import es_administrador
import streamlit as st
import io
from datetime import datetime, date
import pandas as pd
import math
import CRUDs.crud_insumos as crud_insumos
import CRUDs.crud_entradas as crud_le
import CRUDs.crud_lotes as crud_l
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
    Dibuja el encabezado institucional y los metadatos en una hoja de cálculo Excel. Configura las celdas 
    iniciales para mantener la identidad visual de la institución.

    Parámetros:
    ws: Objeto de la hoja de cálculo de openpyxl.
    ultima_letra_col (str): Letra de la última columna del reporte para combinar celdas.
    titulo_reporte (str): Nombre o título del documento.
    usuario_emisor (str): Nombre del usuario que genera el archivo.

    Retorna: int (Fila donde comienza la tabla de datos).
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
    """
    Descripción: Calcula el ancho necesario para cada columna de una hoja Excel 
    basado en la longitud máxima de su contenido.
    Parámetros:
    ws: Objeto de la hoja de cálculo.
    num_columnas (int): Cantidad total de columnas a ajustar.
    fila_inicio_tabla (int): Fila desde la cual comenzar a medir el contenido.
    """
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

    def imprimir_fila_adaptativa(self, datos, tamano_fuente=7.5):
        """
        Dibuja una fila con el Algoritmo de Altura Unificada y Rectángulos Perimetrales.
        Ideal para reportes complejos con textos que se desbordan (como el de Lotes).
        """
        self.set_font('Arial', '', tamano_fuente)
        
        # 1. Calcular altura máxima en base al texto más largo
        max_lineas = 1
        for i, txt in enumerate(datos):
            ancho_util = self.anchos_columnas[i] - 2
            lineas = math.ceil(self.get_string_width(str(txt)) / ancho_util)
            if lineas > max_lineas:
                max_lineas = lineas

        alto_unificado = max_lineas * 4.5

        # 2. Control inteligente de salto de hoja
        if (self.get_y() + alto_unificado) > (279 - 35):
            self.add_page()
            self.escribir_subcabecera_pdf(self.titulo_reporte, self.usuario_emisor, self.filtros_str)
            self._escribir_cabecera_tabla(tamano_fuente + 0.5)
            self.set_font('Arial', '', tamano_fuente)

        # 3. Renderizado de textos y marcos idénticos
        x_inicial = self.get_x()
        y_inicial = self.get_y()

        for i, txt in enumerate(datos):
            self.set_xy(x_inicial, y_inicial)
            self.multi_cell(self.anchos_columnas[i], 4.5, str(txt), 0, self.alineaciones_columnas[i])
            x_inicial += self.anchos_columnas[i]

        x_cuadro = self.l_margin
        for i in range(len(datos)):
            self.rect(x_cuadro, y_inicial, self.anchos_columnas[i], alto_unificado)
            x_cuadro += self.anchos_columnas[i]

        self.set_xy(self.l_margin, y_inicial + alto_unificado)

    def imprimir_fila_estandar(self, datos, alto_fila=6, tamano_fuente=9):
        """
        Dibuja una fila estándar de una sola línea. 
        Ideal para catálogos rápidos que recortan texto largo (como el de Insumos).
        """
        self.set_font('Arial', '', tamano_fuente)

        # 🛑 Control de salto de hoja
        if (self.get_y() + alto_fila) > (279 - 35):
            self.add_page()
            self.escribir_subcabecera_pdf(self.titulo_reporte, self.usuario_emisor, self.filtros_str)
            self._escribir_cabecera_tabla(10) # En este reporte la cabecera es de 10pt
            self.set_font('Arial', '', tamano_fuente)

        # Renderizado línea por línea directo
        for i, txt in enumerate(datos):
            es_ultimo = 1 if i == len(datos) - 1 else 0
            self.cell(self.anchos_columnas[i], alto_fila, str(txt), 1, es_ultimo, self.alineaciones_columnas[i])

    def chapter_title(self, title):
        self.set_font('Arial', 'B', 14)
        self.set_fill_color(200, 220, 255)
        self.cell(0, 10, title, ln=True, fill=True)
        self.ln(5)

# ==============================================================================
# SECCIÓN 1: MÓDULO DE INSUMOS (RF17 & RF18)
# ==============================================================================

def generar_reporte_insumos_excel(txt_buscar: str, opt_estado: str, usuario_emisor: str) -> bytes:
    """Genera el reporte oficial de catálogo de insumos en Excel (.xlsx).
    Incluyen barrera de permisos y gestión de excepciones con log estructurado.

    Parámetros:
    txt_buscar (str): Filtro de texto para el nombre del insumo.
    opt_estado (str): Filtro de estado (ACTIVOS/INACTIVOS).
    usuario_emisor (str): Responsable de la generación.

    Retorna: bytes (Stream binario del archivo generado) o b"" en caso de error.
    """
    
    # Barrera de seguridad explícita
    if not es_administrador():
        st.error("Acceso denegado: Solo administradores pueden generar este reporte.")
        return b""
    
    try:
        lista_insumos = crud_insumos.obtener_insumos(
            solo_activos=(opt_estado == "ACTIVOS"), txt_buscar=txt_buscar, opt_estado=opt_estado
        )
        if not lista_insumos: return b""

        # DataFrame con Pandas y mapeo VED completo
        datos_matriz = []
        for ins in lista_insumos:
            ved = ins.clasificacion_ved.value if hasattr(ins.clasificacion_ved, "value") else ins.clasificacion_ved
            datos_matriz.append({
                "ID": ins.id_insumo,  
                "NOMBRE DEL INSUMO": ins.nombre, 
                "CLASIFICACIÓN VED": 'VITAL' if ved=='V' else 'ESENCIAL' if ved=='E' else 'DESEABLE',
                "STOCK DISPONIBLE": ins.total_stock,  # Corre fluido porque la RAM tiene los lotes cargados
                "ESTADO": "ACTIVO" if ins.activo else "INACTIVO"
            })
            
        # Construye el DataFrame original con las columnas explícitas
        df_final = pd.DataFrame(datos_matriz, columns=["ID", "NOMBRE DEL INSUMO", "CLASIFICACIÓN VED", "STOCK DISPONIBLE", "ESTADO"])

        wb = Workbook()
        ws = wb.active
        ws.title = "Catálogo de Insumos"
        
        # REUTILIZACIÓN: Membrete adaptado a 4 columnas
        fila_tabla = aplicar_membrete_excel(ws, "D", f"Reporte del Catálogo de Insumos ({opt_estado})", usuario_emisor)

        # Cabeceras de tabla
        for col_num, column_title in enumerate(df_final.columns, 1):
            cell = ws.cell(row=fila_tabla, column=col_num, value=column_title)
            cell.font = FUENTE_CABECERA_TABLA
            cell.fill = FILL_AZUL_MILITAR
            cell.alignment = ALINEAR_CENTRO

        # Datos de tabla
        for row_num, row_data in enumerate(dataframe_to_rows(df_final, index=False, header=False), fila_tabla + 1):
            for col_num, val in enumerate(row_data, 1):
                cell = ws.cell(row=row_num, column=col_num, value=val)
                cell.alignment = ALINEAR_IZQ if col_num == 2 else ALINEAR_CENTRO

        # REUTILIZACIÓN: Autoajuste exacto
        autoajustar_columnas_excel(ws, 4, fila_tabla)

        excel_buffer = io.BytesIO()
        wb.save(excel_buffer)
        excel_buffer.seek(0)
        return excel_buffer.getvalue()
    
    except Exception as e:
        # TRAZABILIDAD AVANZADA: Log estructurado ante fallos técnicos
        correlation_id = str(uuid.uuid4())
        logging.error(f'{{"correlation_id": "{correlation_id}", "error": "{str(e)}", "modulo": "reporte_insumos_excel"}}')
        st.error(f"Error generando reporte. Reporte el código: [{correlation_id}]")
        return b""


def generar_reporte_insumos_pdf(txt_buscar: str, opt_estado: str, usuario_emisor: str) -> bytes:
    """Genera el reporte pdf del catálogo de insumos usando la clase base unificada.
    Descripción: Exportan el catálogo de insumos registrados (filtrados por estado). Incluyen barrera de
    permisos y gestión de excepciones con log estructurado.

Parámetros:
txt_buscar (str): Filtro de texto para el nombre del insumo.
opt_estado (str): Filtro de estado (ACTIVOS/INACTIVOS).
usuario_emisor (str): Responsable de la generación.

Retorna: bytes (Stream binario del archivo generado) o b"" en caso de error.
"""
    # Barrera de seguridad explícita
    if not es_administrador():
        st.error("Acceso denegado: Solo administradores pueden generar este reporte.")
        return b""
    
    try:    
        lista_insumos = crud_insumos.obtener_insumos(
            solo_activos=(opt_estado == "ACTIVOS"), txt_buscar=txt_buscar, opt_estado=opt_estado
        )
        if not lista_insumos: return b""

        pdf = PDFBaseSIALMED(orientation='P', unit='mm', format='letter')
        pdf.alias_nb_pages()
        pdf.set_auto_page_break(True, 35)
        
        titulo = f"Catálogo Oficial de Insumos ({opt_estado})"
        filtros = f"Búsqueda: '{txt_buscar if txt_buscar else 'NINGUNA'}'"
        
        # 1. Registramos la configuración de la tabla
        pdf.registrar_datos_tabla(
            titulo=titulo, usuario=usuario_emisor, filtros=filtros,
            anchos=[15, 80, 40, 30, 30],
            titulos=['ID', 'NOMBRE DEL INSUMO', 'CLASIFICACIÓN VED', 'STOCK', 'ESTADO'],
            alineaciones=['C', 'L', 'C', 'C', 'C']
        )

        pdf.add_page()
        pdf.escribir_subcabecera_pdf(titulo, usuario_emisor, filtros)
        pdf._escribir_cabecera_tabla(tamano_fuente=10) # Primera cabecera

        dicc_ved = {"V": "VITAL (V)", "E": "ESENCIAL (E)", "D": "DESEABLE (D)"}
        
        for insumo in lista_insumos:
            estado_str = "ACTIVO" if insumo.activo else "INACTIVO"
            ved_completo = dicc_ved.get(insumo.clasificacion_ved, insumo.clasificacion_ved)
            nombre_ajustado = insumo.nombre[:45] + "..." if len(insumo.nombre) > 45 else insumo.nombre
            
            # 2. Invocamos la fila estándar de una línea
            pdf.imprimir_fila_estandar([
                insumo.id_insumo, nombre_ajustado, ved_completo, f'{insumo.total_stock} unds', estado_str
            ], alto_fila=6, tamano_fuente=9)

        return bytes(pdf.output(dest='S'))

    except Exception as e:
        correlation_id = str(uuid.uuid4())
        logging.error(f'{{"correlation_id": "{correlation_id}", "error": "{str(e)}", "modulo": "reporte_insumos_pdf"}}')
        st.error(f"Error generando PDF. Reporte el código: [{correlation_id}]")
        return b""


# ==============================================================================
# SECCIÓN 2: MÓDULO DE LOTES
# ==============================================================================

def generar_reporte_lotes_excel(txt_universal: str, txt_rango_stock: str, rango_vencimiento: list, opt_estado: str, usuario_emisor: str) -> bytes:
    """Genera el reporte de stock en Excel incluyendo estado y motivo si aplica.
    Incluyen barrera de permisos y gestión de excepciones con log estructurado.

    Parámetros:
    txt_universal (str): Filtro general.
    txt_rango_stock (str): Filtro por cantidad.
    rango_vencimiento (list): Fechas [inicio, fin].
    opt_estado (str): Estado del lote.
    usuario_emisor (str): Responsable de la generación.

    Retorna: bytes (Stream binario del archivo generado) o b"" en caso de error.
    """
    
    # Barrera de seguridad explícita
    if not es_administrador():
        st.error("Acceso denegado: Solo administradores pueden generar este reporte.")
        return b""
    
    try:
        tuplas_lotes = crud_l.obtener_lotes_filtrados(
            txt_universal=txt_universal,
            txt_rango_stock=txt_rango_stock,
            rango_vencimiento=rango_vencimiento,
            opt_estado=opt_estado
        )
        if not tuplas_lotes: return b""

        filas_procesadas = []
        for lote_obj, insumo_obj in tuplas_lotes:
            ved = insumo_obj.clasificacion_ved.value if hasattr(insumo_obj.clasificacion_ved, "value") else insumo_obj.clasificacion_ved
            ved_txt = 'VITAL' if ved=='V' else 'ESENCIAL' if ved=='E' else 'DESEABLE'
            f_venc = lote_obj.fecha_vencimiento.strftime("%d/%m/%Y")
            
            registro = {
                "CÓDIGO DE LOTE": lote_obj.codigo_lote,
                "INSUMO MÉDICO": insumo_obj.nombre,
                "VED": ved_txt,
                "STOCK": int(lote_obj.stock_disponible),
                "F. VENCIMIENTO": f_venc,
                "UBICACIÓN": lote_obj.ubicacion_fisica if lote_obj.ubicacion_fisica else "N/A",
                "ESTADO": "ACTIVO" if lote_obj.activo else "INACTIVO"
            }
            
            # 🛠️ Solo agregamos el motivo al Excel si no estamos en ACTIVOS
            if opt_estado != "ACTIVOS":
                registro["MOTIVO DESACTIVACIÓN"] = lote_obj.motivo_desactivacion if lote_obj.motivo_desactivacion else ""
                
            filas_processed = filas_procesadas.append(registro)

        df_final = pd.DataFrame(filas_procesadas)

        wb = Workbook()
        ws = wb.active
        ws.title = "Control de Lotes"
        ws.views.sheetView[0].showGridLines = True
        
        # Determinar letra de columna de fin según el tamaño de la matriz (G o H)
        letra_fin = "H" if opt_estado != "ACTIVOS" else "G"
        num_columnas = 8 if opt_estado != "ACTIVOS" else 7
        
        fila_tabla = aplicar_membrete_excel(ws, letra_fin, f"Reporte Operativo de Lotes ({opt_estado})", usuario_emisor)

        # Cabeceras
        for col_num, column_title in enumerate(df_final.columns, 1):
            cell = ws.cell(row=fila_tabla, column=col_num, value=column_title)
            cell.font = FUENTE_CABECERA_TABLA
            cell.fill = FILL_AZUL_MILITAR
            cell.alignment = ALINEAR_CENTRO

        # Filas
        for row_num, row_data in enumerate(dataframe_to_rows(df_final, index=False, header=False), fila_tabla + 1):
            for col_num, val in enumerate(row_data, 1):
                cell = ws.cell(row=row_num, column=col_num, value=val)
                cell.alignment = ALINEAR_IZQ if col_num == 2 or col_num == 8 else ALINEAR_CENTRO

        # Ajuste automático
        autoajustar_columnas_excel(ws, num_columnas, fila_tabla)

        excel_buffer = io.BytesIO()
        wb.save(excel_buffer)
        excel_buffer.seek(0)
        return excel_buffer.getvalue()
    
    except Exception as e:
        correlation_id = str(uuid.uuid4())
        logging.error(f'{{"correlation_id": "{correlation_id}", "error": "{str(e)}", "modulo": "reporte_lores_excel"}}')
        st.error(f"Error generando PDF. Reporte el código: [{correlation_id}]")
        return b""

 
def generar_reporte_lotes_pdf(txt_universal: str, txt_rango_stock: str, rango_vencimiento: list, opt_estado: str, usuario_emisor: str) -> bytes:
    """Genera el reporte de lotes con celdas adaptativas multilínea usando la clase base unificada.
    Incluyen barrera de permisos y gestión de excepciones con log estructurado.

    Parámetros:
    txt_universal (str): Filtro general.
    txt_rango_stock (str): Filtro por cantidad.
    rango_vencimiento (list): Fechas [inicio, fin].
    opt_estado (str): Estado del lote.
    usuario_emisor (str): Responsable de la generación.

    Retorna: bytes (Stream binario del archivo generado) o b"" en caso de error.
    """
    
    # Barrera de seguridad explícita
    if not es_administrador():
        st.error("Acceso denegado: Solo administradores pueden generar este reporte.")
        return b""
    
    try:
        tuplas_lotes = crud_l.obtener_lotes_filtrados(txt_universal, txt_rango_stock, rango_vencimiento, opt_estado)
        if not tuplas_lotes: return b""

        pdf = PDFBaseSIALMED(orientation='P', unit='mm', format='letter')
        pdf.alias_nb_pages()
        pdf.set_auto_page_break(True, 35)
        
        titulo = "Control General de Lotes e Inventario"
        filtros = f"Búsqueda: '{txt_universal if txt_universal else 'TODOS'}' | Estado: {opt_estado}"

        # Configuramos las columnas dinámicas según los filtros
        if opt_estado == "ACTIVOS":
            anchos, titulos, align = [25, 73, 22, 25, 20, 30], ['CÓDIGO LOTE', 'INSUMO MÉDICO', 'VED', 'F. VENC.', 'STOCK', 'UBICACIÓN FÍSICA'], ['C', 'L', 'C', 'C', 'C', 'L']
        elif opt_estado == "INACTIVOS":
            anchos, titulos, align = [22, 53, 18, 22, 17, 28, 35], ['CÓDIGO LOTE', 'INSUMO MÉDICO', 'VED', 'F. VENC.', 'STOCK', 'UBICACIÓN', 'MOTIVO DE BAJA'], ['C', 'L', 'C', 'C', 'C', 'L', 'L']
        else:
            anchos, titulos, align = [20, 42, 18, 22, 15, 26, 18, 34], ['CÓDIGO LOTE', 'INSUMO MÉDICO', 'VED', 'F. VENC.', 'STOCK', 'UBICACIÓN', 'ESTADO', 'MOTIVO DE BAJA'], ['C', 'L', 'C', 'C', 'C', 'L', 'C', 'L']

        # 1. Registramos la configuración de la tabla
        pdf.registrar_datos_tabla(titulo, usuario_emisor, filtros, anchos, titulos, align)

        pdf.add_page()
        pdf.escribir_subcabecera_pdf(titulo, usuario_emisor, filtros)
        pdf._escribir_cabecera_tabla(tamano_fuente=8)

        for lote_obj, insumo_obj in tuplas_lotes:
            ved = insumo_obj.clasificacion_ved.value if hasattr(insumo_obj.clasificacion_ved, "value") else insumo_obj.clasificacion_ved
            ved_txt = 'VITAL' if ved=='V' else 'ESENCIAL' if ved=='E' else 'DESEABLE'
            f_venc = lote_obj.fecha_vencimiento.strftime("%d/%m/%Y") if lote_obj.fecha_vencimiento else "N/A"
            estado_txt = "ACTIVO" if lote_obj.activo else "INACTIVO"
            motivo_txt = lote_obj.motivo_desactivacion if lote_obj.motivo_desactivacion else ""

            if opt_estado == "ACTIVOS":
                fila = [lote_obj.codigo_lote, insumo_obj.nombre, ved_txt, f_venc, f"{int(lote_obj.stock_disponible)} unds.", lote_obj.ubicacion_fisica]
            elif opt_estado == "INACTIVOS":
                fila = [lote_obj.codigo_lote, insumo_obj.nombre, ved_txt, f_venc, f"{int(lote_obj.stock_disponible)} unds.", lote_obj.ubicacion_fisica, motivo_txt]
            else:
                fila = [lote_obj.codigo_lote, insumo_obj.nombre, ved_txt, f_venc, f"{int(lote_obj.stock_disponible)} unds.", lote_obj.ubicacion_fisica, estado_txt, motivo_txt]

            # 2. Invocamos la fila adaptativa con marcos completos uniformes
            pdf.imprimir_fila_adaptativa(fila, tamano_fuente=7.5)

        return bytes(pdf.output(dest='S'))

    except Exception as e:
        correlation_id = str(uuid.uuid4())
        logging.error(f'{{"correlation_id": "{correlation_id}", "error": "{str(e)}", "modulo": "reporte_lotes_pdf"}}')
        st.error(f"Error generando PDF. Reporte el código: [{correlation_id}]")
        return b""


def generar_reporte_entradas_excel(txt_universal: str, rango_fechas: list, opt_estado: str, usuario_emisor: str) -> bytes:
    """Genera el reporte de stock en Excel incluyendo estado y motivo si aplica.
    Incluyen barrera de permisos y gestión de excepciones con log estructurado.

    Parámetros:
    txt_universal (str): Filtro por orden, usuario o insumo.
    rango_fechas (list): Rango temporal [inicio, fin].
    opt_estado (str): Estado del acta.
    usuario_emisor (str): Responsable de la generación.

    Retorna: bytes (Stream binario del archivo generado) o b"" en caso de error.
    """
    
    # Barrera de seguridad explícita
    if not es_administrador():
        st.error("Acceso denegado: Solo administradores pueden generar este reporte.")
        return b""
    
    try:
        entradas, total_registros_bd = crud_le.obtener_entradas_filtradas_paginadas(
                txt_universal=txt_universal,
                rango_fechas=rango_fechas,
                opt_estado=opt_estado,
                #pagina_actual=st.session_state["pagina_entradas"],
                #registros_por_pagina=REGISTROS_POR_PAGINA
            )
        if not entradas: return b""
        
        filas_raw = []
        for entrada in entradas:
            ved = entrada.lote.insumo.clasificacion_ved.value if hasattr(entrada.lote.insumo.clasificacion_ved, "value") else entrada.lote.insumo.clasificacion_ved
            ved_txt = 'VITAL' if ved=='V' else 'ESENCIAL' if ved=='E' else 'DESEABLE'
            nombre_completo = f"{entrada.usuario.nombres.split()[0]} {entrada.usuario.apellidos.split()[0]}"
            f_pedido = entrada.fecha_pedido.strftime("%d/%m/%Y")
            f_recep = entrada.fecha_recepcion.strftime("%d/%m/%Y")
            
            filas_raw.append({
                "ID": entrada.id_entrada,
                "INSUMO MÉDICO": entrada.lote.insumo.nombre,
                "CÓDIGO LOTE": entrada.lote.codigo_lote,
                "VED": ved_txt,
                "CANTIDAD": entrada.cantidad,
                "FECHA PEDIDO": f_pedido,
                "FECHA RECEPCIÓN": f_recep,
                'TIEMPO DE ENTREGA': f'{entrada.tiempo_entrega_dias} días', 
                "RESPONSABLE": nombre_completo,
                "ESTADO": 'VALIDO' if entrada.estado=='VALIDO' else 'ANULADO'
            })

            # Construcción exacta para que si está vacío no pinte registros fantasmas
            df_entradas = pd.DataFrame(filas_raw)

        wb = Workbook()
        ws = wb.active
        ws.title = "Control de Entradas"
        ws.views.sheetView[0].showGridLines = True
        
        # Determinar letra de columna de fin según el tamaño de la matriz (G o H)
        letra_fin = "H" if opt_estado != "ACTIVOS" else "G"
        num_columnas = 8 if opt_estado != "ACTIVOS" else 7

        if rango_fechas and len(rango_fechas) == 2:
            str_fechas = f" del {rango_fechas[0].strftime('%d/%m/%Y')} al {rango_fechas[1].strftime('%d/%m/%Y')}"
        else:
            str_fechas = ""
        
        fila_tabla = aplicar_membrete_excel(ws, letra_fin, f"Reporte Operativo de Entradas ({opt_estado}) del {str_fechas}", usuario_emisor)

        # Cabeceras
        for col_num, column_title in enumerate(df_entradas.columns, 1):
            cell = ws.cell(row=fila_tabla, column=col_num, value=column_title)
            cell.font = FUENTE_CABECERA_TABLA
            cell.fill = FILL_AZUL_MILITAR
            cell.alignment = ALINEAR_CENTRO

        # Filas
        for row_num, row_data in enumerate(dataframe_to_rows(df_entradas, index=False, header=False), fila_tabla + 1):
            for col_num, val in enumerate(row_data, 1):
                cell = ws.cell(row=row_num, column=col_num, value=val)
                cell.alignment = ALINEAR_IZQ if col_num == 2 or col_num == 8 else ALINEAR_CENTRO

        # Ajuste automático
        autoajustar_columnas_excel(ws, num_columnas, fila_tabla)

        excel_buffer = io.BytesIO()
        wb.save(excel_buffer)
        excel_buffer.seek(0)
        return excel_buffer.getvalue()
    
    except Exception as e:
        correlation_id = str(uuid.uuid4())
        logging.error(f'{{"correlation_id": "{correlation_id}", "error": "{str(e)}", "modulo": "reporte_entradas_excel"}}')
        st.error(f"Error generando PDF. Reporte el código: [{correlation_id}]")
        return b""

def generar_reporte_entradas_pdf(txt_universal: str, rango_fechas: list, opt_estado: str, usuario_emisor: str) -> bytes:
    """
    Genera el acta e historial de entradas en pdf.
    Incluyen barrera de permisos y gestión de excepciones con log estructurado
    
    Parámetros:
    txt_universal (str): Filtro por orden, usuario o insumo.
    rango_fechas (list): Rango temporal [inicio, fin].
    opt_estado (str): Estado del acta.
    usuario_emisor (str): Responsable de la generación.

    Retorna: bytes (Stream binario del archivo generado) o b"" en caso de error.
    """
    # Barrera de seguridad explícita
    if not es_administrador():
        st.error("Acceso denegado: Solo administradores pueden generar este reporte.")
        return b""
    
    try:
        # 1. Consulta al backend
        entradas, _ = crud_le.obtener_entradas_filtradas_paginadas(
            txt_universal=txt_universal,
            rango_fechas=rango_fechas,
            opt_estado=opt_estado,
            pagina_actual=1,
            registros_por_pagina=50000
        )
        
        if not entradas: 
            return b""

        # 2. INICIALIZACIÓN EN VERTICAL ('P' - Portrait)
        pdf = PDFBaseSIALMED(orientation='P', unit='mm', format='letter')
        pdf.alias_nb_pages()
        
        # Salto de página automático con un margen inferior prudente
        pdf.set_auto_page_break(True, 20) 

        if rango_fechas and len(rango_fechas) == 2:
            str_fechas = f" del {rango_fechas[0].strftime('%d/%m/%Y')} al {rango_fechas[1].strftime('%d/%m/%Y')}"
        else:
            str_fechas = ""

        titulo_reporte = f"Historial y Auditoría de Entradas de Inventario del {str_fechas}"
        filtros_aplicados = f"Búsqueda: '{txt_universal if txt_universal else 'TODOS'}' | Estado Acta: {opt_estado}"

        # 📏 Configuración de Columnas en Vertical (Suma exacta = 196 mm)
        # Se eliminó VED y se redistribuyeron los anchos de forma compacta
        anchos = [10, 58, 28, 15, 18, 18, 35, 15]
        titulos = ['ID', 'INSUMO MÉDICO', 'CÓD. LOTE', 'CANT.', 'F. PEDID.', 'F. RECEPC.', 'RESPONSABLE ACTA', 'ESTADO']
        alineaciones = ['C', 'L', 'C', 'C', 'C', 'C', 'C', 'L', 'C']

        pdf.registrar_datos_tabla(titulo_reporte, usuario_emisor, filtros_aplicados, anchos, titulos, alineaciones)

        # 3. Renderizado de la estructura inicial
        pdf.add_page()
        pdf.escribir_subcabecera_pdf(titulo_reporte, usuario_emisor, filtros_aplicados)
        pdf._escribir_cabecera_tabla(tamano_fuente=7.5) 

        # 4. Iteración y formateo de filas
        for entrada in entradas:
            # Extraer la inicial de la clasificación VED de forma segura
            ved = entrada.lote.insumo.clasificacion_ved.value if hasattr(entrada.lote.insumo.clasificacion_ved, "value") else entrada.lote.insumo.clasificacion_ved
            inicial_ved = str(ved)[0].upper() if ved else "D" # Por defecto Deseable si viene vacío
            
            # Inyectar la inicial al principio del nombre: "(V) Adrenalina 1mg/ml"
            nombre_insumo_compacto = f"{entrada.lote.insumo.nombre} ({inicial_ved})"
            
            f_ped = entrada.fecha_pedido.strftime("%d/%m/%Y") if entrada.fecha_pedido else "N/A"
            f_rec = entrada.fecha_recepcion.strftime("%d/%m/%Y") if entrada.fecha_recepcion else "N/A"
            
            # Nombre de auditoría corto para no romper la celda en vertical
            nombre_completo = f"{entrada.usuario.nombres.split()[0]} {entrada.usuario.apellidos.split()[0]}"
            
            # Limpieza estricta del string del Enum de estado
            estado_crudo = str(entrada.estado)
            estado_limpio = estado_crudo.replace("Estado.", "").strip()
            estado_final = "VALIDO" if "VALIDO" in estado_limpio.upper() else "ANULADO"

            # Armamos el array con las 9 columnas resultantes
            fila_datos = [
                entrada.id_entrada,
                nombre_insumo_compacto,
                entrada.lote.codigo_lote,
                f"{int(entrada.cantidad)} unds.",
                f_ped,
                f_rec,
                nombre_completo,
                estado_final
            ]

            # Reducimos ligeramente la fuente a 7 para asegurar el encaje en el formato vertical
            pdf.imprimir_fila_adaptativa(fila_datos, tamano_fuente=7.5)

        return bytes(pdf.output(dest='S'))

    except Exception as e:
        correlation_id = str(uuid.uuid4())
        logging.error(f'{{"correlation_id": "{correlation_id}", "error": "{str(e)}", "modulo": "reporte_entradas_pdf"}}')
        st.error(f"Error generando PDF. Reporte el código: [{correlation_id}]")
        return b""


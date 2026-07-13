from reportes import *

def generar_reporte_salidas_excel(txt_universal: str, rango_fechas: list, opt_estado: str, usuario_emisor: str) -> bytes:
    """
    Genera el reporte en bloques tipo tarjetas herméticas.
    """
    
    # crear emisor
    emisor_limpio = "Usuario de Auditoria" if isinstance(usuario_emisor, bool) else str(usuario_emisor)
    
    # Determinar el estado para el título
    estado_texto = "TODAS LAS SALIDAS"
    if opt_estado and "VALI" in opt_estado.upper():
        estado_texto = "SALIDAS VÁLIDAS"
    elif opt_estado and "ANUL" in opt_estado.upper():
        estado_texto = "SALIDAS ANULADAS"

    # Formatear el rango de fechas de manera limpia para el título
    if rango_fechas and len(rango_fechas) == 2:
        str_fechas = f" del {rango_fechas[0].strftime('%d/%m/%Y')} al {rango_fechas[1].strftime('%d/%m/%Y')}"
    else:
        str_fechas = ""

    # Construir el título final limpio sin duplicar "SIAL-MED"
    titulo_final = f"REPORTE ESTRUCTURADO DE {estado_texto}{str_fechas}"

    lista_salidas, _ = crud_salidas.obtener_salidas_filtradas_paginadas(
        txt_universal=txt_universal, rango_fechas=rango_fechas, opt_estado=opt_estado,
        pagina_actual=1, registros_por_pagina=50000
    )
    
    if not lista_salidas: 
        return b""

    wb = Workbook()
    ws = wb.active
    ws.title = "Reporte de Despachos"
    
    # Ajuste manual inicial de columnas para el contenedor (Columnas A a la E)
    ws.column_dimensions['A'].width = 18
    ws.column_dimensions['B'].width = 45
    ws.column_dimensions['C'].width = 22
    ws.column_dimensions['D'].width = 25
    ws.column_dimensions['E'].width = 20
    
    # Aplicar membrete estándar
    fila_actual = aplicar_membrete_excel(ws, "E", titulo_final, emisor_limpio)
    
    # CONTROL: Si el usuario realizó una búsqueda por texto, la agregamos limpiamente debajo
    if txt_universal and txt_universal.strip():
        ws.cell(row=fila_actual, column=1, value="Criterio de Búsqueda:").font = Font(name="Arial", size=9, bold=True, color="555555")
        ws.cell(row=fila_actual, column=2, value=f'"{txt_universal.strip()}"').font = Font(name="Arial", size=9, italic=True)
        fila_actual += 2
    else:
        fila_actual += 1 # Si no buscó nada, solo dejamos una línea en blanco de cortesía

    # Estilos de Bordes para el contenedor cerrado
    med_side = Side(style='medium', color='1F497D')    # Borde exterior grueso (azul militar)
    thin_side = Side(style='thin', color='D3D3D3')      # Borde interno sutil (gris claro)
    fill_subcabecera = PatternFill(start_color="F2F2F2", end_color="F2F2F2", fill_type="solid")

    for salida_obj in lista_salidas:
        nombre_responsable = f"{salida_obj.usuario.nombres.split()[0]} {salida_obj.usuario.apellidos.split()[0]}"
        fecha_str = salida_obj.fecha.strftime("%d/%m/%Y %I:%M %p") if salida_obj.fecha else "N/A"
        estado_str = salida_obj.estado.value if hasattr(salida_obj.estado, "value") else str(salida_obj.estado)
        
        renglones_detalles = crud_salidas.obtener_detalles_insumos_por_acta(salida_obj.id_salida)
        
        fila_inicio_tarjeta = fila_actual

        # 1. CABECERA DE LA TARJETA (Usa FILL_AZUL_MILITAR global)
        ws.merge_cells(start_row=fila_actual, start_column=1, end_row=fila_actual, end_column=5)
        celda_titulo = ws.cell(row=fila_actual, column=1, 
                               value=f" ACTA DE SALIDA #{salida_obj.id_salida}  |  ORDEN: {salida_obj.orden_salida}  |  ESTADO: {estado_str}")
        celda_titulo.font = Font(name="Arial", size=10, bold=True, color="FFFFFF")
        celda_titulo.fill = FILL_AZUL_MILITAR
        celda_titulo.alignment = ALINEAR_IZQ
        fila_actual += 1
        
        # 2. METADATOS ÚNICOS DE LA SALIDA
        ws.cell(row=fila_actual, column=1, value="  Fecha Despacho:").font = Font(name="Arial", size=9, bold=True, color="555555")
        ws.cell(row=fila_actual, column=2, value=fecha_str).font = Font(name="Arial", size=9)
        ws.cell(row=fila_actual, column=4, value="Responsable:").font = Font(name="Arial", size=9, bold=True, color="555555")
        ws.cell(row=fila_actual, column=5, value=nombre_responsable).font = Font(name="Arial", size=9)
        fila_actual += 1
        
        ws.cell(row=fila_actual, column=1, value="  Destino / Paciente:").font = Font(name="Arial", size=9, bold=True, color="555555")
        ws.cell(row=fila_actual, column=2, value=salida_obj.paciente_destino).font = Font(name="Arial", size=9)
        ws.cell(row=fila_actual, column=4, value="Razon Logistica:").font = Font(name="Arial", size=9, bold=True, color="555555")
        ws.cell(row=fila_actual, column=5, value=salida_obj.razon_salida).font = Font(name="Arial", size=9)
        fila_actual += 1
        
        # 3. LÍNEA DE RESPIRO INTERNA (Fila vacía dentro del contenedor)
        ws.cell(row=fila_actual, column=1, value="")
        fila_actual += 1
        
        # 4. ENCABEZADOS DE LA SUBTABLA DE INSUMOS
        headers_detalle = ["ID REGISTRO", "INSUMO MEDICO DESPACHADO", "CODIGO DE LOTE", "CANTIDAD DESPACHADA"]
        for col_idx, text in enumerate(headers_detalle, 1):
            c = ws.cell(row=fila_actual, column=col_idx, value=text)
            c.font = Font(name="Arial", size=8.5, bold=True, color="333333")
            c.fill = fill_subcabecera
            c.alignment = ALINEAR_CENTRO
            c.border = Border(top=thin_side, bottom=thin_side, left=thin_side, right=thin_side)
        fila_actual += 1
        
        # 5. CONTENIDO DE LOS INSUMOS
        if renglones_detalles:
            for det in renglones_detalles:
                ws.cell(row=fila_actual, column=1, value=det[0]).alignment = ALINEAR_CENTRO
                ws.cell(row=fila_actual, column=2, value=f"  {det[2]}").alignment = ALINEAR_IZQ
                ws.cell(row=fila_actual, column=3, value=det[3]).alignment = ALINEAR_CENTRO
                
                c4 = ws.cell(row=fila_actual, column=4, value=f"{int(det[4])} u.")
                c4.alignment = ALINEAR_CENTRO
                c4.font = Font(name="Arial", size=9, bold=True)
                
                # Asignar bordes del cuerpo de la tabla
                for c in range(1, 5):
                    ws.cell(row=fila_actual, column=c).border = Border(top=thin_side, bottom=thin_side, left=thin_side, right=thin_side)
                fila_actual += 1
        else:
            ws.merge_cells(start_row=fila_actual, start_column=1, end_row=fila_actual, end_column=4)
            ws.cell(row=fila_actual, column=1, value="  No se encontraron insumos registrados.").font = Font(italic=True, size=9)
            for c in range(1, 5):
                ws.cell(row=fila_actual, column=c).border = Border(top=thin_side, bottom=thin_side, left=thin_side, right=thin_side)
            fila_actual += 1

        # 6. ENCAPSULAMIENTO EN UNA CAJA PERIMETRAL EXTERIOR
        # Este ciclo garantiza que todo el bloque mantenga un borde continuo en el extremo exterior
        for r in range(fila_inicio_tarjeta, fila_actual):
            for c in range(1, 6):
                cell = ws.cell(row=r, column=c)
                t = cell.border.top
                b = cell.border.bottom
                l = cell.border.left
                r_side = cell.border.right
                
                if r == fila_inicio_tarjeta: t = med_side
                if r == fila_actual - 1: b = med_side
                if c == 1: l = med_side
                if c == 5: r_side = med_side
                
                cell.border = Border(top=t, bottom=b, left=l, right=r_side)
                
        fila_actual += 2  # Separador entre tarjetas independientes

    excel_buffer = io.BytesIO()
    wb.save(excel_buffer)
    excel_buffer.seek(0)
    return excel_buffer.getvalue()


def generar_reporte_salidas_pdf(txt_universal: str, rango_fechas: list, opt_estado: str, usuario_emisor: str) -> bytes:
    """
    Genera el reporte de auditoría en PDF estructurando de manera elegante las actas.
    Cada acta se encapsula herméticamente dentro de una sola tabla compacta
    """    
    emisor_limpio = "Usuario de Auditoria" if isinstance(usuario_emisor, bool) else str(usuario_emisor)
    
    lista_salidas, _ = crud_salidas.obtener_salidas_filtradas_paginadas(
        txt_universal=txt_universal, rango_fechas=rango_fechas, opt_estado=opt_estado,
        pagina_actual=1, registros_por_pagina=50000
    )
    
    if not lista_salidas: 
        return b""

    # 1. Determinar el estado y rango de fechas para el título (Lógica unificada con Excel)
    estado_texto = "TODAS LAS SALIDAS"
    if opt_estado and "VALI" in opt_estado.upper():
        estado_texto = "SALIDAS VÁLIDAS"
    elif opt_estado and "ANUL" in opt_estado.upper():
        estado_texto = "SALIDAS ANULADAS"

    if rango_fechas and len(rango_fechas) == 2:
        str_fechas = f" del {rango_fechas[0].strftime('%d/%m/%Y')} al {rango_fechas[1].strftime('%d/%m/%Y')}"
    else:
        str_fechas = ""

    titulo_reporte = f"Historial de {estado_texto}{str_fechas}"
    
    # Si el usuario realizó una búsqueda por texto, la dejamos en la descripción de filtros
    filtros_aplicados = f"Búsqueda: '{txt_universal.strip()}'" if txt_universal and txt_universal.strip() else "Ninguna"

    pdf = PDFBaseSIALMED(orientation='P', unit='mm', format='letter')
    pdf.alias_nb_pages()
    pdf.set_auto_page_break(True, 20)
    
    pdf.add_page()
    pdf.escribir_subcabecera_pdf(titulo_reporte, emisor_limpio, filtros_aplicados)

    ancho_total = 196

    for salida_obj in lista_salidas:
        nombre_responsable = f"{salida_obj.usuario.nombres.split()[0]} {salida_obj.usuario.apellidos.split()[0]}"
        fecha_str = salida_obj.fecha.strftime("%d/%m/%Y %I:%M %p") if salida_obj.fecha else "N/A"
        
        estado_crudo = salida_obj.estado.value if hasattr(salida_obj.estado, "value") else str(salida_obj.estado)
        estado_final = "VALIDO" if "VALIDO" in estado_crudo.upper() else "ANULADO"
        
        renglones_detalles = crud_salidas.obtener_detalles_insumos_por_acta(salida_obj.id_salida)
        
        # Validación de desborde dinámico de página (Evita que la tabla se rompa)
        alto_bloque_estimado = 25 + (len(renglones_detalles) * 5.5)
        if (pdf.get_y() + alto_bloque_estimado) > (279 - 25):
            pdf.add_page()
            pdf.escribir_subcabecera_pdf(titulo_reporte, emisor_limpio, filtros_aplicados)

        # ==============================================================================
        # ESTRUCTURA DE TABLA UNIFICADA (BLOQUE CONTINUO Y HERMÉTICO)
        # ==============================================================================
        
        # 1. ENCABEZADO PRINCIPAL (Azul Militar SIAL-MED / Letras Blancas)
        pdf.set_fill_color(31, 73, 125) 
        pdf.set_text_color(255, 255, 255)
        pdf.set_font('Arial', 'B', 9.5)
        pdf.cell(ancho_total, 6.5, f"  ACTA DE SALIDA #{salida_obj.id_salida}   |   ORDEN LOGÍSTICA: {salida_obj.orden_salida}   |   ESTADO: {estado_final}", 1, 1, 'L', True)
        
        # 2. FILAS DE METADATOS INTERNOS
        pdf.set_text_color(0, 0, 0)
        
        # Fila de Metadatos 1: Fecha y Responsable
        pdf.set_font('Arial', 'B', 8.5)
        pdf.cell(32, 5, " Fecha de Emisión:", 'L', 0, 'L')
        pdf.set_font('Arial', '', 8.5)
        pdf.cell(65, 5, fecha_str, 0, 0, 'L')
        
        pdf.set_font('Arial', 'B', 8.5)
        pdf.cell(25, 5, "Responsable:", 0, 0, 'L')
        pdf.set_font('Arial', '', 8.5)
        pdf.cell(74, 5, nombre_responsable, 'R', 1, 'L')
        
        # Fila de Metadatos 2: Destino y Razón Logística
        pdf.set_font('Arial', 'B', 8.5)
        pdf.cell(32, 5, " Destino / Paciente:", 'L', 0, 'L')
        pdf.set_font('Arial', '', 8.5)
        pdf.cell(65, 5, salida_obj.paciente_destino[:38], 0, 0, 'L')
        
        pdf.set_font('Arial', 'B', 8.5)
        pdf.cell(25, 5, "Razón Logística:", 0, 0, 'L')
        pdf.set_font('Arial', '', 8.5)
        pdf.cell(74, 5, salida_obj.razon_salida[:38], 'R', 1, 'L')
        
        # 3. CABECERA DE LA SUBTABLA (Gris claro de respiro y texto negro para continuidad visual)
        pdf.set_fill_color(240, 240, 240)  # Gris claro armonizado
        pdf.set_text_color(0, 0, 0)        # Texto negro
        pdf.set_font('Arial', 'B', 8)
        
        pdf.cell(20, 5, "ID REG.", 1, 0, 'C', True)
        pdf.cell(111, 5, "INSUMO MÉDICO DESPACHADO", 1, 0, 'L', True)
        pdf.cell(35, 5, "CÓDIGO DE LOTE", 1, 0, 'C', True)
        pdf.cell(30, 5, "CANTIDAD", 1, 1, 'C', True)
        
        # 4. CUERPO DE DETALLES DE INSUMOS
        pdf.set_font('Arial', '', 8)
        
        if renglones_detalles:
            for det in renglones_detalles:
                pdf.cell(20, 5, str(det[0]), 1, 0, 'C')
                nombre_insumo_recortado = det[2][:62] + "..." if len(det[2]) > 62 else det[2]
                pdf.cell(111, 5, f" {nombre_insumo_recortado}", 1, 0, 'L')
                pdf.cell(35, 5, str(det[3]), 1, 0, 'C')
                
                pdf.set_font('Arial', 'B', 8)
                pdf.cell(30, 5, f"{int(det[4])} u.", 1, 1, 'C')
                pdf.set_font('Arial', '', 8)
        else:
            pdf.set_font('Arial', 'I', 8)
            pdf.cell(ancho_total, 5, "   No hay registros de insumos vinculados en este despacho.", 1, 1, 'L')
        
        # Separación limpia antes de la siguiente tarjeta/tabla autónoma
        pdf.ln(5) 

    return bytes(pdf.output(dest='S'))
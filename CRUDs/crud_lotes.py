import uuid
import logging
from sqlmodel import Session, select, and_, or_, func  # Operaciones de consulta
from models import Entradas, Lotes, Insumos, Usuarios, DetallesSalida, Estado, engine  # Modelos de datos del SIAL-MED
from seguridad import sanitizar_input, usuario_tiene_permiso_escritura
from datetime import date, datetime, time  # Manejo de fechas para vencimientos
from sqlalchemy.orm import joinedload, make_transient, selectinload
from sqlalchemy.exc import IntegrityError  # 💡 Importación clave para detectar duplicados
from typing import List  # Tipado de listas
from pydantic import ValidationError


def obtener_lotes_filtrados(
    txt_universal: str = "",       # Barra 1: Insumo, VED, Código de lote o Ubicación
    txt_rango_stock: str = "",     # Barra 2: Existencias (Min-Max)
    rango_vencimiento: list = None,# Barra 3: Fechas [Inicio, Fin]
    opt_estado: str = "ACTIVOS"    # Barra 4: ACTIVOS / INACTIVOS / TODOS
):
    """
    Consulta y filtra lotes de insumos desde la base de datos aplicando lógica de negocio.

    Esta función realiza un JOIN entre Lotes e Insumos y aplica filtros dinámicos. 
    Resuelve la matemática de stock disponible en tiempo de ejecución para cada lote 
    según las entradas y salidas registradas.

    Parámetros:
    -----------
    txt_universal : str, opcional
        Texto para búsqueda general. Busca coincidencias en: nombre del insumo, 
        código de lote, ubicación física, motivo de desactivación o clasificación VED.
    txt_rango_stock : str, opcional
        Filtro de existencia. Admite valores exactos (ej: "10") o rangos 
        mediante guiones (ej: "5-50").
    rango_vencimiento : list, opcional
        Lista con dos elementos [fecha_inicio, fecha_fin] para filtrar por 
        vigencia del lote.
    opt_estado : str, opcional
        Define el estado de los lotes a recuperar: "ACTIVOS", "INACTIVOS" o "TODOS". 
        Por defecto es "ACTIVOS".

    Retorna:
    --------
    list
        Una lista de tuplas con la estructura [(Lotes, Insumos), ...] que cumplen 
        con todos los criterios de filtro aplicados. Retorna una lista vacía si 
        ocurre un error o no hay coincidencias.
    """
    with Session(engine) as session:
        try:
            # 1. Uniones base (JOIN) para poder buscar datos del Insumo desde el Lote
            statement = select(Lotes, Insumos).join(Insumos, Lotes.id_insumo == Insumos.id_insumo)
            condiciones = []

            # FILTRO 1: ESTADO DEL LOTE
            if opt_estado == "ACTIVOS":
                condiciones.append(Lotes.activo == True)
            elif opt_estado == "INACTIVOS":
                condiciones.append(Lotes.activo == False)

            # FILTRO 2: BARRA UNIVERSAL (Insumo, VED, Código, Ubicación)
            if txt_universal:
                busqueda = txt_universal.upper()
                # Traducimos VED por si busca la palabra completa
                letra_ved = {"VITAL": "V", "ESENCIAL": "E", "DESEABLE": "D"}.get(busqueda)
                
                bloque_or = [
                    Insumos.nombre.ilike(f"%{txt_universal}%"),
                    Lotes.codigo_lote.ilike(f"%{txt_universal}%"),
                    Lotes.ubicacion_fisica.ilike(f"%{txt_universal}%"),
                    Lotes.motivo_desactivacion.ilike(f"%{txt_universal}%")
                ]
                if letra_ved:
                    bloque_or.append(Insumos.clasificacion_ved == letra_ved)
                
                condiciones.append(or_(*bloque_or))

            # 🎛️ FILTRO 3: RANGO DE FECHAS DE VENCIMIENTO
            if rango_vencimiento and len(rango_vencimiento) == 2:
                condiciones.append(Lotes.fecha_vencimiento >= rango_vencimiento[0])
                condiciones.append(Lotes.fecha_vencimiento <= rango_vencimiento[1])

            # Aplicamos todos los filtros acumulados y precargamos las relaciones indispensables
            statement = statement.where(*condiciones).options(
                selectinload(Lotes.entrada),
                selectinload(Lotes.detalles_salida).selectinload(DetallesSalida.salida)
            )
            statement= statement.order_by(Lotes.fecha_vencimiento)
            # Ejecutamos la consulta en SQLite
            resultados = session.exec(statement).all()
            
            # Formateamos los resultados en tuplas (Lote, Insumo) compatibles con tu estructura
            lista_estructurada = []
            for item in resultados:
                # SQLModel puede retornar tuplas (Lotes, Insumos) al hacer un join explícito
                lote_obj = item[0]
                insumo_obj = item[1]
                
                # 🎛️ FILTRO 4: FILTRADO DE STOCK EN BACKEND VÍA PYTHON (Evaluando la property)
                if txt_rango_stock:
                    try:
                        if "-" in txt_rango_stock:
                            partes = txt_rango_stock.split("-")
                            val_min = int(partes[0].strip()) if partes[0].strip() else 0
                            val_max = int(partes[1].strip()) if partes[1].strip() else 999999
                        else:
                            val_min = int(txt_rango_stock)
                            val_max = 999999
                        
                        # Si el stock calculado no entra en el rango, lo ignoramos antes de enviarlo
                        if not (val_min <= lote_obj.stock_disponible <= val_max):
                            continue
                    except ValueError:
                        pass # Si meten basura en el stock, ignora el filtro numérico
                
                lista_estructurada.append((lote_obj, insumo_obj))

            return lista_estructurada

        except Exception as e:
            # Trazabilidad Avanzada: Log estructurado en formato JSON
            correlation_id = str(uuid.uuid4())
            logging.error(f'{{"correlation_id": "{correlation_id}", "error": "{str(e)}", "modulo": "crud_lotes_filtrados"}}')
            
            # Retorno seguro
            return []
    

def actualizar_registros_lotes_masivo(cambios_dict: dict):
    """
    Actualiza de forma masiva las propiedades físicas de múltiples lotes en una sola transacción.
    Permite modificar atributos esenciales como la ubicación física o el código identificador
    de varios lotes de manera simultánea en el archivo SQLite.

    Parámetros: cambios_dict : dict
        Un diccionario estructurado donde las llaves son los IDs de los lotes (int) 
        y los valores son diccionarios con los campos que se van a modificar 
        (ej. {2: {"ubicacion_fisica": "Estante B-4"}}).

    Retorna: bool
        Retorna True si todas las actualizaciones se consolidaron con éxito en la base de datos.
        Ejecuta un rollback integral y retorna False si ocurre cualquier error de persistencia.
    """
    # 🛡️ BARRERA BLUETEAM: Control de acceso explícito
    if not usuario_tiene_permiso_escritura():
        return "✖️ ACCESO DENEGADO: Permisos insuficientes."

    hoy = date.today()
    
    with Session(engine) as session:
        try:
            for id_lote_str, modificaciones in cambios_dict.items():
                id_lote = int(id_lote_str)
                
                lote = session.get(Lotes, id_lote)
                entrada= session.scalars(select(Entradas).where(Entradas.id_lote== lote.id_lote)).first() 
                
                if "CÓDIGO DE LOTE" in modificaciones:
                        lote = session.get(Lotes, entrada.id_lote)
                        if lote:
                            # 🧼 SANITIZACIÓN: Limpieza de cadena antes de validación
                            nuevo_codigo = sanitizar_input(str(modificaciones["CÓDIGO DE LOTE"]))
                            mensaje= Lotes.validar_textos_lote(valor= nuevo_codigo, campo='código de lote')
                        # Buscamos si ya existe el mismo código activo para ESTE insumo específico
                        stmt_duplicado = select(Lotes).where(
                            Lotes.id_insumo == lote.id_insumo,
                            Lotes.codigo_lote == nuevo_codigo,
                            Lotes.activo == True
                        )
                        lote_existente = session.exec(stmt_duplicado).first()
                        if lote_existente:
                            raise ValueError("DUPLICADO ACTIVO") # Retornamos un código de error controlado para la interfaz
                        lote.codigo_lote= nuevo_codigo
                        session.add(lote)
                        #print(lote)

                if "INSUMO ASOCIADO" in modificaciones:
                    # busco el insumo con ese nombre
                    insumo= session.scalars(select(Insumos).where(Insumos.nombre== modificaciones['INSUMO ASOCIADO'])).first() 
                    if insumo and lote:
                        if insumo.activo==False:
                            raise ValueError('No se puede realizar la actualización porque el nuevo insumo está inactivo')
                        if lote.stock_disponible<entrada.cantidad:
                            raise ValueError(
                        "No se puede editar el insumo. "
                        f"Ya se han despachado {entrada.cantidad-lote.stock_disponible} unidades del lote "
                        f"'{lote.codigo_lote}' en órdenes médicas activas."
                    )
                        # Buscamos si ya existe el mismo código activo para ESTE insumo específico
                        stmt_duplicado = select(Lotes).where(
                            Lotes.id_insumo == insumo.id_insumo,
                            Lotes.codigo_lote == lote.codigo_lote,
                            Lotes.activo == True
                        )
                        lote_existente = session.exec(stmt_duplicado).first()
                        if lote_existente:
                            raise ValueError("No se puede editar el insumo. Ya hay un insumo con este código de lote") # Retornamos un código de error controlado para la interfaz
                        lote.id_insumo= insumo.id_insumo

                # 3. Modificación de la ubicación en estanterías
                if "UBICACIÓN FÍSICA" in modificaciones:
                    # 🧼 SANITIZACIÓN: Limpieza de cadena
                    lote.ubicacion_fisica = sanitizar_input(modificaciones["UBICACIÓN FÍSICA"])
                    mensaje= Lotes.validar_textos_lote(valor= lote.ubicacion_fisica, campo='ubicación')

                # 4. Modificación de la Fecha de Vencimiento
                if "FECHA VENCIMIENTO" in modificaciones:
                    f_vence = modificaciones["FECHA VENCIMIENTO"]
                    if isinstance(f_vence, str):
                        lote.fecha_vencimiento = date.fromisoformat(f_vence)
                    else:
                        lote.fecha_vencimiento = f_vence
                    mensaje= Lotes.validar_fecha_vencimiento(valor= lote.fecha_vencimiento)

                # REGLAS AUTOMÁTICAS DE INACTIVACIÓN DE SEGURIDAD MÉDICA
                if lote.stock_disponible == 0:
                    lote.activo = False  
                    lote.motivo_desactivacion = "AGOTADO"
                else:
                    if "ESTADO" in modificaciones:
                        estado_celda = modificaciones["ESTADO"].upper()
                        
                        # REGLA CORTAFUEGOS: Insumo inactivo
                        if estado_celda == "ACTIVO" and hasattr(lote, "insumo") and not lote.insumo.activo:
                            session.rollback()        
                            return "INSUMO_INACTIVO"  
                        
                        # Solución al error de escritura:
                        # Si pasa de Inactivo a Activo, limpiamos el motivo de la desactivación previa
                        nuevo_estado = (estado_celda == "ACTIVO")
                        if nuevo_estado and not lote.activo:
                            lote.motivo_desactivacion = None # Se limpia el rastro del error
                        elif not nuevo_estado and lote.activo:
                            lote.motivo_desactivacion = "DESACTIVACIÓN MANUAL"
                            
                        lote.activo = nuevo_estado

                    session.add(lote)           
            
            # Aquí es donde SQLAlchemy compila el SQL y SQLite valida el índice compuesto
            session.commit()
            return True
        
        except ValueError as e:
            session.rollback()
            return f"✖️ REGLA LOGÍSTICA: {str(e)}"
        except Exception as e:
            session.rollback()
            # TRAZABILIDAD AVANZADA: Log estructurado JSON con UUID para el caos
            correlation_id = str(uuid.uuid4())
            logging.error(f'{{"correlation_id": "{correlation_id}", "error": "{str(e)}", "modulo": "actualizar_lotes"}}')
            return f"✖️ Ocurrió un error inesperado. Reporte el código: [{correlation_id}]"
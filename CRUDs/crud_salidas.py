import uuid
import logging
from sqlmodel import Session, select, and_, or_, func
from models import Salidas, DetallesSalida, Lotes, Insumos, Usuarios, Estado, engine
from seguridad import sanitizar_input, usuario_tiene_permiso_escritura
from datetime import datetime, date, time
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import selectinload, joinedload
from typing import Optional, List
from sqlalchemy import or_, and_, func


def obtener_lotes_disponibles_fefo(
    id_insumo: int, 
    razon_salida: str = "Consumo Clínico",
    session_externa: Optional[Session] = None  # 1. Agregamos el parámetro opcional para las pruebas
):
    """
    Busca y ordena los lotes de un insumo priorizando su fecha de vencimiento (FEFO).
    Implementa logs estructurados para trazabilidad y protección de datos en caso de error.

    Parámetros:
        id_insumo (int): Identificador del insumo a consultar.
        razon_salida (str): Razón del movimiento (define reglas de filtrado).
        session_externa (Optional[Session]): Sesión opcional para inyección en pruebas unitarias.

    Retorna:
        list: Lista ordenada de lotes con stock disponible, o una lista vacía en caso de error.
    """
    try:
        # <- 2. Si viene sesión de las pruebas, usamos esa. Si no, abrimos la local de producción.
        session = session_externa if session_externa is not None else Session(engine)
        
        # Encapsulamos la lógica para poder reutilizar la sesión correctamente
        hoy = date.today()
        
        # Base de datos: Lotes activos que pertenecen al insumo seleccionado
        statement = (
            select(Lotes)
            .where(Lotes.id_insumo == id_insumo)
            .where(Lotes.activo == True)
            .options(
                selectinload(Lotes.entrada),
                selectinload(Lotes.detalles_salida)
            )
        )
        
        # CORTAFUEGOS DE INTEGRIDAD SEGÚN RAZÓN LOGÍSTICA
        if razon_salida == "Perdida por Caducidad":
            # REGLA: Si es perdida, el sistema SOLO permite aislar y ver lotes VENCIDOS
            statement = statement.where(Lotes.fecha_vencimiento <= hoy)
        else:
            # REGLA: Consumos, Traslados, Donaciones y Otros SOLO operan con lotes VIGENTES
            statement = statement.where(Lotes.fecha_vencimiento > hoy)

        todos_los_lotes = session.exec(statement).all()
        
        # Filtramos en memoria RAM que posean existencias reales mayores a cero
        lotes_con_existencias = [lote for lote in todos_los_lotes if lote.stock_disponible > 0]
        
        # Ordenación secuencial FEFO (Garantiza prioridad de vencimiento en el vector)
        return sorted(lotes_con_existencias, key=lambda x: x.fecha_vencimiento if x.fecha_vencimiento else date.max)
            
    except Exception as e:
        # Trazabilidad Avanzada: Log estructurado en formato JSON
        correlation_id = str(uuid.uuid4())
        logging.error(f'{{"correlation_id": "{correlation_id}", "error": "{str(e)}", "modulo": "obtener_lotes_fefo"}}')
        
        # Respuesta segura para no romper el flujo de la UI
        return []



def registrar_despacho_combinado_fefo(
    orden_salida: str, 
    paciente_destino: str, 
    razon_salida: str, 
    id_usuario: int, 
    lista_pedidos: list,
    session_externa: Optional[Session] = None
):
    """
    Procesa la salida de insumos distribuyendo la cantidad solicitada entre múltiples lotes bajo la doctrina FEFO.
    
    Esta función crea una cabecera de salida y genera automáticamente los registros de detalle,
    descontando el inventario de forma atómica y priorizando los lotes con vencimiento más próximo.

    Parámetros:
    - orden_salida (str): Identificador único de la orden médica o logística.
    - paciente_destino (str): Nombre del paciente o área destino.
    - razon_salida (str): Motivo de la salida (ej. 'Consumo Clínico').
    - id_usuario (int): ID del usuario que registra el despacho.
    - lista_pedidos (list): Lista de diccionarios con la estructura: 
      {'id_insumo': int, 'cantidad': int, 'nombre_insumo': str, ...}
    - session_externa (Optional[Session]): Sesión de base de datos para pruebas unitarias.

    Retorna:
    - dict: Contiene 'status' (bool) y 'despacho' (hoja de ruta) si es exitoso.
    - str: Mensaje de error controlado en caso de fallos.
    """

    # BARRERA BLUETEAM: Control de acceso estricto antes de procesar
    if not usuario_tiene_permiso_escritura():
        return "✖️ ACCESO DENEGADO: Permisos insuficientes."

    # Si viene sesión externa (pruebas), la usamos. Si no, creamos una local.
    session = session_externa if session_externa is not None else Session(engine)

    try:
        # 🧼 SANITIZACIÓN: Limpieza de entradas para evitar inyecciones
        orden_salida = sanitizar_input(orden_salida)
        paciente_destino = sanitizar_input(paciente_destino)

        # Buscamos si ya existe esa misma orden en estado VALIDO
        stmt_duplicado = select(Salidas).where(
            Salidas.orden_salida == orden_salida,
            Salidas.estado == Estado.VALIDO
        )
        orden_existente = session.exec(stmt_duplicado).first()    
        if orden_existente:
            return "ORDEN_DUPLICADA"
        
        # Creamos la cabecera del registro administrativo
        nueva_salida = Salidas(
            id_usuario=id_usuario,
            orden_salida=orden_salida,
            paciente_destino=paciente_destino,
            razon_salida=razon_salida,
            fecha=datetime.now(),
        )
        session.add(nueva_salida)
        session.flush()  # Sincroniza para obtener el ID autogenerado
        
        hoja_ruta_operario = []
        
        for pedido in lista_pedidos:
            id_insumo = pedido["id_insumo"]
            cantidad_requerida = pedido["cantidad"]
            nombre_medicamento = pedido["nombre_insumo"]
            lote_manual_id = pedido.get("lote_especifico_id")
            modo = pedido.get("modo_extraccion")
            
            # DETERMINACIÓN DEL CANAL DE STOCK (MANUAL VS AUTOMÁTICO)
            if lote_manual_id and modo == "SELECCIÓN MANUAL":
                lote_obj = session.get(Lotes, lote_manual_id)
                lotes_disponibles = [lote_obj] if lote_obj and lote_obj.activo else []
            else:
                # 💡 EL CAMBIO REY: Pásale la sesión activa a tu función FEFO
                lotes_disponibles = obtener_lotes_disponibles_fefo(
                    id_insumo, 
                    razon_salida, 
                    session_externa=session  # 👈 Le inyectas la sesión que ya tienes abierta
                )
            
            # Validación de respaldo físico en base de datos
            stock_disponible_total = sum(l.stock_disponible for l in lotes_disponibles)
            if stock_disponible_total < cantidad_requerida:
                raise ValueError(
                    f"Inventario insuficiente para '{nombre_medicamento}'. "
                    f"Requerido: {cantidad_requerida} u. | Disponible: {stock_disponible_total} u."
                )
            
            # Bucle de descuento físico de inventario
            unidades_por_descontar = cantidad_requerida
            for lote in lotes_disponibles:
                if unidades_por_descontar <= 0:
                    break
                    
                lote_bd = session.get(Lotes, lote.id_lote)
                if not lote_bd or not lote_bd.activo:
                    continue
                    
                cant_lote = lote.stock_disponible
                cant_a_descontar = min(unidades_por_descontar, cant_lote)
                
                nuevo_detalle = DetallesSalida(
                    id_salida=nueva_salida.id_salida,
                    id_lote=lote.id_lote,
                    cantidad=cant_a_descontar
                )
                session.add(nuevo_detalle)
                
                hoja_ruta_operario.append({
                    "MEDICAMENTO": nombre_medicamento,
                    "LOTE": lote.codigo_lote,
                    "UBICACIÓN": lote.ubicacion_fisica,
                    "CANTIDAD A RETIRAR": f"{cant_a_descontar} unds."
                })
                
                unidades_por_descontar -= cant_a_descontar
                
                if (cant_lote - cant_a_descontar) == 0:
                    lote_bd.activo = False
                    lote_bd.motivo_desactivacion = 'AGOTAMIENTO'
                    session.add(lote_bd)
        
        if session_externa is None:
            session.commit()
            
        return {"status": True, "despacho": hoja_ruta_operario}
        
    except IntegrityError:
        if session_externa is None:
            session.rollback()
        return "ORDEN_DUPLICADA"
        
    except ValueError as e:
        # 💡 CORRECCIÓN CRUCIAL DE FLUJO LOGICIAL:
        if session_externa is not None:
            raise e  # Si estamos en pruebas, lanzamos el error inmediatamente
        
        session.rollback()
        return str(e)
        
    except Exception as e:
        if session_externa is not None:
            raise e
        session.rollback()
        # 🔍 TRAZABILIDAD AVANZADA: Log seguro con UUID
        correlation_id = str(uuid.uuid4())
        logging.error(f'{{"correlation_id": "{correlation_id}", "error": "{str(e)}", "modulo": "salidas_despacho"}}')
        return f"🛑 Ocurrió un error inesperado. Reporte el código: [{correlation_id}]"
        
    finally:
        if session_externa is None:
            session.close()
        

    



def obtener_salidas_filtradas_paginadas(
    txt_universal: str = "",
    rango_fechas: list = None,
    opt_estado: str = "VALIDO",
    pagina_actual: int = 1,
    registros_por_pagina: int = 50
):
    """
    Filtra y pagina las cabeceras de las Actas de Salida, permitiendo búsquedas en 
    datos del acta, usuario responsable, insumos o clasificación VED.
    Utiliza joinedload para cargar el usuario y los detalles (con sus respectivos lotes e insumos), 
    asegurando que los datos estén disponibles tras cerrar la sesión.

    Parámetros:
    - txt_universal (str): Texto para buscar en paciente, orden, razón, nombre de usuario, 
                           nombre del insumo o clasificación (V, E, D).
    - rango_fechas (list): [date_inicio, date_fin] para filtrar por fecha de la salida.
    - opt_estado (str): Estado del acta ('VALIDO', 'ANULADO' o 'TODOS').
    - pagina_actual (int): Número de página (base 1).
    - registros_por_pagina (int): Cantidad de resultados por página.

    Retorna:
    - tuple: (lista_salidas, total_coincidencias) 
        - lista_salidas: Lista de objetos Salidas con sus relaciones cargadas.
        - total_coincidencias: Entero con el conteo total sin paginar.
    """
    with Session(engine) as session:
        try:
            # Precargamos Usuario y la cadena completa: Salida -> Detalles -> Lote -> Insumo
            statement = select(Salidas).options(
                joinedload(Salidas.usuario),
                joinedload(Salidas.detalles).joinedload(DetallesSalida.lote).joinedload(Lotes.insumo)
            ).join(Usuarios, Salidas.id_usuario == Usuarios.id_usuario)

            # Join con detalles para permitir filtrar por Insumos
            statement = statement.join(DetallesSalida, Salidas.id_salida == DetallesSalida.id_salida) \
                                 .join(Lotes, DetallesSalida.id_lote == Lotes.id_lote) \
                                 .join(Insumos, Lotes.id_insumo == Insumos.id_insumo)

            condiciones = []

            if opt_estado != "TODOS":
                condiciones.append(Salidas.estado == opt_estado)

            if txt_universal:
                busqueda = txt_universal.strip().upper()
                letra_ved = {"VITAL": "V", "ESENCIAL": "E", "DESEABLE": "D"}.get(busqueda)
                
                bloque_or = [
                    Salidas.paciente_destino.ilike(f"%{busqueda}%"),
                    Salidas.orden_salida.ilike(f"%{busqueda}%"),
                    Salidas.razon_salida.ilike(f"%{busqueda}%"),
                    Usuarios.nombres.ilike(f"%{busqueda}%"),
                    Usuarios.apellidos.ilike(f"%{busqueda}%"),
                    Insumos.nombre.ilike(f"%{busqueda}%")
                ]
                if letra_ved:
                    bloque_or.append(Insumos.clasificacion_ved == letra_ved)
                
                condiciones.append(or_(*bloque_or))

            if rango_fechas and len(rango_fechas) == 2:
                dt_inicio = datetime.combine(rango_fechas[0], time.min)
                dt_fin = datetime.combine(rango_fechas[1], time.max)
                condiciones.append(and_(Salidas.fecha >= dt_inicio, Salidas.fecha <= dt_fin))

            if condiciones:
                statement = statement.where(*condiciones)

            # CONTEO (Usamos distinct porque el join con detalles multiplica las filas)
            stmt_count = select(func.count(func.distinct(Salidas.id_salida))).select_from(Salidas) \
                         .join(Usuarios, Salidas.id_usuario == Usuarios.id_usuario) \
                         .join(DetallesSalida, Salidas.id_salida == DetallesSalida.id_salida) \
                         .join(Lotes, DetallesSalida.id_lote == Lotes.id_lote) \
                         .join(Insumos, Lotes.id_insumo == Insumos.id_insumo)
            
            if condiciones:
                stmt_count = stmt_count.where(*condiciones)
            total_coincidencias = session.exec(stmt_count).one()

            # PAGINACIÓN
            offset_calculado = (pagina_actual - 1) * registros_por_pagina
            statement = statement.distinct().order_by(Salidas.fecha.desc()).limit(registros_por_pagina).offset(offset_calculado)
            
            resultados = session.exec(statement).unique().all()
            return resultados, total_coincidencias

        except Exception as e:
            # Trazabilidad Avanzada: Log estructurado en formato JSON
            correlation_id = str(uuid.uuid4())
            logging.error(f'{{"correlation_id": "{correlation_id}", "error": "{str(e)}", "modulo": "crud_salidas_paginadas"}}')
            return [], 0


def obtener_detalles_insumos_por_acta(id_salida: int):
    """
    Recupera los insumos y lotes específicos que componen una orden de salida determinada.
    Parámetro: id_salida (int): Identificador único de la salida.
    Retorna: list: Lista de tuplas con detalles de insumos, o una lista vacía en caso de error.
    """
    with Session(engine) as session:
        try:
            # Forzamos un SELECT plano extrayendo solo las columnas que la grilla necesita
            statement = (
                select(
                    DetallesSalida.id_detalle_salida,
                    DetallesSalida.id_salida,
                    Insumos.nombre,
                    Insumos.clasificacion_ved,
                    Lotes.codigo_lote,
                    DetallesSalida.cantidad
                )
                .join(Lotes, DetallesSalida.id_lote == Lotes.id_lote)
                .join(Insumos, Lotes.id_insumo == Insumos.id_insumo)
                .where(DetallesSalida.id_salida == int(id_salida)) # Forzamos casteo a entero por seguridad
            )
            
            # Ejecutamos con la sesión nativa para obtener un resultado iterable limpio
            resultados = session.execute(statement).all()
            
            #print(f"🔍 BUSCANDO ID {id_salida} -> Filas encontradas en BD: {len(resultados)}")
            return resultados # Retorna una lista de filas con datos planos
            
        except Exception as e:
            # Trazabilidad Avanzada: Log estructurado en formato JSON
            correlation_id = str(uuid.uuid4())
            logging.error(f'{{"correlation_id": "{correlation_id}", "error": "{str(e)}", "modulo": "crud_salidas_detalles"}}')
            return []



def actualizar_registros_salidas_masivo(cambios_cabecera: dict, cambios_detalle: dict, df_maestro, df_detalle):
    """
    Actualiza de forma masiva múltiples actas de salida y sus detalles en una única transacción atómica.
    Aplica barreras de rol (BlueTeam), sanitización de cadenas y logs en formato JSON.

    Parámetros:
    - cambios_cabecera (dict): Diccionario con cambios en la cabecera (maestro).
    - cambios_detalle (dict): Diccionario con cambios en las líneas de detalle.
    - df_maestro (DataFrame): Referencia visual de la tabla de salidas.
    - df_detalle (DataFrame): Referencia visual de la tabla de detalles.

    Retorna:
    - bool: True si la transacción fue exitosa.
    - str: Mensaje de error controlado en caso de fallo.
    """
    # BARRERA BLUETEAM: Control de acceso estricto
    if not usuario_tiene_permiso_escritura():
        return "✖️ ACCESO DENEGADO: Permisos insuficientes."

    with Session(engine) as session:
        try:
            # ==================================================================
            # 1️ FASE MAESTRA: Cambios en la cabecera (Salidas)
            # ==================================================================
            for idx_m_str, modificaciones in cambios_cabecera.items():
                idx_m = int(idx_m_str)
                id_salida_real = int(df_maestro.iloc[idx_m]["ID"])
                
                salida_maestra = session.get(Salidas, id_salida_real)
                if not salida_maestra:
                    continue

                # Edición directa de campos de texto 
                if "ORDEN DE SALIDA" in modificaciones:
                    # SANITIZACIÓN: Limpieza de entrada
                    salida_maestra.orden_salida = sanitizar_input(modificaciones["ORDEN DE SALIDA"])
                    resultado = Salidas.validar_datos_salida(valor=salida_maestra.orden_salida, info='Orden de salida')

                if "DESTINO / PACIENTE" in modificaciones:
                    # SANITIZACIÓN: Limpieza de entrada
                    salida_maestra.paciente_destino = sanitizar_input(modificaciones["DESTINO / PACIENTE"])
                    resultado = Salidas.validar_datos_salida(valor=salida_maestra.paciente_destino, info='Destino/Paciente')

                # Captura del estado modificado en la grilla maestra
                nuevo_estado_str = modificaciones.get("ESTADO") or modificaciones.get("estado")
                
                # EL FILTRO CRÍTICO: Solo evaluamos la lógica si el estado REALMENTE cambió
                if nuevo_estado_str is not None:
                    nuevo_estado_str = nuevo_estado_str.upper()
                    
                    # TU CÓDIGO ORIGINAL (CASO A: ANULACIÓN)
                    if nuevo_estado_str == "ANULADO":
                        if salida_maestra.estado == Estado.ANULADO:
                            continue
                        
                        # Recorremos los detalles de esta salida para devolver el stock
                        for detalle in salida_maestra.detalles:
                            lote = session.get(Lotes, detalle.id_lote)
                            if lote:
                                lote.activo = True
                                if lote.motivo_desactivacion == 'AGOTADO':
                                    lote.motivo_desactivacion = None
                                session.add(lote)
                        
                        salida_maestra.estado = Estado.ANULADO

                    # CASO B: RE-VALIDACIÓN
                    elif nuevo_estado_str == "VALIDO":
                        if salida_maestra.estado == Estado.VALIDO:
                            continue
                        
                        for detalle in salida_maestra.detalles:
                            lote = session.get(Lotes, detalle.id_lote)
                            if lote:
                                if lote.stock_disponible < detalle.cantidad:
                                    raise ValueError(
                                        f"No se puede reactivar la salida. El lote '{lote.codigo_lote}' "
                                        f"solo tiene {lote.stock_disponible} u. disponibles."
                                    )
                                session.flush()
                                if lote.stock_disponible - detalle.cantidad == 0:
                                    lote.activo = False
                                    lote.motivo_desactivacion = 'AGOTADO'
                                    session.add(lote)
                        
                        salida_maestra.estado = Estado.VALIDO

                session.add(salida_maestra)

            # ==================================================================
            # 2️ FASE DETALLE: Cambios en las cantidades (DetallesSalida)
            # ==================================================================
            for idx_d_str, modificaciones in cambios_detalle.items():
                idx_d = int(idx_d_str)
                # Mapeo usando el mapa visual de detalles para evitar el error del ID 0
                id_real_detalle = int(df_detalle.iloc[idx_d]["ID DETALLE"])
                
                detalle = session.get(DetallesSalida, id_real_detalle)
                if not detalle:
                    continue
                
                salida_maestra = detalle.salida
                
                # Cortafuegos: Si la orden está anulada, no se tocan cantidades
                if salida_maestra.estado == Estado.ANULADO:
                    continue

                # (CASO C: MODIFICACIÓN MANUAL DE CANTIDADES)
                if "CANTIDAD" in modificaciones:
                    nueva_cantidad = modificaciones["CANTIDAD"]
                    resultado = DetallesSalida.validar_cantidad_salida(valor=nueva_cantidad)
                    lote = session.get(Lotes, detalle.id_lote)
                    
                    diferencia = nueva_cantidad - detalle.cantidad
                    
                    if lote:
                        if lote.stock_disponible < diferencia:
                            raise ValueError(
                                f"Existencias insuficientes en el lote '{lote.codigo_lote}' "
                                f"para asimilar el ajuste. Stock disponible actual: {lote.stock_disponible} u."
                            )
                        if diferencia < 0:
                            lote.activo = True
                            session.add(lote)
                    
                    detalle.cantidad = nueva_cantidad
                    session.add(detalle)
                    
                    session.flush()
                    if lote and lote.stock_disponible == 0:
                        lote.activo = False
                        session.add(lote)
            
            session.commit()
            return True
            
        except IntegrityError:
            session.rollback()
            return "⚠️ ERROR DE RESTRICCIÓN: La orden de salida ya se encuentra registrada."
        except ValueError as e:
            session.rollback()
            return f"⚠️ REGLA LOGÍSTICA: {str(e)}"
        except Exception as e:
            session.rollback()
            # TRAZABILIDAD AVANZADA: Log seguro con UUID para auditoría
            correlation_id = str(uuid.uuid4())
            logging.error(f'{{"correlation_id": "{correlation_id}", "error": "{str(e)}", "modulo": "actualizar_salidas_masivo"}}')
            return f"✖️ Ocurrió un error inesperado. Reporte el código: [{correlation_id}]"
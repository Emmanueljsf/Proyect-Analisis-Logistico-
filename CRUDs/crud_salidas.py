from sqlmodel import Session, select, and_, or_, func
from models import Salidas, DetallesSalida, Lotes, Insumos, Estado, engine
from datetime import datetime, date, time
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import selectinload, joinedload
from typing import Optional, List

def obtener_lotes_disponibles_fefo(
    id_insumo: int, 
    razon_salida: str = "Consumo Clínico",
    session_externa: Optional[Session] = None  # 👈 1. Agregamos el parámetro opcional para las pruebas
):
    """
    Busca y ordena los lotes de un insumo priorizando su fecha de vencimiento (First Expired, First Out).
    Soporta inyección de sesión externa para la ejecución aislada de pruebas unitarias.
    """
    try:
        # 👈 2. Si viene sesión de las pruebas, usamos esa. Si no, abrimos la local de producción.
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
        
        # 🔀 CORTAFUEGOS DE INTEGRIDAD SEGÚN RAZÓN LOGÍSTICA
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
        print(f"🛑 Error crítico en obtener lotes disponibles fefo: {e}")
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
    Asienta la orden de salida y descuenta los inventarios de forma atómica en una única transacción.
    """

    # Si viene sesión externa (pruebas), la usamos. Si no, creamos una local.
    session = session_externa if session_externa is not None else Session(engine)

    try:
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
            raise e  # Si estamos en pruebas, lanzamos el error inmediatamente a pytest y salimos
        
        # Si es producción (Streamlit), ejecutamos el rollback local y retornamos la alerta en texto
        session.rollback()
        return str(e)
        
    except Exception as e:
        if session_externa is not None:
            raise e
        session.rollback()
        print(f"🛑 ERROR BACKEND: {str(e)}")
        return f"🛑 ERROR BACKEND: {str(e)}"
        
    finally:
        if session_externa is None:
            session.close()
        

def obtener_historico_salidas_completo(): # NO ESTÁ EN USO
    """
    [READ] Carga el histórico maestro de movimientos de salida con carga eficiente
    de relaciones para evitar el problema de consultas N+1.
    """
    with Session(engine) as session:
        statement = (
            select(Salidas)
            .options(
                joinedload(Salidas.usuario),
                joinedload(Salidas.detalles).joinedload(DetallesSalida.lote).joinedload(Lotes.insumo)
            )
            .order_by(Salidas.fecha.desc())
        )
        
        # DESDUPLICACIÓN EN MEMORIA: Evita la multiplicación de filas por el JOIN uno-a-muchos
        result = session.exec(statement)
        return result.unique().all()
    

def obtener_salidas_filtradas_paginadas(
    txt_universal: str = "",         # Filtra por Paciente/Destino u Orden
    rango_fechas: list = None,       # Filtra sobre Salidas.fecha
    opt_estado: str = "VALIDO",      # VALIDO / ANULADO / TODOS
    pagina_actual: int = 1,
    registros_por_pagina: int = 50
):
    """
    Busca y pagina las cabeceras de las Actas de Salida usando las variables
    exactas del modelo Salidas (fecha, paciente_destino, orden_salida).
    """
    with Session(engine) as session:
        try:
            statement = select(Salidas)
            condiciones = []

            # FILTRO 1: ESTADO DEL ACTA (Usa el Enum o String)
            if opt_estado != "TODOS":
                # Convertimos a string o dejamos el valor si se pasa directo
                condiciones.append(Salidas.estado == opt_estado)

            # FILTRO 2: BUSCADOR UNIVERSAL (Paciente/Destino u Orden de Salida)
            if txt_universal:
                txt_universal = txt_universal.strip()
                condiciones.append(
                    or_(
                        Salidas.paciente_destino.like(f"%{txt_universal}%"),
                        Salidas.orden_salida.like(f"%{txt_universal}%"),
                        Salidas.razon_salida.like(f"%{txt_universal}%"),
                    )
                )

            # FILTRO 3: RANGO DE FECHAS (Usa 'fecha')
            if rango_fechas and len(rango_fechas) == 2:
                # Convertimos a datetime cubriendo el inicio y fin del día si es necesario
                
                dt_inicio = datetime.combine(rango_fechas[0], time.min)
                dt_fin = datetime.combine(rango_fechas[1], time.max)
                condiciones.append(and_(Salidas.fecha >= dt_inicio, Salidas.fecha <= dt_fin))

            if condiciones:
                statement = statement.where(*condiciones)

            # CONTEO DE COINCIDENCIAS
            stmt_count = select(func.count()).select_from(Salidas)
            if condiciones:
                stmt_count = stmt_count.where(*condiciones)
            total_coincidencias = session.exec(stmt_count).one()

            # PAGINACIÓN CON LIMIT Y OFFSET
            offset_calculado = (pagina_actual - 1) * registros_por_pagina
            statement = statement.order_by(Salidas.id_salida.desc()).limit(registros_por_pagina).offset(offset_calculado)
            statement = statement.options(selectinload(Salidas.usuario))
            
            resultados = session.exec(statement).all()
            return resultados, total_coincidencias

        except Exception as e:
            print(f"🛑 Error crítico en obtener_salidas_cabecera_filtradas_paginadas_backend: {e}")
            return [], 0


def obtener_detalles_insumos_por_acta(id_salida: int):
    """
    Recupera los insumos y lotes específicos que componen una orden de salida determinada.
    """
    with Session(engine) as session:
        try:
            # Forzamos un SELECT plano extrayendo solo las columnas que la grilla necesita
            statement = (
                select(
                    DetallesSalida.id_detalle_salida,
                    DetallesSalida.id_salida,
                    Insumos.nombre,
                    Lotes.codigo_lote,
                    DetallesSalida.cantidad
                )
                .join(Lotes, DetallesSalida.id_lote == Lotes.id_lote)
                .join(Insumos, Lotes.id_insumo == Insumos.id_insumo)
                .where(DetallesSalida.id_salida == int(id_salida)) # Forzamos casteo a entero por seguridad
            )
            
            # Ejecutamos con la sesión nativa para obtener un resultado iterable limpio
            resultados = session.execute(statement).all()
            
            print(f"🔍 BUSCANDO ID {id_salida} -> Filas encontradas en BD: {len(resultados)}")
            return resultados # Retorna una lista de filas con datos planos
            
        except Exception as e:
            print(f"Error crítico en obtener_detalles_insumos_por_acta: {e}")
            return []


def actualizar_registros_salidas_masivo(cambios_cabecera: dict, cambios_detalle: dict, df_maestro, df_detalle):
    """
    Actualiza de forma masiva múltiples actas de entrada en una única transacción atómica.
    Parámetros: cambios_dict : dict
        Un diccionario mapeado donde las llaves son los IDs de las entradas (int) 
        y los valores son diccionarios con los campos modificados (ej. {'cantidad': 50}).

    Retorna: bool
        True si todas las actualizaciones se consolidaron con éxito en SQLite. 
        Realiza un rollback completo y retorna False o un mensaje si ocurre un error.
    """
    with Session(engine) as session:
        try:
            # ==================================================================
            # 1️⃣ FASE MAESTRA: Cambios en la cabecera (Salidas)
            # ==================================================================
            for idx_m_str, modificaciones in cambios_cabecera.items():
                idx_m = int(idx_m_str)
                id_salida_real = int(df_maestro.iloc[idx_m]["ID"])
                
                salida_maestra = session.get(Salidas, id_salida_real)
                if not salida_maestra:
                    continue

                # Edición directa de campos de texto 
                if "ORDEN DE SALIDA" in modificaciones:
                    salida_maestra.orden_salida = (modificaciones["ORDEN DE SALIDA"])
                    resultado= Salidas.validar_datos_salida(valor= modificaciones["ORDEN DE SALIDA"], info='Orden de salida')

                if "DESTINO / PACIENTE" in modificaciones:
                    print('perra', salida_maestra, modificaciones)
                    salida_maestra.paciente_destino = (modificaciones["DESTINO / PACIENTE"])
                    resultado= Salidas.validar_datos_salida(valor= modificaciones["DESTINO / PACIENTE"], info='Destino/Paciente')

                # 🔄 Captura del estado modificado en la grilla maestra
                nuevo_estado_str = modificaciones.get("ESTADO") or modificaciones.get("estado")
                
                # 🎯 EL FILTRO CRÍTICO: Solo evaluamos la lógica si el estado REALMENTE cambió (No es None)
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
            # 2️⃣ FASE DETALLE: Cambios en las cantidades (DetallesSalida)
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
                    resultado= DetallesSalida.validar_cantidad_salida(valor= nueva_cantidad)
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
            return "⚠️ ERROR DE RESTRICCIÓN: La de Orden de Salida ya se encuentra registrado y activo."
        except ValueError as e:
            session.rollback()
            return f"⚠️ REGLA LOGÍSTICA: {str(e)}"
        except Exception as e:
            session.rollback()
            print(f"FALLA EN BASE DE DATOS: {str(e)}")
            return 'la operación falló de manera inesperada'
from sqlmodel import Session, select
from models import Salidas, DetallesSalida, Lotes, engine
from datetime import datetime
from sqlalchemy.exc import IntegrityError

def obtener_lotes_disponibles_fifo(id_insumo: int):
    """
    Busca los lotes de un insumo específico. Filtra por stock y ordena por FIFO 
    utilizando Python en RAM para poder leer la @property 'stock_disponible'.
    """
    with Session(engine) as session:
        # 1. Buscamos TODOS los lotes de ese insumo en la base de datos
        statement = select(Lotes).where(Lotes.id_insumo == id_insumo)
        todos_los_lotes = session.exec(statement).all()
        
        # 2. Evaluamos la @property de Python para dejar solo los que tengan stock real
        lotes_con_existencias = [lote for lote in todos_los_lotes if lote.stock_disponible > 0]
        
        # 3. Ordenamos por fecha de vencimiento ascendente (FIFO)
        lotes_ordenados_fifo = sorted(
            lotes_con_existencias, 
            key=lambda x: x.fecha_vencimiento if x.fecha_vencimiento else datetime.max.date()
        )
        
        return lotes_ordenados_fifo


def registrar_despacho_combinado_fifo(orden_medica: str, paciente: str, id_usuario: int, lista_pedidos: list):
    """
    Recibe una lista de pedidos multi-insumo, aplica FIFO automático a cada uno
    y guarda todo bajo una única transacción segura y atómica.
    """
    if not lista_pedidos:
        return "ERROR: No ha agregado ningún insumo a la orden médica."

    with Session(engine) as session:
        try:
            # 1. Validación preventiva de Orden Médica Única
            orden_limpia = orden_medica.strip().upper()
            existente = session.exec(select(Salidas).where(Salidas.orden_medica == orden_limpia)).first()
            if existente:
                return "ORDEN_DUPLICADA"

            # 2. Crear la cabecera del despacho (Maestro)
            nueva_salida = Salidas(
                id_usuario=id_usuario,
                fecha=datetime.now(),
                orden_medica=orden_limpia,
                paciente=paciente.strip().upper()
            )
            session.add(nueva_salida)
            session.flush() # Genera el id_salida en memoria RAM

            hoja_ruta_final = [] # Lista guía para el operador

            # 3. Procesar cada medicamento del carrito
            for pedido in lista_pedidos:
                id_insumo = pedido["id_insumo"]
                nombre_insumo = pedido["nombre_insumo"]
                cantidad_pendiente = pedido["cantidad"]

                # Reutilizamos la función FIFO segura que declaramos arriba
                lotes_disponibles = obtener_lotes_disponibles_fifo(id_insumo)

                # Validar existencias totales para este medicamento
                stock_total_insumo = sum(l.stock_disponible for l in lotes_disponibles)
                if stock_total_insumo < cantidad_pendiente:
                    session.rollback() # Cancelamos toda la receta si falta stock en un solo renglón
                    return f"ERROR: Stock insuficiente para '{nombre_insumo}'. Solicitado: {cantidad_pendiente} u. Disponible total: {stock_total_insumo} u."

                # Algoritmo de reparto multi-lote FIFO
                for lote_ram in lotes_disponibles:
                    if cantidad_pendiente <= 0:
                        break

                    lote = session.get(Lotes, lote_ram.id_lote) # Sincronizamos con la sesión de la BD

                    if lote.stock_disponible >= cantidad_pendiente:
                        cantidad_a_extraer = cantidad_pendiente
                        cantidad_pendiente = 0
                    else:
                        cantidad_a_extraer = lote.stock_disponible
                        cantidad_pendiente -= lote.stock_disponible

                    # Registrar detalle
                    nuevo_detalle = DetallesSalida(
                        id_salida=nueva_salida.id_salida,
                        id_lote=lote.id_lote,
                        cantidad=cantidad_a_extraer
                    )
                    session.add(nuevo_detalle)

                    # Anexar a la hoja de ruta
                    hoja_ruta_final.append({
                        "MEDICAMENTO": nombre_insumo,
                        "LOTE": lote.codigo_lote,
                        "UBICACIÓN": lote.ubicacion_fisica.upper(),
                        "CANTIDAD A RETIRAR": cantidad_a_extraer
                    })

            session.commit() # Guardado permanente en la base de datos
            return {"status": True, "despacho": hoja_ruta_final}

        except IntegrityError:
            session.rollback()
            return "ORDEN_DUPLICADA"
        except Exception as e:
            session.rollback()
            return f"ERROR OPERATIVO: {str(e)}"
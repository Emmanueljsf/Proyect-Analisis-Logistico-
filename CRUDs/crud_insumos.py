from sqlmodel import Session, select
from sqlalchemy.orm import selectinload, joinedload
from models import engine, Insumos, Usuarios, Lotes, Entradas, DetallesSalida, obtener_sesion_bd
from datetime import date
from typing import List

# ==============================================================================
# 📦 1. PIPELINES DE PERSISTENCIA Y CONSULTA PARA INSUMOS (CATÁLOGO)
# ==============================================================================

def crear_insumo(nombre: str, ved: str) -> Insumos:
    """
    Inserta un nuevo registro de insumo maestro en la base de datos.
    Fuerza la limpieza de espacios en blanco y retorna la instancia con su ID autogenerado.
    """
    with obtener_sesion_bd() as session:
        nuevo = Insumos(nombre=nombre.strip(), clasificacion_ved=ved)
        session.add(nuevo)
        session.commit()
        session.refresh(nuevo) # Sincroniza el objeto local con la clave primaria generada por SQLite
        return nuevo

def obtener_todos_insumos() -> List[Insumos]:
    """
    [CRÍTICO] -> Resuelve el DetachedInstanceError en Streamlit.
    Ejecuta una consulta profunda utilizando 'selectinload'. Carga en un solo viaje 
    los Insumos, sus Lotes adjuntos, y las sub-relaciones de Entradas y Salidas de cada lote.
    Mantiene todos los datos en memoria RAM listos para las propiedades dinámicas de cálculo de stock.
    """
    with obtener_sesion_bd() as session:
        try:
            # Construcción de la consulta con precarga encadenada por subconsultas optimizadas
            statement = (
                select(Insumos).options(
                    selectinload(Insumos.lotes).options(
                        selectinload(Lotes.entrada),          # Requerido para stock_inicial
                        selectinload(Lotes.detalles_salida)   # Requerido para consumos de stock
                    )
                )
            )
            return session.exec(statement).all()
        except Exception as e:
            print(f"🛑 Error crítico en obtener_todos_insumos: {e}")
            return []

def actualizar_insumo(id_insumo: int, nuevo_nombre: str, nuevo_ved: str) -> bool:
    """
    Busca un insumo mediante su ID y actualiza sus atributos básicos.
    Retorna True si la mutación fue exitosa, False si el registro no existía.
    """
    with obtener_sesion_bd() as session:
        db_insumo = session.get(Insumos, id_insumo)
        if not db_insumo:
            return False
        
        db_insumo.nombre = nuevo_nombre.strip()
        db_insumo.clasificacion_ved = nuevo_ved

        session.add(db_insumo)
        session.commit()
        session.refresh(db_insumo)
        return True

def eliminar_insumo(id_insumo: int) -> bool:
    """Elimina físicamente un insumo del catálogo mediante su Clave Primaria."""
    with obtener_sesion_bd() as session:
        insumo = session.get(Insumos, id_insumo)
        if insumo:
            session.delete(insumo)
            session.commit()
            return True
        return False


# ==============================================================================
# 📥 2. CONTROL TRANSACCIONAL DE INVENTARIO (LOTES Y ENTRADAS)
# ==============================================================================

def registrar_ingreso_inventario(id_insumo: int, codigo_lote: str, fecha_vencimiento: date, 
                                 ubicacion_fisica: str, cantidad: int, id_usuario: int, 
                                 fecha_pedido: date) -> bool:
    """
    [ATÓMICO] -> Garantiza la Integridad Referencial de los Almacenes.
    Registra en un solo bloque el Lote físico y asienta su Acta de Entrada.
    Si el lote falla (ej: código duplicado), el rollback automático evita la creación 
    de actas de entradas huérfanas en el sistema.
    """
    with obtener_sesion_bd() as session:
        try:
            # 1. Instanciación e inserción del contenedor físico (Lote)
            nuevo_lote = Lotes(
                id_insumo=id_insumo,
                codigo_lote=codigo_lote.strip().upper(),
                fecha_vencimiento=fecha_vencimiento,
                ubicacion_fisica=ubicacion_fisica.strip()
            )
            session.add(nuevo_lote)
            session.flush() # Comunica con la BD para obtener el id_lote sin cerrar la ventana transaccional
            
            # 2. Vinculación del acta de entrada documental usando la llave foránea obtenida
            nueva_entrada = Entradas(
                id_lote=nuevo_lote.id_lote,
                id_usuario=id_usuario,
                fecha_pedido=fecha_pedido,
                cantidad=cantidad
            )
            session.add(nueva_entrada)
            
            # Consolidación final unificada en disco
            session.commit()
            return True
        except Exception as e:
            session.rollback() # Revierte todos los cambios parciales ante fallos
            print(f"❌ Error crítico en la transacción de ingreso: {e}")
            return False

def obtener_historial_entradas() -> List[Entradas]:
    """
    Recupera el historial de ingresos ordenados de forma cronológica descendente.
    Aplica 'joinedload' para traer de forma inmediata la información del lote y del insumo acoplado.
    """
    with obtener_sesion_bd() as session:
        statement = (
            select(Entradas).options(
                joinedload(Entradas.lote).joinedload(Lotes.insumo)
            ).order_by(Entradas.fecha_recepcion.desc())
        )
        return session.exec(statement).all()

def eliminar_lote_vacio(id_lote: int) -> bool:
    """
    Elimina un lote técnico y su entrada correspondiente SI Y SOLO SI no ha tenido
    ningún movimiento de despacho, blindando la integridad histórica de auditorías.
    """
    with obtener_sesion_bd() as session:
        lote = session.get(Lotes, id_lote)
        if not lote:
            return False
        try:
            if lote.detalles_salida:
                return False # Bloqueo logístico: No se pueden borrar lotes con salidas registradas
            
            if lote.entrada:
                session.delete(lote.entrada) # Remueve primero el documento de entrada asociado
            session.delete(lote)             # Remueve el contenedor del lote
            session.commit()
            return True
        except Exception as e:
            print(f"❌ Error al intentar eliminar el lote: {e}")
            return False
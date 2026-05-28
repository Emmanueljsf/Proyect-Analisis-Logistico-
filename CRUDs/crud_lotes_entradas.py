from sqlmodel import Session, select  # Operaciones de consulta
from models import Entradas, Lotes, Insumos, Usuarios, engine  # Modelos de datos del SIAL-MED
from datetime import date  # Manejo de fechas para vencimientos
from sqlalchemy.orm import joinedload, make_transient
from sqlalchemy.exc import IntegrityError  # 💡 Importación clave para detectar duplicados
from typing import List  # Tipado de listas

def obtener_todos_insumos() -> List[Insumos]:
    """[READ] Retorna el catálogo completo de insumos médicos."""
    with Session(engine) as session:
        return session.exec(select(Insumos)).all()  # Consulta simple a la base de datos

def registrar_ingreso_inventario(id_insumo, codigo_lote, fecha_vencimiento, ubicacion_fisica, cantidad, id_usuario, fecha_pedido):
    """
    Registra el lote acoplándolo rigurosamente al insumo base 
    y asienta el acta de entrada en una misma transacción.
    """
    with Session(engine) as session:
        try:
            # 1. Crear y registrar el lote técnico asegurando su id_insumo
            nuevo_lote = Lotes(
                id_insumo=id_insumo,
                codigo_lote=codigo_lote,
                fecha_vencimiento=fecha_vencimiento,
                ubicacion_fisica=ubicacion_fisica,
                stock_inicial=cantidad # Asegúrate de que mapee al atributo que suma tu modelo
            )
            session.add(nuevo_lote)
            session.flush() # Sincroniza para obtener el nuevo nuevo_lote.id_lote
            
            # 2. Crear el acta de entrada asociada al lote generado
            nueva_entrada = Entradas(
                id_lote=nuevo_lote.id_lote,
                id_usuario=id_usuario,
                fecha_pedido=fecha_pedido,
                cantidad=cantidad
            )
            session.add(nueva_entrada)
            
            # 3. Consolidar la transacción y limpiar sesión
            session.commit()
            return True
        except Exception as e:
            session.rollback()
            return False

def obtener_historial_entradas():
    """
    Versión blindada definitiva para Python 3.8 y SQLModel antiguo.
    Retorna tuplas explícitas con todas las relaciones cargadas en caliente antes de cerrar la sesión.
    """
    with Session(engine) as session:
        # Añadimos Usuarios al select y hacemos el join correspondiente usando la llave foránea
        statement = (
            select(Entradas, Lotes, Insumos, Usuarios)
            .join(Lotes, Entradas.id_lote == Lotes.id_lote)
            .join(Insumos, Lotes.id_insumo == Insumos.id_insumo)
            .join(Usuarios, Entradas.id_usuario == Usuarios.id_usuario)  # 👈 Join directo con el operador/militar
            .order_by(Entradas.fecha_recepcion.desc())
        )
        # Retorna una lista de tuplas con la forma: [(entrada, lote, insumo, usuario), ...]
        return session.exec(statement).all()
    

def actualizar_registros_entradas_masivo(cambios_dict: dict):
    """
    Procesa un diccionario de cambios proveniente de st.data_editor.
    Modifica las propiedades de la Entrada y sincroniza el Lote correspondiente.
    """
    with Session(engine) as session:
        for id_entrada_str, modificaciones in cambios_dict.items():
            id_entrada = int(id_entrada_str)
            # 1. Buscamos la entrada original
            entrada = session.get(Entradas, id_entrada)
            if entrada:
                # Actualizamos los campos de la entrada modificados por el usuario
                if "CANTIDAD" in modificaciones:
                    entrada.cantidad = int(modificaciones["CANTIDAD"])
                if "FECHA PEDIDO" in modificaciones:
                    entrada.fecha_pedido = modificaciones["FECHA PEDIDO"]
                
                # 2. Buscamos su lote asociado para mantener la integridad referencial
                lote = session.get(Lotes, entrada.id_lote)
                if lote and "CÓD. LOTE" in modificaciones:
                    lote.codigo_lote = str(modificaciones["CÓD. LOTE"]).strip().upper()
                
                session.add(entrada)
                if lote:
                    session.add(lote)
        session.commit()
    return True

def eliminar_registro_entrada(id_entrada: int):
    """
    Elimina un acta de entrada de la base de datos y su lote asociado.
    """
    with Session(engine) as session:
        entrada = session.get(Entradas, id_entrada)
        if entrada:
            # Buscamos el lote para no dejar un lote huérfano sin registro de entrada
            lote = session.get(Lotes, entrada.id_lote)
            if lote:
                session.delete(lote)
            session.delete(entrada)
            session.commit()
            return True
    return False



def obtener_todos_lotes_con_relaciones():
    """
    Trae los lotes acoplados a sus insumos y entradas en un solo viaje.
    Asigna las relaciones en caliente para evitar el error DetachedInstanceError
    cuando las propiedades dinámicas del modelo intenten acceder a ellas en Streamlit.
    """
    with Session(engine) as session:
        statement = (
            select(Lotes, Insumos, Entradas)
            .join(Insumos, Lotes.id_insumo == Insumos.id_insumo)
            .join(Entradas, Lotes.id_lote == Entradas.id_lote)
            .order_by(Lotes.fecha_vencimiento.asc())
        )
        resultados = session.exec(statement).all()
        
        lista_blindada = []
        
        for lote_obj, insumo_obj, entrada_obj in resultados:
            # 💡 EL TRUCO MAGISTRAL:
            # Asignamos la entrada directamente al atributo del objeto lote en RAM.
            # Como la sesión sigue abierta dentro de este bucle, SQLAlchemy lo permite sin chistar.
            lote_obj.entrada = entrada_obj
            
            # (Opcional) Si en tu @property de stock_disponible también usas "detalles_salida", 
            # forzamos su carga aquí de la misma manera para blindarlo al 100%:
            if hasattr(lote_obj, "detalles_salida"):
                _ = lote_obj.detalles_salida  # Esto fuerza la lectura en RAM antes de cerrar la sesión
            
            # Guardamos la tupla ya asociada
            lista_blindada.append((lote_obj, insumo_obj, entrada_obj))
            
        return lista_blindada

def actualizar_registros_lotes_masivo(cambios_dict: dict):
    """
    Procesa las modificaciones enviadas desde st.data_editor para la tabla Lotes.
    Retorna True si todo fue exitoso, o una cadena de texto con el error si falla.
    """
    with Session(engine) as session:
        try:
            for id_lote_str, modificaciones in cambios_dict.items():
                id_lote = int(id_lote_str)
                lote = session.get(Lotes, id_lote)
                
                if lote:
                    if "CÓD. LOTE" in modificaciones:
                        lote.codigo_lote = str(modificaciones["CÓD. LOTE"]).strip().upper()
                    if "UBICACIÓN" in modificaciones:
                        lote.ubicacion_fisica = str(modificaciones["UBICACIÓN"]).strip().upper()
                    if "F. VENCIMIENTO" in modificaciones:
                        lote.fecha_vencimiento = modificaciones["F. VENCIMIENTO"]
                    
                    session.add(lote)
            session.commit()
            return True
        except IntegrityError:
            session.rollback()  # Cancela los cambios para no corromper la BD
            return "DUPLICADO"  # Identificador para nuestra interfaz
        except Exception as e:
            session.rollback()
            return f"ERROR: {str(e)}"
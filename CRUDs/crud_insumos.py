import uuid
import logging
import re
from seguridad import sanitizar_input, usuario_tiene_permiso_escritura
from sqlmodel import Session, select
from sqlalchemy.orm import selectinload, joinedload
from models import engine, Insumos, Usuarios, Lotes, Entradas, Salidas, DetallesSalida, Estado, Rol, obtener_sesion_bd
from datetime import date
from typing import List
import math



def crear_insumo(nombre: str, ved: str) -> Insumos:
    """
    Inserta un nuevo registro de insumo en la base de datos.
    Fuerza la limpieza de espacios en blanco y retorna la instancia con su ID autogenerado.
    """
    if not usuario_tiene_permiso_escritura(): return None
    try:
        with obtener_sesion_bd() as session:
            # Sanitización de datos de entrada
            nuevo = Insumos(nombre=sanitizar_input(nombre), clasificacion_ved=ved)
            session.add(nuevo)
            session.commit()
            session.refresh(nuevo) # Sincroniza el objeto local con la clave primaria generada por SQLite
            return nuevo
    except Exception as e:
            # Blindaje: logueo interno y error genérico
            c_id = str(uuid.uuid4())
            logging.error(f"UUID: {c_id} | Error: {e}")
            return None


def obtener_insumos(solo_activos: bool = False, txt_buscar: str = "", opt_estado: str = "ACTIVOS"):
    """
    Consulta y filtra el catálogo de insumos de la base de datos utilizando carga selectiva (selectinload).
    Permite la búsqueda por coincidencia de texto (nombre o clasificación VED) y discriminación por estado.

    Parámetros:
        solo_activos (bool): Si es True, filtra únicamente insumos con estado activo.
        txt_buscar (str): Cadena de texto para buscar por nombre o clasificación VED.
        opt_estado (str): Filtro administrativo ("ACTIVOS", "INACTIVOS", "TODOS").

    Retorna:
        list: Lista de objetos 'Insumos' encontrados, o una lista vacía si ocurre un error o no hay resultados.
    """
    with Session(engine) as session:
        try:
            condiciones = []
            
            # Filtro de Estado administrativo
            if solo_activos:
                condiciones.append(Insumos.activo == True)
            else:
                if opt_estado == "ACTIVOS":
                    condiciones.append(Insumos.activo == True)
                elif opt_estado == "INACTIVOS":
                    condiciones.append(Insumos.activo == False)

            # Buscador básico por texto/VED en Base de Datos
            if txt_buscar:
                busqueda = txt_buscar.strip().upper()
                letra_ved = {"VITAL": "V", "ESENCIAL": "E", "DESEABLE": "D"}.get(busqueda)
                if letra_ved:
                    condiciones.append(Insumos.clasificacion_ved == letra_ved)
                else:
                    condiciones.append(Insumos.nombre.like(f"%{txt_buscar}%"))

            # Consulta maestra con precarga profunda
            statement = select(Insumos).where(*condiciones).options(
                selectinload(Insumos.lotes).options(
                    selectinload(Lotes.entrada),
                    selectinload(Lotes.detalles_salida).selectinload(DetallesSalida.salida)
                )
            )
            
            return session.exec(statement).all()
            
        except Exception as e:
            # Trazabilidad Avanzada: Log estructurado JSON para auditoría técnica
            correlation_id = str(uuid.uuid4())
            logging.error(f'{{"correlation_id": "{correlation_id}", "error": "{str(e)}", "modulo": "crud_entradas_paginadas"}}')
            
            # Retorno seguro: Se devuelve una lista vacía y 0 registros para mantener la estabilidad del sistema
            return [], 0
        

def actualizar_catalogo_insumos_masivo(cambios_dict: dict) -> bool:
    """
    Actualiza de forma masiva o parcial los atributos de un insumo existente.
    Aplica validaciones de obligatoriedad antes de consolidar los cambios en SQLite.

    Parámetros: campos : dict
        Un diccionario estructurado donde las llaves son los IDs de los insumos (int) 
        y los valores son diccionarios con los campos que se van a modificar 
        (ej. {2: {"NOMBRE DEL INSUMO": "NUEVO NOMBRE", "CLASIFICACIÓN VED": "V"}}).

    Retorna: bool o str
        Retorna True si la transacción se consolidó exitosamente. 
        En caso de violar reglas lógicas o fallas de BD, ejecuta un rollback y retorna un str con el error.
    """
    if not usuario_tiene_permiso_escritura():
        return "✖️ ACCESO DENEGADO: Permisos insuficientes."

    with Session(engine) as session:
        try:
            for id_ins_str, campos in cambios_dict.items():
                # Busca el insumo en la BD usando su ID
                insumo_bd = session.get(Insumos, int(id_ins_str))
                
                if insumo_bd:
                    # Si la celda "ESTADO" fue editada en la grilla
                    if "ESTADO" in campos:
                        nuevo_estado = (campos["ESTADO"].upper() == "ACTIVO") # True si es ACTIVO, False si es INACTIVO
                        insumo_bd.activo = nuevo_estado
                        # SI EL INSUMO TIENE LOTES ACTIVOS, MANDA MENSAJE DE ERROR
                        for lote in insumo_bd.lotes:
                            if not nuevo_estado and lote.activo:
                                raise ValueError("No se puede desactivar el insumo con lotes activos.")
                            
                    if "NOMBRE DEL INSUMO" in campos:
                        # Sanitización aplicada a la edición
                        insumo_bd.nombre = sanitizar_input(campos["NOMBRE DEL INSUMO"])
                        if not insumo_bd.nombre:
                            raise ValueError("El nombre es obligatorio.")

                    if "CLASIFICACIÓN VED" in campos:
                        insumo_bd.clasificacion_ved = campos["CLASIFICACIÓN VED"][0]
                    
                    session.add(insumo_bd) # Registra el insumo modificado en la sesión
                    
            session.commit() # Guarda los cambios de insumos en un solo viaje
            return True
        
        except ValueError as e:
            session.rollback()
            return f"✖️ REGLA LOGÍSTICA: {str(e)}"
        except Exception as e:
            # Generación de UUID para trazabilidad sin exponer código
            c_id = str(uuid.uuid4())
            logging.error(f"UUID: {c_id} | Error: {e}")
            session.rollback()
            return f"Ocurrió un error inesperado. Reporte el código: {c_id}"
    
    







"""
AVANCE 6:
Barreras de permiso: Verificación mediante usuario_tiene_permiso_escritura().  
Sanitización: Uso de sanitizar_input() para limpiar entradas.  
Gestión segura de errores: Uso de uuid y logging para evitar exponer detalles técnicos al usuario final. 
"""

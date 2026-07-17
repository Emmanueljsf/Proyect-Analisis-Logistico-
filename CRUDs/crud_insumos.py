from sqlmodel import Session, select
from sqlalchemy.orm import selectinload, joinedload
from bd.models import engine, Insumos, Usuarios, Lotes, Entradas, Salidas, DetallesSalida, Estado, obtener_sesion_bd
from datetime import date
from typing import List
import math

# ==============================================================================
# 📦 1. PIPELINES DE PERSISTENCIA Y CONSULTA PARA INSUMOS (CATÁLOGO)
# ==============================================================================

def crear_insumo(nombre: str, ved: str) -> Insumos:
    """
    Inserta un nuevo registro de insumo en la base de datos.
    Fuerza la limpieza de espacios en blanco y retorna la instancia con su ID autogenerado.
    """
    try:
        with obtener_sesion_bd() as session:
            nuevo = Insumos(nombre=nombre.strip(), clasificacion_ved=ved)
            session.add(nuevo)
            session.commit()
            session.refresh(nuevo) # Sincroniza el objeto local con la clave primaria generada por SQLite
            return nuevo
    except Exception as e:
            print(f"Error crítico en crear_insumos: {e}")


def obtener_insumos(
    solo_activos: bool= False, txt_buscar: str= "", opt_estado: str= "ACTIVOS"):
    """
    Consulta y filtra el catálogo de insumos de la base de datos.
    Permite la búsqueda por coincidencia de texto y discriminación por estado administrativo.
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

            # Consulta maestra con tu precarga profunda original
            statement = select(Insumos).where(*condiciones).options(
                selectinload(Insumos.lotes).options(
                    selectinload(Lotes.entrada),
                    selectinload(Lotes.detalles_salida).selectinload(DetallesSalida.salida)
                )
            )
            
            # Retorna absolutamente TODOS los registros coincidentes de golpe
            return session.exec(statement).all()
            
        except Exception as e:
            print(f"🛑 Error crítico en obtener_insumos: {e}")
            return []
        

        

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
    with Session(engine) as session:
        try:
            for id_ins_str, campos in cambios_dict.items():
                # Busca el insumo en la BD usando su ID
                insumo_bd = session.get(Insumos, int(id_ins_str))
                
                if insumo_bd:
                    # Si la celda "ESTADO" fue editada en la grilla
                    if "ESTADO" in campos:
                        nuevo_estado= (campos["ESTADO"].upper() == "ACTIVO")  # True si es ACTIVO, False si es INACTIVO
                        insumo_bd.activo= nuevo_estado  # Actualiza el estado del insumo
                        
                        # SI EL INSUMO TIENE LOTES ACTIVOS, MANDA MENSAJE DE ERROR
                        for lote in insumo_bd.lotes:
                            if nuevo_estado==False and lote.activo==True:
                                raise ValueError("No se puede desactivar el insumo porque tiene lotes asociados")
                            
                    # Edición de nombre 
                    if "NOMBRE DEL INSUMO" in campos:
                        insumo_bd.nombre = str(campos["NOMBRE DEL INSUMO"]).strip().upper()
                        if insumo_bd.nombre==None or insumo_bd.nombre=='':
                            raise ValueError("​ El nombre de los insumos es un dato obligatorio ")

                    # Edición de clasificación VED 
                    if "CLASIFICACIÓN VED" in campos:
                        insumo_bd.clasificacion_ved = campos["CLASIFICACIÓN VED"][0]
                        if insumo_bd.nombre==None or insumo_bd.nombre=='':
                            raise ValueError("​ La clasificación VED es obligatoria ")
                    
                    session.add(insumo_bd)  # Registra el insumo modificado en la sesión
                    
            session.commit()  # 💾 Guarda los cambios de insumos en un solo viaje
            return True
        
        except ValueError as e:
            session.rollback()
            return f"✖️ REGLA LOGÍSTICA: {str(e)}"
        except Exception as e:
            session.rollback()
            return f"✖️ FALLA CRÍTICA EN BASE DE DATOS: {str(e)}"


# NO ESTÁ EN USO ESTA FUNCIÓN
def eliminar_insumo(id_insumo: int) -> bool:
    """Elimina físicamente un insumo del catálogo mediante su Clave Primaria."""
    with obtener_sesion_bd() as session:
        insumo = session.get(Insumos, id_insumo)
        if insumo:
            session.delete(insumo)
            session.commit()
            return True
        return False



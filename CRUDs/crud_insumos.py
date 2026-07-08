from sqlmodel import Session, select
from sqlalchemy.orm import selectinload, joinedload
from models import engine, Insumos, Usuarios, Lotes, Entradas, Salidas, DetallesSalida, Estado, obtener_sesion_bd
from datetime import date
from typing import List
import math

# ==============================================================================
# 📦 1. PIPELINES DE PERSISTENCIA Y CONSULTA PARA INSUMOS (CATÁLOGO)
# ==============================================================================

def crear_insumo(nombre: str, ved: str) -> Insumos:
    """
    Inserta un nuevo registro de insumo maestro en la base de datos.
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
            print(f"🛑 Error crítico en crear_insumos: {e}")


def obtener_insumos(
    solo_activos: bool= False,                
    txt_buscar: str= "",                       # Entrada de la barra única (Nombre/VED)
    opt_estado: str= "ACTIVOS",                # Selector administrativo del catálogo
):
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
        


def obtener_insumos_con_paginacion(  # FUNCION DESCARTADA
    solo_activos: bool= False,                
    txt_buscar: str= "",                       # Entrada de la barra única (Nombre/VED)
    txt_rango_stock: str= "",                  # Rango numérico de existencias
    opt_estado: str= "ACTIVOS",                # Selector administrativo del catálogo
    pagina_actual: int= 1,                     # Control de posición para la grilla
    registros_por_pagina: int=50              # Tamaño del fragmento visual
):
    with Session(engine) as session:
        try:
            condiciones = []         # Lista para acumular los filtros WHERE 
            
            # 1. FILTRO DE ESTADO ADMINISTRATIVO
            if solo_activos:
                condiciones.append(Insumos.activo == True)
            else:
                if opt_estado == "ACTIVOS":
                    condiciones.append(Insumos.activo == True)
                elif opt_estado == "INACTIVOS":
                    condiciones.append(Insumos.activo == False)

            # 2. BUSCADOR UNIVERSAL (Nombre comercial o Clasificación VED traducida)
            if txt_buscar:
                busqueda = txt_buscar.strip().upper()
                letra_ved = {"VITAL": "V", "ESENCIAL": "E", "DESEABLE": "D"}.get(busqueda)
                
                if letra_ved:
                    condiciones.append(Insumos.clasificacion_ved == letra_ved) # Busca letra exacta #
                else:
                    condiciones.append(Insumos.nombre.like(f"%{txt_buscar}%")) # Coincidencia parcial #

            # 3. CONSTRUCCIÓN DEL STATEMENT BASE CON TU FILTRADO ORIGINAL EN CASCADA
            statement = select(Insumos).where(*condiciones).options(
                selectinload(Insumos.lotes).options(
                    selectinload(Lotes.entrada),
                    selectinload(Lotes.detalles_salida).selectinload(DetallesSalida.salida)
                )
            )

            # 🎯 CASO A: SI EL USUARIO FILTRA POR STOCK (Segmentamos en RAM)
            if txt_rango_stock:
                todos_coincidentes = session.exec(statement).all() # Trae los filtrados con sus relaciones #
                
                try:
                    if "-" in txt_rango_stock:
                        partes = txt_rango_stock.split("-")
                        val_min = int(partes[0].strip()) if partes[0].strip() else 0
                        val_max = int(partes[1].strip()) if partes[1].strip() else 999999
                    else:
                        val_min = int(txt_rango_stock)
                        val_max = 999999
                    
                    # Filtramos usando @property total_stock que ya lee la RAM perfectamente 
                    filtrados_por_stock = [ins for ins in todos_coincidentes if val_min <= ins.total_stock <= val_max]
                except ValueError:
                    filtrados_por_stock = todos_coincidentes
                
                total_registros = len(filtrados_por_stock)
                total_paginas = math.ceil(total_registros / registros_por_pagina)
                
                inicio = (pagina_actual - 1) * registros_por_pagina
                fin = inicio + registros_por_pagina
                resultados_paginados = filtrados_por_stock[inicio:fin]

            # 🎯 CASO B: FLUJO GENERAL / SIN FILTRO DE STOCK (Paginación pura en BD)
            else:
                # Contamos de forma ligera los registros totales que cumplen texto/estado 
                count_stmt = select(Insumos).where(*condiciones)
                total_registros = len(session.exec(count_stmt).all())
                total_paginas = math.ceil(total_registros / registros_por_pagina)
                
                # Aplicamos LIMIT y OFFSET manteniendo la precarga para los 50 registros de la página 
                offset_val = (pagina_actual - 1) * registros_por_pagina
                statement = statement.limit(registros_por_pagina).offset(offset_val)
                
                resultados_paginados = session.exec(statement).all()

            # Retornamos la tupla con los datos y el conteo de páginas 
            return resultados_paginados, total_paginas
            
        except Exception as e:
            print(f"🛑 Error crítico en obtener_todos_insumos: {e}")
            return [], 1
        

def actualizar_catalogo_insumos_masivo(cambios_dict: dict) -> bool:
    """Procesa modificaciones y bajas lógicas en cascada desde la grilla."""
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



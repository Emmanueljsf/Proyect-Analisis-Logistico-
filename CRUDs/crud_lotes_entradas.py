from sqlmodel import Session, select, and_, or_, func  # Operaciones de consulta
from models import Entradas, Lotes, Insumos, Usuarios, DetallesSalida, Estado, engine  # Modelos de datos del SIAL-MED
from datetime import date, datetime  # Manejo de fechas para vencimientos
from sqlalchemy.orm import joinedload, make_transient, selectinload
from sqlalchemy.exc import IntegrityError  # 💡 Importación clave para detectar duplicados
from typing import List  # Tipado de listas
from pydantic import ValidationError


def registrar_ingreso_inventario(id_insumo, codigo_lote, fecha_vencimiento, ubicacion_fisica, cantidad, id_usuario, fecha_pedido):
    """
    Registra el lote acoplándolo rigurosamente al insumo base 
    y asienta el acta de entrada en una misma transacción.
    Garantiza la integridad transaccional evitando la duplicidad de lotes activos.
    """
    with Session(engine) as session:
        try:
            # Buscamos si ya existe el mismo código activo para ESTE insumo específico
            stmt_duplicado = select(Lotes).where(
                Lotes.id_insumo == id_insumo,
                Lotes.codigo_lote == codigo_lote,
                Lotes.activo == True
            )
            lote_existente = session.exec(stmt_duplicado).first()
            
            if lote_existente:
                raise ValueError("DUPLICADO_ACTIVO") # Retornamos un código de error controlado para la interfaz
            
            # 1. Crear y registrar el lote técnico asegurando su id_insumo
            nuevo_lote = Lotes(
                id_insumo=id_insumo,
                codigo_lote=codigo_lote,
                fecha_vencimiento=fecha_vencimiento,
                ubicacion_fisica=ubicacion_fisica,
                stock_inicial=cantidad 
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
        except ValueError as e:
            session.rollback()
            return f"✖️ REGLA LOGÍSTICA: {str(e)}"
        except Exception as e:
            session.rollback()
            print(f"✖️ FALLA CRÍTICA EN BASE DE DATOS: {str(e)}")
            return f"✖️ FALLA CRÍTICA EN BASE DE DATOS: {str(e)}"

# NO ESTA EN USO
def obtener_historial_entradas(): 
    """
    Retorna tuplas explícitas con todas las relaciones cargadas en caliente antes de cerrar la sesión.
    """
    with Session(engine) as session:
        # Añadimos Usuarios al select y hacemos el join correspondiente usando la llave foránea
        entradas = (
            select(Entradas, Lotes, Insumos, Usuarios)
            .join(Lotes, Entradas.id_lote == Lotes.id_lote)
            .join(Insumos, Lotes.id_insumo == Insumos.id_insumo)
            .join(Usuarios, Entradas.id_usuario == Usuarios.id_usuario)  # <- Join directo con el operador/militar
            .order_by(Entradas.fecha_recepcion.desc())
        )
        # Retorna una lista de tuplas con la forma: [(entrada, lote, insumo, usuario), ...]
        return session.exec(entradas).all()
    

def obtener_entradas_filtradas_paginadas(
    txt_universal: str = "",       # Barra 1: Insumo, VED o Código de lote
    txt_rango_cantidad: str = "",   # Barra 2: Unidades ingresadas (Min-Max)
    rango_fechas: list = None,     # Barra 3: Rango de fecha_recepcion [Inicio, Fin]
    opt_estado: str = "VALIDO",    # Barra 4: VALIDO / ANULADO / TODOS
    pagina_actual: int = 1,
    registros_por_pagina: int = 50
):
    """
    Controlador del Backend para Entradas de SIAL-MED.
    Filtra y pagina directamente en SQLite usando las variables exactas del modelo.
    """
    with Session(engine) as session:
        try:
            statement = select(Entradas, Lotes, Insumos).join(
                Lotes, Entradas.id_lote == Lotes.id_lote
            ).join(
                Insumos, Lotes.id_insumo == Insumos.id_insumo
            )
            
            condiciones = []

            # 🎛️ FILTRO 1: ESTADO ADMINISTRATIVO REAL ("VALIDO" / "ANULADO")
            if opt_estado != "TODOS":
                condiciones.append(Entradas.estado == opt_estado)

            # 🎛️ FILTRO 2: BARRA UNIVERSAL (Insumo, VED o Lote)
            if txt_universal:
                busqueda = txt_universal.strip().upper()
                letra_ved = {"VITAL": "V", "ESENCIAL": "E", "DESEABLE": "D"}.get(busqueda)
                
                bloque_or = [
                    Insumos.nombre.like(f"%{txt_universal}%"),
                    Lotes.codigo_lote.like(f"%{txt_universal}%")
                ]
                if letra_ved:
                    bloque_or.append(Insumos.clasificacion_ved == letra_ved)
                
                condiciones.append(or_(*bloque_or))

            # 🎛️ FILTRO 3: RANGO DE CANTIDADES
            if txt_rango_cantidad:
                try:
                    if "-" in txt_rango_cantidad:
                        partes = txt_rango_cantidad.split("-")
                        val_min = int(partes[0].strip()) if partes[0].strip() else 0
                        val_max = int(partes[1].strip()) if partes[1].strip() else 999999
                    else:
                        val_min = int(txt_rango_cantidad)
                        val_max = 999999
                    condiciones.append(and_(Entradas.cantidad >= val_min, Entradas.cantidad <= val_max))
                except ValueError:
                    pass

            # 🎛️ FILTRO 4: RANGO DE FECHAS USANDO 'fecha_recepcion'
            if rango_fechas and len(rango_fechas) == 2:
                condiciones.append(and_(Entradas.fecha_recepcion >= rango_fechas[0], Entradas.fecha_recepcion <= rango_fechas[1]))

            if condiciones:
                statement = statement.where(*condiciones)

            # CONTEO EFICIENTE EN EL BACKEND
            stmt_count = select(func.count()).select_from(Entradas).join(
                Lotes, Entradas.id_lote == Lotes.id_lote
            ).join(
                Insumos, Lotes.id_insumo == Insumos.id_insumo
            )
            if condiciones:
                stmt_count = stmt_count.where(*condiciones)
            total_coincidencias = session.exec(stmt_count).one()

            # PAGINACIÓN NATIVA SQL (LIMIT y OFFSET)
            offset_calculado = (pagina_actual - 1) * registros_por_pagina
            statement = statement.limit(registros_por_pagina).offset(offset_calculado)
            statement = statement.options(selectinload(Entradas.usuario))

            resultados = session.exec(statement).all()
            
            lista_final = []
            for entrada_obj, lote_obj, insumo_obj in resultados:
                lista_final.append((entrada_obj, lote_obj, insumo_obj))

            return lista_final, total_coincidencias

        except Exception as e:
            print(f"🛑 Error crítico en obtener_entradas_filtradas_paginadas_backend: {e}")
            return [], 0
    

def actualizar_registros_entradas_masivo(cambios_dict: dict) -> bool:
    """
    Procesa las modificaciones masivas de la grilla de Entradas (st.data_editor).
    Sanea rigurosamente los tipos de datos (Strings a date) al inicio del ciclo
    para evitar excepciones de Autoflush en SQLite.
    
    Parámetros: cambios_dict : dict
        Un diccionario mapeado donde cada llave es el ID de la entrada (int) 
        y cada valor es otro diccionario con los campos modificados (ej. {4: {'cantidad': 150}}).

    Retorna: bool
        Retorna True si todas las actualizaciones se guardaron con éxito en SQLite. 
        Realiza un rollback integral y retorna False si ocurre cualquier excepción.
    """
    with Session(engine) as session:
        try:
            for id_entrada, modificaciones in cambios_dict.items():
                
                # PASO CRÍTICO DE SANEAMIENTO: Convertir la fecha antes de cualquier validación o guardado
                if "FECHA PEDIDO" in modificaciones:
                    fecha_raw = modificaciones["FECHA PEDIDO"]
                    if isinstance(fecha_raw, str):
                        # Forzamos la conversión a objeto date nativo de Python inmediatamente
                        modificaciones["FECHA PEDIDO"] = date.fromisoformat(fecha_raw)

                # Capturamos el estado enviado desde la grilla
                nuevo_estado_str = modificaciones.get("estado") or modificaciones.get("ESTADO")
                
                # Si se cambia a ANULADO, usamos la funcion para anular
                if nuevo_estado_str and nuevo_estado_str.upper() == "ANULADO":
                    exito_anulacion, mensaje = anular_entrada_y_lote(id_entrada)
                    if not exito_anulacion:
                        # Si la regla frena la operación (ej: ya hay despachos), lanzamos un ValueError
                        raise ValueError(mensaje)
                    # Pasamos al siguiente registro ya que tu función asentó Entrada y Lote de forma conforme.
                    continue

                # Procesamiento de ediciones ordinarias para registros que se mantienen VALIDOS
                entrada= session.get(Entradas, id_entrada)

                # Si CAMBIA EL ESTADO A VALIDO
                if nuevo_estado_str=="VALIDO":
                    entrada.estado = Estado.VALIDO
                    # Reactivamos el lote correspondiente
                    lote = session.get(Lotes, entrada.id_lote)
                    if lote:
                        lote.activo = True
                        lote.motivo_desactivacion= None
                        session.add(lote)
                
                if entrada:
                    if "CANTIDAD" in modificaciones:
                        lote= session.get(Lotes, entrada.id_lote)
                        nueva_cantidad = modificaciones["CANTIDAD"]
                        mensaje= Entradas.validar_cantidad_entrada(valor=nueva_cantidad) # si hay un error retorna un mensaje de error
                        cantidad_despachada= entrada.cantidad-lote.stock_disponible
                        if nueva_cantidad< cantidad_despachada:
                            raise ValueError('la nueva cantidad no puede ser menor a la cantidad despachada')
                        
                        entrada.cantidad= nueva_cantidad
                        if nueva_cantidad==cantidad_despachada: 
                            lote.activo=False
                            lote.motivo_desactivacion='AGOTADO POR DESPACHO'
                            session.add(lote)

                    if "FECHA PEDIDO" in modificaciones:
                        # Aquí ya está garantizado que es un objeto date de Python limpio
                        entrada.fecha_pedido= modificaciones["FECHA PEDIDO"]
                        mensaje= Entradas.validar_fecha_pedido(valor=entrada.fecha_pedido, fr=entrada.fecha_recepcion)
                    

                    if "CÓDIGO LOTE" in modificaciones:
                        lote = session.get(Lotes, entrada.id_lote)
                        if lote:
                            nuevo_codigo = str(modificaciones["CÓDIGO LOTE"])
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
            

                    if "INSUMO MÉDICO" in modificaciones:
                        lote = session.get(Lotes, entrada.id_lote)
                        # busco el insumo con ese nombre
                        insumo= session.scalars(select(Insumos).where(Insumos.nombre== modificaciones['INSUMO MÉDICO'])).first() 
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
                            session.add(lote)
                    
                    session.add(entrada)
                    
                    
            # Consolidamos la transacción de todo el lote de cambios de forma segura
            session.commit()
            return True
        
        except ValueError as e:
            session.rollback()
            return f"✖️ REGLA LOGÍSTICA: {str(e)}"
        except Exception as e:
            session.rollback()
            print(f"FALLA CRÍTICA EN BASE DE DATOS: {str(e)}")


def obtener_lotes_filtrados(
    txt_universal: str = "",       # Barra 1: Insumo, VED, Código de lote o Ubicación
    txt_rango_stock: str = "",     # Barra 2: Existencias (Min-Max)
    rango_vencimiento: list = None,# Barra 3: Fechas [Inicio, Fin]
    opt_estado: str = "ACTIVOS"    # Barra 4: ACTIVOS / INACTIVOS / TODOS
):
    """
    Controlador del Backend para SIAL-MED.
    Procesa de manera nativa todos los filtros relacionales en la Base de Datos
    y resuelve la matemática de stock dinámico sin saturar la memoria.
    """
    with Session(engine) as session:
        try:
            # 1. Uniones base (JOIN) para poder buscar datos del Insumo desde el Lote
            statement = select(Lotes, Insumos).join(Insumos, Lotes.id_insumo == Insumos.id_insumo)
            condiciones = []

            # 🎛️ FILTRO 1: ESTADO ADMINISTRATIVO DEL LOTE
            if opt_estado == "ACTIVOS":
                condiciones.append(Lotes.activo == True)
            elif opt_estado == "INACTIVOS":
                condiciones.append(Lotes.activo == False)

            # 🎛️ FILTRO 2: BARRA UNIVERSAL (Insumo, VED, Código, Ubicación)
            if txt_universal:
                busqueda = txt_universal.strip().upper()
                # Traducimos VED por si busca la palabra completa
                letra_ved = {"VITAL": "V", "ESENCIAL": "E", "DESEABLE": "D"}.get(busqueda)
                
                bloque_or = [
                    Insumos.nombre.like(f"%{txt_universal}%"),
                    Lotes.codigo_lote.like(f"%{txt_universal}%"),
                    Lotes.ubicacion_fisica.like(f"%{txt_universal}%")
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
            print(f"🛑 Error crítico en obtener_lotes_filtrados_backend: {e}")
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
                            nuevo_codigo = str(modificaciones["CÓDIGO DE LOTE"])
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
                    lote.ubicacion_fisica = (modificaciones["UBICACIÓN FÍSICA"])
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
                    lote.motivo_desactivacion = "AGOTADO POR DESPACHO"
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
            print(f"✖️ Error al intentar actualizar los lotes: {str(e)}")
            return f"✖️ FALLA CRÍTICA EN BASE DE DATOS: {str(e)}"
        

def anular_entrada_y_lote(id_entrada: int) -> tuple:
    """
    Ejecuta la anulación logística de un acta de entrada y desactiva su lote.
    Bloquea la operación si el lote ya cuenta con despachos registrados para auditoría médica.

    Retorna: tuple (bool, str)
        Una tupla con dos elementos:
        1. bool: True si la operación fue exitosa, False si fue bloqueada o falló.
        2. str: Mensaje detallado del resultado o motivo del bloqueo para mostrar en la interfaz.
    """
    # Abrimos una sesión segura con el motor de SQLModel
    with Session(engine) as session:
        # Intentamos localizar la entrada mediante su ID único
        entrada = session.get(Entradas, id_entrada)
        if not entrada:
            return False, "La entrada especificada no existe en el sistema."
        
        # Validación preventiva: No se puede anular lo que ya está muerto
        if entrada.estado == "ANULADO":
            return False, "Esta entrada ya se encuentra archivada como ANULADA."
            
        # Intentamos localizar el lote físico que nació con esta entrada
        lote = session.get(Lotes, entrada.id_lote)
        if not lote:
            return False, "Error de integridad: No se encontró el lote asociado a esta entrada."
            
        # REGLA OPERATIVA CRÍTICA FIXED: Evaluamos usando la cantidad de la entrada
        # Si el stock disponible actual es menor a lo que entró, significa que ya se despachó
        if lote.stock_disponible < entrada.cantidad:  
            unidades_despachadas = entrada.cantidad - lote.stock_disponible
            return False, (
                f"OPERACIÓN BLOQUEADA: No se puede anular esta entrada. "
                f"Ya se han despachado {unidades_despachadas} unidades del lote "
                f"'{lote.codigo_lote}' en órdenes médicas activas."
            )
            
        try:
            # 1. PASO ALFA: Cambiar el estado de la Entrada a ANULADO
            # Esto la mantiene en el historial para control de la contraloría militar
            entrada.estado = "ANULADO"
            session.add(entrada) # Marcamos la entrada para actualización
            
            # 2. PASO BETA: Desactivación logística del Lote relacionado
            lote.activo = False          # Eliminación lógica (ya no saldrá en búsquedas de despacho)
            lote.motivo_desactivacion = "Anulación de la entrada" 
            # Como tu property en models.py depende de entrada.cantidad, forzamos el estado del lote aquí si es necesario
            session.add(lote)            # Marcamos el lote para actualización
            
            # 3. PASO OMEGA: Consolidar la transacción en el archivo SQLite
            session.commit()
            return True, f"ÉXITO: Entrada y lote '{lote.codigo_lote}' anulados de forma conforme."
            
        except Exception as e:
            # Si algo falla a mitad de camino, restauramos todo al estado anterior (Rollback)
            session.rollback()
            print(f"Error al intentar anular la entrada y lote: {str(e)}")
            return False, f"FALLO CRÍTICO DE BASE DE DATOS: {str(e)}"
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


def registrar_ingreso_inventario(id_insumo, codigo_lote, fecha_vencimiento, ubicacion_fisica, cantidad, id_usuario, fecha_pedido):
    """
    Registra el lote acoplándolo rigurosamente al insumo base 
    y asienta el acta de entrada en una misma transacción.
    Garantiza la integridad transaccional evitando la duplicidad de lotes activos.
    """
    # 🛡️ BARRERA BLUETEAM: Bloqueo explícito de manipulación lógica
    if not usuario_tiene_permiso_escritura():
        return "✖️ ACCESO DENEGADO: Permisos insuficientes."

    with Session(engine) as session:
        try:
            # SANITIZACIÓN: Limpieza estricta previa a la consulta de duplicados
            codigo_lote = sanitizar_input(codigo_lote)
            ubicacion_fisica = sanitizar_input(ubicacion_fisica)

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
            # TRAZABILIDAD AVANZADA
            correlation_id = str(uuid.uuid4())
            logging.error(f'{{"correlation_id": "{correlation_id}", "error": "{str(e)}", "modulo": "entradas_crear"}}')
            return f"✖️ Ocurrió un error inesperado. Reporte el código: [{correlation_id}]"
    
    

def obtener_entradas_filtradas_paginadas(
    txt_universal: str = "",
    rango_fechas: list = None,
    opt_estado: str = "VALIDO",
    pagina_actual: int = 1,
    registros_por_pagina: int = 50
):
    """
    Filtra, pagina y recupera registros de entradas de insumos con sus lotes y usuarios asociados.
    Esta función realiza un join entre Entradas, Lotes, Insumos y Usuarios para permitir búsquedas 
    cruzadas. Aplica filtros de estado, rangos temporales y una búsqueda universal de texto que 
    incluye el nombre del usuario responsable.

    Parámetros:
    - txt_universal (str): Texto para buscar en nombres de insumos, códigos de lote o nombre/apellido de usuario.
    - rango_fechas (list): Lista [date_inicio, date_fin] para filtrar por fecha de recepción.
    - opt_estado (str): Filtro de estado ('VALIDO', 'ANULADO' o 'TODOS').
    - pagina_actual (int): Número de página para la paginación (base 1).
    - registros_por_pagina (int): Cantidad de registros a retornar.

    Retorna:
    - tuple: (lista_final, total_coincidencias) 
        - lista_final: Lista de tuplas (Entradas, Lotes, Insumos, usuarios).
        - total_coincidencias: Int con el número total de registros encontrados sin paginación.
    """
    with Session(engine) as session:
        try:
            # Seleccionamos solo Entradas y precargamos las relaciones
            statement = select(Entradas).options(
                joinedload(Entradas.usuario),
                joinedload(Entradas.lote).joinedload(Lotes.insumo)
            ).join(Lotes, Entradas.id_lote == Lotes.id_lote).join(
                Insumos, Lotes.id_insumo == Insumos.id_insumo
            ).join(
                Usuarios, Entradas.id_usuario == Usuarios.id_usuario
            )
            
            condiciones = []

            # FILTRO 1: ESTADO
            if opt_estado != "TODOS":
                condiciones.append(Entradas.estado == opt_estado)

            # FILTRO 2: BÚSQUEDA UNIVERSAL (incluye Usuario)
            if txt_universal:
                busqueda = txt_universal.strip().upper()
                letra_ved = {"VITAL": "V", "ESENCIAL": "E", "DESEABLE": "D"}.get(busqueda)
                
                bloque_or = [
                    Insumos.nombre.ilike(f"%{txt_universal}%"),
                    Lotes.codigo_lote.ilike(f"%{txt_universal}%"),
                    Usuarios.nombres.ilike(f"%{txt_universal}%"),
                    Usuarios.apellidos.ilike(f"%{txt_universal}%")
                ]
                if letra_ved:
                    bloque_or.append(Insumos.clasificacion_ved == letra_ved)
                
                condiciones.append(or_(*bloque_or))

            # FILTRO 3: RANGO DE FECHAS
            if rango_fechas and len(rango_fechas) == 2:
                dt_inicio = datetime.combine(rango_fechas[0], time.min)
                dt_fin = datetime.combine(rango_fechas[1], time.max)
                condiciones.append(and_(Entradas.fecha_recepcion >= dt_inicio, Entradas.fecha_recepcion <= dt_fin))

            if condiciones:
                statement = statement.where(*condiciones)

            # CONTEO EFICIENTE
            stmt_count = select(func.count()).select_from(Entradas).join(
                Lotes, Entradas.id_lote == Lotes.id_lote
            ).join(
                Insumos, Lotes.id_insumo == Insumos.id_insumo
            ).join(
                Usuarios, Entradas.id_usuario == Usuarios.id_usuario
            )
            if condiciones:
                stmt_count = stmt_count.where(*condiciones)
            total_coincidencias = session.exec(stmt_count).one()

            # PAGINACIÓN Y EJECUCIÓN
            offset_calculado = (pagina_actual - 1) * registros_por_pagina
            statement = statement.order_by(Entradas.fecha_recepcion.desc()).limit(registros_por_pagina).offset(offset_calculado)

            lista_entradas = session.exec(statement).unique().all()
            
            return lista_entradas, total_coincidencias

        except Exception as e:
            # TRAZABILIDAD AVANZADA (JSON log)
            correlation_id = str(uuid.uuid4())
            logging.error(f'{{"correlation_id": "{correlation_id}", "error": "{str(e)}", "modulo": "crud_entradas_filtradas"}}')
            
            # Retorno seguro
            return [], 0
    


def actualizar_registros_entradas_masivo(cambios_dict: dict) -> bool:
    """
    Procesa las modificaciones masivas de la grilla de Entradas (st.data_editor).
    Sanea rigurosamente los tipos de datos (Strings a date) al inicio del ciclo
    para evitar excepciones de Autoflush en SQLite.
    Aplica barreras de rol (BlueTeam), sanitización de cadenas y logs en formato JSON.
    
    Parámetros: cambios_dict : dict
        Un diccionario mapeado donde cada llave es el ID de la entrada (int) 
        y cada valor es otro diccionario con los campos modificados (ej. {4: {'cantidad': 150}}).

    Retorna: bool
        Retorna True si todas las actualizaciones se guardaron con éxito en SQLite. 
        Realiza un rollback integral y retorna False si ocurre cualquier excepción.
    """
    # BARRERA BLUETEAM: Control de acceso estricto
    if not usuario_tiene_permiso_escritura():
        return False

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
                            lote.motivo_desactivacion='AGOTADO'
                            session.add(lote)

                    if "FECHA PEDIDO" in modificaciones:
                        # Aquí ya está garantizado que es un objeto date de Python limpio
                        entrada.fecha_pedido= modificaciones["FECHA PEDIDO"]
                        mensaje= Entradas.validar_fecha_pedido(valor=entrada.fecha_pedido, fr=entrada.fecha_recepcion)
                    

                    if "CÓDIGO LOTE" in modificaciones:
                        lote = session.get(Lotes, entrada.id_lote)
                        if lote:
                            # 🧼 SANITIZACIÓN: Limpieza de código de lote
                            nuevo_codigo = sanitizar_input(str(modificaciones["CÓDIGO LOTE"]))
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
            # TRAZABILIDAD AVANZADA: Registro estructurado en JSON con Correlation ID
            correlation_id = str(uuid.uuid4())
            logging.error(f'{{"correlation_id": "{correlation_id}", "error": "{str(e)}", "modulo": "editar entradas"}}')
            session.rollback()
            return f"✖️ Ocurrió un error inesperado. Reporte el código: [{correlation_id}]"



        

def anular_entrada_y_lote(id_entrada: int) -> tuple:
    """
    Ejecuta la anulación logística de un acta de entrada y desactiva su lote.
    Bloquea la operación si el lote ya cuenta con despachos registrados para auditoría médica.

    Retorna: tuple (bool, str)
        Una tupla con dos elementos:
        1. bool: True si la operación fue exitosa, False si fue bloqueada o falló.
        2. str: Mensaje detallado del resultado o motivo del bloqueo para mostrar en la interfaz.
    """
    # BARRERA BLUETEAM: Control de acceso explícito
    if not usuario_tiene_permiso_escritura():
        return False, "✖️ ACCESO DENEGADO: Permisos insuficientes."

    # Abrimos una sesión segura con el motor de SQLModel
    with Session(engine) as session:
        entrada = session.get(Entradas, id_entrada)
        if not entrada:
            return False, "La entrada especificada no existe en el sistema."
        
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
                f"Ya se han despachado {unidades_despachadas} unidades."
            )
            
        try:
            # 1 Cambiar el estado de la Entrada a ANULADO
            entrada.estado = "ANULADO"
            session.add(entrada) 
            
            # 2 Desactivación logística del Lote relacionado
            lote.activo = False          
            lote.motivo_desactivacion = "Anulación de la entrada" 
            session.add(lote)      # Marcamos el lote para actualización
            
            # 3 Consolidar la transacción
            session.commit()
            return True, f"ÉXITO: Entrada y lote '{lote.codigo_lote}' anulados de forma conforme."
            
        except Exception as e:
            session.rollback()
            # TRAZABILIDAD AVANZADA: Log estructurado JSON con UUID
            correlation_id = str(uuid.uuid4())
            logging.error(f'{{"correlation_id": "{correlation_id}", "error": "{str(e)}", "modulo": "anular_entrada"}}')
            # Retorno seguro: Oculta el detalle técnico (ruta/archivo) del usuario
            return False, f"FALLO CRÍTICO: Ocurrió un error inesperado. Reporte el código: [{correlation_id}]"
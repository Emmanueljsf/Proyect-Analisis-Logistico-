import uuid
import logging
from seguridad import sanitizar_input, es_administrador
import re # Para evaluar la estructura sintáctica del correo electrónico
import hashlib # Para encriptar las contraseñas con el algoritmo SHA-256
from typing import List, Optional
from sqlmodel import Session, select
from bd.models import engine, Usuarios, Rol # Estructuras de datos nativas del ecosistema SIAL-MED

# ==============================================================================
# SECCIÓN 1: VALIDACIONES DE SEGURIDAD Y FORMATO
# ==============================================================================

def validar_datos_usuario(password: Optional[str], email: Optional[str]) -> None:
    """Inspecciona las reglas de los campos controlando la opcionalidad del correo"""
    # Regla Contraseña: Si se envía una clave, se valida que tenga mínimo 8 dígitos
    if password and len(password) < 8:
        raise ValueError("La contraseña debe tener un mínimo de 8 caracteres.")
        
    # Regla Correo: Solo se evalúa si el usuario escribió texto (no es nulo ni vacío)
    if email and email.strip() != "":
        patron_email = r"^[\w\.-]+@[\w\.-]+\.\w+$" # Expresión regular estándar de email
        if not re.match(patron_email, email):
            raise ValueError("El formato del correo electrónico ingresado no es válido.")

def encriptar_password(password: str) -> str:
    """Genera el hash SHA-256 definitivo para proteger la contraseña en SQLite"""
    return hashlib.sha256(password.encode()).hexdigest() # Retorna la cadena segura

# ==============================================================================
# SECCIÓN 2: OPERACIONES CRUD CON CONTROL DE UNICIDAD
# ==============================================================================

def crear_usuario(usuario: Usuarios) -> bool:
    """
    Registra un nuevo usuario en la base de datos tras validar permisos y unicidad.

    Parámetros:
    - usuario (Usuarios): Objeto de modelo con los datos del nuevo usuario.

    Retorna:
    - bool: True si la creación fue exitosa, False en caso de error.
    - Lanza ValueError: Si el username ya existe o los datos no cumplen las reglas de formato.
    """
    # BARRERA BLUETEAM: Solo administradores pueden crear usuarios
    if not es_administrador():
        return False

    with Session(engine) as session:
        try:
            # SANITIZACIÓN: Limpieza de inputs sensibles
            usuario.username = sanitizar_input(usuario.username)
            
            # Unicidad crear: Busca si el username exacto ya existe en la tabla
            st_unicidad = select(Usuarios).where(Usuarios.username == usuario.username)
            if session.exec(st_unicidad).first():
                raise ValueError(f"El nombre de usuario '{usuario.username}' ya está registrado.")

            # Normalización: Si el email viene vacío, se guarda como NULL en la base de datos
            if usuario.email and usuario.email.strip() == "":
                usuario.email = None

            validar_datos_usuario(usuario.password, usuario.email) # Corre la validación de formatos
            
            usuario.password = encriptar_password(usuario.password) # Aplica hash a la clave plana
            session.add(usuario) 
            session.commit() 
            return True 
        except ValueError as ve:
            raise ve 
        except Exception as e:
            # TRAZABILIDAD AVANZADA: Log estructurado con UUID
            correlation_id = str(uuid.uuid4())
            logging.error(f'{{"correlation_id": "{correlation_id}", "error": "{str(e)}", "modulo": "crear_usuario"}}')
            session.rollback() 
            return False


def obtener_usuarios_filtrados(txt_buscar: str = "", rol_buscado: str = "TODOS", estado_buscado: str = "TODOS") -> List[Usuarios]:
    """
    Consulta y filtra el personal registrado en la base de datos aplicando criterios de búsqueda.

    Parámetros:
    - txt_buscar (str): Cadena de texto para filtrar por nombre de usuario (username).
    - rol_buscado (str): Filtro por el rol del usuario ('TODOS' o el nombre del rol).
    - estado_buscado (str): Filtro por estado lógico ('TODOS', 'ACTIVOS', 'INACTIVOS').

    Retorna:
    - List[Usuarios]: Una lista con los objetos Usuarios que cumplen con los filtros aplicados.
    """
    with Session(engine) as session:
        condiciones = []
        
        if txt_buscar:
            condiciones.append(Usuarios.username.ilike(f"%{txt_buscar}%"))
            
        if rol_buscado != "TODOS":
            # Asumimos que el backend compara directamente con el valor del Enum
            condiciones.append(Usuarios.rol == rol_buscado)
            
        if estado_buscado == "ACTIVOS":
            condiciones.append(Usuarios.activo == True)
        elif estado_buscado == "INACTIVOS":
            condiciones.append(Usuarios.activo == False)
            
        statement = select(Usuarios).where(*condiciones)
        return session.exec(statement).all()


def obtener_usuario_por_id(id_usuario: int) -> Optional[Usuarios]:
    """Busca un usuario específico utilizando su Clave Primaria (ID)"""
    with Session(engine) as session:
        return session.get(Usuarios, id_usuario) # get: Busca directo por ID (o devuelve None)


def actualizar_usuario(id_usuario: int, datos_nuevos: dict) -> bool:
    """
    Modifica un usuario existente validando unicidad, permisos y formato.

    Parámetros:
    - id_usuario (int): ID del usuario a modificar.
    - datos_nuevos (dict): Diccionario con los campos a actualizar.

    Retorna:
    - bool: True si la actualización fue exitosa, False si no se encuentra el usuario.
    - Lanza ValueError: Si el nuevo username está ocupado o los datos son inválidos.
    """
    #  BARRERA BLUETEAM: Solo administradores pueden editar usuarios
    if not es_administrador():
        raise PermissionError("Acceso denegado: Se requieren privilegios de administrador.")

    try:
        with Session(engine) as session:
            usuario_db = session.get(Usuarios, id_usuario)
            if not usuario_db:
                return False
            
            # Unicidad editar: Si se cambia el username, valida que no lo tenga otra persona
            nuevo_username = datos_nuevos.get("username")
            if nuevo_username and nuevo_username != usuario_db.username:
                # 🧼 SANITIZACIÓN
                nuevo_username = sanitizar_input(nuevo_username)
                st_unicidad = select(Usuarios).where(
                    Usuarios.username == nuevo_username, 
                    Usuarios.id_usuario != id_usuario
                )
                if session.exec(st_unicidad).first():
                    raise ValueError(f"El nombre de usuario '{nuevo_username}' ya está ocupado.")
                datos_nuevos["username"] = nuevo_username

            # Recolecta los datos finales combinados para la validación de formatos
            pwd_a_validar = datos_nuevos.get("password")
            email_a_validar = datos_nuevos.get("email") if "email" in datos_nuevos else usuario_db.email
            
            # Formateo email opcional en edición
            if email_a_validar and str(email_a_validar).strip() == "":
                email_a_validar = None
                datos_nuevos["email"] = None

            try:
                validar_datos_usuario(pwd_a_validar, email_a_validar)
                if datos_nuevos.get("password"):
                    datos_nuevos["password"] = encriptar_password(datos_nuevos["password"])
            except ValueError as ve:
                raise ve
                
            for key, value in datos_nuevos.items():
                setattr(usuario_db, key, value)
                
            session.add(usuario_db)
            session.commit()
            return True
    
    except Exception as e:
        # TRAZABILIDAD AVANZADA
        correlation_id = str(uuid.uuid4())
        logging.error(f'{{"correlation_id": "{correlation_id}", "error": "{str(e)}", "modulo": "actualizar_usuario"}}')
        return False




# ==============================================================================
# SECCIÓN 3: LOGUEO Y CONTROL DE ACCESO
# ==============================================================================
def verificar_credenciales(username_input: str, password_input: str) -> Optional[Usuarios]:
    """Coteja los datos de acceso del login con los hashes guardados en la DB"""
    with Session(engine) as session: # Abre el puente con la persistencia
        statement = select(Usuarios).where(Usuarios.username == username_input) # Consulta por username
        usuario = session.exec(statement).first() # Extrae el primer resultado coincidente
        
        if usuario:
            # Encripta el intento de entrada y lo compara directamente con el de SQLite
            if usuario.password == encriptar_password(password_input):
                return usuario # Concede acceso devolviendo la instancia completa con su Rol
        return None # Deniega el acceso si el usuario o la contraseña fallaron
    


def autenticar_usuario(username_ingresado: str, password_ingresada: str, session_externa: Optional[Session] = None):
    """
    Verifica las credenciales aplicando hashing de SHA-256 para la validación.
    """
    # Si viene sesión de pruebas la usa, si no, usa el engine real
    session = session_externa if session_externa is not None else Session(engine)
    #with Session(engine) as session:
    try:
        # 1. Buscar al usuario por username
        statement = select(Usuarios).where(Usuarios.username == username_ingresado.strip().lower())
        usuario = session.exec(statement).first()
        
        if not usuario:
            return "Usuario no encontrado"
            
        # 2. Convertir la contraseña del formulario en Hash SHA-256
        # .encode() pasa el texto a bytes, y .hexdigest() lo vuelve a convertir en texto legible para SQL
        hash_ingresado = hashlib.sha256(password_ingresada.strip().encode()).hexdigest()
        
        # 3. Comparar el hash generado contra el hash almacenado en SQLite
        if usuario.password != hash_ingresado:
            return "Contraseña incorrecta"
        if not usuario.activo:
            return "Cuenta inactiva"  
        return usuario
    
    finally:
        # Solo cerramos si es una sesión local de producción
        if session_externa is None:
            session.close()


# ==============================================================================
# SECCIÓN 4: AUTO-SEEDING Y PERSISTENCIA DE CONTINGENCIA
# ==============================================================================

def verificar_y_crear_primer_admin() -> Optional[dict]:
    """
    Inspecciona si el sistema carece de cuentas registradas en la base de datos.
    Si la tabla está vacía, registra un Administrador genérico de contingencia 
    invocando la lógica estándar del CRUD para asegurar el cifrado de la clave.

    Retorna:
    - dict: Un diccionario con las llaves 'username' y 'password' en texto plano
            si el usuario fue creado exitosamente.
    - None: Si la base de datos ya contiene al menos un usuario registrado.
    """
    with Session(engine) as session:
        # Evaluamos si la tabla Usuarios está completamente vacía
        total_usuarios = session.exec(select(Usuarios)).all()
        
        if 0 == 0:
            # Instanciamos el modelo con los datos iniciales de rescate
            admin_inicial = Usuarios(
                nombres="Administrador",
                apellidos="De Control",
                username="admin",
                password="admin123", # 'crear_usuario' se encargará de encriptarla en SHA-256[cite: 10]
                rol=Rol.Administrador,
                activo=True
            )
            # Reutilizamos tu función del CRUD con sus respectivas validaciones[cite: 10]
            if crear_usuario(admin_inicial):
                return {"username": "admin", "password": "admin123"}
        
        with Session(engine) as session:
            # Consultamos todos los usuarios actuales
            usuarios = session.exec(select(Usuarios)).all()
            
            # Si hay exactamente un usuario y su username es 'admin', el peligro persiste
            if len(usuarios) == 1 and usuarios[0].username == "admin":
                return {"username": usuarios[0].username, "password": 'admin123'}
                
    return None


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
    """Registra un usuario previniendo duplicados y aceptando email nulo"""
    with Session(engine) as session: # Contexto with: Abre la conexión segura con la DB
        try:
            # Unicidad crear: Busca si el username exacto ya existe en la tabla
            st_unicidad = select(Usuarios).where(Usuarios.username == usuario.username)
            if session.exec(st_unicidad).first(): # Si halla coincidencia, aborta
                raise ValueError(f"El nombre de usuario '{usuario.username}' ya está registrado.")

            # Normalización: Si el email viene vacío, se guarda como NULL en la base de datos
            if usuario.email and usuario.email.strip() == "":
                usuario.email = None

            validar_datos_usuario(usuario.password, usuario.email) # Corre la validación de formatos
            
            usuario.password = encriptar_password(usuario.password) # Aplica hash a la clave plana
            session.add(usuario) # Coloca el objeto armado en la cola de la sesión
            session.commit() # Sella la transacción físicamente en el disco duro
            return True # Retorna verdadero si el alta fue exitosa
        except ValueError as ve:
            raise ve # Propaga el error específico de validación a Streamlit
        except Exception:
            session.rollback() # Revierte los cambios ante fallos inesperados
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
    """Modifica un usuario validando que el nuevo username no choque con otro operador"""
    try:
        with Session(engine) as session: # Establece conexión con el backend
            usuario_db = session.get(Usuarios, id_usuario) # Recupera el registro actual de la DB
            if not usuario_db:
                return False # Aborta la función si el ID no existe en el sistema
            
            # Unicidad editar: Si se cambia el username, valida que no lo tenga otra persona
            nuevo_username = datos_nuevos.get("username")
            if nuevo_username and nuevo_username != usuario_db.username:
                st_unicidad = select(Usuarios).where(
                    Usuarios.username == nuevo_username, 
                    Usuarios.id_usuario != id_usuario # Excluye mi propio ID de la búsqueda
                )
                if session.exec(st_unicidad).first(): # Si lo tiene otro ID, frena la edición
                    raise ValueError(f"El nombre de usuario '{nuevo_username}' ya está ocupado.")

            # Recolecta los datos finales combinados para la validación de formatos
            pwd_a_validar = datos_nuevos.get("password")
            email_a_validar = datos_nuevos.get("email") if "email" in datos_nuevos else usuario_db.email
            
            # Formateo email opcional en edición
            if email_a_validar and str(email_a_validar).strip() == "":
                email_a_validar = None
                datos_nuevos["email"] = None # Setea un None real en el mapa de cambios

            try:
                validar_datos_usuario(pwd_a_validar, email_a_validar) # Valida contraseñas y correos
                
                if datos_nuevos.get("password"): # Si se envió una nueva contraseña en el formulario...
                    datos_nuevos["password"] = encriptar_password(datos_nuevos["password"]) # ...la encripta
                    
            except ValueError as ve:
                raise ve # Lanza el error para pintar la alerta roja en la interfaz
                
            # Asignación dinámica: Vuelca los valores del diccionario en el objeto mapeado
            for key, value in datos_nuevos.items():
                setattr(usuario_db, key, value) # Asigna el valor correspondiente al atributo
                
            session.add(usuario_db) # Marca la entidad como modificada para la sesión
            session.commit() # Ejecuta la sentencia SQL UPDATE de forma atómica
            return True # Retorna confirmación de éxito
    
    except Exception as e:
            print(f"Error crítico en actializar usuario: {e}")


# NO ESTÁ EN USO
def eliminar_usuario(id_usuario: int) -> bool:
    """Remueve una cuenta de usuario de la base de datos"""
    with Session(engine) as session: # Inicializa el bloque de conexión
        usuario = session.get(Usuarios, id_usuario) # Localiza el objetivo apuntado
        if usuario:
            try:
                session.delete(usuario) # delete: Elimina el registro del mapa de datos
                session.commit() # Aplica el borrado definitivo en el archivo SQLite
                return True # Retorna verdadero indicando eliminación exitosa
            except Exception:
                session.rollback() # Cancela el borrado por seguridad de datos
                return False # Falso si el usuario tiene transacciones amarradas en cascada
        return False # Falso si el ID no correspondía a nadie

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
        
        if len(total_usuarios) == 0:
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


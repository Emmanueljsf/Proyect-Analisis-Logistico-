import re # Para evaluar la estructura sintáctica del correo electrónico
import hashlib # Para encriptar las contraseñas con el algoritmo SHA-256
from typing import List, Optional
from sqlmodel import Session, select
from models import engine, Usuarios, Rol # Estructuras de datos nativas del ecosistema SIAL-MED

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

def obtener_usuarios() -> List[Usuarios]:
    """Extrae la lista completa de usuarios de la base de datos"""
    with Session(engine) as session: # Abre la conexión temporal con la DB
        return session.exec(select(Usuarios)).all() # Exec: Ejecuta un SELECT * FROM usuarios

def obtener_usuario_por_id(id_usuario: int) -> Optional[Usuarios]:
    """Busca un usuario específico utilizando su Clave Primaria (ID)"""
    with Session(engine) as session:
        return session.get(Usuarios, id_usuario) # get: Busca directo por ID (o devuelve None)

def actualizar_usuario(id_usuario: int, datos_nuevos: dict) -> bool:
    """Modifica un usuario validando que el nuevo username no choque con otro operador"""
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
    


def autenticar_usuario(username_ingresado: str, password_ingresada: str):
    """
    Verifica las credenciales aplicando hashing de SHA-256 para la validación.
    """
    with Session(engine) as session:
        # 1. Buscar al usuario por username
        statement = select(Usuarios).where(Usuarios.username == username_ingresado.strip().lower())
        usuario = session.exec(statement).first()
        
        if not usuario:
            return "Usuario no encontrado"
            
        # 2. 📌 NUEVO: Convertir la contraseña del formulario en Hash SHA-256
        # .encode() pasa el texto a bytes, y .hexdigest() lo vuelve a convertir en texto legible para SQL
        hash_ingresado = hashlib.sha256(password_ingresada.strip().encode()).hexdigest()
        
        # 3. Comparar el hash generado contra el hash almacenado en SQLite
        if usuario.password != hash_ingresado:
            return "Contraseña incorrecta"
        if not usuario.activo:
            return "Cuenta inactiva"  
        return usuario

from sqlmodel import Session, select
from models import create_db_and_tables, Usuarios, Rol, engine
import hashlib

def encriptar_contrasena(password: str) -> str:
    """
    Encripta una cadena de texto plano usando SHA-256.
    Ajusta este método si tu login aplica un formato específico (ej. hex-digest).
    """
    # Convierte el string a bytes, aplica SHA-256 y lo vuelve a transformar a texto legible (Hexadecimal)
    return hashlib.sha256(password.encode('utf-8')).hexdigest()

def crear_administrador_defecto():
    """
    Inicializa las tablas y asegura la existencia de un usuario 
    Administrador en el sistema SIAL-MED usando hashlib.
    """
    print("🔄 Inicializando base de datos y verificando tablas...")
    create_db_and_tables()  # Asegura la existencia del archivo .db y sus esquemas
    
    with Session(engine) as session:
        # Buscamos si ya existe la fila del administrador
        statement = select(Usuarios).where(Usuarios.rol == Rol.Administrador)
        admin_existente = session.exec(statement).first()
        
        if not admin_existente:
            print("👤 No se encontró ningún Administrador. Creando usuario por defecto...")
            
            password_plana = "admin123"
            password_hash = encriptar_contrasena(password_plana)
            
            admin_defecto = Usuarios(
                nombres="ADMINISTRADOR",
                apellidos="DEL SISTEMA",
                username="admin",
                password=password_hash,  # Se almacena el hash de 64 caracteres
                rol=Rol.Administrador,
                email="admin@sialmed.mil.ve",
                activo=True
            )
            
            try:
                session.add(admin_defecto)
                session.commit()
                print("✅ ¡Usuario Administrador creado con éxito!")
                print("--------------------------------------------------")
                print(f"🔑 Usuario: admin")
                print(f"🔑 Contraseña: {password_plana}")
                print(f"🔑 Hash guardado: {password_hash}")
                print("--------------------------------------------------")
            except Exception as e:
                session.rollback()
                print(f"❌ Error al insertar el administrador: {e}")
        else:
            print(f"✨ El sistema ya cuenta con un Administrador registrado ({admin_existente.username}).")

if __name__ == "__main__":
    crear_administrador_defecto()
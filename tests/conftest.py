import pytest
from sqlmodel import SQLModel, Session, create_engine
from models import engine as modelo_engine  # Importamos tu configuración base

# Creamos un engine dedicado exclusivamente a las pruebas en memoria
@pytest.fixture(scope="session")
def engine():
    engine_prueba = create_engine(
        "sqlite:///:memory:", 
        connect_args={"check_same_thread": False}
    )
    # Crea físicamente todas las tablas del SIAL-MED (Insumos, Lotes, Usuarios, etc.) en la memoria
    SQLModel.metadata.create_all(engine_prueba)
    yield engine_prueba
    SQLModel.metadata.drop_all(engine_prueba)

# Esta es la "fixture" mágica que están pidiendo a gritos tus funciones de prueba
@pytest.fixture(scope="function")
def session(engine):
    """Proporciona una sesión de base de datos limpia para cada función de prueba."""
    connection = engine.connect()
    transaction = connection.begin()
    
    # Creamos la sesión vinculada a la conexión de pruebas
    session_prueba = Session(bind=connection)
    
    yield session_prueba  # Aquí es donde se ejecutan tus pruebas (test_1, test_2, etc.)
    
    # Al terminar la prueba, cerramos y revertimos todo para que el siguiente test empiece de cero
    session_prueba.close()
    transaction.rollback()
    connection.close()
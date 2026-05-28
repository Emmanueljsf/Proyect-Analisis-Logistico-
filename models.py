from sqlmodel import SQLModel, Field, Relationship, create_engine, Session
from typing import List, Optional
from datetime import date, datetime
import sqlalchemy
from enum import Enum
from sqlalchemy import MetaData # Importar esto es clave

# virtualenv -p python3 o python -m venv env
# .\env\Scripts\activate

# 1. BORRADO AGRESIVO DE MAPPERS (Corta el error de raíz)
sqlalchemy.orm.clear_mappers()

# 2. CONFIGURACIÓN DEL ENGINE
sqlite_url = "sqlite:///Control_insumos.db"
engine = create_engine(sqlite_url, connect_args={"check_same_thread": False})

# Esto limpia el registro de mappers cada vez que el archivo se recarga
SQLModel.metadata = MetaData()
# Verificamos si ya hay tablas registradas para no duplicar el 'Mapper'
if hasattr(SQLModel, "metadata"):
    SQLModel.metadata.clear()
# ==============================================================================
# 📌 LO QUE TE FALTABA: FUNCIÓN PARA GENERAR SESIONES EFÍMERAS
# ==============================================================================
def obtener_sesion_bd():
    """
    Genera una sesión limpia de la base de datos para ejecutar consultas
    y asegura su cierre correcto al finalizar la operación.
    """
    return Session(engine)




# --- 1. DEFINICIÓN DE ENUMS Y EXCEPCIONES ---
class TipoVED(str, Enum):
    V = "V"
    E = "E"
    D = "D"

class Rol(str, Enum):
    Administrador = "Administrador"
    Encargado = "Encargado del area"
    Personal_otra_area = "Personal de otras areas"

# --- 2. MODELOS DE TABLAS (ORDENADOS POR JERARQUÍA) ---

class Insumos(SQLModel, table=True):
    """
    Modelo que representa la tabla 'insumos' en la base de datos.
    table=True indica a SQLModel que debe mapear esta clase como una tabla física de SQL.
    """
    __table_args__ = {"extend_existing": True} # Permite redefinir la tabla en memoria sin lanzar errores de duplicado
    
    # Optional[int]: Indica que el campo puede ser un entero o None (nulo). Es necesario porque
    # al registrar un nuevo insumo, el ID no existe en Python hasta que SQLite lo autogenera.
    # primary_key=True: Establece este campo como la clave primaria única de la tabla.
    id_insumo: Optional[int] = Field(default=None, primary_key=True)
    nombre: str = Field(max_length=150)
    # sa_column_kwargs={"nullable": False}: Pasa un argumento directo a SQLAlchemy (SA) para 
    # forzar que la columna sea 'NOT NULL' a nivel de esquema en la base de datos.
    clasificacion_ved: TipoVED = Field(sa_column_kwargs={"nullable": False})
    # List["Lotes"]: Establece una relación de uno a muchos (1:N). Un insumo puede tener una lista de lotes.
    # back_populates="insumo": Vincula esta relación con el atributo 'insumo' del modelo Lotes para
    # mantener la sincronización bidireccional automáticamente en memoria.
    lotes: List["Lotes"] = Relationship(back_populates="insumo")

    @property
    def total_stock(self) -> int:
        """
        Calcula el stock total sumando el stock disponible de todos sus lotes.
        """
        if not self.lotes:
            return 0
        try:
            # Forzamos que evalúe y sume como enteros puros
            return sum(int(lote.stock_disponible) for lote in self.lotes if lote.stock_disponible is not None)
        except Exception:
            return 0
    

class Usuarios(SQLModel, table=True):
    __table_args__ = {"extend_existing": True}
    id_usuario: Optional[int] = Field(default=None, primary_key=True)
    nombres: str = Field(max_length=100)
    apellidos: str = Field(max_length=100)
    username: str = Field(max_length=50, unique=True)
    password: str = Field(max_length=255)
    rol: Rol = Field(sa_column_kwargs={"nullable": False})
    email: Optional[str] = Field(default=None, max_length=100, nullable=True)
    activo: bool= Field(default=True)

    entradas: List["Entradas"] = Relationship(back_populates="usuario") # Registros de entrada realizados
    salidas: List["Salidas"] = Relationship(back_populates="usuario")   # Despachos autorizados


# ==============================================================================
# MODELOS CORREGIDOS SEGÚN EL DIAGRAMA DE LA IMAGEN image_4f7a72.png
# ==============================================================================

class Lotes(SQLModel, table=True):

    __table_args__ = {"extend_existing": True}
    id_lote: Optional[int] = Field(default=None, primary_key=True)
    id_insumo: int = Field(foreign_key="insumos.id_insumo") 
    codigo_lote: str = Field(max_length=50, unique=True) 
    fecha_vencimiento: date = Field()       
    ubicacion_fisica: str = Field(max_length=100) 
    # Optional[Insumos]: Cardinalidad Muchos a Uno (N:1). Muchos lotes pertenecen a un Insumo.
    # Permite acceder de forma directa al objeto Insumo padre (ej: lote.insumo.nombre).
    insumo: Optional[Insumos] = Relationship(back_populates="lotes") 
    # Optional["Entradas"]: Cardinalidad Uno a Uno (1:1). Cada lote está ligado a una única transacción de entrada.
    # Al no usar 'List', el ORM entiende que la relación recuperará un solo objeto o None.
    entrada: Optional["Entradas"] = Relationship(back_populates="lote") 
    # List["DetallesSalida"]: Cardinalidad Uno a Muchos (1:N). Un lote puede ser distribuido 
    # fraccionadamente en múltiples despachos o entregas logísticas.
    detalles_salida: List["DetallesSalida"] = Relationship(back_populates="lote") 

    @property
    def stock_disponible(self) -> int:
        """
        Propiedad dinámica que deduce el stock remanente del lote restando
        los consumos parciales de la cantidad de entrada original.
        """
        # Control de flujo preventivo: Si el lote no posee un registro documental de entrada,
        # carece de stock inicial, por ende retorna 0 inmediatamente sin procesar restas.
        if not self.entrada:
            return 0
            
        # Acceso directo al atributo del objeto relacionado 1:1 (Navegación del grafo de objetos).
        cantidad_inicial = self.entrada.cantidad 
        
        # Sumariza todas las unidades que han salido de este lote.
        # Si la lista de detalles_salida está vacía, sum() devuelve 0 de manera automática y segura.
        cantidad_despachada = sum(detalle.cantidad for detalle in self.detalles_salida)
        
        # Operación aritmética de sustracción logística.
        disponible = cantidad_inicial - cantidad_despachada
        
        # Cláusula de resguardo: Si por errores de transcripción las salidas superan la entrada,
        # se retorna 0 para blindar el sistema contra la existencia de inventario negativo.
        return disponible if disponible > 0 else 0



class Entradas(SQLModel, table=True):
    __table_args__ = {"extend_existing": True}
    id_entrada: Optional[int] = Field(default=None, primary_key=True)
    id_lote: int = Field(foreign_key="lotes.id_lote")       # Enlace relacional al lote ingresado
    id_usuario: int = Field(foreign_key="usuarios.id_usuario") # 📌 NUEVO: Usuario que procesó el ingreso
    fecha_pedido: date = Field()       # Fecha en la que se solicitó el insumo a la red militar
    fecha_recepcion: datetime = Field(default_factory=datetime.now) # Registra: AAAA-MM-DD HH:MM:SS
    cantidad: int = Field()            # Volumen de insumos ingresados a las cajas
    # Relaciones del Modelo Entradas
    lote: Optional["Lotes"] = Relationship(back_populates="entrada")
    usuario: Optional[Usuarios] = Relationship(back_populates="entradas") # Acceso al responsable de la carga

    # 📌 NUEVA PROPIEDAD DINÁMICA: Cálculo del Lead Time (Tiempo de Entrega)
    @property
    def tiempo_entrega_dias(self) -> int:
        """
        Calcula la diferencia en días entre la solicitud del pedido 
        y la recepción física en el almacén.
        """
        # Extraemos solo la fecha (año, mes, día) del datetime de recepción
        fecha_recep_pura = self.fecha_recepcion.date()
        # Operación aritmética entre objetos date (retorna un timedelta)
        diferencia = fecha_recep_pura - self.fecha_pedido
        # Retornamos el valor absoluto en días (evita números negativos por error de carga)
        return abs(diferencia.days)


class Salidas(SQLModel, table=True):
    __table_args__ = {"extend_existing": True}
    id_salida: Optional[int] = Field(default=None, primary_key=True)
    id_usuario: int = Field(foreign_key="usuarios.id_usuario") # Usuario que despacha la orden medica
    fecha: datetime = Field(default_factory=datetime.now) # Registro temporal exacto del despacho
    orden_medica: str = Field(max_length=100, unique=True)             # Código identificador del justificante médico
    paciente: str = Field(max_length=150)                 # Nombre del efectivo militar o civil atendido
    # Relaciones del Modelo Salidas
    usuario: Optional[Usuarios] = Relationship(back_populates="salidas") # Enlace al operador del sistema
    detalles: List["DetallesSalida"] = Relationship(back_populates="salida") # Lista de insumos incluidos

class DetallesSalida(SQLModel, table=True): # 📌 NUEVA TABLA: Normalización del despacho de insumos
    __table_args__ = {"extend_existing": True}
    id_detalle_salida: Optional[int] = Field(default=None, primary_key=True)
    id_salida: int = Field(foreign_key="salidas.id_salida", ondelete="CASCADE") # Clave foránea al documento de salida maestro
    id_lote: int = Field(foreign_key="lotes.id_lote")     # Clave foránea al lote específico extraído
    cantidad: int = Field() # Volumen numérico de artículos retirados de este lote en particular
    # Relaciones del Modelo DetallesSalida
    salida: Optional[Salidas] = Relationship(back_populates="detalles") # Conexión a la cabecera de la salida
    lote: Optional[Lotes] = Relationship(back_populates="detalles_salida") # Conexión al lote del insumo


# --- 3. CONFIGURACIÓN DE CONEXIÓN ---

def create_db_and_tables():
    """Llamar al inicio de app.py"""
    SQLModel.metadata.create_all(engine)














"""Conceptos clave que aplicamos del diagrama:
Herencia de SQLModel y table=True: Esto le dice a Python que esa clase no es solo un objeto, sino una tabla real en la base de datos.

Field(foreign_key=...): Esto establece la unión entre tablas. Por ejemplo, en Salidas vinculamos el id_usuario para saber quién entregó el medicamento.

Relationship: No es obligatorio para la base de datos, pero te ayuda mucho en Python. Si tienes una salida, puedes hacer salida.usuario.nombres y obtendrás el nombre del militar sin tener que hacer otra consulta SQL manual."""



"""
Uno a Muchos (1:N): Se define declarando el tipo como una lista: List["Modelo"]. Por ejemplo, un Insumo tiene muchos lotes (List["Lotes"]).
Muchos a Uno (N:1): Se define declarando el tipo como el objeto individual (u opcional): Optional["Modelo"]. Por ejemplo, un Lote pertenece a un Insumo (Optional[Insumos]).
Uno a Uno (1:1): Se declara como un objeto individual en ambos lados, pero se añade el argumento sa_relationship_kwargs={"uselist": False} en el lado inverso para obligar a SQLAlchemy a no usar listas.
"""

"""
💡 La Solución de Base de Datos sobre el si la fecha de vencimiento debe ser nulo o no:
El campo debe ser obligatorio (nullable=False). Permitir nulos (NULL) en un inventario militar te va a generar vacíos de control ("agujeros negros" de datos).
Si un insumo no vence (como una pinza), la doctrina logística dicta que se registra una fecha límite estándar a muy largo plazo (por ejemplo, 10 años en el futuro o la fecha límite de su empaque estéril). Mantener el campo obligatorio te obliga a mantener la disciplina de vigilar el estado del almacén.
"""
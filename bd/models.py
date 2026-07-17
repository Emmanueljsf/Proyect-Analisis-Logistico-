from sqlmodel import SQLModel, Field, Relationship, create_engine, Session
from typing import List, Optional
from datetime import date, datetime
import sqlalchemy
from enum import Enum
from sqlalchemy import MetaData, event, Index, text # Importar esto es clave
from sqlite3 import Connection as SQLite3Connection
from pydantic import field_validator  #  Importación obligatoria para validaciones

# virtualenv -p python3 o python -m venv env
# .\env\Scripts\activate

# 1. BORRADO AGRESIVO DE MAPPERS (Corta el error de raíz)
sqlalchemy.orm.clear_mappers()

# 2. CONFIGURACIÓN DEL ENGINE
sqlite_url = "sqlite:///Control_insumos.db"
# 📌 Añadimos timeout=30 para que si la base de datos está ocupada, espere hasta 30 segundos antes de dar error
engine = create_engine(
    sqlite_url, 
    connect_args={
        "check_same_thread": False,
        "timeout": 30
    }
)

# 🔒 CORTAFUEGOS DE INTEGRIDAD Y CONCURRENCIA MULTIUSUARIO (WAL)
@event.listens_for(engine, "connect")
def configurar_conexion_sqlite(dbapi_connection, connection_record):
    if isinstance(dbapi_connection, SQLite3Connection):
        cursor = dbapi_connection.cursor()
        # 1. Obliga a SQLite a respetar las llaves foráneas
        cursor.execute("PRAGMA foreign_keys=ON;")
        # 2. ACTIVACIÓN DEL MODO WAL: Permite lecturas concurrentes mientras se escribe
        cursor.execute("PRAGMA journal_mode=WAL;")
        # 3. Sincronización normal (Recomendada para WAL, mejora la velocidad de escritura considerablemente)
        cursor.execute("PRAGMA synchronous=NORMAL;")
        cursor.close()

# Esto limpia el registro de mappers cada vez que el archivo se recarga
SQLModel.metadata = MetaData()
# Verificamos si ya hay tablas registradas para no duplicar el 'Mapper'
if hasattr(SQLModel, "metadata"):
    SQLModel.metadata.clear()
# ==============================================================================
# FUNCIÓN PARA GENERAR SESIONES EFÍMERAS
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

class Estado(str, Enum):
    VALIDO='VALIDO'
    ANULADO='ANULADO'

# --- 2. MODELOS DE TABLAS (ORDENADOS POR JERARQUÍA) ---

class Insumos(SQLModel, table=True):
    """
    Modelo que representa la tabla 'insumos' en la base de datos.
    table=True indica a SQLModel que debe mapear esta clase como una tabla física de SQL.
    """
    __table_args__ = {"extend_existing": True} # Permite redefinir la tabla en memoria sin lanzar errores de duplicado
    
    # Optional[int]: Indica que el campo puede ser un entero o None (nulo). Es necesario porque
    # al registrar un nuevo insumo, el ID no existe en Python hasta que SQLite lo autogenera.
    id_insumo: Optional[int] = Field(default=None, primary_key=True)
    nombre: str = Field(max_length=80, sa_column_kwargs={"nullable": False})
    # sa_column_kwargs={"nullable": False}: Pasa un argumento directo a SQLAlchemy (SA) para 
    # forzar que la columna sea 'NOT NULL' a nivel de esquema en la base de datos.
    clasificacion_ved: TipoVED = Field(sa_column_kwargs={"nullable": False})
    activo: bool = Field(default=True, sa_column_kwargs={"server_default": "1"})  # True = Disponible, False = Oculto/Archivado
    # List["Lotes"]: Establece una relación de uno a muchos (1:N). Un insumo puede tener una lista de lotes.
    # back_populates="insumo": Vincula esta relación con el atributo 'insumo' del modelo Lotes para
    # mantener la sincronización bidireccional automáticamente en memoria.
    lotes: List["Lotes"] = Relationship(back_populates="insumo")

    @property
    def total_stock(self) -> int:
        """
        Calcula el stock total sumando el stock disponible UNICAMENTE 
        de los lotes que se encuentren en estado activo.
        """
        if not self.activo or not self.lotes:
            return 0
        try:
            # Filtramos en la lista de comprensión: 'if lote.activo'
            return sum(
                lote.stock_disponible
                for lote in self.lotes 
                if lote.stock_disponible is not None and lote.activo is True
            )
        except Exception:
            return 0
    

class Usuarios(SQLModel, table=True):
    __table_args__ = {"extend_existing": True}
    id_usuario: Optional[int] = Field(default=None, primary_key=True)
    nombres: str = Field(max_length=100, sa_column_kwargs={"nullable": False})
    apellidos: str = Field(max_length=100, sa_column_kwargs={"nullable": False})
    username: str = Field(max_length=50, unique=True, sa_column_kwargs={"nullable": False})
    password: str = Field(max_length=255, sa_column_kwargs={"nullable": False})
    rol: Rol = Field(sa_column_kwargs={"nullable": False})
    email: Optional[str] = Field(default=None, max_length=100, nullable=True)
    activo: bool= Field(default=True)
    entradas: List["Entradas"] = Relationship(back_populates="usuario") # Registros de entrada realizados
    salidas: List["Salidas"] = Relationship(back_populates="usuario")   # Despachos autorizados

    @field_validator("nombres", "apellidos", "username", mode="before")
    def validar_textos_usuario(cls, valor, info):
        if valor is None:
            raise ValueError(f"El campo '{info.field_name}' no puede ser nulo.")
        if isinstance(valor, str) and not valor.strip():
            raise ValueError(f"El campo '{info.field_name}' no puede quedarse vacío.")
        return valor.strip()


class Lotes(SQLModel, table=True):
    __table_args__ = (
        # Bloquea duplicados SOLO si coinciden el código Y el mismo medicamento Y está activo.
        Index(
            "ix_lotes_codigo_insumo_activo_unique", 
            "codigo_lote", 
            "id_insumo",  # <--- Agregamos el medicamento al cruce único
            unique=True, 
            sqlite_where= text("activo = 1"),
            postgresql_where= text("activo = 1")
        ),
        {"extend_existing": True}
    )
    id_lote: Optional[int] = Field(default=None, primary_key=True)
    id_insumo: int = Field(foreign_key="insumos.id_insumo", sa_column_kwargs={"nullable": False}) 
    codigo_lote: str = Field(max_length=50, sa_column_kwargs={"nullable": False}) 
    fecha_vencimiento: date = Field(sa_column_kwargs={"nullable": False})       
    ubicacion_fisica: str = Field(max_length=100, sa_column_kwargs={"nullable": False}) 
    activo: bool = Field(default=True, sa_column_kwargs={"server_default": "1"})  # True = En almacén, False = Dado de baja (Agotado/Anulado)
    motivo_desactivacion: Optional[str] = Field(default=None, sa_column_kwargs={"nullable": True})
    # Optional[Insumos]: Cardinalidad Muchos a Uno (N:1). Muchos lotes pertenecen a un Insumo.
    # Permite acceder de forma directa al objeto Insumo padre (ej: lote.insumo.nombre).
    insumo: Optional[Insumos] = Relationship(back_populates="lotes") 
    # Optional["Entradas"]: Cardinalidad Uno a Uno (1:1). Cada lote está ligado a una única transacción de entrada.
    # Al no usar 'List', el ORM entiende que la relación recuperará un solo objeto o None.
    entrada: Optional["Entradas"] = Relationship( back_populates="lote", sa_relationship_kwargs={"cascade": "all, delete-orphan"})
    # List["DetallesSalida"]: Cardinalidad Uno a Muchos (1:N). Un lote puede ser distribuido 
    # fraccionadamente en múltiples despachos o entregas logísticas.
    detalles_salida: List["DetallesSalida"] = Relationship(back_populates="lote") 

    @field_validator("codigo_lote", "ubicacion_fisica", mode="before")
    def validar_textos_lote(cls, valor, campo):
        if valor is None:
            raise ValueError(f"El campo de {campo} es un requisito obligatorio.")
        if isinstance(valor, str) and not valor.strip():
            raise ValueError(f"El campo {campo} no puede quedar en blanco.")
        return valor.strip().upper()

    @field_validator("fecha_vencimiento", mode="before")
    def validar_fecha_vencimiento(cls, valor):
        if valor is None:
            raise ValueError("La fecha de vencimiento es un requisito obligatorio.")
        if isinstance(valor, str):
            try:
                valor = datetime.strptime(valor, "%Y-%m-%d").date()
            except ValueError:
                raise ValueError("El formato de fecha de vencimiento debe ser YYYY-MM-DD.")
        
        # Validación doctrinal: No permitir el registro inicial de insumos caducados
        if valor < date.today():
            raise ValueError("No se permite el ingreso de lotes cuya fecha de vencimiento sea anterior al día de hoy.")
        return valor

    @property
    def stock_disponible(self) -> int:
        if not self.activo:
            return 0   
        cantidad_inicial = self.entrada.cantidad 
        # Sumariza todas las unidades que han salido de este lote.
        # Si la lista de detalles_salida está vacía, sum() devuelve 0 de manera automática y segura.
        cantidad_despachada = sum(detalle.cantidad for detalle in self.detalles_salida if detalle.salida.estado==Estado.VALIDO)
        disponible = cantidad_inicial - cantidad_despachada
        return disponible



class Entradas(SQLModel, table=True):
    __table_args__ = {"extend_existing": True}
    id_entrada: Optional[int] = Field(default=None, primary_key=True)
    id_lote: int = Field(foreign_key="lotes.id_lote", ondelete="CASCADE", sa_column_kwargs={"nullable": False})       # Enlace relacional al lote ingresado
    id_usuario: int = Field(foreign_key="usuarios.id_usuario", sa_column_kwargs={"nullable": False}) # NUEVO: Usuario que procesó el ingreso
    fecha_pedido: date = Field(sa_column_kwargs={"nullable": False})       # Fecha en la que se solicitó el insumo a la red militar
    fecha_recepcion: datetime = Field(default_factory=datetime.now) # Registra: AAAA-MM-DD HH:MM:SS
    cantidad: int = Field(sa_column_kwargs={"nullable": False})            # Volumen de insumos ingresados a las cajas
    estado: Estado = Field(default=Estado.VALIDO) # Usamos string para el estado. Valores estándar: "VALIDO", "ANULADO"
    # Relaciones del Modelo Entradas
    lote: Optional["Lotes"] = Relationship(back_populates="entrada", sa_relationship_kwargs={"cascade": "all, delete-orphan", "single_parent": True}) # SOLUCIÓN CRÍTICA: Fuerza la existencia exclusiva 1 a 1
    usuario: Optional[Usuarios] = Relationship(back_populates="entradas") # Acceso al responsable de la carga

    @field_validator("cantidad", mode="before")
    def validar_cantidad_entrada(cls, valor):
        if valor is None:
            raise ValueError("La cantidad de insumos ingresados no puede ser nula.")
        if int(valor) <= 0:
            raise ValueError("La cantidad de entrada debe ser un entero estrictamente mayor a cero (0).")
        return int(valor)

    @field_validator("fecha_pedido", mode="before")
    def validar_fecha_pedido(cls, valor, fr):
        if valor is None:
            raise ValueError("La fecha de solicitud de pedido es obligatoria.")
        if isinstance(valor, str):
            try:
                valor = datetime.strptime(valor, "%Y-%m-%d").date()
            except ValueError:
                raise ValueError("El formato de la fecha de pedido debe ser YYYY-MM-DD.")
        if valor>date.today() or valor> fr.date():
            raise ValueError("La fecha de pedido no puede estar en el futuro, ni ser más lejana que la fecha de recepción.")
        return valor

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
    __table_args__ = (
        # 🎯 BLINDAJE DE SALIDAS vivos:
        # Bloquea duplicados de órdenes de salida SOLO si el estado es 'VALIDO'.
        # Permite reutilizar el número si el registro histórico previo fue 'ANULADO'.
        Index(
            "ix_salidas_orden_estado_unique", 
            "orden_salida", 
            unique=True, 
            sqlite_where= text("estado = 'VALIDO'"),
            postgresql_where= text("estado = 'VALIDO'")
        ),
        {"extend_existing": True}
    )
    id_salida: Optional[int] = Field(default=None, primary_key=True)
    id_usuario: int = Field(foreign_key="usuarios.id_usuario", sa_column_kwargs={"nullable": False}) 
    fecha: datetime = Field(default_factory=datetime.now) 
    orden_salida: str = Field(max_length=100, sa_column_kwargs={"nullable": False}) # Recibe código de receta u Oficio de Comandancia
    paciente_destino: str = Field(max_length=150, sa_column_kwargs={"nullable": False}) # nombre del efectivo atendido o Destino institucional
    # Clasificación estructural para el Análisis Logístico (Evita sesgo de datos)
    # Valores esperados: "CONSUMO CLÍNICO", "TRASLADO PREVENTIVO", "PERDIDA POR CADUCIDAD"
    razon_salida: str = Field(sa_column_kwargs={"nullable": False})
    estado: Estado = Field(default=Estado.VALIDO) # Control de integridad transaccional (VALIDO / ANULADO)
    # RELACIONES DEL MODELO
    usuario: Optional[Usuarios] = Relationship(back_populates="salidas") 
    detalles: List["DetallesSalida"] = Relationship(back_populates="salida") 

    # 🧠 VALIDACIONES DE INTEGRIDAD DE DATOS (PYDANTIC)
    @field_validator("orden_salida", "paciente_destino", "razon_salida", mode="before")
    def validar_datos_salida(cls, valor, info):
        if valor is None:
            raise ValueError(f"El campo '{info}' en el acta de salida es obligatorio.")
        if isinstance(valor, str) and not valor.strip():
            raise ValueError(f"El campo '{info}' no puede procesarse vacío.")
        return valor.strip().upper()

class DetallesSalida(SQLModel, table=True): 
    __table_args__ = {"extend_existing": True}
    id_detalle_salida: Optional[int] = Field(default=None, primary_key=True)
    id_salida: int = Field(foreign_key="salidas.id_salida", ondelete="CASCADE", sa_column_kwargs={"nullable": False}) # Clave foránea al documento de salida maestro
    id_lote: int = Field(foreign_key="lotes.id_lote", sa_column_kwargs={"nullable": False})    
    cantidad: int = Field(sa_column_kwargs={"nullable": False}) 
    # Relaciones del Modelo DetallesSalida
    salida: Optional[Salidas] = Relationship(back_populates="detalles") # Conexión a la cabecera de la salida
    lote: Optional[Lotes] = Relationship(back_populates="detalles_salida") # Conexión al lote del insumo

    @field_validator("cantidad", mode="before")
    def validar_cantidad_salida(cls, valor):
        if valor is None:
            raise ValueError("La cantidad a despachar es obligatoria.")
        if int(valor) <= 0:
            raise ValueError("La cantidad solicitada en el renglón debe ser un entero mayor a cero (0).")
        return int(valor)


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


# -------------MIGRACIONES------------
"""
🚀 Paso 4: Generar tu Primera Migración Automática
Ahora que Alembic conoce tus modelos y tu archivo .db, puede comparar ambos estados. Imagina que agregaste una columna nueva a la tabla Insumos en tu código. Ejecutas en la terminal:

Bash


alembic revision --autogenerate -m "añadir_nueva_columna_a_insumos"
¿Qué acaba de pasar? Alembic inspeccionó tu código, detectó la diferencia con la base de datos física y creó un script de Python único dentro de la carpeta alembic/versions/. Si abres ese archivo, verás que tiene dos funciones:

upgrade(): Contiene las instrucciones SQL (como ALTER TABLE) para aplicar el cambio sin tocar el resto de los datos.

downgrade(): Contiene las instrucciones por si te arrepientes y deseas revertir el cambio al estado anterior.

💾 Paso 5: Aplicar los Cambios Físicamente
El paso anterior solo creó el plano de la modificación. Para inyectar los cambios en tu base de datos sin alterar los registros existentes, ejecuta:

Bash

alembic upgrade head
head significa "llévame a la versión más reciente disponible". Tu base de datos se actualizará instantáneamente en segundo plano preservando la integridad de la data histórica de tus lotes y despachos.
"""
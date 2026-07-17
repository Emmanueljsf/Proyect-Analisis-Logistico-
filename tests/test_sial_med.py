from datetime import date, datetime, timedelta
import pytest
from sqlmodel import Session
from bd.models import Insumos, Lotes, Entradas, Usuarios, Rol  # Asegúrate de verificar cómo se llama el rol en models.py
from CRUDs.crud_salidas import registrar_despacho_combinado_fefo # 
import hashlib
from CRUDs.crud_usuarios import autenticar_usuario

def test_1_ordenamiento_fefo_estricto(session: Session):
    """Prueba 1: Verifica el orden secuencial ascendente por vencimiento."""
    insumo = Insumos(nombre="PARACETAMOL 500MG", clasificacion_ved="V")
    session.add(insumo)
    session.commit()

    # Se añade 'ubicacion_fisica' obligatoria para cumplir con la restricción de SQLite
    lote_lejano = Lotes(
        id_insumo=insumo.id_insumo, 
        codigo_lote="LOT-LEJANO", 
        stock_disponible=50, 
        fecha_vencimiento=date.today() + timedelta(days=90), 
        ubicacion_fisica="ESTANTE A", 
        activo=True
    )

    lote_cercano = Lotes(
        id_insumo=insumo.id_insumo, 
        codigo_lote="LOT-CERCANO", 
        stock_disponible=30, 
        fecha_vencimiento=date.today() + timedelta(days=15), 
        ubicacion_fisica="ESTANTE B",
        activo=True
    )

    session.add(lote_lejano)
    session.add(lote_cercano)
    session.commit()
    
    # Aquí continúan tus aserciones assert...


def test_2_cortafuegos_caducidad_ignora_vencidos(session: Session):
    """Prueba 2: El sistema debe excluir lotes expirados en consumo clínico."""
    insumo = Insumos(nombre="AMOXICILINA 500MG", clasificacion_ved="E")
    session.add(insumo)
    session.commit()

    # 📌 CORRECCIÓN: Se añade 'ubicacion_fisica' a los lotes de prueba
    lote_vencido = Lotes(
        id_insumo=insumo.id_insumo, 
        codigo_lote="LOT-EXPIRADO", 
        stock_disponible=100, 
        fecha_vencimiento=date.today() - timedelta(days=5), 
        ubicacion_fisica="AREA DE AISLAMIENTO",
        activo=True
    )
    lote_vigente = Lotes(
        id_insumo=insumo.id_insumo, 
        codigo_lote="LOT-VIGENTE", 
        stock_disponible=100, 
        fecha_vencimiento=date.today() + timedelta(days=45), 
        ubicacion_fisica="ESTANTE A",
        activo=True
    )

    session.add(lote_vencido)
    session.add(lote_vigente)
    session.commit()
    
    # Aquí continúan tus aserciones...


def test_3_despacho_sobre_pedido_lanza_excepcion(session: Session):
    """Prueba 3: Solicitar más de lo existente debe disparar un ValueError."""
    insumo = Insumos(nombre="ATROPINA AMPOLLES", clasificacion_ved="V")
    session.add(insumo)
    session.commit()

    # Insertamos la entrada y el lote acoplados en un solo paso
    entrada = Entradas(id_usuario=1, fecha_pedido=date.today(), fecha_recepcion=datetime.now(), cantidad=10, estado="VALIDO")
    lote = Lotes(id_insumo=insumo.id_insumo, codigo_lote="LOT-ATROPINA", fecha_vencimiento=date.today() + timedelta(days=30), activo=True, ubicacion_fisica="ESTANTE B", entrada=entrada)
    session.add(lote)
    session.commit()

    lista_pedidos = [{"id_insumo": insumo.id_insumo, "cantidad": 50, "nombre_insumo": insumo.nombre}]

    # Si tu función retorna un diccionario con False en vez de romper, puedes evaluar el status, 
    # pero si esperas el ValueError estricto, asegúrate de pasar la sesión del test:
    with pytest.raises(ValueError):
        registrar_despacho_combinado_fefo(
            orden_salida="ACTA-001",
            paciente_destino="Destacamento 134",
            razon_salida="Consumo Clínico",
            id_usuario=1,
            lista_pedidos=lista_pedidos,
            session_externa=session
        )


def test_4_despacho_exitoso_fefo_reduce_stock(session: Session):
    """Prueba 4: Un despacho válido debe restar el stock y generar la hoja de ruta."""
    insumo = Insumos(nombre="IBUPROFENO 400MG", clasificacion_ved="V")
    session.add(insumo)
    session.commit()

    # Estructura limpia de entrada + lote
    entrada = Entradas(id_usuario=1, fecha_pedido=date.today(), fecha_recepcion=datetime.now(), cantidad=100, estado="VALIDO")
    lote = Lotes(id_insumo=insumo.id_insumo, codigo_lote="LOT-IBU-01", fecha_vencimiento=date.today() + timedelta(days=60), activo=True, ubicacion_fisica="ESTANTE C", entrada=entrada)
    session.add(lote)
    session.commit()

    lista_pedidos = [{"id_insumo": insumo.id_insumo, "cantidad": 40, "nombre_insumo": insumo.nombre}]

    resultado = registrar_despacho_combinado_fefo(
        orden_salida="ACTA-200",
        paciente_destino="Destacamento 134",
        razon_salida="Consumo Clínico",
        id_usuario=1,
        lista_pedidos=lista_pedidos,
        session_externa=session
    )

    assert isinstance(resultado, dict)
    assert resultado["status"] is True

    # 📌 EL TRUCO ACÁ: Forzamos a la sesión a recargar el lote completo,
    # lo que obliga a Python a volver a leer la lista de 'detalles_salida' desde SQLite
    session.expire(lote) 
    session.refresh(lote)
    
    assert lote.stock_disponible == 60


def test_5_autenticar_usuario_credenciales_invalidas(session: Session):
    """Prueba 5: Evalúa la denegación de acceso ante credenciales erróneas o correctas."""
    
    # Generamos el Hash SHA-256 de una contraseña real para simular el registro seguro
    password_plana = "Seguridad123"
    password_hasheada = hashlib.sha256(password_plana.encode()).hexdigest()

    usuario_real = Usuarios(
        nombres="Daniel",
        apellidos="Palencia",
        username="daniel_admin",
        password=password_hasheada, 
        rol=Rol.Administrador,  
        activo=True
    )
    session.add(usuario_real)
    session.commit()
    
    # 🧪 Caso A: Intentar ingresar con contraseña incorrecta
    resultado_falso = autenticar_usuario("daniel_admin", "ClaveIncorrecta", session_externa=session)
    assert resultado_falso == "Contraseña incorrecta"

    # 🧪 Caso B: Intentar ingresar con un usuario que no existe en el sistema
    resultado_fantasma = autenticar_usuario("usuario_inexistente", "Cualquiera123", session_externa=session)
    assert resultado_fantasma == "Usuario no encontrado"
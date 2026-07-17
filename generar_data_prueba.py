import random
from datetime import date, datetime, timedelta
from typing import Optional
from sqlmodel import Session, select, Field
from bd.models import Insumos, Lotes, Entradas, Salidas, DetallesSalida, Usuarios, Estado, Rol, engine
import hashlib

def Generar_datos_prueba():
    try:
        def encriptar_password(password: str) -> str:
            """Toma la contraseña en texto plano y devuelve su hash SHA-256 en hexadecimal."""
            return hashlib.sha256(password.encode("utf-8")).hexdigest()

        def poblar_sistema_con_data_realista():
            with Session(engine) as session:
                # 🔄 LIMPIADOR AUTOMÁTICO PARA PRUEBAS: Limpia el histórico viejo
                print("🗑️ Limpiando tablas para reestructurar el volumen de datos...")
                session.execute(select(DetallesSalida)).all() # Asegura el correcto mapeo
                
                if session.exec(select(Insumos)).first():
                    print("💡 Ya existen datos. Procediendo a refrescar el catálogo de simulación...")
                    session.query(DetallesSalida).delete()
                    session.query(Salidas).delete()
                    session.query(Entradas).delete()
                    session.query(Lotes).delete()
                    session.query(Insumos).delete()
                    session.commit()

                print("🧬 Iniciando simulación de carga logística calibrada para SIAL-MED...")

                # ======================================================================
                # 1. CREAR EL USUARIO ADMINISTRADOR RESPONSABLE
                # ======================================================================
                print("👤 Registrando usuario administrador de control militar...")
                usuario_admin = session.exec(select(Usuarios).where(Usuarios.username == "admin")).first()
                
                if not usuario_admin:
                    try:
                        # ENCRIPTACIÓN EN ACCIÓN: Pasamos "admin123" por sha256
                        password_seguro = encriptar_password("admin123")

                        usuario_admin = Usuarios(
                            nombres="tu nombre",
                            apellidos="tu apellido",
                            username="admin",
                            password=password_seguro,    # 👈 Se guardará un string largo de 64 caracteres alfa-numéricos
                            rol=Rol.Administrador, 
                            activo=True
                        )
                        session.add(usuario_admin)
                        session.flush() 
                    except Exception as e:
                        session.rollback()
                        usuario_admin = session.exec(select(Usuarios)).first()
                        if not usuario_admin:
                            print(f"🛑 Error crítico al gestionar el usuario: {str(e)}")
                            return

                # ======================================================================
                # 2. CATÁLOGO DE INSUMOS MÉDICOS REALES CON CLASIFICACIÓN VED
                # ======================================================================
                nombres_insumos = [
                    # VITALES (V)
                    ("Adrenalina 1mg/ml", "V"), ("Atropina 1mg/ml", "V"), ("Díazepam 10mg/2ml", "V"),
                    ("Hidrocortisona 100mg", "V"), ("Amiodarona 150mg", "V"), ("Lidocaína 2%", "V"),
                    ("Oxígeno Medicinal", "V"), ("Suero Fisiológico 0.9% 500ml", "V"), ("Ringer Lactato 500ml", "V"),
                    ("Dextrosa 5% 500ml", "V"), ("Insulina Cristalina", "V"), ("Fentanilo 0.5mg", "V"),
                    ("Morfina 10mg", "V"), ("Tramadol 100mg", "V"), ("Diclofenac Sódico 75mg", "V"),
                    # ESENCIALES (E)
                    ("Amoxicilina 500mg", "E"), ("Azitromicina 500mg", "E"), ("Ceftriaxona 1g", "E"), 
                    ("Ciprofloxacina 500mg", "E"), ("Losartán Potásico 50mg", "E"), ("Enalapril 20mg", "E"), 
                    ("Amlodipina 10mg", "E"), ("Metformina 850mg", "E"), ("Glibenclamida 5mg", "E"), 
                    ("Omeprazol 20mg", "E"), ("Ranitidina 50mg", "E"), ("Metoclopramida 10mg", "E"), 
                    ("Salbutamol Inhalador", "E"), ("Budesonida Inhalador", "E"), ("Loratadina 10mg", "E"), 
                    ("Cetirizina 10mg", "E"), ("Acetaminofén 500mg", "E"), ("Ibuprofeno 400mg", "E"), 
                    ("Ketoprofeno 100mg", "E"), ("Betametasona Crema", "E"),
                    # DESEABLES (D)
                    ("Complejo B Tabletas", "D"), ("Vitamina C 500mg", "D"), ("Ácido Fólico 5mg", "D"),
                    ("Sulfato Ferroso 200mg", "D"), ("Grasa Parafinada", "D"), ("Alcohol Antiséptico 70%", "D"),
                    ("Agua Oxigenada", "D"), ("Povidona Yodada Espuma", "D"), ("Gasas Estériles 10x10", "D"),
                    ("Vendas Elásticas 4\"", "D"), ("Adhesivo Médico", "D"), ("Jeringas 3ml", "D"),
                    ("Jeringas 5ml", "D"), ("Jeringas 10ml", "D"), ("Guantes de Examen", "D")
                ]

                lista_insumos = []
                for nombre, ved in nombres_insumos:
                    insumo = Insumos(nombre=nombre, clasificacion_ved=ved)
                    session.add(insumo)
                    lista_insumos.append(insumo)
                session.flush()

                hoy = date.today()
                fecha_inicio_sistema = hoy - timedelta(days=90)
                estantes_militares = ["Vitrina Urgencias A-1", "Estante Principal B-3", "Pasillo Logistico C", "Nevera de cadena de frio"]

                # ======================================================================
                # 3. ENTRADAS DE INVENTARIO EQUILIBRADAS (DÍA -90)
                # ======================================================================
                print("📦 Registrando inventario inicial proporcional (Día -90)...")
                lotes_creados = []
                mapeo_cantidades_iniciales = {}

                for i, insumo in enumerate(lista_insumos):
                    for num_lote in range(1, 3):
                        lead_time_simulado = random.randint(3, 7)
                        f_pedido = fecha_inicio_sistema - timedelta(days=lead_time_simulado)
                        f_recepcion_dt = datetime.combine(fecha_inicio_sistema, datetime.min.time())

                        # Escenario de Alertas de Caducidad
                        if "Adrenalina" in insumo.nombre and num_lote == 1:
                            f_vencimiento = hoy + timedelta(days=12)  
                        elif "Amoxicilina" in insumo.nombre and num_lote == 1:
                            f_vencimiento = hoy + timedelta(days=18)  
                        else:
                            f_vencimiento = hoy + timedelta(days=random.randint(15, 200))

                        lote = Lotes(
                            codigo_lote=f"LT-{insumo.id_insumo:02d}-{num_lote}",
                            id_insumo=insumo.id_insumo,
                            fecha_vencimiento=f_vencimiento,
                            ubicacion_fisica=random.choice(estantes_militares),
                            activo=True,
                            motivo_desactivacion=None
                        )
                        session.add(lote)
                        session.flush()

                        # 🧮 CALIBRACIÓN LOGÍSTICA DE ENTRADAS BASADA EN LA NUEVA ROTACIÓN:
                        if insumo.clasificacion_ved == "E":
                            # Esenciales (Máxima rotación): Entradas fuertes para soportar el alto volumen de despachos
                            cantidad_entrada = random.randint(180, 280) 
                        elif insumo.clasificacion_ved == "V":
                            # Vitales (Rotación media-alta): Cantidades para alternarse entre Óptimo y Reorden
                            cantidad_entrada = random.randint(130, 220)
                        else:
                            # Deseables (Baja rotación)
                            if "Guantes de Examen" in insumo.nombre:
                                # Forzamos a que este sea el único Deseable que quiebre a 0 u.
                                cantidad_entrada = random.randint(55, 75) 
                            else:
                                # Los demás deseables se mantienen estables porque se despachan poco
                                cantidad_entrada = random.randint(100, 180)

                        entrada = Entradas(
                            id_lote=lote.id_lote,
                            id_usuario=usuario_admin.id_usuario,
                            fecha_pedido=f_pedido,
                            fecha_recepcion=f_recepcion_dt,
                            cantidad=cantidad_entrada, 
                            estado=Estado.VALIDO
                        )
                        session.add(entrada)
                        
                        lotes_creados.append(lote)
                        mapeo_cantidades_iniciales[lote.id_lote] = cantidad_entrada

                session.flush()

                # ======================================================================
                # 4. SIMULACIÓN DE SALIDAS PONDERADAS POR CRITERIO DE USO (VED INVESTIGADO)
                # ======================================================================
                print("📈 Procesando 90 días con frecuencia de despachos: Esenciales > Vitales > Deseables...")

                destinos_militares = [
                    "Puesto de seguridad operativo Dabajuro", "Personal militar en guardia", 
                    "Luis Arraez", "Bob Abreu", "Miguel Cabrera", "José Altuve", "Maikel Garcia",
                    "Ronald Acuña", "Eugenio Suarez", 'Wilyer Abreu', 'Eduardo Rodriguez', 
                    'Daniel Palencia','Ezequiel Tovar','Javier Sanoja','Andrés Gimenez','Salvador Perez',
                    'Wilyan Contreras','Jackson Chourio', "Jefatura de Operaciones Dabajuro"
                ]
                
                conteo_oficios = 1
                fecha_cursor = fecha_inicio_sistema
                stock_virtual = {lote_id: cant for lote_id, cant in mapeo_cantidades_iniciales.items()}

                # 🎯 MAPEO DE PROBABILIDAD DE SER DESPACHADO (FRECUENCIA DE SELECCIÓN)
                # Esenciales (1.00) > Vitales (0.65) > Deseables (0.20)
                pesos_frecuencia = []
                for ins in lista_insumos:
                    if ins.clasificacion_ved == "E":
                        pesos_frecuencia.append(0.80)
                    elif ins.clasificacion_ved == "V":
                        pesos_frecuencia.append(0.55)
                    else:
                        pesos_frecuencia.append(0.35)
                
                while fecha_cursor < hoy:
                    transacciones_semana = random.randint(150, 250)
                    
                    for _ in range(transacciones_semana):
                        dia_aleatorio_semana = random.randint(0, 6)
                        fecha_salida_exacta = fecha_cursor + timedelta(days=dia_aleatorio_semana)
                        
                        if fecha_salida_exacta >= hoy:
                            continue

                        salida_maestra = Salidas(
                            id_usuario=usuario_admin.id_usuario,
                            fecha=fecha_salida_exacta,
                            orden_salida=f"OFICIO-GNB-134-{conteo_oficios:05d}",
                            paciente_destino=random.choice(destinos_militares),
                            razon_salida="Consumo Clínico",
                            estado=Estado.VALIDO
                        )
                        conteo_oficios += 1
                        session.add(salida_maestra)
                        session.flush()

                        # SELECCIÓN PONDERADA POR USO: Aumenta la probabilidad de aparición (despachos), no la cantidad por salida
                        k_insumos = random.randint(1, 2)
                        muestreo_inicial = random.choices(lista_insumos, weights=pesos_frecuencia, k=k_insumos)
                        # Eliminación de duplicados segura para SQLModel usando diccionario por ID
                        insumos_elegidos = list({ins.id_insumo: ins for ins in muestreo_inicial}.values())
                        
                        for insumo_en_turno in insumos_elegidos:
                            # La cantidad que se descuenta por salida se mantiene uniforme (3 a 7 unidades)
                            cantidad_a_despachar = random.randint(1, 6) 
                            
                            lotes_del_insumo = [l for l in lotes_creados if l.id_insumo == insumo_en_turno.id_insumo and l.activo]
                            lotes_ordenados_fefo = sorted(lotes_del_insumo, key=lambda x: x.fecha_vencimiento)
                            
                            for lote_elegido in lotes_ordenados_fefo:
                                if cantidad_a_despachar <= 0:
                                    break
                                    
                                stock_actual_lote = stock_virtual.get(lote_elegido.id_lote, 0)
                                if stock_actual_lote <= 0:
                                    continue
                                    
                                cantidad_efectiva = min(stock_actual_lote, cantidad_a_despachar)
                                stock_virtual[lote_elegido.id_lote] -= cantidad_efectiva
                                
                                if stock_virtual[lote_elegido.id_lote] == 0:
                                    lote_elegido.activo = False
                                    lote_elegido.motivo_desactivacion = "AGOTADO"
                                    session.add(lote_elegido)
                                    
                                detalle = DetallesSalida(
                                    id_salida=salida_maestra.id_salida,
                                    id_lote=lote_elegido.id_lote,
                                    cantidad=cantidad_efectiva
                                )
                                session.add(detalle)
                                cantidad_a_despachar -= cantidad_efectiva

                    fecha_cursor += timedelta(days=7)

                session.commit()
                print(f"🎉 [ÉXITO CENTRALIZADO] Poblamiento cronológico impecable. Frecuencias: E > V > D.")

    except Exception as e:
        print(f"Error crítico en la generacion de datos de prueba: {e}")

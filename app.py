import streamlit as st
from models import create_db_and_tables
from insumos1 import Insumos
from lotes import Vista_Control_Lotes
from entradas import Vista_Registrar_Entradas
from salidas import modal_registro_salida_fifo
from usuarios import Vista_gestion_usuarios
from login import Vista_Login
import pandas as pd
import re
import json # 📌 NUEVO: Para guardar y leer la sesión en un archivo local
import os # 📌 NUEVO: Para verificar si el archivo de sesión existe

# ==============================================================================
# 1. CONFIGURACIÓN DE PÁGINA E INICIALIZACIÓN
# ==============================================================================
st.set_page_config(page_title="SIAL-MED | Gestión de Insumos", layout="wide")
create_db_and_tables()

def cargar_css(archivo_css):
    try:
        with open(archivo_css, "r", encoding="utf-8") as f:
            st.markdown(f"<style>{f.read()}</style>", unsafe_allow_html=True)
    except FileNotFoundError:
        st.error(f"No se encontró el archivo de estilos: {archivo_css}")

cargar_css("styles.css")

# ==============================================================================
# 2. PERSISTENCIA DE SESIÓN LOGÍSTICA (EVITA CIERRES AL RECARGAR)
# ==============================================================================
SESSION_FILE = "session_cache.json" # Nombre del archivo JSON local donde se respaldará la sesión

def guardar_sesion_local():
    """Guarda los datos esenciales en el disco para soportar recargas de página."""
    datos = {
        "autenticado": st.session_state.get("usuario_autenticado", False), # Captura el estado actual de autenticación
        "rol": st.session_state.get("user_rol", None),                    # Captura el rol del usuario en la RAM
        "nombre": st.session_state.get("user_nombre_completo", "")        # Captura el nombre completo del operario
    }
    with open(SESSION_FILE, "w") as f: # Abre el archivo JSON en modo escritura
        json.dump(datos, f)            # Escribe las variables de la sesión de Streamlit en el disco

def cargar_sesion_local():
    """Recupera la sesión del archivo JSON si la página fue recargada."""
    if os.path.exists(SESSION_FILE): # Verifica si existe el archivo JSON de caché en la carpeta
        try:
            with open(SESSION_FILE, "r") as f: # Abre el archivo JSON en modo lectura
                datos = json.load(f)           # Convierte el texto del archivo en un diccionario Python
                
                # Forzamos la restauración directa de los datos en la memoria RAM de Streamlit
                st.session_state["usuario_autenticado"] = datos.get("autenticado", False)
                st.session_state["user_rol"] = datos.get("rol", None)
                st.session_state["user_nombre_completo"] = datos.get("nombre", "")
        except:
            pass # Si el archivo está corrupto o vacío, ignora el fallo y solicita credenciales

# 🔄 CONTROL DE FLUJO CRÍTICO: Sincronización automática de RAM y Disco
if "usuario_autenticado" not in st.session_state:
    cargar_sesion_local() # Intenta levantar los datos del JSON si el usuario recargó la página (F5)
    
    # Si tras revisar el archivo el usuario aún no está registrado en la RAM de Streamlit
    if "usuario_autenticado" not in st.session_state:
        st.session_state["usuario_autenticado"] = False # Inicializa la bandera de login en Falso (Cerrado)
        st.session_state["user_rol"] = None             # Inicializa el contenedor del rol en vacío
        st.session_state["user_nombre_completo"] = ""   # Inicializa el contenedor del nombre en vacío
else:
    # Si el usuario ya está autenticado y navegando de forma activa por la interfaz
    guardar_sesion_local() # Reescribe el JSON en cada clic para asegurar que mantenga el estado más reciente

# ==============================================================================
# 3. ENRUTADOR DE CONTROL DE ACCESO
# ==============================================================================
if not st.session_state["usuario_autenticado"]:
    Vista_Login()
    
    # Si el login fue exitoso en este ciclo, guardamos en el JSON inmediatamente
    if st.session_state["usuario_autenticado"]:
        guardar_sesion_local()

else:
    # 🔓 INTERFAZ DESBLOQUEADA (SIAL-MED)
    
    # ==========================================
    # 4. BARRA LATERAL (SIDEBAR DE NAVEGACIÓN)
    # ==========================================
    with st.sidebar:
        # 📌 LOGO EN MENÚ LATERAL: Muestra el escudo arriba del nombre del sistema
        c_logo, _ = st.columns([1, 2])
        with c_logo:
            st.image("media/emblema proyecto.jpg", use_container_width=True)
            
        st.markdown("<h1 style='color: #ef4444; margin-top: 0;'>SIAL-MED</h1>", unsafe_allow_html=True)
        st.markdown("<p style='font-size: 0.8rem;'>SISTEMA INTEGRAL DE LOGÍSTICA MÉDICA</p>", unsafe_allow_html=True)
        st.divider() 
        
        st.markdown(f"### 🎖️ Operador: \n**{st.session_state['user_nombre_completo']}**")
        st.caption(f"Privilegio: {st.session_state['user_rol']}") 
        st.divider()
        
        # 📌 MODIFICACIÓN: Separamos los módulos "Catálogo", "Lotes" y "Entradas"
        opciones_menu = [
            "📦 Catálogo Insumos", 
            "🔢 Lotes en Existencia", # Módulo enfocado en ver el stock y vencimientos
            "📥 Registrar Entradas" ,   # Módulo enfocado en los formularios de recepción
            'Salidas'
        ]
        
        if str(st.session_state["user_rol"]).startswith("Admin"):
            opciones_menu.append("👥 Gestión de Personal")
            
        menu = st.radio("MÓDULOS DE LOGÍSTICA", opciones_menu)
        st.divider()
        
        # Desencadena la intención de salir
        if st.button("🚪 Cerrar Sesión", use_container_width=True, type="secondary"):
            st.session_state["mostrar_modal_salida"] = True # Activa la bandera del modal

    # ==============================================================================
    # 5. MODAL DE CONFIRMACIÓN DE CIERRE DE SESIÓN
    # ==============================================================================
    if st.session_state.get("mostrar_modal_salida", False):
        @st.dialog("Confirmar Salida")
        def modal_confirmar_logout():
            st.write("⚠️ ¿Está seguro de que desea cerrar sesión en SIAL-MED? Se requerirán credenciales para volver a entrar.")
            c_si, c_no = st.columns(2)
            with c_si:
                if st.button("Sí, Salir", use_container_width=True, type="primary"):
                    # Limpiamos la RAM de Streamlit
                    st.session_state["usuario_autenticado"] = False 
                    st.session_state["user_rol"] = None 
                    st.session_state["mostrar_modal_salida"] = False
                    # Borramos el archivo físico JSON de persistencia
                    if os.path.exists(SESSION_FILE):
                        os.remove(SESSION_FILE)
                    st.rerun()
            with c_no:
                if st.button("Cancelar", use_container_width=True):
                    st.session_state["mostrar_modal_salida"] = False # Apaga el modal
                    st.rerun()
        
        modal_confirmar_logout() # Despliega el diálogo en pantalla

    # ==============================================================================
    # 6. EJECUCIÓN DE VISTAS SEGÚN SELECCIÓN DE NAVEGACIÓN
    # ==============================================================================
    if menu == "📦 Catálogo Insumos":
        Insumos()
        
    elif menu == "🔢 Lotes en Existencia":
        st.subheader("🔢 Consulta de Lotes e Inventario Disponible")
        st.caption("Filtros avanzados por fecha de vencimiento (FEFO) y ubicación física.")
        # Aquí llamarás a la función de lectura de lotes cuando la programemos
        Vista_Control_Lotes()
        
    elif menu == "📥 Registrar Entradas":
        Vista_Registrar_Entradas()
    
    elif menu=='Salidas':
        modal_registro_salida_fifo()
        
    elif menu == "👥 Gestión de Personal":
        Vista_gestion_usuarios()
        
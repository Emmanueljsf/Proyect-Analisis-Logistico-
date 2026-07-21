import re
import streamlit as st
from models import engine, Rol 

# --- Funciones auxiliares de seguridad ---

def sanitizar_input(valor: str, longitud_max=100) -> str:
    """Limpia entradas para prevenir inyecciones y limita longitud."""
    if not isinstance(valor, str): return ""
    return re.sub(r'[<>;\'"\\/]', '', valor[:longitud_max]).strip()


# Roles autorizados para alterar datos del catálogo médico
ROLES_AUTORIZADOS = [Rol.Administrador, Rol.Encargado]

def usuario_tiene_permiso_escritura() -> bool:
    """Evalúa los rangos en sesión para habilitar o bloquear la edición."""
    es_autenticado = st.session_state.get("usuario_autenticado", False)  # Revisa login
    rol_usuario = st.session_state.get("user_rol", None)  # Captura rol del usuario
    return es_autenticado and (rol_usuario in ROLES_AUTORIZADOS)  # Retorna permiso booleano


def es_administrador() -> bool:
    """Verifica si el usuario actual tiene rol de Administrador."""
    return st.session_state.get("user_rol") == Rol.Administrador
import streamlit as st
import CRUDs.crud_usuarios as crud_u  # Importamos la función de arriba
import time # 📌 NUEVO: Librería nativa para controlar el tiempo

def Vista_Login():
    
    # 📌 Creamos 3 columnas con proporciones [1, 1, 1] para que la del medio quede perfectamente centrada
    col_izq, col_centro, col_der = st.columns([2.2, 1.0, 2.2])
    with col_centro:
        # 📌 Renderiza la imagen en la columna central ocupando todo su ancho disponible
        st.image("media/emblema proyecto.jpg", use_container_width=True)

    st.markdown("<h2 style='text-align: center;'>🔐 SIAL-MED</h2>", unsafe_allow_html=True)
    st.markdown("<p style='text-align: center; color: gray;'>Sistema de Análisis Logístico de Insumos Médicos</p>", unsafe_allow_html=True)
    
    # Creamos un contenedor centrado y estético para el formulario
    with st.container(border=True):
        st.subheader("Inicio de Sesión")
        
        txt_user = st.text_input("Nombre de Usuario / Username:", placeholder="Ej: yuka")
        txt_pass = st.text_input("Contraseña del Sistema:", type="password", placeholder="••••••••")
        
        st.write("") # Espaciador manual
        
        if st.button("INGRESAR AL SISTEMA", use_container_width=True, type="primary"):
            if not txt_user or not txt_pass:
                st.warning("⚠️ Por favor, complete todos los campos obligatorios.")
            else:
                # Invocamos la función de validación del CRUD
                resultado = crud_u.autenticar_usuario(txt_user, txt_pass)
                
                # Evaluamos las respuestas posibles de la lógica de negocio
                if resultado == "Usuario no encontrado":
                    st.error("🛑 Usuario no encontrado.")
                elif resultado == "Contraseña incorrecta":
                    st.error('Contraseña incorrecta.')
                    
                elif resultado == "Cuenta inactiva":
                    st.error("🚫 Acceso Denegado: Esta cuenta de usuario ha sido desactivada por la administración.")
                    
                else:
                    # El login fue exitoso (resultado contiene el objeto usuario de SQLModel)
                    st.success(f"🔓 Bienvenido, {resultado.nombres.upper()}.")
                    
                    # Guardamos los metadatos esenciales en la memoria global de Streamlit
                    st.session_state["usuario_autenticado"] = True
                    st.session_state["user_id"] = resultado.id_usuario
                    st.session_state["user_rol"] = resultado.rol.value # Controla accesos a pestañas
                    st.session_state["user_nombre_completo"] = f"{resultado.nombres} {resultado.apellidos}"

                    # 2. 📌 EL TRUCO: Congelamos la ejecución por 1.5 segundos para que dé tiempo de leer
                    time.sleep(2.0)
                    
                    # Forzamos la recarga de Streamlit para que dibuje el menú principal del sistema
                    st.rerun()
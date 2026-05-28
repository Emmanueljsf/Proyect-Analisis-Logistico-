import streamlit as st
import CRUDs.crud_usuarios as crud_u # Conexión directa con las validaciones del backend
from models import Usuarios, Rol # Estructuras de datos nativas de SIAL-MED

def Vista_gestion_usuarios():
    # ==============================================================================
    # 1. CONTROL DE MEMORIA ESTRICTA PARA LOS OBJETIVOS DE LOS MODALES
    # ==============================================================================
    if "id_u_eliminar" not in st.session_state: 
        st.session_state["id_u_eliminar"] = None          # RAM: Guarda el ID del usuario a dar de baja
    if "id_u_editar" not in st.session_state: 
        st.session_state["id_u_editar"] = None            # RAM: Guarda el ID del usuario a editar

    # ==============================================================================
    # 2. CONTROLES SUPERIORES (FILTRADO Y ACCIÓN PRINCIPAL)
    # ==============================================================================
    st.title("👥 Control y Registro de Personal") 
    st.markdown("Gestión de operarios, privilegios de acceso y auditoría del sistema.")

    # 🔄 REDISEÑO: Añadimos una columna extra para el combobox de Estado (Dividimos en 4 columnas)
    c_buscar, c_rol, c_estado, c_btn = st.columns([2.5, 1.2, 1.1, 1.2]) 
    
    with c_buscar:
        search_user = st.text_input("Buscar", placeholder="🔍 Buscar por username...", label_visibility="collapsed")
    with c_rol:
        opciones_busqueda = ["TODOS"] + [r.value for r in Rol] 
        search_rol = st.selectbox("Rol", options=opciones_busqueda, label_visibility="collapsed")
        
    with c_estado:
        # 📌 NUEVO FILTRO: Controla el filtrado del estado lógico de los operarios
        search_estado = st.selectbox("Estado", options=["TODOS", "ACTIVOS", "INACTIVOS"], label_visibility="collapsed")
        
    with c_btn:
        if st.button("➕ NUEVO USUARIO", use_container_width=True, type="primary"):
            modal_registro_usuario() 

    st.divider() 

    # ==============================================================================
    # 3. PIPELINE DE FILTRADO EN MEMORIA
    # ==============================================================================
    lista_completa = crud_u.obtener_usuarios() 
    usuarios_filtrados = [] 

    for u in lista_completa:
        if search_user and search_user.lower() not in u.username.lower(): 
            continue 
        if search_rol != "TODOS" and u.rol.value != search_rol: 
            continue 
            
        # 📌 NUEVO FILTRO EN PIPELINE: Evalúa la columna booleana 'u.activo'
        if search_estado == "ACTIVOS" and not u.activo:
            continue # Salta si el filtro pide activos y el usuario es False
        if search_estado == "INACTIVOS" and u.activo:
            continue # Salta si el filtro pide inactivos y el usuario es True
            
        usuarios_filtrados.append(u) 

    # ==============================================================================
    # 4. RENDERIZADO DE TABLA COMPACTA ESTILIZADA
    # ==============================================================================
    if not usuarios_filtrados:
        st.info("No se encontraron usuarios que coincidan con los parámetros.")
    else:
        # 🔄 REDISEÑO: Ajustamos el tamaño relativo para acomodar la columna de Estado en el índice [3]
        prop_u = [1.2, 1.1, 1.4, 0.9, 0.5, 0.5] 
        st.markdown("<div class='tabla-insumos-contenedor'>", unsafe_allow_html=True)
        
        # --- ENCABEZADOS DE LA REJILLA ---
        cabecera = st.columns(prop_u)
        cabecera[0].markdown("<p class='tabla-cabecera'>NOMBRE COMPLETO</p>", unsafe_allow_html=True)
        cabecera[1].markdown("<p class='tabla-cabecera'>USERNAME</p>", unsafe_allow_html=True)
        cabecera[2].markdown("<p class='tabla-cabecera'>ROL / CONTACTO</p>", unsafe_allow_html=True)
        cabecera[3].markdown("<p class='tabla-cabecera'>ESTADO</p>", unsafe_allow_html=True) # 📌 NUEVA COLUMNA EN TABLA
        cabecera[4].markdown("<p class='tabla-cabecera' style='text-align:center;'>EDIT</p>", unsafe_allow_html=True)
        cabecera[5].markdown("<p class='tabla-cabecera' style='text-align:center;'>DEL</p>", unsafe_allow_html=True)
        st.markdown("<hr class='linea-separadora'>", unsafe_allow_html=True)

        # --- FILAS DINÁMICAS ---
        for idx, u in enumerate(usuarios_filtrados):
            col_nom, col_user, col_rol, col_est, col_edit, col_del = st.columns(prop_u)
            
            email_display = f" <br><small style='color:gray;'>✉️ {u.email}</small>" if u.email else ""
            col_nom.markdown(f"<p class='tabla-celda'>{u.nombres.upper()} {u.apellidos.upper()}</p>", unsafe_allow_html=True)
            col_user.markdown(f"<p class='tabla-celda-bold'>{u.username}</p>", unsafe_allow_html=True)
            col_rol.markdown(f"<p class='tabla-celda'>{u.rol.value}{email_display}</p>", unsafe_allow_html=True)
            
            # 📌 NUEVO: Lógica de renderizado para el Badge de Estado (Reutiliza clases CSS de badges si tienes)
            if u.activo:
                badge_html = "<span style='color:#238636; background-color:rgba(35,134,54,0.15); padding:3px 8px; border-radius:10px; font-size:12px; font-weight:bold;'>ACTIVO</span>"
            else:
                badge_html = "<span style='color:#da3633; background-color:rgba(218,54,51,0.15); padding:3px 8px; border-radius:10px; font-size:12px; font-weight:bold;'>INACTIVO</span>"
            col_est.markdown(f"<p class='tabla-celda'>{badge_html}</p>", unsafe_allow_html=True)
            
            with col_edit:
                if st.button("📝", key=f"btn_ed_u_{u.id_usuario}_{idx}", use_container_width=True):
                    st.session_state["id_u_editar"] = u.id_usuario 
                    modal_edicion_usuario() 
            with col_del:
                if st.button("❌", key=f"btn_dl_u_{u.id_usuario}_{idx}", use_container_width=True):
                    st.session_state["id_u_eliminar"] = u.id_usuario 
                    modal_confirmar_baja() 
            st.markdown("<hr class='linea-separadora'>", unsafe_allow_html=True)
        st.markdown("</div>", unsafe_allow_html=True)

# ==============================================================================
# DIÁLOGO FLOTANTE: REGISTRO DE NUEVO PERSONAL
# ==============================================================================
@st.dialog("➕ Registrar Nuevo Usuario")
def modal_registro_usuario():
    nom = st.text_input("Nombres:")
    ape = st.text_input("Apellidos:")
    usr = st.text_input("Username (Nombre de cuenta único):")
    pas = st.text_input("Contraseña inicial (Mínimo 8 caracteres):", type="password")
    email = st.text_input("Correo Electrónico (Opcional):")
    
    lista_roles_str = [r.value for r in Rol] # Convierte los enums a texto para el selectbox
    rol_seleccionado_str = st.selectbox("Rol del Sistema:", options=lista_roles_str)
    
    if st.button("Guardar Registro", use_container_width=True, type="primary"):
        if nom and ape and usr and pas: # Verifica campos obligatorios en el formulario
            rol_enum = next(r for r in Rol if r.value == rol_seleccionado_str) # Convierte el texto de vuelta a Enum
            nuevo_u = Usuarios(nombres=nom, apellidos=ape, username=usr, password=pas, rol=rol_enum, email=email)
            
            try:
                if crud_u.crear_usuario(nuevo_u): # Envía el objeto de negocio al backend
                    st.success("Usuario dado de alta exitosamente.")
                    st.rerun() # Refresca la vista principal para ver los cambios reflejados
            except ValueError as e:
                st.error(f"🛑 Error de validación: {e}") # Atrapa duplicados o fallos de robustez
        else:
            st.warning("Por favor, rellene los campos obligatorios obligatoriamente (Nombres, Apellidos, Username y Clave).")

@st.dialog("📝 Modificar Cuenta de Usuario")
def modal_edicion_usuario():
    id_target = st.session_state["id_u_editar"] # Extrae el ID guardado al pulsar el botón
    u_data = crud_u.obtener_usuario_por_id(id_target) # Va al backend a buscar el estado original
    
    nom = st.text_input("Nombres:", value=u_data.nombres)
    ape = st.text_input("Apellidos:", value=u_data.apellidos)
    usr = st.text_input("Username:", value=u_data.username) # Permite corregir el username si es necesario
    email = st.text_input("Correo Electrónico (Opcional):", value=u_data.email if u_data.email else "")
    
    lista_roles_str = [r.value for r in Rol]
    indice_actual = lista_roles_str.index(u_data.rol.value) # Calcula el índice para precargar el rol actual
    rol_seleccionado_str = st.selectbox("Rol del Sistema:", options=lista_roles_str, index=indice_actual)
    
    pas = st.text_input("Cambiar Contraseña (Dejar vacío para mantener la actual):", type="password")
    
    # 📌 NUEVO: Interruptor visual para activar/desactivar la cuenta del operador militar
    # value=u_data.activo precarga el estado booleano (True/False) que está guardado en SQLite
    cuenta_activa = st.toggle("Cuenta de usuario activa", value=u_data.activo, help="Desactiva para bloquear el acceso al sistema sin borrar su historial.")
    
    if st.button("Actualizar Información", use_container_width=True, type="primary"):
        rol_enum = next(r for r in Rol if r.value == rol_seleccionado_str) # Mapea string a Enum
        
        # Mapea los campos modificados e incorpora el nuevo estado booleano
        cambios = {
            "nombres": nom, 
            "apellidos": ape, 
            "username": usr, 
            "email": email, 
            "rol": rol_enum,
            "activo": cuenta_activa # 📌 NUEVO: Envía el True o False capturado del st.toggle
        }
        
        if pas: # Si escribió caracteres en el input, se incorpora para actualización de clave
            cambios["password"] = pas
            
        try:
            if crud_u.actualizar_usuario(id_target, cambios): # Lanza la actualización al CRUD
                st.success("Cambios aplicados de forma conforme.")
                st.rerun() # Recarga la interfaz general con la grilla fresca
        except ValueError as e:
            st.error(f"🛑 Error de validación: {e}") # Atrapa choques de nombres de usuario duplicados

# ==============================================================================
# DIÁLOGO FLOTANTE: CONFIRMACIÓN DE DESTRUCCIÓN DE REGISTRO
# ==============================================================================
@st.dialog("⚠️ Confirmar Baja de Usuario")
def modal_confirmar_baja():
    id_target = st.session_state["id_u_eliminar"] # Recupera el ID objetivo de la memoria
    u_data = crud_u.obtener_usuario_por_id(id_target) # Trae sus detalles para personalizar la advertencia
    
    st.warning(f"¿Está seguro de eliminar de forma permanente la cuenta de '{u_data.username}'?")
    st.info("Esta acción revocará de inmediato sus accesos a la plataforma de suministros.")
    
    c_si, c_no = st.columns(2)
    with c_si:
        if st.button("SÍ, ELIMINAR", use_container_width=True, type="primary"):
            if crud_u.eliminar_usuario(id_target): # Ordena la purga en SQLite
                st.success("Registro destruido de la base de datos.")
                st.rerun() # Fuerza la actualización de la grilla de fondo
            else:
                st.error("No se puede borrar: El usuario posee historial de transacciones activas en auditoría.")
    with c_no:
        if st.button("CANCELAR", use_container_width=True):
            st.rerun() # Simplemente recarga el script para cerrar el modal limpiamente
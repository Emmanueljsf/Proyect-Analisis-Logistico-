import streamlit as st
import CRUDs.crud_usuarios as crud_u # Conexión directa con las validaciones del backend
from bd.models import Usuarios, Rol # Estructuras de datos nativas de SIAL-MED
import pandas as pd

def Vista_gestion_usuarios():
    try:

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


        # ==============================================================================
        # 1. CONTROL DE MEMORIA ESTRICTA PARA LOS OBJETIVOS DE LOS MODALES
        # ==============================================================================
        if "id_u_eliminar" not in st.session_state: 
            st.session_state["id_u_eliminar"] = None          # RAM: Guarda el ID del usuario a dar de baja
        if "id_u_editar" not in st.session_state: 
            st.session_state["id_u_editar"] = None            # RAM: Guarda el ID del usuario a editar

        # 1. TÍTULO CON DINAMISMO INICIAL
        contenedor_titulo = st.empty()
        st.caption("Gestión integral de operarios, privilegios y estado de cuenta.")

        # 2. PANEL DE FILTROS DESPLEGABLE
        with st.expander("🔍 Buscador Universal de Personal", expanded=True):
            c_buscar, c_rol, c_estado, c_btn = st.columns([1.8, 1.5, 1.1, 1]) 
            
            with c_buscar:
                search_user = st.text_input("Buscar por username:", placeholder="🔍 Ej: admin", key="f_txt_buscar")
            with c_rol:
                opciones_rol = ["TODOS"] + [r.value for r in Rol] 
                search_rol = st.selectbox("Rol", options=opciones_rol, key="f_opt_rol")
            with c_estado:
                search_estado = st.selectbox("Estado", options=["TODOS", "ACTIVOS", "INACTIVOS"], key="f_opt_estado")
            with c_btn:
                # Botón de creación 
                st.write('')
                if st.button("➕ NUEVO USUARIO", type="primary"):
                    modal_registro_usuario() 
        

        st.divider() 

        # 3. CONSULTA AL BACKEND (Procesa el filtrado en una sola línea)
        usuarios_filtrados = crud_u.obtener_usuarios_filtrados(
            txt_buscar=search_user,
            rol_buscado=search_rol,
            estado_buscado=search_estado
        )

        # 4. TÍTULO ACTUALIZADO SEGÚN BACKEND
        contenedor_titulo.markdown(
            f"<h2 style='margin-bottom: 0;'>👥 Control de Personal ({len(usuarios_filtrados)} registros filtrados)</h2>", 
            unsafe_allow_html=True
        )


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
            
            # Interruptor visual para activar/desactivar la cuenta del operador militar
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
                    "activo": cuenta_activa # Envía el True o False capturado del st.toggle
                }
                
                if pas: # Si escribió caracteres en el input, se incorpora para actualización de clave
                    cambios["password"] = pas
                    
                try:
                    if crud_u.actualizar_usuario(id_target, cambios): # Lanza la actualización al CRUD
                        st.success("Cambios aplicados de forma conforme.")
                        st.rerun() # Recarga la interfaz general con la grilla fresca
                except ValueError as e:
                    st.error(f"🛑 Error de validación: {e}") # Atrapa choques de nombres de usuario duplicados
        
        # 5. RENDERIZADO RESPONSIVE CON DATAFRAME SELECCIONABLE
        if not usuarios_filtrados:
            st.info("No se encontraron usuarios que coincidan con los parámetros.")
        else:
            st.markdown("Seleccione un usuario para editar.")

            # Preparamos los datos para el DataFrame
            data = [{
                "NOMBRE": f"{u.nombres.upper()} {u.apellidos.upper()}",
                "USERNAME": u.username,
                "ROL": u.rol.value,
                "ESTADO": "ACTIVO" if u.activo else "INACTIVO",
                "ID_REF": u.id_usuario # ID oculto para referencia interna
            } for u in usuarios_filtrados]

            df = pd.DataFrame(data)

            # Configuramos la tabla
            event = st.dataframe(
                df,
                column_config={
                    "ID_REF": None, # Ocultamos la columna del ID
                    "ESTADO": st.column_config.TextColumn("ESTADO", help="Estado actual en sistema"),
                },
                use_container_width=True,
                hide_index=True,
                selection_mode="single-row",
                on_select="rerun"
            )

            # Lógica de Selección y Edición
            if event.selection["rows"]:
                idx_seleccionado = event.selection["rows"][0]
                usuario_seleccionado = usuarios_filtrados[idx_seleccionado]
                
                st.divider()
                st.subheader(f"Acciones para: {usuario_seleccionado.username}")
                
                col_btn, _= st.columns([1.5,4])
                with col_btn:
                    if st.button("📝 Editar Usuario", type="primary", use_container_width=True):
                        st.session_state["id_u_editar"] = usuario_seleccionado.id_usuario
                        modal_edicion_usuario()



        

        

       

    except Exception as e:
            print(f"Error crítico en la vista de Usuarios: {e}")
            st.error(f"Error crítico en la vista de Usuarios: {e}")
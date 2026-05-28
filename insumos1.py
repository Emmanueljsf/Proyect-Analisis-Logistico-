import streamlit as st
import CRUDs.crud_insumos as crud_insumos  # Importación del controlador backend para persistencia y consultas SQL
import pandas as pd
import re 

# ==============================================================================
# CONFIGURACIÓN DE SEGURIDAD GENERAL (RBAC)
# ==============================================================================
# Lista explícita de las cadenas de texto (Strings) de roles con privilegios de escritura
ROLES_AUTORIZADOS = ["Administrador", "Encargado del area"]

def usuario_tiene_permiso_escritura() -> bool:
    """
    Analiza el estado de la sesión activa para validar el rango del operador.
    
    Retorna:
        bool: True si el usuario inició sesión y tiene un rol autorizado; False si es de solo lectura.
    """
    # Recuperación segura de variables de estado de la memoria RAM de Streamlit
    es_autenticado = st.session_state.get("usuario_autenticado", False)
    rol_usuario = st.session_state.get("user_rol", None)
    
    # Comprobación de doble factor: verificación de login activo y pertenencia a la lista de privilegios
    return es_autenticado and (rol_usuario in ROLES_AUTORIZADOS)

def Insumos():
    """
    Componente de Interfaz de Usuario para el catálogo base de insumos médicos.
    Administra la presentación de datos, búsquedas dinámicas, filtros y seguridad por roles.
    """
    # Consulta al backend: trae todos los registros de la tabla Insumos con carga ansiosa de lotes.
    lista_insumos = crud_insumos.obtener_todos_insumos()  

    # Determinar los permisos del usuario de forma atómica para este ciclo de renderizado
    tiene_permisos = usuario_tiene_permiso_escritura()

    # ==============================================================================
    # 1. CONTROL DE MEMORIA (SESSION STATE) - ALMACENAMIENTO DE OBJETIVOS
    # ==============================================================================
    if "id_a_eliminar" not in st.session_state:
        st.session_state["id_a_eliminar"] = None          # RAM: Almacena temporalmente el ID del insumo a borrar
    if "id_a_editar" not in st.session_state:
        st.session_state["id_a_editar"] = None            # RAM: Almacena temporalmente el ID del insumo a editar

    # ==============================================================================
    # 2. CONTROL DE MEMORIA PARA BUSCADORES (SESSION STATE)
    # ==============================================================================
    if "txt_buscar_nombre" not in st.session_state:
        st.session_state["txt_buscar_nombre"] = ""        # RAM: Conserva el texto de búsqueda entre ciclos de renderizado
    if "sb_criticidad_ved" not in st.session_state:
        st.session_state["sb_criticidad_ved"] = "TODOS"   # RAM: Conserva el filtro de criticidad seleccionado

    # ==============================================================================
    # 3. DIÁLOGOS MODALES PROTEGIDOS (DISPARO DIRECTO CON @ST.DIALOG)
    # ==============================================================================

    @st.dialog("📦 Registrar Nuevo Insumo")
    def modal_registro():
        """Formulario flotante limpio para la inserción de nuevos insumos base."""
        # Capa de Seguridad Interna: Si se burla la UI, el modal aborta de inmediato sin alterar la BD
        if not usuario_tiene_permiso_escritura():
            st.error("🛑 Operación rechazada: Su rol no posee permisos de escritura.")
            return

        with st.form("form_nuevo", border=False):
            nombre = st.text_input("Nombre completo del Insumo")
            ved = st.selectbox("Clasificación VED", options=["V", "E", "D"])
            st.caption("Asegúrese de que el nombre coincida con el catálogo oficial.")
            
            c1, c2 = st.columns(2)
            if c1.form_submit_button("💾 GUARDAR REGISTRO", use_container_width=True, type='primary'):
                if nombre.strip():
                    crud_insumos.crear_insumo(nombre.strip(), ved) # Envía los datos limpios al backend CRUD
                    st.rerun() # Fuerza recarga para pintar el insumo insertado en la tabla inmediatamente
                else:
                    st.error("El nombre es obligatorio.")
            if c2.form_submit_button("❌ CANCELAR", use_container_width=True):
                st.rerun() 


    @st.dialog("📝 Modificar Insumo Médico")
    def modal_edicion_rapida():
        """Formulario flotante acoplado al ID en memoria para mutación de atributos."""
        # Capa de Seguridad Interna: Bloqueo de actualización fraudulenta
        if not usuario_tiene_permiso_escritura():
            st.error("🛑 Operación rechazada: Su rol no posee permisos de edición.")
            return

        id_edit = st.session_state["id_a_editar"] # Extrae de la RAM el ID que guardó el botón editar
        insumo_edit = next(i for i in lista_insumos if i.id_insumo == id_edit) # Localiza el objeto correspondiente
        
        with st.form("form_edicion_directa", border=False):
            st.write(f"Modificando Registro Código ID: **{id_edit}**")
            nuevo_nom = st.text_input("Nombre del Insumo", value=insumo_edit.nombre)
            nueva_crit = st.selectbox("Clasificación VED", options=["V", "E", "D"], index=["V", "E", "D"].index(insumo_edit.clasificacion_ved))
            
            c1, c2 = st.columns(2)
            if c1.form_submit_button("💾 GUARDAR CAMBIOS", use_container_width=True):
                if nuevo_nom.strip():
                    crud_insumos.actualizar_insumo(id_edit, nuevo_nom.strip(), nueva_crit) # Actualiza la fila en SQLite
                    st.rerun() 
            if c2.form_submit_button("❌ CANCELAR", use_container_width=True):
                st.rerun()


    @st.dialog("⚠️ Confirmar Eliminación de Registro")
    def modal_confirmar_borrado():
        """Ventana de confirmación de destrucción física de filas en el catálogo."""
        # Capa de Seguridad Interna: Bloqueo de destrucción física de tuplas
        if not usuario_tiene_permiso_escritura():
            st.error("🛑 Operación rechazada: Su rol no posee permisos de eliminación.")
            return

        id_del = st.session_state["id_a_eliminar"] # Extrae de la RAM el ID que guardó el botón borrar
        insumo_del = next((i for i in lista_insumos if i.id_insumo == id_del), None)
        
        if insumo_del:
            st.warning(f"⚠️ **¿Está seguro de eliminar '{insumo_del.nombre.upper()}'?**")
            st.write("Esta acción destruirá el registro en la base de datos de forma permanente.")
            
            c1, c2 = st.columns(2)
            if c1.button("✔️ SÍ, ELIMINAR", use_container_width=True, type="primary"):
                crud_insumos.eliminar_insumo(id_del) # Purga física de la fila en SQLite
                st.toast("Insumo eliminado.", icon="🗑️") 
                st.rerun() 
            if c2.button("❌ CANCELAR", use_container_width=True):
                st.rerun()

    # ==============================================================================
    # 4. BARRA DE CONTROLES SUPERIORES (FILTRADO Y BÚSQUEDA)
    # ==============================================================================
    c_nombre_master, c_ved, c_btn = st.columns([3.0, 1.5, 1.5])
    
    with c_nombre_master:
        col_input, col_lupa, col_reset = st.columns([3.0, 0.6, 0.6])
        with col_input:
            search_nombre = st.text_input(
                "Nombre del Insumo", 
                value=st.session_state["txt_buscar_nombre"], 
                placeholder="Escriba nombre del insumo...", 
                label_visibility="collapsed",
                key="input_nombre_catalogo"
            )
        with col_lupa:
            st.button("🔍", key="btn_ejecutar_lupa", use_container_width=True)
        with col_reset:
            if st.button("🔄", key="btn_limpiar_filtros", use_container_width=True):
                st.session_state["txt_buscar_nombre"] = ""      
                st.session_state["sb_criticidad_ved"] = "TODOS" 
                st.rerun()
        
    with c_ved:
        opciones_ved = ["TODOS", "V", "E", "D"]
        idx_actual = opciones_ved.index(st.session_state["sb_criticidad_ved"]) 
        
        search_ved = st.selectbox(
            "Criticidad (VED)", 
            options=opciones_ved, 
            index=idx_actual, 
            label_visibility="collapsed",
            key="filtro_ved" 
        )
        
    with c_btn:
        # 📌 RESTRICCIÓN VISUAL 1: El botón de registro se muestra verde si es un rol válido.
        # De lo contrario, dibuja un candado informativo de solo lectura (Modo Consulta).
        if tiene_permisos:
            if st.button("➕ REGISTRAR INSUMO", use_container_width=True, type="primary"):
                modal_registro()
        else:
            st.info("🔒 Modo Lectura")

    st.divider()

    # Sincronizamos los inputs dinámicos con el session_state
    st.session_state["txt_buscar_nombre"] = search_nombre
    st.session_state["sb_criticidad_ved"] = search_ved

    # Pipeline de filtrado secuencial en memoria
    if not search_nombre and search_ved == "TODOS":
        insumos_filtrados = lista_insumos.copy()
    else:
        insumos_filtrados = []
        for insumo in lista_insumos:
            if search_nombre and search_nombre.lower() not in insumo.nombre.lower():
                continue
            if search_ved != "TODOS" and insumo.clasificacion_ved.value.upper() != search_ved:
                continue
            insumos_filtrados.append(insumo)

    # Cabecera dinámica con contadores
    st.title(f"📦 Catálogo de Insumos ({len(insumos_filtrados)} / {len(lista_insumos)})")
    st.markdown("Gestione los productos base del inventario médico del **Destacamento 134**.")

    # ==============================================================================
    # 5. MOTOR DE RENDERIZADO DE TABLA HÍBRIDA POR PERMISOS
    # ==============================================================================
    if not insumos_filtrados:
        st.info("No se encontraron registros que coincidan con los filtros de búsqueda.")
    else:
        # 📌 RESTRICCIÓN VISUAL 2: Si el usuario tiene permisos, se define espacio para EDIT/DEL (0.5 cada uno).
        # Si es un rol no autorizado, se eliminan esas columnas y el nombre se estira (5.2) para aprovechar la pantalla.
        if tiene_permisos:
            proporciones = [0.6, 4.2, 2.0, 1.7, 0.5, 0.5]
        else:
            proporciones = [0.6, 5.2, 2.5, 2.1]

        st.markdown("<div class='tabla-insumos-contenedor'>", unsafe_allow_html=True)

        with st.container():
            encabezado = st.columns(proporciones)
            encabezado[0].markdown("<p class='tabla-cabecera'>ID</p>", unsafe_allow_html=True)
            encabezado[1].markdown("<p class='tabla-cabecera'>NOMBRE DEL PRODUCTO</p>", unsafe_allow_html=True)
            encabezado[2].markdown("<p class='tabla-cabecera'>CRITICIDAD (VED)</p>", unsafe_allow_html=True)
            encabezado[3].markdown("<p class='tabla-cabecera'>TOTAL STOCK</p>", unsafe_allow_html=True)
            
            # Encabezados operativos condicionales
            if tiene_permisos:
                encabezado[4].markdown("<p class='tabla-cabecera' style='text-align:center;'>EDIT</p>", unsafe_allow_html=True)
                encabezado[5].markdown("<p class='tabla-cabecera' style='text-align:center;'>DEL</p>", unsafe_allow_html=True)
            
            st.markdown("<hr class='linea-separadora'>", unsafe_allow_html=True)

            for idx, insumo in enumerate(insumos_filtrados): 
                crit = insumo.clasificacion_ved.value.upper()
                
                if crit == "V":
                    ved_html = "<div class='badge-base badge-rojo'>VITAL (V)</div>"
                elif crit == "E":
                    ved_html = "<div class='badge-base badge-amarillo'>ESENCIAL (E)</div>"
                else:
                    ved_html = "<div class='badge-base badge-verde'>DESEABLE (D)</div>"
                    
                stock_html = f"<p class='tabla-celda'>{insumo.total_stock} unds.</p>"

                # Inicialización de la fila según la cantidad de celdas resueltas por las proporciones
                celdas_fila = st.columns(proporciones)
                celdas_fila[0].markdown(f"<p class='tabla-celda'>{insumo.id_insumo}</p>", unsafe_allow_html=True)
                celdas_fila[1].markdown(f"<p class='tabla-celda-bold'>{insumo.nombre.upper()}</p>", unsafe_allow_html=True)
                celdas_fila[2].markdown(ved_html, unsafe_allow_html=True)
                celdas_fila[3].markdown(stock_html, unsafe_allow_html=True)
                
                # 📌 RESTRICCIÓN VISUAL 3: Dibujar los botones interactivos únicamente si el rol está autorizado
                if tiene_permisos:
                    with celdas_fila[4]:
                        if st.button("📝", key=f"btn_edit_{insumo.id_insumo}_{idx}", use_container_width=True):
                            st.session_state["id_a_editar"] = insumo.id_insumo  
                            modal_edicion_rapida()  
                    
                    with celdas_fila[5]:
                        if st.button("❌", key=f"btn_del_{insumo.id_insumo}_{idx}", use_container_width=True):
                            st.session_state["id_a_eliminar"] = insumo.id_insumo  
                            modal_confirmar_borrado()  
                
                st.markdown("<hr class='linea-separadora'>", unsafe_allow_html=True)
                
        st.markdown("</div>", unsafe_allow_html=True)
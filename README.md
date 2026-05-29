### 👥 Diagrama de Casos de Uso
```mermaid
graph LR
    subgraph Actores
        Admin((Administrador))
        Encargado((Encargado de Área))
        Consultor((Consultor <br>Otras Áreas))
    end

    subgraph SIAL-MED [sistema de Analisis Logistico para control de insumos medicos]
        UC1(Gestionar Usuarios)
        UC2(Gestionar Insumos)
        UC3(Gestionar Lotes)
        UC4(Registrar Entradas)
        UC5(Registrar Salidas)
        UC6(Notificar Salida<br>vía Gmail)
        UC7(Iniciar Sesión)
        UC8(Validar Datos / Credenciales)
        UC9(Consultar Insumos, Lotes, Movimientos)
        UC10(Visualizar Indicadores y Dashboards)
    end

    Admin --> Encargado
    Admin --> UC1

    Encargado --> Consultor
    Encargado --> UC2
    Encargado --> UC3
    Encargado --> UC4
    Encargado --> UC5

    UC5 -.->|include <br> Si es Vital| UC6

    Consultor --> UC7
    Consultor --> UC9
    Consultor --> UC10

    UC7 -.->|include| UC8

---

### 2. Diagrama Entidad-Relación (Basado en `diagrama entidad-relacion3 proyecto (2).png`)

```markdown
### 🗄️ Diagrama Entidad-Relación
```mermaid
erDiagram
    Insumos {
        int id_insumo PK
        string nombre
        string clasificacion_ved
    }

    Usuarios {
        int id_usuario PK
        string nombres
        string apellidos
        string username
        string password
        string rol
        string email
        boolean activo
    }

    Lotes {
        int id_lote PK
        int id_insumo FK
        string codigo_lote
        date fecha_vencimiento
        string ubicacion_fisica
    }

    Entradas {
        int id_entrada PK
        int id_lote FK
        int id_usuario FK
        date fecha_pedido
        date fecha_recepcion
        int cantidad
    }

    Salidas {
        int id_salida PK
        int id_usuario FK
        date fecha
        string orden_medica
        string paciente
    }

    DetallesSalida {
        int id_detalle_salida PK
        int id_salida FK
        int id_lote FK
        int cantidad
    }

    Insumos ||--|{ Lotes : "tiene"
    Lotes ||--|{ Entradas : "recibe"
    Usuarios ||--|{ Entradas : "registra"
    Lotes ||--|{ DetallesSalida : "incluido_en"
    Salidas ||--|{ DetallesSalida : "compone"
    Usuarios ||--|{ Salidas : "despacha"

---

### 3. Diagrama de Arquitectura (Basado en `image_1b9c43.png`)

```markdown
### 🏗️ Diagrama de Arquitectura
```mermaid
graph TD
    subgraph Entorno Local (Destacamento 134)
        subgraph Capa de Presentación (Frontend / UX)
            Streamlit[Interfaz Streamlit]
            Plotly[Dashboards Plotly]
            Streamlit <-->|Renderiza Gráficos Interactivos| Plotly
        end

        subgraph Capa de Lógica de Negocio (Backend)
            Auth[Gestor de Autenticación]
            Controlador[Controlador de Inventario y Despacho]
            Pandas[Motor Analítico Pandas]
            
            Auth -->|Inyecta Estado de Sesión<br>st.session_state| Controlador
            Streamlit -->|Invocación Nativa<br>Módulos Python| Auth
            Streamlit -->|Envía datos de formularios<br>Llamada a Funciones| Controlador
            Controlador <-->|Encapsula / Invoca| Pandas
            Pandas -->|Provee matrices depuradas<br>y filtradas por Rol| Plotly
        end

        subgraph Capa de Datos (Persistencia)
            SQLite[(SQLite Engine<br>Modo WAL Activo)]
            Tablas[Tablas Relacionales]
            SQLite --- Tablas
        end
    end

    Controlador -->|Escritura Atómica<br>Transacciones CRUD| SQLite
    SQLite -->|Provee datos crudos SQLModel| Controlador

    classDef note fill:#fffde6,stroke:#eee3a3,stroke-width:1px;
    Nota[Punto de Control Central:<br>Verifica Roles y Permisos antes<br>de permitir consultas o escrituras.]:::note
    Controlador --- Nota

---

### 4. Diagrama de Secuencia (Basado en `image_1b9c24.png`)

```markdown
### ⏱️ Diagrama de Secuencia: Registro de Salida Médica
```mermaid
sequenceDiagram
    autonumber
    actor U as Operador Logístico<br>(Enfermero/Farmacéutico)
    participant F as Interfaz Streamlit<br>(Vistas)
    participant C as Controlador de Inventario<br>y Despacho (CRUDs)
    participant M as Motor Analítico<br>(Pandas en RAM)
    participant D as SQLite Engine<br>(Modo WAL)
    participant S as Servicio SMTP<br>(Hilo Secundario)

    U->>F: 1 Introduce Orden Médica, Paciente y Cantidad
    F->>C: 2 registrar_despacho_combinado_fifo(datos)
    
    Note over C: Validación 1: Verificar Existencias Físicas
    C->>D: 3 Consultar lotes disponibles (id_insumo)
    D-->>C: 4 Retorna lista de lotes y cantidades

    alt Triste: Cantidad Solicitada > Stock Disponible
        C-->>F: 5 Retorna "ERROR: Stock insuficiente"
        F-->>U: 6 Renderiza st.error("Stock insuficiente")
    else Disponible OK
        Note over C: Validación 2: Regla de Negocio VED (RN-05)
        alt Triste: Insumo V o E SIN datos de orden/paciente
            C-->>F: 7 Retorna "ERROR: Campos obligatorios vacíos"
            F-->>U: 8 Renderiza st.warning("Complete campos obligatorios")
        else de Negocio Aprobadas
            Note over C: Inicio de Transacción Atómica en Base de Datos
            C->>D: 9 INSERT Salidas & DetallesSalida (Descuento de Stock)
            D-->>C: 10 Transacción Exitosa (Commit)
            
            opt Insumo es de Clasificación "V" (Vital)
                C->>S: 11 Disparar hilo en segundo plano (Thread)
                Note over S: El flujo principal continúa inmediatamente.<br>No congela la pantalla si el servidor web tarda.
                S-->>U: 12 Enviar correo de alerta en background
            end
            
            C-->>F: 13 Retorna Estado Exitoso y Hoja de Ruta
            F-->>U: 14 Muestra st.success() y Guía de Recolección en Pantalla
        end
    end

    Note over U, S: PROCESAMIENTO ANALÍTICO BAJO DEMANDA (FUERA DEL FLUJO VIVO)
    Note over U: El operador decide abrir la pestaña del Dashboard
    U->>F: 15 Selecciona ver Reportes Analíticos
    F->>C: 16 obtener_metricas_rendimiento()
    Note over C: Pandas se ejecuta bajo demanda,<br>NO durante el despacho diario.
    C->>D: 17 SELECT histórico de movimientos
    D-->>C: 18 Retorna filas crudas
    C->>M: 19 Cargar DataFrame y calcular Lead Time / Stock Mínimo
    M-->>C: 20 Retorna matrices optimizadas y depuradas
    C-->>F: 21 Entrega datos listos para Plotly
    F-->>U: 22 Renderiza gráficos interactivos de consumo

---

### 5. Diagramas de Flujo (Basados en `image_1b9c1c.png` e `image_1b9be4.png`)

#### Flujo A: Proceso de Salida de Insumos Médicos
```markdown
### 🔄 Diagrama de Flujo 1: Salida de Insumos Médicos
```mermaid
graph TD
    A([ ]) --> B[Seleccionar lote]
    B --> C[Ingresar cantidad a despachar]
    C --> D{¿Hay stock suficiente?}
    
    D -- No --> E[Mostrar alerta de stock insuficiente]
    E --> F([ ])
    
    D -- Sí --> G{¿Insumo es Vital o Esencial?}
    
    G -- Sí --> H[Solicitar Orden Médica y Paciente]
    H --> I{¿Datos completos?}
    I -- No --> J[Mostrar alerta: Datos Requeridos]
    J --> K[Reingresar Orden/Paciente]
    K --> I
    I -- Sí --> L[Aplicar criterio FEFO]
    
    G -- No --> L
    
    classDef note fill:#fffde6,stroke:#eee3a3,stroke-width:1px;
    Nota[Salida rápida para<br>insumos Deseables]:::note
    G --- Nota
    
    L --> M[Actualizar cantidad en tabla Lotes]
    M --> N[Registrar movimiento en tabla Salidas]
    N --> O{¿Es clasificación Vital?}
    
    O -- Sí --> P[Enviar alerta automática vía Gmail]
    O -- No --> Q([ ])
    P --> Q

#### Flujo B: Procesamiento Analítico del Inventario
```markdown
### 📊 Diagrama de Flujo 2: Procesamiento Analítico de Inventario
```mermaid
graph TD
    A([ ]) --> B[Solicitar reporte de inventario]
    B --> C[Pandas extrae datos de la DB]
    C --> D[Cálculo de frecuencia de consumo]
    D --> E[Asignar categoría VED Vital, Esencial, Deseable]
    E --> F[Generar indicadores de rendimiento KPIs]
    F --> G[Renderizar gráficos interactivos con Plotly]
    G --> H{¿Existen alertas de stock crítico?}
    
    H -- si --> I[Resaltar insumos en color rojo/alerta]
    H -- no --> J[Mostrar Dashboard final]
    I --> J
    J --> K([ ])
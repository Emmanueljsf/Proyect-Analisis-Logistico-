# SIAL-MED: Aplicación Web de Análisis Logístico para el Control de Insumos Médicos

### 🏥 Destacamento 134 de la Guardia Nacional Bolivariana (Dabajuro, Edo. Falcón)

---

## 📝 Descripción General

**SIAL-MED** es una plataforma web de ingeniería y analítica logística diseñada para optimizar, controlar y auditar el flujo de inventario médico del **Destacamento 134 de la GNB**. El sistema mitiga la incertidumbre en el reabastecimiento mediante el cálculo automatizado de métricas como el *Lead Time* de proveedores, la aplicación de la matriz de criticidad VED (Vital, Esencial, Deseable) y la ejecución de algoritmos de despacho basados estrictamente en el criterio **FEFO** (*First Expired, First Out*).

Además, el sistema cuenta con un módulo de gobernanza que restringe acciones según el rol del usuario y dispara alertas automatizadas por protocolo SMTP (Gmail) en tiempo real cuando ocurren salidas de insumos clasificados como **Vitales**.

> ⚠️ **Nota de Estado del Proyecto:** El sistema se encuentra actualmente en su **fase de desarrollo y construcción activa** (Avance #3). Se ha consolidado con éxito la arquitectura base, la estructura de persistencia local, las políticas de gobernanza, el pipeline de integración continua y la paridad de entornos. Los módulos avanzados de interfaz de usuario y analítica matemática se irán expandiendo en los próximos ciclos de trabajo.

---

## 🛠️ Arquitectura del Sistema (Doc-as-Code)

La arquitectura de SIAL-MED está programada en su totalidad utilizando bloques sintácticos de **Mermaid.js**, permitiendo su renderizado nativo y dinámico dentro de la interfaz de GitHub sin depender de imágenes externas.

### 1. Diagrama Entidad-Relación
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
    Lotes ||--|| Entradas : "tiene"
    Usuarios ||--|{ Entradas : "registra"
    Lotes ||--|{ DetallesSalida : "incluido_en"
    Salidas ||--|{ DetallesSalida : "compone"
    Usuarios ||--|{ Salidas : "despacha"
```
---

### 2. Diagrama de Casos de Uso
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
```
---

### 3. Diagrama de Arquitectura 
```mermaid
flowchart TB
    subgraph Entorno ["Entorno Local (Destacamento 134)"]
        
        subgraph Pres ["Capa de Presentación (Frontend / UX)"]
            Streamlit["Interfaz Streamlit"]
            Plotly["Dashboards Plotly"]
            Plotly -->|"Renderiza Gráficos Interactivos"| Streamlit
        end

        subgraph Back ["Capa de Lógica de Negocio (Backend)"]
            Auth["Gestor de Autenticación"]
            Controlador["Controlador de Inventario y Despacho"]
            Pandas["Motor Analítico (Pandas)"]
            
            Auth -->|"Inyecta Estado de Sesión (st.session_state)"| Controlador
            Controlador -->|"Encapsula / Invoca"| Pandas
        end

        subgraph Persistencia ["Capa de Datos"]
            SQLite[("SQLite Engine (Modo WAL Activo)")]
            Tablas["Tablas Relacionales"]
            SQLite --- Tablas
        end

    end

    %% Conexiones directas entre los componentes principales
    Streamlit -->|"Invocación Nativa"| Auth
    Streamlit -->|"Envía datos de formularios"| Controlador
    Pandas -->|"Provee matrices depuradas"| Plotly

    Controlador -->|"Escritura Atómica"| SQLite
    SQLite -->|"Provee datos crudos"| Controlador

    %% Nota de control
    PuntoControl["Punto de Control Central: Verifica Roles y Permisos antes de permitir consultas o escrituras."]
    Controlador --- PuntoControl

    %% Estilos sencillos para evitar errores de compilación
    classDef nota fill:#fffde6,stroke:#eee3a3,stroke-width:1px;
    class PuntoControl nota;
```
---

### 4. Diagrama de Secuencia 

### ⏱Diagrama de Secuencia: Registro de Salida Médica
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
```
---

### 5. Diagramas de Flujo 

### 🔄 Diagrama de Flujo: Registro de Salida Médica 
```mermaid
flowchart TD
    %% Definición de Estilos de Nodos
    classDef inicioFin fill:#1f1f1f,stroke:#43a047,stroke-width:2px,color:#ffffff;
    classDef proceso fill:#121212,stroke:#43a047,stroke-width:1px,color:#ffffff;
    classDef decision fill:#1a1a1a,stroke:#43a047,stroke-width:1px,color:#ffffff;

    %% Nodos Principales
    Start([●]):::inicioFin
    
    %% Bucle de Selección de Insumos
    SelectInsumo["Seleccionar insumo"]:::proceso
    IngresarCant["Ingresar cantidad a despachar"]:::proceso
    CheckStock{"¿Hay stock suficiente?"}:::decision
    AnexarInsumo["Anexar insumo al despacho"]:::proceso
    AlertStock["Mostrar alerta de stock insuficiente"]:::proceso
    
    CheckMasInsumos{"¿Desea anexar más insumos?"}:::decision
    ContinuarReg["Continuar agregando"]:::proceso

    %% Bloque de Datos obligatorios
    SolicitarDatos["Solicitar Orden Médica y Paciente"]:::proceso
    CheckDatos{"¿Datos completos?"}:::decision
    ReingresarDatos["Reingresar Orden/Paciente"]:::proceso

    %% Bloque de Persistencia y Cierre
    AplicarFEFO["Aplicar criterio FEFO"]:::proceso
    MostrarResumen["Mostrar resumen de la salida en pantalla"]:::proceso
    RegSalida["Registrar movimiento en tabla Salidas"]:::proceso
    ActLotes["Actualizar cantidad en tabla Lotes"]:::proceso
    
    CheckVital{"¿Existe algún insumo de<br>clasificación Vital?"}:::decision
    AlertaGmail["Enviar alerta automática vía Gmail"]:::proceso
    End([●]):::inicioFin

    %% ==========================================
    %% ENLACES Y LOGICA DE FLUJO (Fiel a la imagen)
    %% ==========================================
    Start --> SelectInsumo
    SelectInsumo --> IngresarCant
    IngresarCant --> CheckStock
    
    CheckStock -- Sí --> AnexarInsumo
    CheckStock -- No --> AlertStock
    
    AnexarInsumo --> Merge1{" "}:::decision
    AlertStock --> Merge1
    style Merge1 fill:none,stroke:none;
    
    Merge1 --> CheckMasInsumos
    
    CheckMasInsumos -- Sí --> ContinuarReg
    ContinuarReg --> SelectInsumo
    
    CheckMasInsumos -- No --> Merge2{" "}:::decision
    style Merge2 fill:none,stroke:none;
    
    Merge2 --> SolicitarDatos
    SolicitarDatos --> CheckDatos
    
    CheckDatos -- No --> ReingresarDatos
    ReingresarDatos --> SolicitarDatos
    
    CheckDatos -- Sí --> AplicarFEFO
    
    AplicarFEFO --> MostrarResumen
    MostrarResumen --> RegSalida
    RegSalida --> ActLotes
    ActLotes --> CheckVital
    
    CheckVital -- Sí --> AlertaGmail
    CheckVital -- No --> End
    AlertaGmail --> End
```

#### Flujo B: Procesamiento Analítico del Inventario
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
```
---


🚀 Guía de Instalación Determinista
El objetivo de esta guía es garantizar que cualquier desarrollador pueda desplegar y operar el sistema de forma autónoma en el menor tiempo posible, obteniendo un entorno local idéntico al de producción.

Requisitos Mínimos del Sistema
Python 3.8 (o superior) instalado globalmente.

Git instalado y configurado en la máquina local.

Pasos Exactos para el Despliegue Local
Clonar el repositorio oficial:

Bash
   git clone [https://github.com/Emmanueljsf/Proyect-Analisis-Logistico-.git](https://github.com/Emmanueljsf/Proyect-Analisis-Logistico-.git)
   cd Proyect-Analisis-Logistico-

Crear e inicializar el entorno virtual aislado:
Esto evita conflictos con librerías globales de la máquina.

Bash
   python -m venv env
   # En Windows (Ejecutar en PowerShell):
   .\env\Scripts\Activate.ps1
   # En Linux / macOS:
   source env/bin/activate

Instalar las dependencias del proyecto:
La instalación es determinista y utiliza las versiones exactas congeladas en el manifiesto.

Bash
   pip install --upgrade pip
   pip install -r requirements.txt

Configurar el archivo de variables de entorno:
Cree una copia local de la plantilla de configuración (el archivo .env real está protegido por el .gitignore y jamás se subirá al repositorio público).

Bash
   cp .env.example .env

Nota: Proceda a abrir el archivo .env generado con su editor de texto y rellene las credenciales SMTP locales con sus datos de prueba personalizados.

Iniciar el servidor local de SIAL-MED:
Bash
   streamlit run app.py

   
🔑 Configuración de Variables de Entorno
El sistema se rige bajo el principio de paridad de entornos. A continuación se detalla el propósito de cada variable requerida en el archivo .env para la correcta inicialización del software:

PORT: Puerto de red para la escucha de la aplicación web (Valor por defecto: 8501).

ENVIRONMENT: Define el comportamiento del sistema frente a errores y logs (development para depuración local o production para despliegue final).

DATABASE_URL: Cadena de conexión para el mapeo relacional de datos (sqlite:///Control_insumos.db).

EMAIL_HOST: Dirección del servidor de salida para el protocolo de correos (smtp.gmail.com).

EMAIL_PORT: Puerto para conexiones seguras cifradas bajo TLS (587).

EMAIL_USER: Cuenta de correo emisora encargada de enviar las alertas de insumos críticos del destacamento.

EMAIL_PASSWORD: Contraseña de aplicación segura de 16 caracteres generada desde la suite de seguridad de Google Account.

📜 Bitácora de Cambios (Changelog Basado en Commits)
Este proyecto no cuenta con una bitácora escrita de forma manual; el historial de desarrollo se explica de forma autónoma y transparente a través de los mensajes del control de versiones. Gracias a la metodología GitFlow y al estándar de Conventional Commits, cada confirmación en el código define con precisión el progreso técnico del sistema:

feat(ci): Inicialización del flujo de integración continua en la nube a través de GitHub Actions (.github/workflows/ci.yml), encargado de validar la sintaxis de Python (compileall) de manera automática ante cada Pull Request.

docs(architecture): Migración y programación completa de los diagramas de casos de uso, capas y flujos de SIAL-MED en el archivo principal utilizando la sintaxis pura de Mermaid.js (Doc-as-Code).

config(env): Estructuración de las políticas de paridad de entornos mediante la configuración estricta del archivo .gitignore y el diseño de la plantilla técnica .env.example.

docs(governance): Redacción del archivo regulatorio CONTRIBUTING.md para establecer de forma obligatoria las reglas de Peer Review, nomenclatura de ramas auxiliares (feature/, bugfix/, docs/) y formato de confirmaciones.
# ==============================================================================
# SIAL-MED: ARTEFACTO INMUTABLE EN PRODUCCIÓN (PYTHON 3.8)
# ==============================================================================
FROM python:3.8-slim

# Evitar escritura de bytecode y habilitar logs en tiempo real
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

WORKDIR /app

# Instalar herramientas esenciales del sistema y curl para el Healthcheck
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Copiar e instalar dependencias del entorno de ejecución
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copiar el código del sistema completo
COPY . .

# Crear el directorio seguro y persistente para la base de datos SQLite
RUN mkdir -p /app/data

EXPOSE 8501

# Ejecución del servidor Streamlit en modo Producción
CMD ["streamlit", "run", "main.py", "--server.port=8501", "--server.address=0.0.0.0"]
# Guía de Contribución - SIAL-MED

Este documento establece las reglas obligatorias para el desarrollo y flujo de trabajo del sistema SIAL-MED en el Destacamento 134 de la GNB.

## 1. Estándar de Ramas (GitFlow Simplificado)
Queda totalmente prohibido realizar cambios directamente en la rama `main`. Todo desarrollo debe hacerse en ramas auxiliares siguiendo esta nomenclatura:
* **Nuevas Características:** `feature/nombre-modulo` (Ej: `feature/salidas-fifo`)
* **Corrección de Errores:** `bugfix/nombre-error` (Ej: `bugfix/alerta-stock`)
* **Documentación y Diagramas:** `docs/nombre-tarea` (Ej: `docs/diagramas-mermaid`)

## 2. Mensajes de Historial (Conventional Commits)
Para mantener una bitácora de cambios clara, cada confirmación de código (`git commit`) debe usar una estructura fija en minúsculas: `tipo(módulo): descripción corta`.

### Tipos Permitidos:
* `feat`: Una nueva funcionalidad (Ej: `feat(salidas): implementar algoritmo de descuento fifo`)
* `fix`: Reparación de un error de código (Ej: `fix(lotes): corregir validacion de cantidad ingresada`)
* `docs`: Cambios exclusivos en la documentación (Ej: `docs(gantt): actualizar matriz de actividades`)
* `config`: Modificaciones de configuración básica (Ej: `config(env): inicializar env.example`)
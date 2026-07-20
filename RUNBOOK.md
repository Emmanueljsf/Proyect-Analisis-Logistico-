# RUNBOOK: Sistema SIAL-MED (Destacamento 134)

## Fase #1: Diagnóstico (Salud del Sistema)
* **Verificación de Entorno:** SQLite requiere acceso al sistema de archivos. Verificar presencia del archivo:
  `ls -lh Control_insumos.db`
* **Salud del Proceso:** Confirmar que la aplicación Streamlit está corriendo:
  `ps aux | grep streamlit`
* **Log de Trazabilidad:** Revisar errores detectados por el sistema (formato JSON):
  `cat sialmed_errors.log`

## Fase #2: Protocolo ante Caídas (Contención)
1. **Identificación:** Si el usuario reporta error, buscar el UUID asociado en `sialmed_errors.log` mediante `grep [UUID] sialmed_errors.log`.
2. **Ciclo de Reinicio:** 
   * Si la app no responde, forzar reinicio: `pkill -f streamlit` y relanzar con `streamlit run app.py`.
3. **Bloqueo por Concurrencia:** Si aparece `database is locked`, borrar archivos de journal creados por SQLite para liberar bloqueos:
   `rm Control_insumos.db-journal`

## Fase #3: Recuperación ante Desastres (Regla 3-2-1)
Procedimiento para recreación total del entorno:
1. **Reinicio de Esquema:** Si el archivo `.db` se pierde o corrompe, la función `create_db_and_tables()` de `app.py` reconstruirá automáticamente las tablas al iniciar la aplicación[cite: 8].
2. **Inyección de Data Maestra:** Ejecutar el script de poblado de datos para restaurar la integridad operativa del destacamento:
   `python genera_data_prueba.py`
3. **Validación:** Acceder al módulo "Análisis Logístico" para verificar que las métricas de stock y caducidad sean consistentes.
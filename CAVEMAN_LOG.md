# Trazabilidad de Agentes sin Prosa: El Caveman Log (`CAVEMAN_LOG.md`)

Este estándar define el mecanismo de memoria persistente externa diseñado para registrar las actividades y cambios funcionales realizados por agentes de IA dentro de un repositorio de código, reduciendo la deriva de contexto y facilitando la rotación de modelos cognitivos.

---

## 1. Fundamentos y Propósito

Los agentes autónomos sufren de **deriva de contexto cognitivo**. A medida que una conversación de chat se alarga, el modelo olvida decisiones tomadas en pasos previos, alucina sobre la ubicación de componentes recién creados o revierte cambios sutiles realizados por humanos o IAs predecesoras.

`CAVEMAN_LOG.md` actúa como un **disco duro de contexto**. Es una bitácora redactada en un dialecto "caveman" (ultra-simplificado, modular, sin prosa explicativa ni adornos lingüísticos). 

### Por qué funciona
* **Lectura ultrarrápida:** Un agente puede consumir las últimas 3 entradas del log en menos de 500 tokens de contexto y entender el 100% del estado vivo del proyecto.
* **Trazabilidad multimodelo:** Permite alternar la ejecución de tareas entre diferentes modelos (ej. usar un modelo potente como Claude 3.5 Sonnet para diseño y un modelo rápido como Gemini 2.5 Flash para pruebas) sin perder el hilo de ejecución.

---

## 2. Plantilla de Bitácora para `CAVEMAN_LOG.md`

Toda entrada en el log debe respetar de forma estricta el siguiente formato:

```markdown
# Caveman Log

> Bitácora estructurada para consumo de modelos de código. Una entrada por actividad.
> Formato estrictamente fijo. Sin prosa decorativa ni explicaciones extensas.

---

## Entrada [Número de Entrada Correlativo, ej. 008]
Fecha: [AAAA-MM-DD]
Modelo: [Nombre y Versión de la IA, ej. Gemini 2.5 Flash]
Actividad: [ID de la Tarea] — [Breve Descripción de la Actividad]
Archivos tocados:
  - [Ruta relativa del archivo 1] ([creado / modificado / eliminado])
  - [Ruta relativa del archivo 2]
Qué hice:
  - [Acción técnica 1, ej. Implementé validador de claims en quality_harness.py]
  - [Acción técnica 2, ej. Agregué 5 casos de prueba unitarios en test_quality.py]
Por qué:
  - [Explicación técnica / Justificación del diseño de software adoptado]
Qué falta:
  - [Tareas pendientes críticas para la siguiente fase o agente]
Qué no tocar:
  - [Directivas explícitas de preservación de código legacy o sensible]
Estado: [Listo para revisión / En desarrollo / Tests pasando]
```

---

## 3. Feedback Crítico y Recomendaciones de Mejora

### Evaluación Crítica de la Práctica Actual
* **Fortaleza:** Es simple, humana y sumamente efectiva. Actúa como el puente perfecto entre el historial de Git (que suele ser demasiado atómico o descriptivo del código crudo) y los tableros de Jira/Trello (que suelen ser demasiado abstractos).
* **Debilidad (Vulnerabilidad):** **Mantenimiento manual.** Requiere que el agente "recuerde" actualizar el log de forma honesta. Si el agente comete un error, puede documentar acciones que no corresponden con los cambios reales en el código de Git, rompiendo la confiabilidad del log.

### Propuestas de Mejora para Ingeniería de Alto Nivel

1. **Auto-Generación del Log vía Git Diff Parser:**
   Elimine el error humano y de alucinación del agente. Implemente una herramienta o script Python local en el entorno del agente que compare el `git diff` de la rama actual contra `main`, extraiga los cambios físicos reales y use un prompt de compresión semántica rápido para auto-redactar el bloque `Archivos tocados` y `Qué hice` del log.
   
   ```python
   # scripts/generate_caveman_entry.py
   import subprocess
   
   def generate_entry():
       # Obtiene archivos modificados en staged
       diff_files = subprocess.check_output(["git", "diff", "--name-status", "--cached"]).decode()
       # Invocación rápida al LLM pasando el diff e indicando el formato fijo
       entry_draft = call_fast_llm_parser(diff_files)
       append_to_caveman_log(entry_draft)
   ```

2. **Ventana Dinámica de Contexto para Agentes (Context Windowing):**
   No le pases todo el historial de `CAVEMAN_LOG.md` (que puede medir miles de líneas) al agente. Configura un script de lectura que recorte el archivo dinámicamente y solo le inyecte al agente las **últimas N entradas activas** en su system prompt de inicio, ahorrando sustancialmente latencia y costos de procesamiento.

3. **Verificación Estática del Log en CI/CD:**
   Agregue una prueba en su suite de integración continua que valide que toda Pull Request que modifique código contenga obligatoriamente una nueva entrada correlativa en `CAVEMAN_LOG.md` y que los archivos listados en el bloque `Archivos tocados` coincidan exactamente con los archivos modificados en la PR de Git.

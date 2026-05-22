# El Bucle Metodológico: Framework TCAD (Traducir, Contexto, Abordaje, Desarrollo + Documentación)

Este estándar define el framework de pensamiento sistemático que regula cómo se procesa un requerimiento desde el lenguaje natural hasta la ejecución en código, previniendo la inyección de soluciones redundantes o parches de baja calidad.

---

## 1. Fundamentos y Propósito

TCAD nace para combatir el **código espagueti inductivo** generado por Inteligencia Artificial. Los agentes suelen programar de manera impulsiva: leen un problema, infieren una solución rápida y parchan archivos sin comprender la arquitectura global del sistema.

TCAD divide el flujo de desarrollo en 4 compuertas secuenciales rígidas que forzan al agente a reflexionar, inspeccionar y estructurar antes de escribir código:

```markdown
  [Traducir]         --> Entender la necesidad del usuario y fijar la métrica de éxito.
       |
  [Contexto]         --> Investigar el repositorio para reutilizar y evadir zonas sensibles.
       |
  [Abordaje]         --> Diseñar contratos de datos e interfaces limpias. (Aprobación humana)
       |
  [Desarrollo + Doc] --> Codificar de manera limpia y escribir la bitácora técnica.
```

---

## 2. Plantilla de Operación para Agentes bajo TCAD

Cuando asigne una tarea al agente, este debe responder estructurando su plan de trabajo en base a este documento:

```markdown
# PROPUESTA DE IMPLEMENTACIÓN BAJO FRAMEWORK TCAD

## 1. T — Traducir (Comprensión del Requerimiento)
- **Problema de Negocio / Técnico:** [Explicar qué dolor o necesidad resuelve].
- **Criterio de Aceptación Humano:** [Especificar qué comportamiento visible validará el usuario].
- **Límites de Ambigüedad:** [Qué partes quedan fuera del alcance y qué suposiciones se hacen].

## 2. C — Contexto (Inspección del Repositorio)
- **Componentes y Clases Reutilizables:** [Listar archivos que ya resuelven problemas similares, ej. base_store.py].
- **Restricciones Activas:** [Indicar contratos o bases de datos existentes que debemos respetar].
- **Zonas de Peligro Identificadas:** [Archivos sensibles que NO deben alterarse en esta tarea].

## 3. A — Abordaje / Arquitectura (Diseño Técnico Propueto)
- **Contratos de Datos Nuevos o Modificados:**
  ```python
  # Definición de Pydantic o TypeScript de entrada/salida
  class NewFeaturePayload(BaseModel):
      id: str
      value: float
  ```
- **Flujo de Ejecución e Interacción:** [Esquema del flujo, ej. API -> Caso de Uso -> Repositorio -> DB].
- **Plan de Pruebas Automatizadas:** [Ej. Comandos y casos de prueba exactos que se desarrollarán].

> [!IMPORTANT]
> **Espera de Aprobación Humana:** Detener ejecución aquí. El usuario debe revisar el Abordaje. Una vez aprobado con "GO", continuar con la fase D.

## 4. D — Desarrollar + Documentar (Ejecución y Cierre)
- **Código Desarrollado:** [Proceder con la codificación limpia].
- **Resultado de Pruebas:** [Pegar snippet de pytest / npm test pasando exitosamente].
- **Documentación de Bitácora:** [Actualizar CAVEMAN_LOG.md con la entrada correspondiente].
```

---

## 3. Feedback Crítico y Recomendaciones de Mejora

### Evaluación Crítica de la Práctica Actual
* **Fortaleza:** Excelente separación de responsabilidades. Detener la ejecución en el "Abordaje" (fase A) para obtener la aprobación del desarrollador humano ahorra horas de refactorización y previene errores catastróficos.
* **Debilidad (Vulnerabilidad):** La fase "A" (Abordaje) carece de una compuerta de validación semántica automatizada. Depende exclusivamente del ojo del revisor humano. Si el revisor humano está cansado o aprueba por inercia, se pueden colar malas arquitecturas.

### Propuestas de Mejora para Ingeniería de Alto Nivel

1. **Automatización de Contratos del Abordaje:**
   El agente no debería solo proponer el código en markdown. Debe generar un **archivo de especificación temporal (draft)** en un directorio aislado (ej. `/temp/contracts/draft_schema.json`). Un validador automático del sistema puede analizar este esquema temporal y certificar que cumple con las reglas básicas del proyecto (ej. que no use tipados prohibidos o que no viole la estructura de herencia corporativa) antes de presentarlo al humano.

2. **Integración con Herramientas de Modelado de LLM (Strict Schema Output):**
   Durante la fase A, fuerza al agente a exportar la arquitectura en formatos estandarizados como OpenAPI (para APIs REST) o diagramas Mermaid estructurados. Puedes usar scripts locales para validar sintácticamente los diagramas Mermaid, asegurando que no haya ciclos de dependencia o arquitecturas circulares en la propuesta de la IA.

3. **Métrica de Cobertura de Reutilización (Reuse Coverage Score):**
   Introduce en la fase C una métrica automatizada donde el agente deba reportar qué porcentaje del código propuesto reutiliza APIs ya existentes. Si el agente propone crear una función para formatear fechas cuando ya existe `date_helper.py`, el sistema de IA debe penalizar la propuesta por baja reutilización y forzar un rediseño de la fase A.

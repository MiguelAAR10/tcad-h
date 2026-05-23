# Gobernanza Funcional por Hitos de Desarrollo: Las Phase Cards (Fichas de Fase)

Este estándar define el mecanismo de control de hitos funcionales que regula y acota el desarrollo incremental de software, impidiendo que los agentes de IA introduzcan código desalineado de los planes maestros.

---

## 1. Fundamentos y Propósito

En proyectos asistidos por IA, los agentes suelen sufrir de **sobreacoplamiento o anticipación funcional** (ej. intentar implementar pasarelas de pago o APIs avanzadas cuando la base de datos de usuarios ni siquiera ha sido validada). Esto provoca código muerto, deudas técnicas masivas e incompatibilidades.

Las **Phase Cards** (Fichas de Fase) actúan como **compuertas funcionales de graduación**. Dividen el roadmap maestro en hitos discretos y autónomos. 

### La Regla de Oro
> [!IMPORTANT]
> Un agente tiene estrictamente prohibido escribir código o proponer soluciones correspondientes a la **Fase N+1** si todos los criterios de aceptación, pruebas unitarias y documentación técnica de la **Fase N** no han sido validados con éxito y aprobados por el humano.

---

## 2. Plantilla Estándar para Fichas de Fase (`Phase Card Template`)

Cada fase activa del proyecto debe documentarse bajo un archivo markdown dedicado (ej. `/docs/phases/phase_001_poblacion_sintetica.md`) usando esta plantilla:

```markdown
# FICHA DE FASE: Phase 00[X] — [Nombre del Hito Funcional]

## 1. Declaración de Objetivos y Alcance
- **Objetivo Principal:** [Resumen de lo que se debe lograr al finalizar esta fase].
- **Criterios de Aceptación Funcionales (Checklist):**
  - [ ] Requerimiento 1 (ej. El motor debe generar 100 perfiles sintéticos en < 2 segundos).
  - [ ] Requerimiento 2 (ej. Guardado determinístico de perfiles en Firestore/Memoria).

## 2. Contratos y Esquemas Obligatorios
Para graduar esta fase, se deben validar y respetar los siguientes contratos de datos:
- [ ] Esquema JSON / Modelo Pydantic: `schemas/synthetic_profile.json`
- [ ] Interfaz de API HTTP: `POST /api/demo/profiles/generate`

## 3. Zonas de Archivos Autorizadas
El agente solo tiene autorización para crear o modificar los siguientes archivos específicos:
- `backend/app/population/profile_generator.py`
- `backend/app/population/schemas.py`
- `backend/tests/test_profile_generator.py`

## 4. Plan de Pruebas y Validación de Hito
Comandos de terminal obligatorios para certificar la estabilidad de los entregables de esta fase:
- `pytest tests/test_profile_generator.py -q`
- `python scripts/check_demo_contracts.py`

## 5. Criterio de Graduación Humana
- Estado de Pruebas: 100% exitosas.
- Cobertura de Código: Mínimo 90% en archivos autorizados.
- Revisión de Diseño: Aprobado por el líder técnico con tag "PHASE_GRADUATED".
```

---

## 3. Feedback Crítico y Recomendaciones de Mejora

### Evaluación Crítica de la Práctica Actual
* **Fortaleza:** Excelente control de la progresión del proyecto. Evita el "scope creep" agéntico (agregado desmedido de características secundarias) y asegura que cada ladrillo del sistema sea sólido antes de construir el siguiente piso.
* **Debilidad (Vulnerabilidad):** La correlación entre la Ficha de Fase en markdown y lo que el agente realmente hace en el código no está automatizada. El desarrollador humano debe chequear manualmente que el agente no haya tocado archivos fuera de las "Zonas Autorizadas" o se haya saltado requerimientos.

### Propuestas de Mejora para Ingeniería de Alto Nivel

1. **Creación de la CLI de Graduación de Fases (`check-phase`):**
   No dependa de la inspección manual. Implemente una herramienta CLI utilitaria en el repositorio (ej. `npm run check-phase` o `python scripts/check_phase.py`) que analice la Ficha de Fase activa en formato estructurado (ej. YAML/JSON) y verifique automáticamente:
   - Que no haya modificaciones en Git en rutas fuera de las "Zonas Autorizadas" de la fase activa.
   - Que todos los tests listados en el bloque "Validación de Hito" hayan corrido y tengan estado exitoso.
   - De lo contrario, bloquea el despliegue o commit.

2. **Integración con Sistemas de Tareas Dinámicos (`task.md`):**
   Cuando un agente inicia una fase, debe leer la Phase Card y auto-generar un archivo dinámico de progreso en la raíz del proyecto llamado `task.md` (un checklist TODO interactivo). El agente actualizará el estado de los ítems a medida que programa (`[ ]` -> `[/]` -> `[x]`). Esto le da visibilidad al humano del progreso en tiempo real de la fase.

3. **Inyección de Phase Cards en Contexto:**
   Establezca en su system prompt que el agente de IA solo lea la Phase Card del hito activo y las previas (como referencia). Ignorar las Phase Cards futuras reduce drásticamente las alucinaciones de código y la sobrearquitectura de anticipación, optimizando el consumo de tokens y maximizando la precisión.

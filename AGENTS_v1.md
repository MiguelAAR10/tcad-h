# Constitución del Repositorio y Límites de Contexto (`AGENTS.md`)

Este estándar define las reglas constitucionales que rigen la interacción de cualquier agente autónomo de IA dentro de un repositorio de código corporativo. Su objetivo es delimitar el espacio de acción física de la IA, evitando daños estructurales a la base de código.

---

## 1. Fundamentos y Propósito

Los agentes autónomos de codificación tienen la capacidad de inspeccionar repositorios enteros, modificar múltiples archivos simultáneamente y ejecutar comandos en la terminal del host. Sin regulación, esta autonomía genera tres riesgos críticos:
1. **Regresiones colaterales:** Modificación accidental de código legacy o de otros equipos.
2. **AI Slop:** Inyección masiva de patrones repetitivos, helpers duplicados y dependencias innecesarias.
3. **Caos en Git:** Commits gigantescos con descripciones genéricas que ensucian el historial.

`AGENTS.md` actúa como una **Constitución Inmutable**. Es el primer archivo que un agente debe leer al iniciar su ejecución y sirve para restringir su comportamiento mediante directivas explícitas de preservación.

---

## 2. Plantilla Estándar de `AGENTS.md`

Copie y adapte esta plantilla en la raíz de cualquier nuevo repositorio:

```markdown
# AGENTS.md (Constitución de Gobernanza Agéntica)

## 1. Topografía y Alcance
- Git Root: ./ [Especificar la ruta raíz del repositorio]
- Rama Activa de Trabajo: [Ej. feature/belcorp-demo-foundation]
- Advertencia de Git: [Ej. El worktree puede contener ruido de renombrados. No revertir cambios ajenos].

## 2. Lecturas Obligatorias
Antes de realizar cualquier propuesta o escribir código, debes leer en orden:
1. `docs/standards/TCAD_FRAMEWORK.md` [Marco metodológico de diseño]
2. `docs/CAVEMAN_LOG.md` [Bitácora de contexto vivo]
3. `docs/architecture/ARCHITECTURE.md` [Estructura del sistema]

## 3. Capa Activa (Zonas de Escritura Permitidas)
Tienes permitido crear y modificar archivos exclusivamente bajo las siguientes rutas:
- `/backend/app/domain/`
- `/backend/app/simulation/`
- `/frontend/src/app/lab/`

## 4. Capa Legacy o Intocable (Zonas Prohibidas)
Bajo ninguna circunstancia debes escribir, refactorizar o eliminar archivos en:
- `/backend/app/cache/`
- `/backend/app/mirofish/`
- `/backend/app/models/social_graph.py`
*(Nota: Si una tarea requiere tocar estas zonas, debes detenerte y pedir aprobación humana explícita).*

## 5. Comandos de Validación Obligatorios
Antes de dar una tarea por completada, debes ejecutar y pasar con éxito:
- Backend Tests: `pytest -q`
- Frontend Build: `npm run build`
- Validador de Contratos: `python scripts/check_demo_contracts.py`

## 6. Reglas de Higiene de Git
- **Higiene de Commits:** Utilizar la convención Angular (ej. `feat(componente): descripción`, `fix(core): descripción`).
- **Commits Atómicos:** Prohibido realizar `git add .` global. Debes añadir archivos de forma explícita e individual.
- **Acciones Prohibidas:** No hacer force-push, no hacer amend a commits humanos, no cambiar de rama sin autorización.
```

---

## 3. Feedback Crítico y Recomendaciones de Mejora

### Evaluación Crítica de la Práctica Actual
* **Fortaleza:** Excelente delimitación espacial y metodológica. Evita que la IA actúe a ciegas y ahorra costos de tokens al prevenir que el modelo intente leer directorios legacy irrelevantes.
* **Debilidad (Vulnerabilidad):** **La Constitución actual no es coercitiva.** Depende del "buen comportamiento" y la capacidad del agente de seguir instrucciones en su system prompt. Si un agente sufre de alucinaciones severas o un prompt jailbreak, puede ignorar el archivo `AGENTS.md` y borrar carpetas protegidas.

### Propuestas de Mejora para Ingeniería de Alto Nivel

1. **Constitución Coercitiva con Pre-Commit Hooks:**
   No confíe en la disciplina del LLM. Implemente un hook de Git (usando herramientas como `husky` en JS o `pre-commit` en Python) que lea la Constitución `AGENTS.md` en formato estructurado (ej. YAML/JSON) e impida cualquier commit o modificación de archivos que caiga en la lista de "Zonas Prohibidas".
   
   ```python
   # scripts/check_agent_pre_commit.py
   # Ejecutado en el hook de git pre-commit
   import sys
   import json
   
   # Leer archivos agregados al commit
   staged_files = get_git_staged_files()
   forbidden_paths = ["backend/app/cache/", "backend/app/mirofish/"]
   
   for file in staged_files:
       if any(forbidden in file for forbidden in forbidden_paths):
           print(f"ERROR: El agente intentó modificar la ruta prohibida: {file}")
           sys.exit(1) # Rechaza el commit automáticamente
   ```

2. **Sandbox de Entorno de Ejecución:**
   El agente no debería correr en el sistema operativo del host de manera directa si es autónomo. Debe ejecutarse dentro de un contenedor Docker aislado ("sandbox") donde las carpetas catalogadas como "Legacy o Intocables" estén montadas como **solo lectura (Read-Only)**, forzando la seguridad a nivel de sistema de archivos (File System).

3. **Herramientas de Búsqueda Semántica Acotadas:**
   En lugar de permitir que el agente use comandos shell abiertos como `find` o `grep` en todo el disco, la interfaz del agente (MCP o SDK) debe restringir las herramientas de búsqueda para que solo retornen resultados dentro del alcance de la "Capa Activa".

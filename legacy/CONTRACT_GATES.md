# Guardianes de Integridad de Datos Cruzados: Los Contract Gates

Este estándar define los mecanismos de verificación estática cruzada diseñados para asegurar que las definiciones de datos y APIs en el backend (ej. Python, NestJS, Go) coincidan al 100% con los modelos consumidos en el frontend (ej. TypeScript/Angular/React).

---

## 1. Fundamentos y Propósito

El error más destructivo y recurrente en el desarrollo web moderno es el **desalineamiento de contratos de comunicación**. Esto ocurre cuando un desarrollador o un agente de IA altera el nombre de una propiedad de base de datos en el backend (ej. cambia `aspiration_score` por `aspiration_level`) y olvida actualizar la interfaz correspondiente en el frontend.

En sistemas multi-agentes de IA, este problema se multiplica exponencialmente. Un agente enfocado en backend modificará APIs alegremente sin saber que acaba de romper la compilación de TypeScript de la aplicación frontend.

**Contract Gates** es una barrera estática de validación obligatoria. Asegura la integridad del pipeline de datos de extremo a extremo (E2E) sin depender de pruebas manuales lentas o fallos en tiempo de ejecución.

---

## 2. Implementación de un Script `ContractGate` en Python

Aquí se presenta una plantilla utilitaria en Python para realizar verificaciones estáticas de integridad entre modelos Pydantic del backend e interfaces de TypeScript del frontend de forma automatizada:

```python
# scripts/check_demo_contracts.py
import json
import re
import sys
from pathlib import Path
from typing import Set

# Definición de rutas del proyecto
BACKEND_SCHEMA_PATH = Path("backend/app/population/schemas.py")
FRONTEND_INTERFACE_PATH = Path("frontend/src/app/api.types.ts")

def extract_python_fields(schema_file: Path, class_name: str) -> Set[str]:
    """Extrae las propiedades declaradas en un modelo de Pydantic."""
    if not schema_file.exists():
        return set()
        
    with open(schema_file, "r", encoding="utf-8") as f:
        content = f.read()
        
    # Expresión regular para capturar la clase y sus atributos
    class_pattern = rf"class {class_name}\([^)]*\):(.*?)(?=\nclass|\Z)"
    match = re.search(class_pattern, content, re.DOTALL)
    if not match:
        raise ValueError(f"No se encontró la clase Pydantic {class_name} en {schema_file}")
        
    class_content = match.group(1)
    # Extrae variables tipadas ej. "synthetic_id: str"
    fields = set(re.findall(r"^\s+([a-zA-Z0-9_]+)\s*:\s*[a-zA-Z]", class_content, re.MULTILINE))
    return fields

def extract_typescript_fields(interface_file: Path, interface_name: str) -> Set[str]:
    """Extrae las propiedades declaradas en una interfaz de TypeScript."""
    if not interface_file.exists():
        return set()
        
    with open(interface_file, "r", encoding="utf-8") as f:
        content = f.read()
        
    # Expresión regular para capturar la interfaz
    interface_pattern = rf"export interface {interface_name}\s*{{([^}}]*)(?=\}})"
    match = re.search(interface_pattern, content, re.DOTALL)
    if not match:
        raise ValueError(f"No se encontró la interfaz TS {interface_name} en {interface_file}")
        
    interface_content = match.group(1)
    # Extrae variables tipadas ej. "synthetic_id: string;"
    fields = set(re.findall(r"^\s+([a-zA-Z0-9_]+)\s*[\?]?\s*:\s*[a-zA-Z]", interface_content, re.MULTILINE))
    return fields

def check_gate(python_class: str, ts_interface: str):
    """Compara campo por campo la sincronización del contrato."""
    print(f"Validando integridad: {python_class} <===> {ts_interface}")
    
    py_fields = extract_python_fields(BACKEND_SCHEMA_PATH, python_class)
    ts_fields = extract_typescript_fields(FRONTEND_INTERFACE_PATH, ts_interface)
    
    if not py_fields or not ts_fields:
        print(f"❌ Error: Modelos vacíos o archivos no legibles.")
        sys.exit(1)
        
    diff_py = py_fields - ts_fields
    diff_ts = ts_fields - py_fields
    
    if diff_py or diff_ts:
        print("❌ CONTRATO ROTO DETECTADO")
        if diff_py:
            print(f"  - Campos en Python que faltan en TypeScript: {diff_py}")
        if diff_ts:
            print(f"  - Campos en TypeScript que faltan en Python: {diff_ts}")
        sys.exit(1)
        
    print("✅ Contrato 100% alineado.")

if __name__ == "__main__":
    try:
        # Validación de contratos clave de la aplicación
        check_gate("SyntheticProfile", "ISyntheticProfile")
        check_gate("PersonaMemory", "IPersonaMemory")
        print("🎉 Todos los Contract Gates pasaron con éxito.")
        sys.exit(0)
    except Exception as e:
        print(f"❌ Error catastrófico en validador: {str(e)}")
        sys.exit(1)
```

---

## 3. Feedback Crítico y Recomendaciones de Mejora

### Evaluación Crítica de la Práctica Actual
* **Fortaleza:** Es una de las mejores defensas contra errores colaterales del frontend. Garantiza que el código TypeScript no compile si el agente de IA alteró el backend.
* **Debilidad (Vulnerabilidad):** **Es un enfoque reactivo.** El script actual solo avisa cuando el contrato está roto; no previene la rotura de forma activa ni ayuda a corregirla automáticamente. Además, el parseo por expresiones regulares (`re`) es frágil si cambian las tabulaciones o los estilos de formato en el código.

### Propuestas de Mejora para Ingeniería de Alto Nivel

1. **Auto-Generación del Contrato (Single Source of Truth):**
   No escriba interfaces de TypeScript a mano ni deje que el agente las cree a ciegas. Establezca el Backend como la **Única Fuente de Verdad (SSoT)**. Utilice herramientas como `pydantic-to-typescript` o `fastapi-ts-codegen` para generar automáticamente los archivos de TypeScript (`api.types.ts`) en cada build del servidor de desarrollo.
   
   ```bash
   # package.json script
   # Auto-genera las interfaces TS a partir del esquema OpenAPI generado por FastAPI
   "scripts": {
     "generate-api-types": "npx openapi-typescript http://127.0.0.1:8000/openapi.json --output ./src/app/api.types.ts"
   }
   ```

2. **Detección de Cambios de Comportamiento Semántico:**
   La verificación estática solo valida los nombres de las variables y sus tipos básicos. Si un campo de base de datos se mantiene como `score: float` pero cambia de escala (ej. cambia de un rango `[0, 1]` a un rango `[0, 100]`), la verificación de tipos pasará con éxito, pero la UI del frontend renderizará datos destructivamente desproporcionados.
   El ContractGate debe evaluar los **metadatos de rango (constraints)** de los schemas Pydantic (ej. `Field(ge=0, le=1)`) y mapearlos contra validadores numéricos automáticos en TypeScript.

3. **Check en Pre-Commit y PR obligatorios:**
   Ningún commit del agente debe ser fusionado en la rama principal (`main`) si el ContractGate falla en el servidor de CI. Esto protege las ramas productivas e impide que errores menores de tipado degraden la estabilidad de la plataforma en producción.

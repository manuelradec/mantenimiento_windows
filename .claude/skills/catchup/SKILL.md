---
name: catchup
description: Resume el estado actual del trabajo en la rama. Lee los archivos modificados y entrega un resumen accionable de qué tarea del backlog está en progreso, qué falta, y qué tests correr antes de continuar. Útil al inicio de una sesión nueva o tras /clear.
---

# Catchup — estado actual de la rama

Ejecuta en paralelo:
1. `git status` — archivos modificados/sin trackear
2. `git diff --stat main..HEAD` — magnitud de los cambios respecto a main
3. `git log main..HEAD --oneline` — historia de commits de la rama
4. Lee `CLEANCPU_MASTER_PROMPT.md` (si existe) para conocer el backlog priorizado

Después:
5. Lee cada archivo modificado (no usar git show, usar Read) para entender qué se cambió
6. Si hay commits recientes, lee también el último commit para anclar el contexto

Entrega un resumen de **5-10 bullets** con esta estructura:

- **Tarea en progreso**: nombre/número del backlog que parece estar atendiéndose ahora
- **Qué se hizo**: 2-3 bullets sobre los cambios más significativos
- **Qué falta**: 2-3 bullets sobre lo que quedó pendiente, basado en código a medio terminar, TODOs, o descripciones de commits parciales
- **Tests a correr**: comando exacto de pytest que cubre los archivos modificados (sólo los relevantes, no la suite completa salvo que sean cambios cross-cutting)
- **Riesgos visibles**: cualquier cosa que parezca incompleta, regresiva o pendiente de revisión

**No hacer**:
- No proponer cambios de código en este resumen — sólo describir el estado.
- No correr los tests automáticamente — déjalos como sugerencia.
- No editar archivos.

**Salida esperada**: el resumen en español, sin redundancia, sin emojis, pegado al estado real del repo.

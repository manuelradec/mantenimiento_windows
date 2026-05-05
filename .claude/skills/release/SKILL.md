---
name: release
description: Pipeline de release completa para CleanCPU — corre lint, tests, build del .exe y crea el tag de versión leyendo Config.APP_VERSION. Requiere árbol git limpio antes de empezar.
---

# Release pipeline

**Pre-condición**: árbol git limpio. Corre `git status` primero. Si hay cambios sin commitear, **detente y avisa al usuario** — no commitees por tu cuenta.

## Pasos (secuenciales, abortar al primer rojo)

1. **Lint**: `python -m flake8 core services routes tests`. Si exit ≠ 0, reporta los findings y detente.

2. **Tests**: `python -m pytest -q`. Si hay fallos o errores, reporta y detente.

3. **Versión**: lee `config.py` y extrae `Config.APP_VERSION`. Verifica que el valor sea de forma `X.Y.Z` o `X.Y.Z-suffix`.

4. **Tag exists?**: corre `git tag -l v<VERSION>`. Si ya existe, **detente** — la versión ya fue publicada; el usuario debe bumpear `Config.APP_VERSION` en config.py antes de re-correr este skill.

5. **Build**: `pyinstaller cleancpu.spec --clean --noconfirm`. Verifica `dist/cleancpu.exe` y reporta tamaño.

6. **Tag**: `git tag -a v<VERSION> -m "Release v<VERSION>"`. **No** push automático — deja el tag local para que el usuario revise antes de `git push --tags`.

7. **Reporte final**:
   - Versión publicada
   - Tamaño del binario
   - Hash corto del commit etiquetado (`git rev-parse --short HEAD`)
   - Comando exacto que el usuario debe correr para subir el tag (`git push origin v<VERSION>`)

## No hacer
- No `git push --tags` ni `git push --force` (están denegados explícitamente).
- No editar `config.py` para bumpear versión por tu cuenta — eso lo decide el usuario.
- No commitear `dist/` ni `build/`.
- Si `pyinstaller` no está instalado, **detente** y pide al usuario que corra `pip install pyinstaller`. No intentes instalarlo automáticamente como parte del release.

# Task: Implementar PIPA v1 — Agente Autonomo de Procesamiento de Planos

> **Spec:** `docs/v1-spec.md` (1632 lineas, completa)
> **Fecha inicio:** 2026-02-28
> **Plataforma destino:** Windows (PC dedicado 24/7)
> **Motor:** Claude Code CLI (`claude -p`) headless

---

## Estado Actual del Proyecto

### Que YA existe (reutilizable)
- `PDF-Listado-Materiales/src/crop.py` — Motor de cropping funcional (PyMuPDF)
- `PDF-Listado-Materiales/src/regions.py` — Definiciones de regiones (%, zoom)
- `PDF-Listado-Materiales/src/schemas.py` — Modelos Pydantic (SpoolRecord, MaterialRow, etc.)
- `PDF-Listado-Materiales/src/assemble.py` — Ensamblador de JSONs parciales
- `PDF-Listado-Materiales/.claude/skills/` — Skills extract-plano y read-region (prototipos)
- `.env` con estructura base (faltan ANTHROPIC_API_KEY, credenciales Gmail reales)
- `.gitignore` parcial (falta completar segun §18.1)
- Planos PDF de ejemplo en `PDF-Listado-Materiales/Planos/`

### Que NO existe (hay que crear)
- Estructura de directorios PIPA (`agent/`, `mcp_servers/`, `skills/`, `state/`, `logs/`, `memory/`, `tmp/`)
- `agent/main.py` — Wrapper Python (orquestador)
- `agent/preflight.py` — Pre-flight checks
- `agent/cleanup.py` — Limpieza post-ciclo
- `agent/config_schema.py` — Validacion Pydantic de config.json
- `mcp_servers/gmail/server.py` — MCP Server custom (~250 LOC)
- `SOUL.md`, `HEARTBEAT.md`, `CLAUDE.md`, `MEMORY.md`
- `config.json`, `mcp.json.example`
- `heartbeat-runner.bat`
- Autenticacion OAuth2 Gmail

---

## Fases de Implementacion

### Fase 0: Scaffolding y Archivos de Identidad
- [x] 0.1 Crear estructura de directorios completa (§13)
- [x] 0.2 Crear SOUL.md (§3)
- [x] 0.3 Crear HEARTBEAT.md (§6.2)
- [x] 0.4 Crear CLAUDE.md (§3.1)
- [x] 0.5 Crear MEMORY.md (vacio inicial)
- [x] 0.6 Crear config.json con datos reales (§10.1)
- [x] 0.7 Crear mcp.json.example (§11.4)
- [x] 0.8 Actualizar .gitignore (§18.1)
- [x] 0.9 Crear .env actualizado (§10.2)

**Agente:** Ejecutor directo (Write/Edit tools)
**Dependencias:** Ninguna
**Criterio de exito:** `tree` muestra estructura completa, archivos de identidad legibles

---

### Fase 1: Skill extract-plano (migrar desde prototipo)
- [x] 1.1 Copiar y adaptar crop.py, regions.py, schemas.py, assemble.py a `skills/extract-plano/src/`
- [x] 1.2 Crear `skills/extract-plano/SKILL.md` con contrato de skill (§8.2)
- [x] 1.3 Crear `skills/extract-plano/requirements.txt` (§17.4)
- [x] 1.4 Adaptar paths para que funcionen desde la raiz de PIPA (no desde PDF-Listado-Materiales)
- [x] 1.5 Test manual: crop + assemble con un PDF de ejemplo

**Agente:** Ejecutor directo
**Dependencias:** Fase 0
**Criterio de exito:** `python -m src.crop` funciona desde `skills/extract-plano/`

---

### Fase 2: Config Schema + Preflight (agent/)
- [x] 2.1 Crear `agent/config_schema.py` con modelo Pydantic completo (§10.1)
- [x] 2.2 Crear `agent/preflight.py` — checks de horario, lock, internet (§14.2)
- [x] 2.3 Crear `agent/cleanup.py` — limpieza de tmp/, purga de processed-emails (§5.2 Paso 6)
- [x] 2.4 Crear `agent/requirements.txt` (§17.2)
- [x] 2.5 Tests unitarios para config_schema y preflight

**Agente:** Ejecutor directo
**Dependencias:** Fase 0 (config.json debe existir)
**Criterio de exito:** `load_config()` valida config.json correctamente; preflight detecta fuera de horario

---

### Fase 3: MCP Server Gmail Custom
- [x] 3.1 Crear `mcp_servers/gmail/server.py` con FastMCP (~250 LOC, 5 tools) (§11.3)
- [x] 3.2 Crear `mcp_servers/gmail/requirements.txt` (§17.3)
- [x] 3.3 Implementar OAuth2 compartido (§11.5)
- [x] 3.4 Implementar `search()` — buscar emails
- [x] 3.5 Implementar `get_message()` — obtener mensaje completo
- [x] 3.6 Implementar `get_attachment()` — descargar adjunto a tmp/
- [x] 3.7 Implementar `send_reply()` — responder en hilo con adjuntos (In-Reply-To, References)
- [x] 3.8 Implementar `modify_labels()` — agregar/quitar labels por nombre
- [x] 3.9 Test manual: search, get_message, modify_labels, send_reply — todos OK. Threading verificado.

**Agente:** Agente dedicado (complejidad alta, OAuth2 + MIME + threading)
**Dependencias:** OAuth2 credentials reales (manual, requiere browser)
**Criterio de exito:** Los 5 tools funcionan, reply se queda en el hilo correcto

---

### Fase 4: Wrapper Python — Polling Gmail (agent/main.py parte 1)
- [x] 4.1 Implementar carga de config y estado
- [x] 4.2 Implementar polling con `users.history.list` + historyId persistido (§5.2 Paso 2)
- [x] 4.3 Implementar filtrado por whitelist + adjuntos PDF
- [x] 4.4 Implementar bootstrap (primera ejecucion) (§5.2 Paso 2, nota bootstrap)
- [x] 4.5 Implementar recovery de historyId expirado (404) (§5.2 Paso 2, nota 404)
- [x] 4.6 Implementar actualizacion de state/gmail-state.json
- [x] 4.7 Tests unitarios: 29 tests pasan (state, bootstrap, filtering, heartbeat log, last-run)

**Agente:** Agente dedicado
**Dependencias:** Fase 2 (config_schema), Fase 3 (compartir OAuth2)
**Criterio de exito:** Wrapper detecta emails nuevos con PDFs de remitentes autorizados

---

### Fase 5: Wrapper Python — Orquestacion completa (agent/main.py parte 2)
- [x] 5.1 Implementar invocacion de Claude heartbeat principal (claude -p con flags §14.2)
- [x] 5.2 Implementar invocacion de skills como subprocesos (claude -p --model haiku)
- [x] 5.3 Implementar deduplicacion ADR-006: estado local ANTES del reply
- [x] 5.4 Implementar invocacion de Claude para reply (fase 4 del flujo §5.2)
- [x] 5.5 Implementar persistencia post-ciclo (memory/YYYY-MM-DD.md, heartbeat.log, last-run.json)
- [x] 5.6 Implementar lock directory atomico con stale detection (§14.3)
- [x] 5.7 Implementar timeout de proceso (600s) con subprocess.run(timeout=600)
- [x] 5.8 Implementar manejo de errores segun arbol de decisiones (§12.1)
- [x] 5.9 Implementar sistema de alertas al dueno (§12.3)
- [x] 5.10 Crear heartbeat-runner.bat (§14.1)

**Agente:** Agente dedicado (pieza mas compleja del sistema)
**Dependencias:** Fases 1-4 todas
**Criterio de exito:** Ciclo completo end-to-end: email → extract → reply con JSON

---

### Fase 6: Integracion y Test End-to-End
- [x] 6.1 Test happy path completo: email con 1 PDF → reply con JSON
- [x] 6.2 Test multi-PDF: email con 3 PDFs → reply con tabla + 3 JSONs
- [x] 6.3 Test error parcial: email con 2 PDFs (1 corrupto) → reply con resultados parciales
- [x] 6.4 Test deduplicacion: re-procesar email ya procesado → omitido
- [x] 6.5 Test fuera de horario: ejecutar a las 23:00 → no ejecuta
- [x] 6.6 Test sin emails: ciclo vacio → OK en heartbeat.log
- [x] 6.7 Test alerta al dueno: simular 3 fallos consecutivos → email de alerta
- [x] 6.8 Verificar formato de email HTML en Gmail web

**Agente:** Equipo de agentes en paralelo para tests independientes
**Dependencias:** Fase 5
**Criterio de exito:** Todos los tests pasan

---

### Fase 7: Deploy en Windows + Task Scheduler
- [ ] 7.1 Configurar Task Scheduler segun §14.1
- [ ] 7.2 Verificar que heartbeat-runner.bat funciona como tarea programada
- [ ] 7.3 Dejar corriendo 24h y verificar logs
- [ ] 7.4 Documentar setup-guide.md

**Agente:** Manual (requiere acceso al PC Windows)
**Dependencias:** Fase 6
**Criterio de exito:** PIPA corre autonomamente durante 24h sin fallos

---

## Decisiones

| Decision | Razon | Fecha |
|----------|-------|-------|
| Reutilizar codigo de PDF-Listado-Materiales | Ya esta probado y funcional, solo necesita adaptacion de paths | 2026-02-28 |
| Fase 3 (MCP) como agente dedicado | Complejidad alta: OAuth2 + MIME + threading headers | 2026-02-28 |
| Fase 5 (Wrapper) como agente dedicado | Es la pieza central, ~400+ LOC con muchos edge cases | 2026-02-28 |
| Fases 0-2 como ejecucion directa | Son scaffolding y boilerplate con spec clara | 2026-02-28 |

## Errores Encontrados

| Error | Intento | Resolucion |
|-------|---------|------------|
| (ninguno aun) | — | — |

---

## Estrategia de Agentes

```
Fase 0-2: Ejecucion directa (scaffolding, write/edit)
    |
    v
Fase 3: Agente MCP Gmail ──────┐
Fase 4: Agente Polling Gmail ──┤── Pueden correr en paralelo
    |                          │
    v                          │
Fase 5: Agente Wrapper ────────┘── Depende de Fases 1-4
    |
    v
Fase 6: Agentes de test (paralelo)
    |
    v
Fase 7: Manual (Windows)
```

**Paralelismo posible:**
- Fases 3 y 4 pueden desarrollarse en paralelo (MCP server y polling son independientes)
- Tests de Fase 6 pueden correr en paralelo entre si
- Fases 0, 1, 2 son secuenciales pero rapidas

# Progress Log — PIPA v1 Implementation

## 2026-02-28

### Session 1 — Planificacion

- [x] Revisado estado actual del proyecto
- [x] Analizado codigo existente en PDF-Listado-Materiales/ (crop, regions, schemas, assemble)
- [x] Verificado .env, .gitignore actuales
- [x] Creado task_plan.md con 8 fases
- [x] Creado findings.md con hallazgos del codigo existente
- [x] Plan listo para aprobacion del usuario

**Estado actual:** Fase 0 completada
**Siguiente accion:** Ejecutar Fase 1 (migrar skill extract-plano)

### Session 2 — Fase 0: Scaffolding

- [x] Creada estructura de directorios: agent/, mcp_servers/gmail/, skills/extract-plano/src/, memory/, tmp/, state/, logs/
- [x] Creados .gitkeep en tmp/, state/, logs/ y __init__.py en skills/extract-plano/src/
- [x] Creado SOUL.md — identidad del agente (§3)
- [x] Creado HEARTBEAT.md — checklist del heartbeat (§6.2)
- [x] Creado CLAUDE.md — contexto tecnico para Claude Code (§3.1)
- [x] Creado MEMORY.md — memoria curada (vacio inicial)
- [x] Creado config.json con datos reales: whitelist=[sescanellacaceres@gmail.com], owner=sescanellacaceres@gmail.com, account=projecto.pipa1@gmail.com
- [x] Creado mcp.json.example — template con paths de ejemplo Windows
- [x] Actualizado .gitignore segun §18.1 (agregado mcp.json, **/.venv/, __pycache__/, *.pyc)
- [x] Actualizado .env — limpio con solo 3 vars: ANTHROPIC_API_KEY, GMAIL_CREDENTIALS_PATH, GMAIL_TOKEN_PATH

**Criterio de exito verificado:** Estructura de directorios completa, todos los archivos de identidad creados y legibles.

### Session 3 — Fase 1: Skill extract-plano (migracion desde prototipo)

- [x] 1.1 Copiado y adaptado crop.py, regions.py, schemas.py, assemble.py a skills/extract-plano/src/
- [x] 1.2 Creado SKILL.md con contrato de skill (§8.2) — YAML frontmatter + instrucciones de 4 pasos
- [x] 1.3 Creado requirements.txt (§17.4) — PyMuPDF, Pillow, pydantic
- [x] 1.4 Adaptado paths: output/ -> tmp/crops/ y tmp/json/ (via PIPA root detection con Path(__file__))
- [x] 1.5 Test manual: crop + assemble verificados con PDF de ejemplo (MK-1342-MO-13012-001_0.pdf)
  - crop genera 4 PNGs en tmp/crops/{stem}/ (materiales, soldaduras, cortes, cajetin)
  - assemble lee region JSONs, valida con Pydantic, genera SpoolRecord en tmp/json/{stem}.json
  - Invocacion funciona tanto desde skills/extract-plano/ como desde raiz PIPA
- [x] Creado .venv con dependencias instaladas (PyMuPDF 1.26.5, Pillow 11.3.0, pydantic 2.12.5)

**Cambios clave respecto al prototipo:**
- Imports cambiados de `from src.X import Y` a imports relativos (`.regions`, `.schemas`)
- Default output_dir: `PIPA_ROOT/tmp/crops/{stem}/` (antes: `output/crops/{stem}/`)
- Default JSON output: `PIPA_ROOT/tmp/json/` (antes: `output/json/`)
- PIPA root se detecta con `Path(__file__).resolve().parent.parent.parent.parent`
- SKILL.md adaptado para paths tmp/ y invocacion desde skills/extract-plano/

**Criterio de exito verificado:** `python -m src.crop` funciona desde skills/extract-plano/, genera PNGs correctos; `python -m src.assemble` genera JSON validado por Pydantic.

**Estado actual:** Fase 1 completada
**Siguiente accion:** Ejecutar Fase 2 (Config Schema + Preflight)

### Session 4 — Fase 2: Config Schema + Preflight (agent/)

- [x] 2.1 Creado `agent/config_schema.py` — modelo Pydantic completo (§10.1)
  - Clases: ActiveHours, AgentConfig, GmailConfig, SkillConfig, OwnerConfig, PIPAConfig
  - Validadores: formato HH:MM, rango horario, email basico, whitelist no vacia, extra="forbid"
  - `load_config()` carga y valida config.json
  - `get_project_root()` helper reutilizable
- [x] 2.2 Creado `agent/preflight.py` — checks pre-ciclo (§14.2)
  - `check_active_hours()` — verifica horario 07:00-22:00 con timezone America/Santiago (zoneinfo)
  - `acquire_lock()` — lock atomico con mkdir (§14.3), stale detection por PID y timeout 25min
  - `release_lock()` — cleanup del lock directory
  - `check_internet()` — conectividad via urllib (google.com)
  - `run_preflight()` — orquesta los 3 checks en orden; libera lock si internet falla
  - Compatible Windows (tasklist) y Unix (os.kill signal 0)
- [x] 2.3 Creado `agent/cleanup.py` — limpieza post-ciclo (§14.2 paso 10)
  - `clean_tmp()` — limpia tmp/ preservando heartbeat.lock/ y .gitkeep
  - `purge_processed_emails()` — purga entradas > 30 dias de state/processed-emails.json
  - Escritura atomica (write-to-temp + rename) para processed-emails.json
  - Preserva entradas con timestamps invalidos (safety)
- [x] 2.4 Creado `agent/requirements.txt` (§17.2) — google-api-python-client, google-auth-oauthlib, pydantic
- [x] 2.5 Tests unitarios: 30 tests, todos pasan
  - test_config_schema.py: 10 tests (valid load, defaults, empty whitelist, invalid email, extra fields, time format/range, file load, missing file, invalid JSON)
  - test_preflight.py: 11 tests (hours within/outside/early, lock acquire/held/stale-pid/stale-timeout/no-info, release, internet ok/fail)
  - test_cleanup.py: 9 tests (tmp remove/preserve-lock/empty, purge old/recent/missing/empty/invalid-ts, integration)
- [x] Creado agent/.venv con pydantic y pytest instalados

**Criterio de exito verificado:** `load_config()` carga y valida config.json correctamente; preflight detecta fuera de horario; 30/30 tests pasan.

**Estado actual:** Fase 2 completada
**Siguiente accion:** Ejecutar Fase 3 (MCP Server Gmail Custom)

### Session 5 — Fase 3: MCP Server Gmail Custom

- [x] 3.1 Creado `mcp_servers/gmail/server.py` con FastMCP (5 tools, ~250 LOC funcional + docstrings)
  - Servidor: `FastMCP("pipa-gmail")` con transport stdio
  - OAuth2: `_get_gmail_service()` con auto-refresh, scope `gmail.modify`
  - Paths via env vars: GOOGLE_TOKEN_PATH, GOOGLE_CREDENTIALS_PATH, ATTACHMENT_DOWNLOAD_DIR
  - Logging a stderr (stdout reservado para JSON-RPC/MCP)
  - Servicio Gmail cacheado por proceso (`_service()`)
- [x] 3.2 Creado `mcp_servers/gmail/requirements.txt` — mcp[cli], google-api-python-client, google-auth-oauthlib, google-auth
- [x] 3.3 OAuth2 compartido implementado (§11.5) — lee token.json compartido con agent/main.py
  - Auto-refresh de token expirado
  - Primer uso requiere browser para autorizar (InstalledAppFlow)
  - Persiste token.json despues de autorizacion
- [x] 3.4 `search()` — busca emails con query Gmail, retorna [{id, threadId, snippet, subject, from, date}]
  - Soporta max_results (1-100), truncacion si excede CHARACTER_LIMIT
- [x] 3.5 `get_message()` — obtiene mensaje completo con headers decodificados, body text/html, metadata de adjuntos
  - Recorre MIME multipart recursivamente
  - Extrae body_text, body_html, y lista de attachments con IDs
- [x] 3.6 `get_attachment()` — descarga adjunto a ATTACHMENT_DOWNLOAD_DIR (default: tmp/)
  - Retorna path absoluto del archivo guardado
- [x] 3.7 `send_reply()` — responde en hilo con HTML y adjuntos opcionales
  - Headers In-Reply-To y References correctos para threading
  - Soporta multiples adjuntos via file path (no base64)
  - MIME multipart con encode_base64 para adjuntos
- [x] 3.8 `modify_labels()` — agrega/quita labels por nombre
  - Resuelve nombres a IDs automaticamente
  - Crea labels inexistentes automaticamente
  - Maneja labels no encontradas gracefully (skip con warning)
- [x] 3.9 Verificacion: compilacion OK, imports OK, 5 tools registrados
  - Instalado Python 3.12.12 via Homebrew (macOS dev) — mcp requiere Python 3.10+
  - .venv creado con Python 3.12, todas las dependencias instaladas
  - Test manual de threading correcto pendiente hasta tener credentials.json

- [x] 3.9 Tests manuales ejecutados con cuenta real projecto.pipa1@gmail.com:
  - search('in:inbox') — OK, retorna emails con id, threadId, snippet, subject, from, date
  - get_message('19ca29adbfa8db81') — OK, headers decodificados, body text/html, labels
  - modify_labels(add=['PIPA/Test'], remove=['UNREAD']) — OK, label creada y aplicada
  - send_reply(thread_id, in_reply_to, html) — OK, message ID retornado
  - Threading verificado: reply threadId coincide, In-Reply-To y References correctos
  - get_attachment — no testeable aun (sin emails con adjuntos en la cuenta)

**OAuth2 setup completado:**
- credentials.json: tipo Desktop app, project-pipa-488804
- token.json generado y guardado en raiz del proyecto
- Nota: proyecto OAuth en modo "Testing" — refresh token expira en 7 dias

**Criterio de exito verificado:** Los 5 tools funcionan, reply se queda en el hilo correcto.

**Estado actual:** Fase 3 completada
**Siguiente accion:** Ejecutar Fase 4 (Wrapper Python — Polling Gmail)

### Session 6 — Fase 4: Wrapper Python — Polling Gmail (agent/main.py parte 1)

- [x] 4.1 Creado `agent/main.py` con carga de config y estado
  - `load_config()` desde config.json, `load_gmail_state()` desde state/gmail-state.json
  - `load_processed_emails()` para dedup check
  - OAuth2 compartido con MCP server (mismos token.json y credentials.json)
- [x] 4.2 Polling con `users.history.list` + historyId persistido (§5.2 Paso 2)
  - `_poll_history()` llama history.list con startHistoryId, historyTypes=['messageAdded'], labelId='INBOX'
  - Paginacion automatica con nextPageToken
  - Deduplicacion de message_ids en la respuesta
- [x] 4.3 Filtrado por whitelist + adjuntos PDF
  - `_extract_email_address()` extrae email de "Display Name <email>" format
  - `_has_pdf_attachment()` recorre MIME parts recursivamente buscando .pdf
  - `_filter_messages()` orquesta: dedup + whitelist + PDF check
- [x] 4.4 Bootstrap (primera ejecucion) — `run_bootstrap()`
  - Detecta bootstrap necesario via `_needs_bootstrap()` (no state, no historyId, not completed)
  - Llama `users.getProfile()` para obtener historyId actual
  - Busca emails pre-existentes con query `is:unread has:attachment filename:pdf`
  - Filtra por whitelist y dedup
- [x] 4.5 Recovery de historyId expirado (404) — `_full_sync_recovery()`
  - Detecta HttpError 404 en poll_gmail
  - Ejecuta full sync con query `is:unread`
  - Obtiene historyId fresco de getProfile()
- [x] 4.6 Actualizacion de state/gmail-state.json — `save_gmail_state()`
  - Escritura atomica (write-to-temp + rename)
  - Persiste last_history_id, last_successful_poll, bootstrap_completed
- [x] 4.7 Heartbeat log + last-run.json
  - `write_heartbeat_log()` — append logfmt a logs/heartbeat.log (§6.5)
  - `write_last_run()` — atomic overwrite de state/last-run.json (§6.6)
  - main() escribe ambos para OK, WORK, y ERROR
- [x] Tests unitarios: 29 tests, todos pasan
  - test_main.py: state loading/saving, bootstrap detection, email extraction, PDF detection,
    history polling, whitelist/PDF/dedup filtering, heartbeat log, last-run.json, poll integration
- [x] Instaladas dependencias Gmail API en agent/.venv (google-api-python-client, google-auth-oauthlib)
- [x] Verificado: 59/59 tests pasan (30 previos + 29 nuevos)

**Estructura de main.py (~380 LOC):**
- OAuth2: `get_gmail_service()` — comparte credenciales con MCP server
- State: `load_gmail_state()`, `save_gmail_state()`, `load_processed_emails()`
- Polling: `poll_gmail()`, `run_bootstrap()`, `_poll_history()`, `_full_sync_recovery()`
- Filtering: `_filter_messages()`, `_extract_email_address()`, `_has_pdf_attachment()`, `_get_message_metadata()`
- Logging: `write_heartbeat_log()`, `write_last_run()`
- Entry: `main()` — ciclo completo con preflight, polling, cleanup, try/finally lock release

**Phase 5 TODOs dejados en main.py:**
- Invocar Claude heartbeat para descargar PDFs
- Invocar skill extract-plano por PDF
- Deduplicacion ADR-006 (write to processed-emails.json)
- Invocar Claude para reply
- Escribir memory/YYYY-MM-DD.md

**Criterio de exito verificado:** Wrapper carga config, ejecuta preflight, detecta emails nuevos con PDFs de remitentes autorizados, persiste estado, escribe heartbeat.log y last-run.json. 29/29 tests pasan.

**Estado actual:** Fase 4 completada
**Siguiente accion:** Ejecutar Fase 5 (Wrapper Python — Orquestacion completa)

### Session 7 — Fase 5: Wrapper Python — Orquestacion completa (agent/main.py parte 2)

- [x] 5.1 Implementar invocacion de Claude heartbeat principal
  - `invoke_heartbeat_download()` — construye prompt con HEARTBEAT.md + email IDs
  - Invoca `claude -p` con flags: --allowedTools (Read + 5 MCP tools), --disallowedTools (Bash,Write,Edit,WebFetch,WebSearch)
  - --output-format json, --max-turns 5, --mcp-config mcp.json
  - Fallback: si JSON parsing falla, escanea tmp/ por PDFs descargados
- [x] 5.2 Implementar invocacion de skills como subprocesos
  - `invoke_extract_plano()` — invoca `claude -p --model haiku` por cada PDF
  - --allowedTools "Bash,Read,Write,Glob", --disallowedTools "WebFetch,WebSearch"
  - max_turns y timeout desde config.skills["extract-plano"]
  - Verifica output en tmp/json/{stem}.json
  - Retry x2 por PDF (§12.1)
- [x] 5.3 Implementar deduplicacion ADR-006
  - `save_processed_email()` — append atomico a state/processed-emails.json
  - Se ejecuta ANTES del reply (orden: estado local -> label -> reply)
  - Schema: message_id, processed_at, sender, pdfs_count, status
- [x] 5.4 Implementar invocacion de Claude para reply
  - `invoke_reply()` — construye prompt con resultados de skills
  - Instrucciones: apply label PIPA-procesado, remove UNREAD, send_reply con HTML tabla + JSONs adjuntos
  - Formato HTML segun §15.1 (tabla con #, Plano, OT, Tag, Materiales, Soldaduras, Cortes, Estado)
  - Firma: config.email_signature
  - Retry x2 (§12.1)
- [x] 5.5 Implementar persistencia post-ciclo
  - `write_daily_memory()` — append a memory/YYYY-MM-DD.md con resumen por email
  - heartbeat.log con campos completos: emails, pdfs, ok, fail, duration, cost (§6.5)
  - last-run.json con todos los campos del protocolo §6.4
- [x] 5.6 Lock directory atomico (ya implementado en preflight.py Fase 2)
- [x] 5.7 Implementar timeout de proceso (600s)
  - `_run_claude()` usa `subprocess.run(timeout=...)` — default 600s para heartbeat, configurable por skill
  - `subprocess.TimeoutExpired` -> error_type="claude_timeout"
- [x] 5.8 Implementar manejo de errores segun §12.1
  - PDF corrupto: skill retorna error, se incluye en reply, se continua con otros
  - Gmail API error (HttpError 401 -> oauth_token_expired, otros -> gmail_api_error)
  - Claude Code falla: retry x2 por PDF y por reply
  - OSError: reportado como disk_full
  - Email ya procesado: skipped en filtering (Fase 4)
  - `process_email()` orquesta todo: skills -> dedup -> reply
- [x] 5.9 Implementar sistema de alertas al dueno (§12.3)
  - `_load_consecutive_failures()` / `_save_consecutive_failures()` — logs/consecutive_failures.json
  - `record_failure_and_maybe_alert()` — incrementa count, evalua threshold + cooldown
  - `reset_consecutive_failures()` — en ciclo exitoso (OK o WORK)
  - `_send_owner_alert()` — via Gmail API directa (no MCP)
  - Mapeo completo de error_type -> descripcion + accion sugerida
  - Cooldown respetado: no re-alertar dentro de alert_cooldown_hours
- [x] 5.10 Crear heartbeat-runner.bat (§14.1)
  - agent/heartbeat-runner.bat — cd a raiz PIPA, ejecuta agent\.venv\Scripts\python.exe agent\main.py
- [x] Tests unitarios: 25 tests nuevos, 84/84 total pasan
  - test_phase5.py: ADR-006 dedup (3), consecutive failures (8), daily memory (2),
    PDF attachment names (4), _run_claude (7), error mappings (1)

**Estructura de main.py actualizada (~700 LOC):**
- OAuth2 + State (Phase 4, sin cambios)
- Polling (Phase 4, sin cambios)
- Consecutive failures: `_load/save_consecutive_failures`, `reset_consecutive_failures`, `record_failure_and_maybe_alert`
- Alert system: `_send_owner_alert`, `_ERROR_DESCRIPTIONS`, `_ERROR_ACTIONS`
- Claude invocation: `_find_claude_binary`, `_run_claude`
- PDF download: `invoke_heartbeat_download`
- Skill invocation: `invoke_extract_plano`
- Reply: `invoke_reply`
- Memory: `write_daily_memory`
- Orchestration: `process_email`
- Main: `main()` — ciclo completo end-to-end

**Criterio de exito verificado:** main.py implementa el ciclo completo: polling -> download -> extract -> dedup -> reply -> persist. Error handling per §12.1, alerts per §12.3, timeouts per §14.2. 84/84 tests pasan.

**Estado actual:** Fase 5 completada
**Siguiente accion:** Ejecutar Fase 6 (Integracion y Test End-to-End)

### Session 8 — Fase 6: Integracion y Test End-to-End

- [x] 6.1 Test happy path completo: email con 1 PDF → process_email success, dedup registrado, reply invocado
- [x] 6.2 Test multi-PDF: email con 3 PDFs → 3 skill invocations, 3 resultados OK, stats correctos
- [x] 6.3 Test error parcial: 1 OK + 1 corrupto → reply enviado con resultados parciales, status "partial" en dedup
  - Incluye test all-fail → status "error" pero reply igualmente enviado
- [x] 6.4 Test deduplicacion ADR-006:
  - Email ya procesado es filtrado por _filter_messages (no llama messages.get)
  - Orden ADR-006 verificado: state se guarda ANTES del reply (trackeado con call_order)
  - poll_gmail filtra correctamente emails ya en processed-emails.json
- [x] 6.5 Test fuera de horario: main() retorna 1, heartbeat.log tiene ERROR/preflight_failed
  - Verifica que NO se registra como fallo de infraestructura (no trigger de alertas)
- [x] 6.6 Test sin emails: main() retorna 0, heartbeat.log tiene OK, emails=0
  - Claude NO invocado (invoke_heartbeat_download no llamado)
  - Consecutive failures reseteados en ciclo OK
- [x] 6.7 Test alerta al dueno (§12.3):
  - 3 fallos consecutivos del mismo tipo → _send_owner_alert llamado
  - Cooldown respetado: no re-alertar dentro de 24h
  - Cooldown expirado (>24h) → re-alertar
  - Cambio de error_type resetea contador
  - Gmail 401 → oauth_token_expired registrado en last-run.json
  - Gmail 500 → gmail_api_error registrado
- [x] 6.8 Verificar formato de email HTML (§15.1):
  - Prompt contiene columnas: #, Plano, OT, Tag Spool, Materiales, Soldaduras, Cortes, Estado
  - Prompt contiene firma: "-- Procesado automaticamente por PIPA v1"
  - Prompt especifica colores (verde/green para OK, rojo/red para errores)
  - Prompt incluye paths de JSONs adjuntos
  - Allowed/disallowed tools correctos (MCP tools permitidos, Bash/Write/WebFetch bloqueados)
  - Prompt incluye instrucciones de label (PIPA-procesado + UNREAD)
  - Prompt incluye threading info (thread_id + In-Reply-To)

**Tests adicionales implementados (mas alla del plan):**
- Retry logic: skill retry on failure (CLAUDE_RETRY_MAX=2), reply retry on failure
- Download flow: prompt construction con security preamble, disallowed tools verification
- Main full cycle: WORK result end-to-end, download failure returns ERROR
- Edge case: no PDFs downloaded → reply igualmente enviado informando

**Archivos creados:**
- `agent/tests/test_integration.py` — 39 tests de integracion

**Criterio de exito verificado:** 123/123 tests pasan (84 previos + 39 nuevos). Todos los escenarios de la Fase 6 cubiertos.

**Estado actual:** Fase 6 completada
**Siguiente accion:** Ejecutar Fase 7 (Deploy en Windows + Task Scheduler)

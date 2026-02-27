# Arquitectura del Sistema Heartbeat (basado en OpenClaw)

> Documento de referencia para replicar el sistema de Heartbeat de OpenClaw en un contexto agnostico de stack, con delivery via Gmail y monitoreo de inbox de correo.

## 1. Que es el Heartbeat

El Heartbeat es un **loop autonomo periodico** que transforma un agente de IA de **reactivo** (solo responde cuando le hablan) a **proactivo** (revisa cosas por su cuenta, actua, y alerta al humano solo cuando algo necesita atencion).

**Analogia:** Es como un asistente ejecutivo que cada 30 minutos revisa tu bandeja de entrada, tus pendientes, y solo te interrumpe si hay algo urgente. Si todo esta bien, no dice nada.

### Por que es lo que hace productivo al sistema

Sin heartbeat, un agente solo trabaja cuando el humano inicia la conversacion. Con heartbeat:
- El agente **monitorea proactivamente** (emails, tareas, calendarios)
- **Decide autonomamente** si algo merece atencion
- **Alerta solo cuando es necesario** (no spamea)
- **Mantiene continuidad** entre sesiones (recuerda que revisaba)
- **Se auto-evoluciona** (puede modificar su propia checklist)

---

## 2. Arquitectura General

```
┌─────────────────────────────────────────────────────────────┐
│                    HEARTBEAT SYSTEM                          │
│                                                             │
│  ┌──────────┐    ┌───────────┐    ┌──────────────────┐     │
│  │ SCHEDULER │───>│   WAKE    │───>│  HEARTBEAT       │     │
│  │ (Timer)   │    │ DISPATCHER│    │  RUNNER           │     │
│  └──────────┘    └───────────┘    └────────┬─────────┘     │
│       ^               ^                    │               │
│       │               │                    v               │
│  ┌────┴────┐    ┌─────┴─────┐    ┌──────────────────┐     │
│  │  CRON   │    │  EXTERNAL │    │   AGENT LOOP     │     │
│  │  EVENTS │    │  TRIGGERS │    │   (LLM Turn)     │     │
│  └─────────┘    └───────────┘    └────────┬─────────┘     │
│                                           │               │
│                    ┌──────────────────────┼──────────┐     │
│                    │                      │          │     │
│                    v                      v          v     │
│            ┌────────────┐    ┌─────────┐  ┌────────┐     │
│            │  DELIVERY  │    │ MEMORY  │  │ SKILLS │     │
│            │  (Gmail)   │    │         │  │        │     │
│            └────────────┘    └─────────┘  └────────┘     │
└─────────────────────────────────────────────────────────────┘
```

---

## 3. Los 6 Componentes Fundamentales

### 3.1 SCHEDULER (Planificador)

**Responsabilidad:** Disparar el heartbeat a intervalos regulares.

**Principios de diseno:**
- Usa `setTimeout` (no `setInterval`) para calcular el proximo disparo exacto
- Intervalo configurable (default: 30 minutos)
- Soporte para **Active Hours** (no despertar al humano a las 3am)
- El timer es `.unref()` (no mantiene vivo el proceso si todo lo demas termino)

**Config necesaria:**
```yaml
heartbeat:
  every: "30m"                  # Intervalo entre beats
  activeHours:
    start: "08:00"              # No antes de las 8am
    end: "22:00"                # No despues de las 10pm
    timezone: "America/Mexico_City"
```

**Pseudo-codigo:**
```
function scheduleNext():
    nextDue = now + intervalMs
    if activeHours defined:
        if nextDue outside activeHours:
            nextDue = next_start_of_active_hours
    timer = setTimeout(onTimerFire, nextDue - now)
    timer.unref()

function onTimerFire():
    requestHeartbeatNow(reason="interval")
```

### 3.2 WAKE DISPATCHER (Despachador de Despertares)

**Responsabilidad:** Centralizar y deduplicar todas las fuentes de disparo del heartbeat.

El heartbeat no solo se dispara por timer. Tambien por:
- Cron jobs que completan
- Eventos externos (webhook de Gmail PubSub, etc.)
- Wake manual del usuario
- Ejecuciones async que terminan

**Principios de diseno:**
- **Coalescencia temporal (250ms):** Multiples triggers en <250ms se fusionan en uno
- **Cola de prioridad:** No todos los triggers son iguales
- **Proteccion anti-concurrencia:** Nunca ejecutar dos heartbeats simultaneos
- **Retry con backoff:** Si falla, reintentar con backoff exponencial

**Prioridades de trigger:**
| Prioridad | Razon | Ejemplo |
|---|---|---|
| 0 (baja) | retry | Reintento por fallo previo |
| 1 | interval | Timer periodico normal |
| 2 | cron/wake | Cron job o wake generico |
| 3 (alta) | action/manual | Wake manual, webhook, hook |

**Pseudo-codigo:**
```
pendingWakes = PriorityQueue()
running = false
coalesceTimer = null

function requestHeartbeatNow(reason, coalesceMs=250):
    pendingWakes.enqueue(reason, priority(reason))

    if coalesceTimer:
        return  # Ya hay un timer de coalescencia corriendo

    coalesceTimer = setTimeout(dispatchBatch, coalesceMs)

function dispatchBatch():
    coalesceTimer = null
    if running:
        return  # Ya hay un heartbeat corriendo, se re-despacha al terminar

    running = true
    batch = pendingWakes.drainAll()

    try:
        for wake in batch:
            result = await runHeartbeatOnce(wake)
            if result.status == "skipped" and result.reason == "queue-busy":
                pendingWakes.enqueue("retry", RETRY_PRIORITY)
                scheduleRetry(1000ms)
    catch error:
        # Re-encolar todo el batch para retry
        for wake in batch:
            pendingWakes.enqueue("retry", RETRY_PRIORITY)
        scheduleRetry(1000ms)
    finally:
        running = false
        if pendingWakes.notEmpty():
            setTimeout(dispatchBatch, 0)
```

### 3.3 HEARTBEAT RUNNER (Ejecutor del Beat)

**Responsabilidad:** Ejecutar un ciclo completo de heartbeat.

Este es el componente central. Cada ejecucion sigue este flujo:

```
PRE-FLIGHT CHECKS
    ├─ Heartbeat habilitado? (global + por agente)
    ├─ Dentro de active hours?
    ├─ Cola principal ocupada? → skip + retry
    └─ HEARTBEAT.md efectivamente vacio? → skip (ahorra API calls)

PROMPT RESOLUTION
    ├─ Si trigger = exec-event → prompt de resultado de ejecucion
    ├─ Si trigger = cron-event → prompt de recordatorio cron
    └─ Si trigger = interval  → prompt default (lee HEARTBEAT.md)

LLM EXECUTION
    └─ Turno COMPLETO del agente en la sesion principal
       (acceso a tools, skills, memoria, todo)

RESPONSE PROCESSING
    ├─ Extraer payload de respuesta
    ├─ Strip HEARTBEAT_OK del inicio/final
    ├─ Dedup: mismo texto en <24h? → suprimir
    └─ Clasificar: OK (silencio) vs Alert (entregar)

POST-PROCESSING
    ├─ Si OK: podar transcript, restaurar timestamp de sesion
    ├─ Si Alert: entregar via canal configurado (Gmail)
    └─ Emitir evento de status para observabilidad

SCHEDULE
    └─ Actualizar nextDueMs, re-armar timer
```

**Pre-flight gates (portalas de entrada):**

```
function runHeartbeatOnce(params):
    # Gate 1: Habilitado?
    if not heartbeatsEnabled: return skip("disabled")

    # Gate 2: Active hours?
    if not isWithinActiveHours(config, now): return skip("outside-hours")

    # Gate 3: Cola ocupada?
    if mainQueue.size > 0: return skip("queue-busy")  # retry later

    # Gate 4: HEARTBEAT.md vacio? (solo para trigger=interval)
    if params.reason == "interval":
        content = readFile("HEARTBEAT.md")
        if isEffectivelyEmpty(content): return skip("empty-file")

    # Pasar a ejecucion...
```

### 3.4 HEARTBEAT.md (El Checklist Vivo)

**Responsabilidad:** Definir QUE debe revisar el agente en cada beat.

Este es un archivo Markdown simple en el workspace. Es lo que le da **inteligencia situacional** al heartbeat.

**Ejemplo para monitoreo de Gmail:**
```markdown
# Heartbeat Checklist

## Inbox Monitoring
- Revisar inbox de Gmail por emails no leidos en las ultimas 2 horas
- Priorizar: emails de clientes, emails con "urgente" en subject
- Ignorar: newsletters, notificaciones automaticas de GitHub

## Follow-ups
- Si hay emails sin respuesta de mas de 24h de contactos importantes, alertar
- Si hay invitaciones de calendario sin confirmar, alertar

## Reglas de Silencio
- Si todo esta al dia, responder HEARTBEAT_OK
- NO repetir alertas que ya se enviaron hoy
- NO alertar por emails leidos pero sin respuesta (solo no-leidos)

## Self-Update
- Si un patron de emails se vuelve recurrente (>3 veces/semana del mismo
  remitente), agregar una regla especifica a este checklist
```

**Reglas de OpenClaw para HEARTBEAT.md:**
- Mantenerlo **pequeno** (evitar prompt bloat)
- Es **modificable por el agente** (auto-evolucion)
- Si esta **efectivamente vacio** (solo headers), se salta el beat (ahorra tokens)
- No poner secretos (se inyecta como contexto del prompt)

### 3.5 Response Contract (HEARTBEAT_OK)

**Responsabilidad:** Protocolo de respuesta para distinguir "nada que reportar" de "hay una alerta".

**Reglas:**
1. Si nada necesita atencion: responder **exactamente** `HEARTBEAT_OK`
2. `HEARTBEAT_OK` al inicio o final del reply → se trata como acknowledgment
3. Si texto restante despues de strip <= 300 chars → se trata como OK (configurable via `ackMaxChars`)
4. `HEARTBEAT_OK` en medio del reply → no se trata especialmente
5. Para alertas: **NO incluir** `HEARTBEAT_OK`, solo el texto de la alerta

**Pseudo-codigo de procesamiento:**
```
function processHeartbeatResponse(reply):
    payload = extractPayload(reply)

    # Strip token
    stripped = stripHeartbeatOK(payload.text)

    # Determinar si es OK o alerta
    if stripped.hadToken and len(stripped.remaining) <= ackMaxChars:
        return HeartbeatResult(type="ok", shouldDeliver=false)

    # Dedup check (24h window)
    if stripped.text == lastHeartbeatText and (now - lastHeartbeatAt) < 24h:
        return HeartbeatResult(type="duplicate", shouldDeliver=false)

    # Es una alerta real
    return HeartbeatResult(type="alert", text=stripped.text, shouldDeliver=true)
```

### 3.6 DELIVERY ENGINE (Motor de Entrega)

**Responsabilidad:** Entregar alertas al humano via el canal configurado.

Para tu caso: **Gmail** como canal de delivery.

**Opciones de target:**
| Target | Comportamiento |
|---|---|
| `none` | Ejecuta el heartbeat pero no envia nada externamente |
| `gmail` | Envia email al destinatario configurado |
| `last` | Envia al ultimo canal usado por el humano |

**Consideraciones para Gmail delivery:**
```yaml
heartbeat:
  target: "gmail"
  to: "tu-email@gmail.com"
  delivery:
    subject_prefix: "[PIPA Heartbeat]"
    format: "html"        # o "plain"
    thread_mode: "daily"  # Un thread por dia para no spamear
```

**Comportamiento inteligente:**
- Las alertas se agrupan en un thread diario (no 48 emails/dia)
- `HEARTBEAT_OK` nunca genera email
- Dedup de 24h previene emails repetidos
- Active hours previenen emails nocturnos

---

## 4. Patrones Criticos para Replicar

### 4.1 Transcript Pruning (Poda de Transcript)

**Problema:** Si el heartbeat corre 48 veces/dia y cada vez genera un exchange "prompt + HEARTBEAT_OK", el contexto del agente se llena de basura.

**Solucion de OpenClaw:**
```
Antes del beat:
    transcriptSize = fileSize("session.jsonl")

Despues del beat (si resultado = OK):
    truncateFile("session.jsonl", transcriptSize)
    # El exchange prompt+OK nunca existio
```

**Resultado:** Solo los beats con alertas reales persisten en el historial de la sesion.

### 4.2 Session Timestamp Restoration

**Problema:** Los heartbeats mantienen la sesion "viva" artificialmente, evitando que expire por inactividad.

**Solucion:**
```
Antes del beat:
    previousUpdatedAt = session.updatedAt

Despues del beat (si resultado = OK):
    session.updatedAt = previousUpdatedAt  # Restaurar
    # La sesion "no sabe" que hubo un heartbeat
```

### 4.3 System Event Queue (Cola de Eventos del Sistema)

**Problema:** Los cron jobs y webhooks necesitan inyectar informacion al heartbeat.

**Solucion:** Una cola in-memory, session-scoped:
```
MAX_EVENTS = 20

function enqueueSystemEvent(text, sessionKey):
    queue = getQueue(sessionKey)
    if text == queue.lastText: return  # Skip duplicados consecutivos
    queue.push({ text, ts: now() })
    if queue.length > MAX_EVENTS: queue.shift()

function drainSystemEvents(sessionKey):
    events = getQueue(sessionKey).drainAll()
    return events
```

**Uso:** Cuando llega un webhook de Gmail PubSub diciendo "nuevo email de cliente@importante.com", se encola como system event. El proximo heartbeat lo procesa con un prompt especializado.

### 4.4 Error Backoff Exponencial

```
BACKOFF_SCHEDULE = [30s, 60s, 5m, 15m, 60m]

function getRetryDelay(consecutiveErrors):
    index = min(consecutiveErrors - 1, len(BACKOFF_SCHEDULE) - 1)
    return BACKOFF_SCHEDULE[index]
```

---

## 5. Flujo Completo: Heartbeat + Gmail

### Escenario: Monitoreo de inbox cada 30 minutos

```
08:00  SCHEDULER arma timer para 08:30

08:30  TIMER FIRE → requestHeartbeatNow(reason="interval")
       WAKE DISPATCHER → dispatchBatch()
       PRE-FLIGHT:
         ✓ Habilitado
         ✓ Dentro de active hours (08:00-22:00)
         ✓ Cola vacia
         ✓ HEARTBEAT.md tiene contenido

       PROMPT: "Lee HEARTBEAT.md. Si nada necesita atencion: HEARTBEAT_OK"
       + timestamp: "Current time: 2026-02-27 08:30 CST"

       LLM TURN:
         Agent lee HEARTBEAT.md
         Agent usa tool: gmail_check_inbox()
         → 3 emails no leidos: newsletter, github notif, email de cliente
         Agent filtra segun checklist: solo el de cliente es relevante
         Agent responde: "Email urgente de cliente@empresa.com:
                         Asunto: Revision de contrato Q2
                         Recibido hace 45 minutos, sin leer."

       RESPONSE PROCESSING:
         No contiene HEARTBEAT_OK → es una alerta
         Dedup: no se envio esta alerta antes → nueva

       DELIVERY: Gmail
         To: tu-email@gmail.com
         Subject: [PIPA Heartbeat] Alerta de Inbox
         Body: "Email urgente de cliente@empresa.com..."
         Thread: daily-2026-02-27

       POST: Emitir evento "sent", schedule next at 09:00

09:00  TIMER FIRE → requestHeartbeatNow(reason="interval")
       LLM TURN:
         Agent revisa inbox
         El email del cliente sigue ahi (no leido)
         Agent responde: misma alerta

       RESPONSE PROCESSING:
         Dedup: mismo texto en <24h → SUPRIMIR
         No se envia nada (evita spam)

       POST: Prune transcript, schedule next at 09:30

09:15  WEBHOOK de Gmail PubSub: "nuevo email de VP@empresa.com"
       → enqueueSystemEvent("Nuevo email de VP@empresa.com", session)
       → requestHeartbeatNow(reason="hook:gmail:push")

       WAKE DISPATCHER: reason=hook (priority 3) → ejecutar inmediatamente
       PRE-FLIGHT: ✓ (hook bypasses empty-file gate)
       PROMPT: "Se recibio un nuevo email. Revisar y decidir si alertar."

       LLM TURN:
         Agent usa tool: gmail_read("VP@empresa.com", latest)
         → "Necesito revision urgente del presupuesto para manana"
         Agent decide: esto es urgente → alerta

       DELIVERY: Gmail → alerta enviada

09:30  TIMER FIRE (programado desde 09:00)
       LLM TURN:
         Agent revisa inbox
         Todo ya fue procesado
         Agent responde: "HEARTBEAT_OK"

       POST: Prune transcript, restore timestamp, schedule 10:00
```

---

## 6. Decisiones de Diseno Clave

### 6.1 Por que setTimeout y no setInterval

`setInterval` puede acumular execuciones si el heartbeat tarda mas que el intervalo. `setTimeout` garantiza que el siguiente beat se programa **despues** de que el actual termine.

### 6.2 Por que sesion compartida (no aislada)

El heartbeat corre en la **misma sesion** que las conversaciones normales. Esto le da acceso completo al contexto: que hablo el humano, que se decidio, que tareas hay. Si corriera en sesion aislada, perderia todo el contexto y seria un bot robotico sin memoria.

### 6.3 Por que HEARTBEAT.md y no hardcoded

Externalizar el checklist en un archivo Markdown permite:
- El humano puede editarlo sin tocar codigo
- El agente puede auto-modificarlo (auto-evolucion)
- Es versionable con git
- Es legible y auditable
- Se puede tener diferentes checklists por proyecto

### 6.4 Por que dedup de 24h

Sin dedup, el mismo email no leido generaria la misma alerta cada 30 minutos (48 veces/dia). La ventana de 24h balancea entre no spamear y no perder alertas si el email sigue sin leer al dia siguiente.

### 6.5 Por que transcript pruning

En 24 horas con intervalos de 30min, el heartbeat genera **48 exchanges**. Si cada uno tiene ~500 tokens (prompt + respuesta), eso son **24,000 tokens de contexto** que no aportan nada. Podar los exchanges "nada que reportar" mantiene el contexto limpio.

---

## 7. Consideraciones para Implementacion

### Componentes minimos para un MVP

| Componente | Complejidad | Impacto |
|---|---|---|
| Scheduler basico (setTimeout loop) | Baja | Fundamental |
| HEARTBEAT.md reader | Baja | Fundamental |
| LLM turn con tools | Media | Core |
| HEARTBEAT_OK contract | Baja | Anti-spam |
| Gmail delivery | Media | Entrega |
| Dedup 24h | Baja | Anti-spam |
| Transcript pruning | Media | Salud del contexto |
| Active hours | Baja | Calidad de vida |
| System event queue | Media | Reactivo a webhooks |
| Error backoff | Baja | Resiliencia |

### Dependencias externas necesarias

- **LLM API** (Claude, GPT, etc.) - Para el turno del agente
- **Gmail API** - Para leer inbox y enviar alertas (OAuth2 + Gmail API v1)
- **Almacenamiento de sesion** - Archivo JSON o SQLite para estado
- **Scheduler** - setTimeout nativo del lenguaje o libreria cron

### Gmail-specific: Como monitorear inbox

**Opcion A: Polling (simple)**
- Cada heartbeat llama `gmail.users.messages.list(q="is:unread newer_than:2h")`
- Pro: Simple, sin setup extra
- Con: Latencia de hasta 30min para emails urgentes

**Opcion B: Gmail PubSub Push (reactivo)**
- Configurar `gmail.users.watch()` con Cloud Pub/Sub
- Recibir webhook instantaneo cuando llega email nuevo
- Enqueue como system event → wake inmediato del heartbeat
- Pro: Latencia ~segundos
- Con: Requiere setup de Google Cloud Pub/Sub

**Recomendacion:** Empezar con Opcion A (polling via heartbeat), migrar a B cuando se necesite latencia baja.

---

## 8. Anti-patrones a Evitar

| Anti-patron | Porque es malo | Que hacer |
|---|---|---|
| Heartbeat sin HEARTBEAT_OK | Cada beat genera una alerta aunque no haya nada | Implementar contrato de silencio |
| Sin dedup | 48 alertas/dia por el mismo email | Implementar ventana de dedup |
| Sin transcript pruning | Contexto del agente se llena de basura | Podar exchanges vacios |
| Sin active hours | Alertas a las 3am | Respetar horarios del humano |
| Sesion aislada | Agente pierde todo contexto entre beats | Usar sesion compartida |
| HEARTBEAT.md enorme | Prompt bloat, tokens caros | Mantener checklist conciso |
| Sin error backoff | Error en Gmail API → 48 errores/dia | Backoff exponencial |
| setInterval | Beats se acumulan si uno tarda mucho | Usar setTimeout |

---

## 9. Referencias

- **Repositorio OpenClaw:** https://github.com/openclaw/openclaw
- **Heartbeat docs:** `docs/gateway/heartbeat.md`
- **Heartbeat runner source:** `src/infra/heartbeat-runner.ts`
- **Wake dispatcher:** `src/infra/heartbeat-wake.ts`
- **Cron vs Heartbeat:** `docs/automation/cron-vs-heartbeat.md`

---

## 10. Proximos Pasos

1. [ ] Definir el HEARTBEAT.md inicial para monitoreo de Gmail
2. [ ] Elegir stack de implementacion
3. [ ] Implementar scheduler + runner MVP
4. [ ] Configurar Gmail API (OAuth2 + read/send scopes)
5. [ ] Implementar HEARTBEAT_OK contract + dedup
6. [ ] Agregar transcript pruning
7. [ ] Configurar active hours
8. [ ] Testing: correr 24h y auditar falsos positivos/negativos
9. [ ] Iterar HEARTBEAT.md basado en patrones observados

# Arquitectura del Sistema Heartbeat — Implementacion con Claude Code CLI

> Documento de referencia para implementar el sistema Heartbeat usando **Claude Code CLI** (`claude -p`) corriendo en un Mac Mini siempre encendido, programado con `launchd`, usando MCP servers para Gmail/Calendar y Pushover/Telegram para alertas.
>
> **Stack elegido:** Claude Code CLI (headless) + launchd (macOS) + MCP servers + archivos JSON de estado
>
> **Proyectos de referencia:** OpenClaw (patron original), Murmur (daemon de cron para AI), Harper Reed (email triage con MCP)

## 1. Que es el Heartbeat

El Heartbeat es un **loop autonomo periodico** que transforma un agente de IA de **reactivo** (solo responde cuando le hablan) a **proactivo** (revisa cosas por su cuenta, actua, y alerta al humano solo cuando algo necesita atencion).

**Analogia:** Es como un asistente ejecutivo que cada 30 minutos revisa tu bandeja de entrada, tus pendientes, y solo te interrumpe si hay algo urgente. Si todo esta bien, no dice nada.

### Por que es lo que hace productivo al sistema

Sin heartbeat, un agente solo trabaja cuando el humano inicia la conversacion. Con heartbeat:
- El agente **monitorea proactivamente** (emails, tareas, calendarios)
- **Decide autonomamente** si algo merece atencion
- **Alerta solo cuando es necesario** (no spamea)
- **Mantiene continuidad** via archivos de estado en disco (no necesita sesion persistente)
- **Se auto-evoluciona** (puede modificar su propia checklist)

### Decision de stack: Claude Code CLI, no API directa

En vez de programar directamente contra la Anthropic API (`anthropic.messages.create()`), usamos el binario `claude` con su flag `-p` (headless mode). Ventajas:

| Claude Code CLI (`claude -p`) | API directa |
|---|---|
| MCP servers integrados (Gmail, Calendar) | Hay que construir tool-calling layer |
| Permisos granulares (`--allowedTools`) | Hay que implementar sandboxing manual |
| CLAUDE.md como contexto automatico | Hay que inyectar system prompt manual |
| Hooks del ciclo de vida (Stop, PostToolUse) | No existen |
| Session resumption si se necesita | Hay que manejar conversation history |
| ~30-50% mas tokens por scaffolding interno | Mas eficiente en tokens |

**Conclusion:** Claude Code CLI es el camino correcto para MVP. Solo migrar a API directa si el costo de tokens se vuelve un problema critico.

---

## 2. Arquitectura General

```
┌──────────────────────────────────────────────────────────────────────┐
│                    HEARTBEAT SYSTEM (Claude Code CLI)                 │
│                                                                      │
│  ┌─────────────┐    ┌───────────────┐    ┌─────────────────────┐    │
│  │   launchd    │───>│  heartbeat-   │───>│  claude -p           │    │
│  │ (cada 30min) │    │  runner.sh    │    │  "$(cat HEARTBEAT.md)"│    │
│  └─────────────┘    └───────────────┘    └────────┬────────────┘    │
│                            │                       │                 │
│                            │                       v                 │
│                     ┌──────┴──────┐    ┌─────────────────────┐      │
│                     │ Pre-flight  │    │   MCP SERVERS        │      │
│                     │ - active hrs│    │   ├─ gmail (read)    │      │
│                     │ - lockfile  │    │   ├─ calendar        │      │
│                     │ - enabled?  │    │   └─ tasks           │      │
│                     └─────────────┘    └────────┬────────────┘      │
│                                                 │                    │
│                              ┌──────────────────┼──────────┐        │
│                              │                  │          │        │
│                              v                  v          v        │
│                     ┌──────────────┐   ┌────────────┐ ┌────────┐   │
│                     │  DELIVERY    │   │  STATE     │ │  LOGS  │   │
│                     │  ├─ Pushover │   │  (JSON)    │ │        │   │
│                     │  ├─ Telegram │   │  ├─ dedup  │ │        │   │
│                     │  ├─ osascript│   │  ├─ last   │ │        │   │
│                     │  └─ Gmail    │   │  └─ watermark│ │        │   │
│                     └──────────────┘   └────────────┘ └────────┘   │
└──────────────────────────────────────────────────────────────────────┘
```

**Principio arquitectonico clave: Claude es stateless, el filesystem es stateful.**

Cada invocacion de `claude -p` es una sesion fresca. Claude lee estado de archivos JSON al inicio. El script orquestador escribe estado de vuelta despues de cada ejecucion. Esto es intencional:
- Evita acumular tokens de contexto (cada sesion cuesta lo mismo)
- El estado es transparente, auditable, y versionable con git
- Sobrevive crashes, actualizaciones de Claude Code, y reinicios

---

## 3. Los 6 Componentes Fundamentales

### 3.1 SCHEDULER — launchd (macOS)

**Responsabilidad:** Disparar el heartbeat a intervalos regulares.

**Decision: launchd, no cron ni setTimeout**

Para nuestra implementacion con Claude Code CLI, el scheduler NO es codigo propio — es `launchd`, el scheduler nativo de macOS. Ventajas sobre cron:
- Maneja correctamente sleep/wake del Mac (cron no garantiza ejecucion post-sleep)
- `StartCalendarInterval` dispara en tiempos de reloj predecibles (:00 y :30)
- Se integra con el Keychain de macOS
- Persiste automaticamente entre reinicios

**Plist de launchd:**

```xml
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN"
  "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key>
  <string>com.pipa.heartbeat</string>

  <key>ProgramArguments</key>
  <array>
    <string>/bin/bash</string>
    <string>/Users/TUUSUARIO/heartbeat/scripts/heartbeat-runner.sh</string>
  </array>

  <!-- Disparar a :00 y :30 de cada hora -->
  <key>StartCalendarInterval</key>
  <array>
    <dict><key>Minute</key><integer>0</integer></dict>
    <dict><key>Minute</key><integer>30</integer></dict>
  </array>

  <key>EnvironmentVariables</key>
  <dict>
    <key>PATH</key>
    <string>/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin</string>
    <key>HOME</key>
    <string>/Users/TUUSUARIO</string>
  </dict>

  <key>StandardOutPath</key>
  <string>/Users/TUUSUARIO/heartbeat/logs/launchd-stdout.log</string>
  <key>StandardErrorPath</key>
  <string>/Users/TUUSUARIO/heartbeat/logs/launchd-stderr.log</string>

  <key>WorkingDirectory</key>
  <string>/Users/TUUSUARIO/heartbeat</string>
</dict>
</plist>
```

**Instalar y administrar:**
```bash
# Instalar
cp com.pipa.heartbeat.plist ~/Library/LaunchAgents/
launchctl load ~/Library/LaunchAgents/com.pipa.heartbeat.plist

# Probar manualmente
launchctl start com.pipa.heartbeat

# Desactivar
launchctl unload ~/Library/LaunchAgents/com.pipa.heartbeat.plist
```

**Active hours:** Se implementan dentro del script `heartbeat-runner.sh`, no en el plist. El plist siempre dispara; el script decide si ejecutar o salir temprano.

**Bug conocido:** Claude Code almacena tokens OAuth en el Keychain de macOS, que NO es accesible desde launchd/SSH. **Solucion:** Usar `ANTHROPIC_API_KEY` desde un archivo con `chmod 600`, no depender del Keychain. (GitHub issues #5515, #9403)

### 3.2 ANTI-CONCURRENCIA (Lockfile)

**Responsabilidad:** Garantizar que nunca haya dos heartbeats corriendo al mismo tiempo.

En la implementacion original de OpenClaw (un proceso Node.js persistente), esto lo maneja un Wake Dispatcher en memoria con coalescencia y colas de prioridad. En nuestra implementacion con launchd + CLI, el mecanismo es mas simple: un **lockfile**.

```bash
LOCKFILE="/tmp/pipa-heartbeat.lock"

# Si ya hay un heartbeat corriendo, salir
if [ -f "$LOCKFILE" ]; then
    log "Previous run still in progress. Skipping."
    exit 0
fi

# Crear lockfile y asegurar limpieza al salir
trap "rm -f $LOCKFILE" EXIT
touch "$LOCKFILE"

# ... ejecutar heartbeat ...
```

**Nota sobre Wake Dispatcher:** En el MVP con launchd, no necesitamos coalescencia ni prioridades. Cada disparo es independiente. Si en el futuro agregamos webhooks de Gmail PubSub para reactividad instantanea, podemos evolucionar a un daemon Node.js con el pattern completo de OpenClaw (ver seccion original en la documentacion de referencia).

### 3.3 HEARTBEAT RUNNER (heartbeat-runner.sh)

**Responsabilidad:** Ejecutar un ciclo completo de heartbeat.

Este es el componente central. Es un script bash que orquesta todo el flujo:

```
PRE-FLIGHT CHECKS
    ├─ Dentro de active hours? (07:00 - 23:00)
    ├─ Lockfile libre? (no hay otro heartbeat corriendo)
    └─ HEARTBEAT.md tiene contenido?

INVOCACION DE CLAUDE
    └─ claude -p "$(cat HEARTBEAT.md)"
       --output-format json
       --max-turns 3
       --allowedTools "Read,mcp__gmail__*,mcp__calendar__*"
       --disallowedTools "Bash,Write,Edit"

RESPONSE PROCESSING (en bash, parseando JSON con jq)
    ├─ Extraer .result del JSON
    ├─ Verificar si contiene HEARTBEAT_OK
    ├─ Dedup: comparar hash contra state/alert-hashes.json
    └─ Clasificar: OK (silencio) vs Alert (entregar)

POST-PROCESSING
    ├─ Si OK: log y salir
    ├─ Si Alert: invocar send-alert.sh (Pushover/Telegram/osascript)
    └─ Actualizar state/last-run.json
```

**Script completo del runner:**

```bash
#!/bin/bash
# heartbeat-runner.sh — Orquestador del heartbeat con Claude Code CLI
set -euo pipefail

REPO_DIR="$(cd "$(dirname "$0")/.." && pwd)"
LOG_FILE="$REPO_DIR/logs/heartbeat-$(date +%Y-%m-%d).log"
STATE_FILE="$REPO_DIR/state/last-run.json"
LOCKFILE="/tmp/pipa-heartbeat.lock"
SECRETS_FILE="$HOME/.pipa-secrets"

log() { echo "[$(date -u +%Y-%m-%dT%H:%M:%SZ)] $*" | tee -a "$LOG_FILE"; }

# --- Cargar secretos ---
source "$SECRETS_FILE"  # exporta ANTHROPIC_API_KEY

# --- Active Hours (07:00 - 23:00) ---
HOUR=$(date +%H)
if [[ "$HOUR" -lt 7 || "$HOUR" -ge 23 ]]; then
    log "Outside active hours ($HOUR:xx). Skipping."
    exit 0
fi

# --- Lockfile ---
if [ -f "$LOCKFILE" ]; then
    log "Previous run still in progress. Skipping."
    exit 0
fi
trap "rm -f $LOCKFILE" EXIT
touch "$LOCKFILE"

# --- Ejecutar Claude Code ---
log "Starting heartbeat..."
mkdir -p "$REPO_DIR/logs" "$REPO_DIR/state"

RESULT=$(claude -p "$(cat "$REPO_DIR/HEARTBEAT.md")" \
    --output-format json \
    --max-turns 3 \
    --allowedTools "Read,mcp__gmail__list_emails,mcp__gmail__get_email,mcp__calendar__list_events" \
    --disallowedTools "Bash,Write,Edit,WebFetch,WebSearch" \
    2>>"$LOG_FILE") || {
    log "ERROR: claude exited with code $?"
    exit 1
}

# --- Parsear resultado ---
RESPONSE=$(echo "$RESULT" | jq -r '.result // "HEARTBEAT_OK"' 2>/dev/null || echo "$RESULT")

# --- Actualizar estado ---
echo "{\"last_run\":\"$(date -u +%Y-%m-%dT%H:%M:%SZ)\",\"status\":\"$(echo "$RESPONSE" | head -c 100)\"}" \
    > "$STATE_FILE"

# --- Decidir: OK o ALERTA ---
if echo "$RESPONSE" | grep -q "HEARTBEAT_OK"; then
    log "Status: OK. No action required."
else
    log "Status: ALERT. Dispatching..."
    echo "$RESPONSE" | "$REPO_DIR/scripts/send-alert.sh"
fi
```

**Flags criticos de Claude Code:**

| Flag | Valor | Proposito |
|---|---|---|
| `-p` | `"$(cat HEARTBEAT.md)"` | Modo headless, prompt desde archivo |
| `--output-format` | `json` | Parseable con `jq` (incluye `result`, `session_id`, `cost`) |
| `--max-turns` | `3` | Limitar profundidad (leer emails + decidir + responder) |
| `--allowedTools` | MCP tools especificos | Solo herramientas necesarias |
| `--disallowedTools` | `Bash,Write,Edit` | Defensa en profundidad: sin acceso a shell ni archivos |

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

**Canales disponibles (de mejor a peor para nuestro caso):**

| Canal | Latencia | Costo | Setup | Ideal para |
|---|---|---|---|---|
| **Pushover** | Instantaneo (push) | $5 una vez | Bajo | Alertas urgentes al celular |
| **Telegram Bot** | Instantaneo (push) | Gratis | Bajo | Alertas urgentes al celular |
| **macOS osascript** | Instantaneo (local) | Gratis | Cero | Cuando estas en el Mac |
| **Gmail via MCP** | Segundos | Gratis | Medio | Digests, alertas no urgentes |

**Recomendacion:** Pushover o Telegram para alertas urgentes + osascript como fallback local.

**Script de alerta con Pushover:**
```bash
#!/bin/bash
# send-alert.sh — Lee JSON de stdin y envia push notification
ALERT_JSON=$(cat)
SUMMARY=$(echo "$ALERT_JSON" | jq -r '.alerts[0].summary // "Heartbeat Alert"' 2>/dev/null || echo "$ALERT_JSON" | head -c 200)

# Pushover (requiere PUSHOVER_TOKEN y PUSHOVER_USER en secrets)
curl -s \
  --form-string "token=$PUSHOVER_TOKEN" \
  --form-string "user=$PUSHOVER_USER" \
  --form-string "title=[PIPA] Heartbeat Alert" \
  --form-string "message=$SUMMARY" \
  --form-string "priority=0" \
  --form-string "sound=pushover" \
  https://api.pushover.net/1/messages.json

# macOS notification como backup
osascript -e "display notification \"$SUMMARY\" with title \"PIPA Heartbeat\" sound name \"Ping\""
```

**Script de alerta con Telegram:**
```bash
#!/bin/bash
# send-alert-telegram.sh
ALERT_JSON=$(cat)
SUMMARY=$(echo "$ALERT_JSON" | jq -r '.alerts[0].summary // "Heartbeat Alert"' 2>/dev/null || echo "$ALERT_JSON" | head -c 200)

curl -s -X POST "https://api.telegram.org/bot${TELEGRAM_BOT_TOKEN}/sendMessage" \
  -d "chat_id=${TELEGRAM_CHAT_ID}" \
  -d "text=[PIPA] $SUMMARY" \
  -d "parse_mode=Markdown"
```

**Comportamiento inteligente:**
- `HEARTBEAT_OK` nunca genera notificacion
- Dedup de 24h previene alertas repetidas (via `state/alert-hashes.json`)
- Active hours previenen notificaciones nocturnas

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

### Estructura del repositorio

```
heartbeat/
├── HEARTBEAT.md                    # Checklist de Claude (version controlled)
├── CLAUDE.md                       # Contexto del proyecto para Claude
├── .mcp.json                       # Configuracion de MCP servers
├── config/
│   └── active-hours.json           # Horarios activos (o hardcoded en script)
├── scripts/
│   ├── heartbeat-runner.sh         # Orquestador principal
│   ├── send-alert.sh               # Entrega de alertas (Pushover/Telegram)
│   └── prune-logs.sh               # Rotacion de logs (cron semanal)
├── state/
│   ├── last-run.json               # Timestamp y resultado del ultimo run
│   └── alert-hashes.json           # Hashes SHA de alertas enviadas (dedup 24h)
├── logs/
│   └── heartbeat-YYYY-MM-DD.log    # Logs diarios
└── com.pipa.heartbeat.plist        # launchd agent para macOS
```

### MCP Servers necesarios

Configurar en `.mcp.json` del proyecto:

```json
{
  "mcpServers": {
    "gmail": {
      "command": "node",
      "args": ["/path/to/gmail-mcp-server/dist/index.js"],
      "env": {
        "GOOGLE_CLIENT_ID": "${GOOGLE_CLIENT_ID}",
        "GOOGLE_CLIENT_SECRET": "${GOOGLE_CLIENT_SECRET}"
      }
    },
    "calendar": {
      "command": "npx",
      "args": ["google-calendar-mcp"],
      "env": {
        "GOOGLE_CALENDAR_CREDENTIALS": "/path/to/credentials.json"
      }
    }
  }
}
```

**Opciones de MCP servers para Google:**

| Server | Cobertura | URL |
|---|---|---|
| `taylorwilsdon/google_workspace_mcp` | Gmail + Calendar + Drive + Docs + Tasks | El mas completo, un solo server |
| `GongRzhe/Gmail-MCP-Server` | Solo Gmail | Mas simple, menos dependencias |
| `nspady/google-calendar-mcp` | Solo Calendar | Multi-cuenta, eventos recurrentes |
| `ngs/google-mcp-server` | Gmail + Calendar + Drive | Instalable con Homebrew |

**Setup OAuth (una sola vez, manual):**
1. Crear proyecto en Google Cloud Console
2. Habilitar Gmail API y Calendar API
3. Crear credenciales OAuth 2.0 (Client ID + Client Secret)
4. Ejecutar el MCP server interactivamente la primera vez → completar flow OAuth en el browser
5. Tokens se guardan en `~/.config/mcp-servers/*/token.json` → `chmod 600`
6. Ejecuciones posteriores usan el refresh token automaticamente

### Costos estimados

| Escenario | Costo mensual |
|---|---|
| 48 runs/dia, sin caching, API pay-as-you-go | $23 - $33 |
| 32 runs/dia (solo active hours) + prompt caching | **$9 - $15** |
| Claude Max plan ($100/mes) | $100 flat (incluye uso interactivo) |

**Desglose por run (Sonnet 4.6, pay-as-you-go):**

| Componente | Tokens estimados |
|---|---|
| HEARTBEAT.md + CLAUDE.md (input, cacheable) | 800 - 1,200 |
| MCP tool responses — emails, calendar (input, variable) | 1,000 - 3,000 |
| Claude razonamiento + respuesta (output) | 200 - 500 |
| **Total por run** | **~2,200 - 5,100 tokens** |

**Prompt caching** reduce el costo del contenido estatico (HEARTBEAT.md, CLAUDE.md) de $3.00/M a $0.30/M — una reduccion del 90%. El contenido variable (emails, calendario) no se cachea.

### Seguridad

**Capas de proteccion:**

1. **`--allowedTools` (allowlist):** Solo los MCP tools necesarios
   ```
   --allowedTools "Read,mcp__gmail__list_emails,mcp__gmail__get_email,mcp__calendar__list_events"
   ```

2. **`--disallowedTools` (denylist como defensa en profundidad):**
   ```
   --disallowedTools "Bash,Write,Edit,WebFetch,WebSearch"
   ```
   Nota: Bug conocido (#12232) donde `--allowedTools` puede ignorarse con `bypassPermissions`. Siempre usar `--disallowedTools` como backup.

3. **API key en archivo seguro:**
   ```bash
   echo 'export ANTHROPIC_API_KEY=sk-ant-...' > ~/.pipa-secrets
   chmod 600 ~/.pipa-secrets
   # NUNCA en git, NUNCA en el plist en texto plano
   ```

4. **OAuth tokens con permisos restringidos:**
   ```bash
   chmod 600 ~/.config/mcp-servers/*/token.json
   ```

**Lo que el agente NUNCA debe tener acceso a:**
- `Bash` tool (prevencion de command injection via emails maliciosos)
- `Write`/`Edit` tools (no puede modificar archivos del sistema)
- `WebFetch`/`WebSearch` (no puede hacer requests HTTP arbitrarios)
- `~/.ssh/`, `.env` de otros proyectos

### Gmail-specific: Como monitorear inbox

**Opcion A: Polling via MCP (simple — MVP)**
- Cada heartbeat, Claude usa `mcp__gmail__list_emails` para buscar no-leidos
- Pro: Simple, sin setup extra mas alla del MCP server
- Con: Latencia de hasta 30min para emails urgentes

**Opcion B: Gmail PubSub Push (reactivo — futuro)**
- Configurar `gmail.users.watch()` con Cloud Pub/Sub
- Recibir webhook → disparar heartbeat inmediato
- Pro: Latencia ~segundos
- Con: Requiere Google Cloud Pub/Sub + un daemon receptor

**Recomendacion:** Empezar con A. La arquitectura soporta B sin cambios — solo agregas un trigger adicional.

### Alternativa sin codigo: runCLAUDErun

Para quien quiera un MVP sin escribir scripts: **runCLAUDErun** (runclauderun.com) es una app nativa macOS gratuita que programa ejecuciones de Claude Code con GUI. No tiene dedup, lockfile, ni alerts — pero sirve para validar el concepto rapido.

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

## 9. Proyectos de Referencia

| Proyecto | URL | Que aprender |
|---|---|---|
| **OpenClaw** | github.com/openclaw/openclaw | Patron original del heartbeat. HEARTBEAT.md, dedup, pruning |
| **Murmur** | github.com/t0dorakis/murmur | Daemon de cron para AI. El mas parecido a nuestra implementacion |
| **Harper Reed email triage** | harper.blog | Claude Code + MCP para Gmail en produccion real |
| **runCLAUDErun** | runclauderun.com | App macOS GUI para scheduling sin codigo |
| **claude-code-scheduler** | github.com/jshchnz/claude-code-scheduler | Plugin de scheduling cross-platform |
| **Continuous Claude** | github.com/AnandChowdhary/continuous-claude | Pattern de loop continuo con memoria en archivos |
| **Ductor** | github.com/PleasePrompto/ductor | Claude Code + Telegram + cron jobs |

**Documentacion oficial de Anthropic:**
- Headless mode: code.claude.com/docs/en/headless
- Hooks: code.claude.com/docs/en/hooks-guide
- Agent SDK: platform.claude.com/docs/en/agent-sdk/overview
- Long-running agents: anthropic.com/engineering/effective-harnesses-for-long-running-agents

**Reportes de investigacion detallados (en esta carpeta):**
- `research-claudecode-headless-automation.md` — CLI flags, scheduling, auth
- `research-background-process-patterns.md` — launchd, systemd, cron, pm2, Docker
- `research-claude-agent-sdk.md` — SDK programatico, hooks, MCP servers
- `research-alwayson-agents-cli.md` — Proyectos comunitarios y patrones
- `research-heartbeat-claudecode.md` — Arquitectura especifica, costos, seguridad

---

## 10. Proximos Pasos

### Fase 1: Core Loop (1-2 dias)
1. [ ] Crear repo `heartbeat/` con estructura de carpetas
2. [ ] Escribir HEARTBEAT.md inicial (solo calendario: "eventos en los proximos 90 min")
3. [ ] Escribir `heartbeat-runner.sh` con active hours + lockfile
4. [ ] Crear archivo de secretos `~/.pipa-secrets` con `ANTHROPIC_API_KEY`
5. [ ] Probar `claude -p "$(cat HEARTBEAT.md)" --output-format json` manualmente
6. [ ] Instalar plist de launchd y verificar que dispara cada 30 min
7. [ ] Alertas via `osascript` (notificacion nativa macOS)

### Fase 2: Integracion (3-5 dias)
8. [ ] Configurar MCP server de Gmail (OAuth2 flow interactivo una vez)
9. [ ] Configurar MCP server de Google Calendar
10. [ ] Expandir HEARTBEAT.md con reglas de email
11. [ ] Implementar `state/alert-hashes.json` para deduplicacion 24h
12. [ ] Implementar `send-alert.sh` con Pushover o Telegram
13. [ ] Parsear JSON de salida con `jq` para detectar HEARTBEAT_OK vs alerta

### Fase 3: Polish (1 semana)
14. [ ] Configurar Pushover ($5) o Telegram Bot para push al celular
15. [ ] Rotacion de logs (`prune-logs.sh` via cron semanal)
16. [ ] Verificar prompt caching funciona (revisar `cost` en JSON de salida)
17. [ ] Agregar MCP server de tasks (Notion, Todoist, etc.)
18. [ ] Testing: correr 48h y auditar falsos positivos/negativos
19. [ ] Iterar HEARTBEAT.md basado en patrones observados
20. [ ] Poner alerta de gasto mensual a $30 en consola de Anthropic

### Fase Futura: Evolucion
- [ ] Migrar de polling a Gmail PubSub para reactividad instantanea
- [ ] Evaluar Agent SDK (`@anthropic-ai/claude-agent-sdk`) si se necesitan hooks programaticos
- [ ] Agregar control remoto via Telegram Bot (enviar comandos al heartbeat)
- [ ] Dashboard web local para ver estado y logs

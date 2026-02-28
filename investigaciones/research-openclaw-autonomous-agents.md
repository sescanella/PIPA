# Investigacion: OpenClaw, Agentes Autonomos 24/7 y Arquitectura PIPA

**Fecha:** 2026-02-27
**Contexto:** Investigacion aplicada al proyecto PIPA - agente autonomo que corre en Windows, usa Claude Code como motor, y monitorea Gmail cada 30 minutos.

---

## Indice de Navegacion

- [Executive Summary](#executive-summary)
- [1. OpenClaw - Arquitectura y Diseno](#1-openclaw---arquitectura-y-diseno)
- [2. Agentes Autonomos 24/7 en Windows](#2-agentes-autonomos-247-en-windows)
- [3. Claude Code como Motor de Agente](#3-claude-code-como-motor-de-agente)
- [4. Sistema de Skills y Plugins](#4-sistema-de-skills-y-plugins)
- [5. Gmail API vs IMAP para Monitoreo](#5-gmail-api-vs-imap-para-monitoreo)
- [Analisis Comparativo y Aplicacion a PIPA](#analisis-comparativo-y-aplicacion-a-pipa)
- [Conclusiones y Recomendaciones](#conclusiones-y-recomendaciones)
- [Referencias](#referencias)

---

## Executive Summary

Este informe sintetiza cinco areas de investigacion criticas para el desarrollo de PIPA, un agente autonomo que corre 24/7 en Windows usando Claude Code como cerebro cognitivo. Se analizan en profundidad OpenClaw como referente de diseno, los patrones de operacion continua en Windows, la integracion programatica de Claude Code via CLI, los sistemas de skills modulares y las opciones para monitoreo de Gmail.

Los hallazgos clave son tres: (1) OpenClaw establece el estandar de la industria para agentes locales con su arquitectura de archivos Markdown como memoria persistente (SOUL.md, AGENTS.md, HEARTBEAT.md), un patron directamente aplicable a PIPA; (2) Claude Code expone un modo headless potente via `claude -p` que permite invocacion desde scripts con sesiones persistentes a traves de `--session-id`, resolviendo el problema de continuidad de contexto; (3) para monitoreo de Gmail en un agente no-publico, la combinacion de Gmail API con `history.list` como fallback es superior a IMAP por su fiabilidad y cuotas mas generosas.

El patron arquitectonico recomendado para PIPA combina un loop central en Python gestionado por NSSM como servicio Windows, invocaciones a `claude -p` con `--session-id` para mantener contexto, un registro de skills basado en YAML + Python, y Gmail API con polling cada 30 minutos como mecanismo de entrada.

---

## Introduccion

El proyecto PIPA requiere disenar un agente que opere de forma autonoma y continua en una maquina Windows, tome decisiones basadas en eventos (emails, calendario, triggers manuales), ejecute tareas concretas (gestionar contactos, analizar documentos, actualizar CRM), y mantenga estado entre sesiones sin perder contexto critico.

Esta investigacion responde a cinco preguntas fundamentales del diseno de PIPA:

1. Como funciona OpenClaw y que podemos aprender de su arquitectura?
2. Cuales son los patrones probados para agentes continuos en Windows?
3. Como se integra Claude Code en un pipeline de automatizacion?
4. Como disenar un sistema de skills extensible y mantenible?
5. Cual es la mejor opcion para monitorear Gmail como fuente de eventos?

---

## Metodologia

La investigacion combino busquedas web multifuente, lectura directa de documentacion oficial (OpenClaw docs, Claude Code docs, Gmail API docs), analisis de repositorios GitHub relevantes y sintesis de articulos tecnicos publicados entre 2025 y febrero 2026. Las fuentes priorizadas fueron documentacion oficial, publicaciones de ingenieria de Anthropic, y la documentacion publica de OpenClaw.

---

## 1. OpenClaw - Arquitectura y Diseno

### 1.1 Que es OpenClaw

OpenClaw es un agente de IA personal de codigo abierto (licencia MIT), publicado originalmente en noviembre 2025 por Peter Steinberger bajo el nombre "Clawdbot". Alcanzo popularidad viral en enero 2026 debido a su naturaleza open-source y la popularidad del proyecto Moltbook. En febrero 2026, Steinberger anuncio que se unira a OpenAI y el proyecto pasara a una fundacion open-source.

**Tres caracteristicas lo definen como referente:**

- **Local-first**: toda la memoria se almacena como archivos Markdown en la maquina del usuario (`~/.openclaw/workspace/`)
- **Open-source (MIT)**: sin vendor lock-in
- **Autonomamente programado**: un daemon de heartbeat actua sin prompting manual

### 1.2 Arquitectura Central

OpenClaw opera bajo un modelo de Gateway WebSocket que actua como plano de control unico:

```
Canales de Mensajeria → Gateway (ws://127.0.0.1:18789) → Pi Agent Runtime + CLI + WebChat + Apps
```

**Componentes principales:**

| Componente | Funcion |
|------------|---------|
| **Gateway** | Control plane: sesiones, canales, herramientas, eventos, cron jobs, webhooks |
| **Pi Agent Runtime** | Modo RPC con streaming de herramientas; procesa mensajes y orquesta ejecucion |
| **Multi-Channel Inbox** | WhatsApp, Telegram, Slack, Discord, Signal, Teams, Matrix, iMessage, etc. |
| **Control UI** | Dashboard web en `http://127.0.0.1:18789/` para monitoreo y configuracion |

### 1.3 Sistema de Archivos de Memoria (Workspace)

El workspace de OpenClaw es el patron mas valioso para PIPA. Cada agente tiene un directorio con archivos Markdown que definen identidad, comportamiento, memoria y tareas periodicas.

**Directorio raiz:** `~/.openclaw/workspace/`

**Archivos principales y sus roles:**

| Archivo | Proposito | Analogia PIPA |
|---------|-----------|---------------|
| `SOUL.md` | Identidad, valores, temperamento, voz del agente. Se lee en cada despertar. | Personalidad y valores del asistente PIPA |
| `AGENTS.md` | Contrato operacional principal: prioridades, limites, flujo de trabajo, estandares de calidad. Solo reglas estables, no tareas temporales. | Instrucciones de sistema de PIPA |
| `IDENTITY.md` | Perfil estructurado: nombre, rol, objetivos, voz. | Descripcion del rol de PIPA |
| `USER.md` | Preferencias personales, tono de comunicacion, restricciones conocidas. | Perfil del usuario (Sebastian) |
| `TOOLS.md` | Documentacion del entorno: convenciones de rutas, alias, comandos riesgosos, comportamientos especificos del host. | Inventario de herramientas disponibles |
| `HEARTBEAT.md` | Checklist para comportamiento periodico: tareas de mantenimiento pasivo, scans recurrentes. | Lista de tareas autonomas de PIPA |
| `BOOT.md` | Rituales de inicio (solo cuando `hooks.internal.enabled: true`). | Inicializacion de sesion |
| `MEMORY.md` | Verdades duraderas y historial comprimido que sobrevive ciclos diarios. | Estado persistente entre sesiones |
| `memory/YYYY-MM-DD.md` | Notas de trabajo del dia. | Logs diarios de actividad |

**Separacion de concerns critica:** SOUL.md contiene reglas permanentes de identidad, AGENTS.md directivas operacionales, y USER.md preferencias personales. Mezclar estos contextos causa comportamiento inestable.

### 1.4 Sistema de Heartbeat - El Daemon Autonomo

El Heartbeat es el mecanismo que convierte a OpenClaw de reactivo a proactivo. Es el patron central mas aplicable a PIPA.

**Como funciona:**

1. El Gateway envia al agente un "heartbeat prompt" cada X minutos (default: 30m)
2. El agente lee `HEARTBEAT.md` en su workspace
3. Evalua si algun item requiere accion
4. Responde `HEARTBEAT_OK` (silencio) o envia una alerta

**Contrato de respuesta:** Si nada requiere atencion, el agente responde `HEARTBEAT_OK`. OpenClaw suprime este acknowledgment si aparece al inicio/fin del mensaje y el contenido restante tiene menos de 300 caracteres (optimizacion de costos). El contenido de alerta nunca incluye `HEARTBEAT_OK`.

**Configuracion en config.json:**

```json
{
  "agents": {
    "defaults": {
      "heartbeat": {
        "every": "30m",
        "model": "anthropic/claude-sonnet-4-5",
        "target": "last",
        "activeHours": {
          "start": "08:00",
          "end": "22:00"
        }
      }
    }
  },
  "timezone": "America/Argentina/Buenos_Aires"
}
```

**Jerarquia de configuracion:** agent-especifico > defaults de agente > channel-especifico > defaults globales.

**Formato de HEARTBEAT.md:**

```markdown
## Morning Briefing (8:00-8:30 AM)
- Check urgent emails from VIP contacts
- Review calendar events for today

## Throughout Day (9 AM - 6 PM)
- Scan inbox every 30 minutes for emails labeled URGENT
- Monitor for new client inquiries

## Anytime
- Alert if CPU usage > 90% for more than 5 minutes
- Check for overdue tasks in project tracker
```

**Costo real:** Con Claude Opus, entre $5-30/dia dependiendo de frecuencia y tamano de contexto. Con Claude Sonnet, ~5x menos costoso.

### 1.5 Skills en OpenClaw

Las skills de OpenClaw siguen una arquitectura de meta-herramienta donde una herramienta llamada `Skill` actua como contenedor y despachador. Las skills se almacenan como directorios:

```
~/.openclaw/workspace/skills/
└── email-monitor/
    └── SKILL.md    # Frontmatter YAML + instrucciones
└── crm-updater/
    └── SKILL.md
```

Arquitectura de tres niveles para eficiencia de tokens:
- **Metadata (frontmatter)**: nombre y criterios de activacion, siempre cargados
- **Instructions**: guia central y patrones, cargados cuando se activa
- **Resources**: ejemplos y templates, cargados bajo demanda

### 1.6 Instalacion en Windows

OpenClaw requiere Node.js 22+ y se recomienda correr bajo WSL2 en Windows. El daemon se instala con:

```bash
npm install -g openclaw@latest
openclaw onboard --install-daemon
```

Variables de entorno configurables: `OPENCLAW_HOME`, `OPENCLAW_STATE_DIR`, `OPENCLAW_CONFIG_PATH`.

---

## 2. Agentes Autonomos 24/7 en Windows

### 2.1 El Problema Central de los Agentes de Larga Duracion

El desafio principal identificado por la investigacion de Anthropic es que los agentes trabajan en sesiones discretas sin memoria de lo ocurrido anteriormente. El problema no es tecnico sino arquitectonico: **como bridgear el gap entre sesiones de manera que cada nueva sesion pueda retomar exactamente donde la anterior termino**.

Anthropic documenta cuatro modos de fallo recurrentes en agentes de larga duracion:

| Problema | Solucion |
|----------|----------|
| Agente intenta completar todo de una vez | Lista de features estructurada con dependencias explicitas |
| Progreso no documentado deja la siguiente sesion rota | Commits git + actualizacion de archivo de progreso obligatoria |
| Completar una feature prematuramente | Testing end-to-end obligatorio antes de marcar como hecho |
| Setup consume todo el contexto | Script `init.sh` pre-escrito para arranque rapido del entorno |

### 2.2 Patron de Dos Fases: Initializer + Worker

Anthropic recomienda este patron para agentes que necesitan continuidad entre sesiones:

**Fase 1 - Initializer Agent (solo primer arranque):**
- Configura infraestructura base
- Crea archivos de estado iniciales
- Establece convencion de logs y formato de progreso
- Documenta el entorno (rutas, herramientas disponibles, restricciones)

**Fase 2 - Worker Agent (cada sesion subsiguiente):**
```
1. pwd  → verificar directorio de trabajo
2. Leer progress.json / progress.txt
3. Leer git log --oneline -20
4. Seleccionar proxima tarea prioritaria
5. Ejecutar servidor de desarrollo
6. Correr tests end-to-end basicos
7. Si no hay bugs criticos: implementar siguiente feature
8. Actualizar archivo de progreso + commit
```

**Formato de estado recomendado:** JSON en lugar de Markdown para el archivo de progreso, ya que los modelos manejan JSON mas confiablemente para parsing estructurado.

### 2.3 Arquitectura de Persistencia de Estado

Para un agente 24/7 en Windows, el estado debe persistir en multiples capas:

**Capa 1 - Estado de Session (efimero):**
- Variables en memoria durante la ejecucion
- Session ID de Claude Code para continuidad dentro de una sesion

**Capa 2 - Estado de Tarea (semi-persistente):**
- Archivo `agent-state.json` con tarea actual, intentos, resultado esperado
- Actualizado al inicio y fin de cada ejecucion

**Capa 3 - Estado de Contexto (duradero):**
- Equivalente a MEMORY.md de OpenClaw
- Hechos importantes que deben sobrevivir reinicios
- Patron: comprimir periodicamente los logs diarios a hechos clave

**Capa 4 - Historial de Actividad (auditoria):**
- Logs rotatorios por dia: `activity-YYYY-MM-DD.log`
- Nunca borrar, solo rotar

### 2.4 Estrategias de Error Handling y Recuperacion

**Clasificacion de errores (critica para retry logic):**

| Tipo | Descripcion | Accion |
|------|-------------|--------|
| **Retriable seguro** | Fetch de datos, llamada de lectura | Retry con backoff exponencial |
| **Retriable con verificacion** | Operacion que puede crear duplicados | Verificar estado primero, luego retry |
| **No retriable** | Error de logica, datos invalidos | Fallar rapido, escalar a humano |
| **Ambiguo (timeout)** | No se sabe si se completo | Consultar estado externo, no asumir |

**Patron de backoff exponencial con jitter:**

```python
import time
import random

def retry_with_backoff(func, max_attempts=5, base_delay=1.0):
    for attempt in range(max_attempts):
        try:
            return func()
        except TransientError as e:
            if attempt == max_attempts - 1:
                raise
            delay = base_delay * (2 ** attempt) + random.uniform(0, 1)
            time.sleep(delay)
```

**Circuit Breaker para proteger servicios externos:**

El patron es especialmente importante para llamadas a APIs externas (Claude API, Gmail API). Una vez que el circuit breaker "dispara" (N fallos en T tiempo), el servicio fallido se excluye del pool de routing y no recibe mas requests hasta que termine el periodo de cooldown.

**Principios de diseno de recuperacion:**

1. **Los rollbacks no existen en sistemas distribuidos** - disenar acciones compensatorias explicitas para cada paso irreversible
2. **Tratar timeouts como incertidumbre, no como fallo** - consultar estado externo antes de reintentar
3. **Idempotencia es esencial** - los retries de llamadas stateful son bugs disfrazados de resiliencia
4. **Workflows estilo Saga** - cada paso registra su logica de compensacion; en caso de fallo se recorre hacia atras

### 2.5 Ejecutar un Agente Python como Servicio Windows con NSSM

NSSM (Non-Sucking Service Manager) es la herramienta recomendada para convertir un script Python en un servicio Windows persistente con auto-restart.

**Instalacion y configuracion:**

```powershell
# Instalar NSSM (descargar nssm.exe de nssm.cc)
# Instalar como servicio:
nssm install PIPA-Agent "C:\Python\python.exe" "C:\PIPA\main.py"

# Configurar auto-restart:
nssm set PIPA-Agent AppRestartDelay 5000  # 5 segundos
nssm set PIPA-Agent AppStdout "C:\PIPA\logs\stdout.log"
nssm set PIPA-Agent AppStderr "C:\PIPA\logs\stderr.log"
nssm set PIPA-Agent AppRotateFiles 1
nssm set PIPA-Agent AppRotateSeconds 86400  # Rotar diariamente

# Iniciar:
nssm start PIPA-Agent
```

**Alternativa con Windows Task Scheduler** (para ejecuciones periódicas, no continuas):

```xml
<!-- Trigger cada 30 minutos -->
<Trigger>
  <Repetition>
    <Interval>PT30M</Interval>
    <Duration>P9999D</Duration>
  </Repetition>
</Trigger>
```

**Recomendacion para PIPA:** NSSM para el loop principal del agente (proceso continuo) + Task Scheduler como backup de watchdog que verifica que el servicio NSSM este corriendo.

### 2.6 Observabilidad como Requisito No Negociable

"Build in observability by tracking every decision, tool call, and schema difference from day one." - Google Cloud Architecture Center

**Checklist de observabilidad minima para PIPA:**

- [ ] Log estructurado (JSON) de cada ejecucion: timestamp, trigger, accion tomada, resultado, duracion
- [ ] Log de errores con stack trace completo
- [ ] Metrica de heartbeat: ultima ejecucion exitosa, duracion promedio, tasa de error
- [ ] Alert si el heartbeat no se ejecuto en 2x el intervalo esperado
- [ ] Dashboard simple (archivo HTML generado) con estado actual del agente

---

## 3. Claude Code como Motor de Agente

### 3.1 Modo Headless: La Interfaz Programatica

Claude Code expone su funcionalidad via el flag `-p` (o `--print`) para ejecucion no interactiva. Este modo es la interfaz natural para integrar Claude Code en pipelines de automatizacion.

**Uso basico:**

```bash
claude -p "Cual es el estado actual del proyecto?" --allowedTools "Read,Bash"
```

**Importante:** La documentacion oficial nota que el modo headless antes se llamaba "headless mode". El SDK de Agentes (Agent SDK) es ahora la interfaz recomendada y el `-p` CLI es su manifestacion en linea de comandos.

### 3.2 Control de Herramientas y Permisos

El flag `--allowedTools` permite especificar exactamente que herramientas puede usar Claude sin pedir confirmacion. Esto es critico para ejecucion autonoma:

```bash
# Uso basico con herramientas especificas
claude -p "Ejecuta los tests y reporta el resultado" \
  --allowedTools "Bash,Read,Edit"

# Con prefix matching para restringir comandos especificos
claude -p "Revisa los cambios staged y crea un commit" \
  --allowedTools "Bash(git diff *),Bash(git log *),Bash(git status *),Bash(git commit *)"
```

**Nota sobre el espacio antes de `*`:** `Bash(git diff *)` (con espacio) solo permite comandos que empiezan exactamente con `git diff `. Sin el espacio, `Bash(git diff*)` tambien matchearia `git diff-index`. El espacio es critico para seguridad.

### 3.3 Sesiones Persistentes: El Problema del Contexto entre Ejecuciones

El problema central de usar Claude Code como motor autonomo es mantener contexto entre ejecuciones separadas. Claude Code resuelve esto con dos mecanismos:

**Mecanismo 1: `--continue` (continuar la sesion mas reciente)**

```bash
# Primera llamada
claude -p "Analiza el codebase para problemas de performance"

# Segunda llamada - continua el contexto de la anterior
claude -p "Enfocate en las queries de base de datos" --continue

# Tercera llamada - sigue en la misma sesion
claude -p "Genera un resumen de todos los issues encontrados" --continue
```

**Mecanismo 2: `--resume` con session ID (sesion especifica)**

```bash
# Capturar session ID de la primera llamada
session_id=$(claude -p "Inicia revision de seguridad" \
  --output-format json | jq -r '.session_id')

# Guardar session_id en archivo de estado
echo "$session_id" > /pipa/state/current-session.txt

# En la siguiente ejecucion, retomar esa sesion especifica
session_id=$(cat /pipa/state/current-session.txt)
claude -p "Continua la revision donde quedamos" --resume "$session_id"
```

**Estrategia recomendada para PIPA:** Mantener un `session-registry.json` que mapea tipo de tarea a su session ID activo. Crear nueva sesion cuando el contexto esta muy cargado o la tarea cambia completamente.

### 3.4 Formatos de Salida Estructurada

Para integracion programatica, `--output-format json` es esencial:

```bash
# Output JSON con metadata de sesion
claude -p "Extrae emails pendientes de respuesta" \
  --output-format json \
  --allowedTools "Read,Bash"
# Retorna: { "result": "...", "session_id": "abc123", "usage": {...} }

# Output con schema especifico (structured output)
claude -p "Clasifica este email: [contenido]" \
  --output-format json \
  --json-schema '{
    "type": "object",
    "properties": {
      "category": {"type": "string", "enum": ["urgent", "normal", "spam"]},
      "requires_action": {"type": "boolean"},
      "summary": {"type": "string"}
    },
    "required": ["category", "requires_action", "summary"]
  }'
```

**Uso con jq para parsing:**

```bash
# Extraer solo el resultado de texto
result=$(claude -p "..." --output-format json | jq -r '.result')

# Extraer structured output
category=$(claude -p "Clasifica..." \
  --output-format json \
  --json-schema '...' | jq -r '.structured_output.category')
```

### 3.5 Personalizacion del System Prompt

```bash
# Agregar instrucciones al system prompt default
gh pr diff "$PR_NUMBER" | claude -p \
  --append-system-prompt "Eres un asistente especializado en gestion de clientes B2B. \
    Tu objetivo es identificar oportunidades de negocio y acciones de seguimiento." \
  --output-format json

# Reemplazar completamente el system prompt
claude -p "Analiza este email" \
  --system-prompt "Eres PIPA, asistente de gestion de clientes de 5INCO..."
```

### 3.6 Patron de Integracion para PIPA

```python
import subprocess
import json
import os

class ClaudeCodeEngine:
    def __init__(self, state_dir: str):
        self.state_dir = state_dir
        self.session_file = os.path.join(state_dir, "claude-sessions.json")
        self.sessions = self._load_sessions()

    def _load_sessions(self) -> dict:
        if os.path.exists(self.session_file):
            with open(self.session_file) as f:
                return json.load(f)
        return {}

    def _save_sessions(self):
        with open(self.session_file, 'w') as f:
            json.dump(self.sessions, f)

    def run(self, prompt: str, task_type: str,
            allowed_tools: str = "Read,Bash",
            json_schema: dict = None) -> dict:

        cmd = ["claude", "-p", prompt,
               "--allowedTools", allowed_tools,
               "--output-format", "json"]

        # Continuar sesion existente del mismo tipo de tarea
        if task_type in self.sessions:
            cmd += ["--resume", self.sessions[task_type]]

        if json_schema:
            cmd += ["--json-schema", json.dumps(json_schema)]

        result = subprocess.run(cmd, capture_output=True, text=True)
        output = json.loads(result.stdout)

        # Guardar session ID para proxima ejecucion
        if 'session_id' in output:
            self.sessions[task_type] = output['session_id']
            self._save_sessions()

        return output
```

### 3.7 Sub-agentes y Agentes Custom

Claude Code soporta definicion de sub-agentes como archivos Markdown con frontmatter YAML en `.claude/agents/`. Esto permite crear agentes especializados que el agente principal puede invocar:

```markdown
---
name: email-processor
description: Especializado en clasificar y procesar emails de clientes
tools: Read, Bash, Edit
---

Eres un experto en gestion de emails de clientes B2B.
Cuando proceses un email, siempre:
1. Identifica el remitente y su nivel de urgencia
2. Clasifica la solicitud (soporte, venta, consulta, queja)
3. Sugiere la respuesta apropiada o accion de CRM
```

---

## 4. Sistema de Skills y Plugins

### 4.1 Patrones de Arquitectura de Plugins

La investigacion identifica tres patrones principales para sistemas de skills extensibles:

**Patron 1: Registry con Decoradores (Python)**

El patron mas idiomatico en Python. Cada skill se autoregistra al importarse:

```python
# skill_registry.py
class SkillRegistry:
    _skills: dict = {}

    @classmethod
    def register(cls, name: str, description: str = ""):
        def decorator(func):
            cls._skills[name] = {
                "handler": func,
                "description": description,
                "name": name
            }
            return func
        return decorator

    @classmethod
    def get(cls, name: str):
        return cls._skills.get(name)

    @classmethod
    def list_all(cls) -> list:
        return list(cls._skills.keys())

# email_skill.py
from skill_registry import SkillRegistry

@SkillRegistry.register("check_emails",
    description="Verifica y clasifica emails nuevos en Gmail")
def check_emails(context: dict) -> dict:
    # implementacion
    pass
```

**Patron 2: Discovery por Directorio (file-based, estilo OpenClaw)**

Las skills son directorios auto-descubiertos. El agente escanea el directorio de skills al inicio:

```
skills/
├── email-monitor/
│   ├── skill.yaml       # Metadata y configuracion
│   └── handler.py       # Logica de ejecucion
├── crm-updater/
│   ├── skill.yaml
│   └── handler.py
└── calendar-sync/
    ├── skill.yaml
    └── handler.py
```

```yaml
# skills/email-monitor/skill.yaml
name: email-monitor
description: Monitorea Gmail cada 30 minutos buscando emails no leidos
version: "1.0"
triggers:
  - type: schedule
    interval: 30m
  - type: manual
    command: check_emails
required_tools:
  - gmail_api
permissions:
  - gmail.readonly
```

**Patron 3: Command Dispatcher (desacoplamiento total)**

El agente principal no conoce las skills directamente. Envia comandos a un dispatcher que los enruta:

```python
class CommandDispatcher:
    def __init__(self):
        self._handlers = {}

    def register(self, command: str, handler):
        self._handlers[command] = handler

    def dispatch(self, command: str, payload: dict) -> dict:
        if command not in self._handlers:
            raise UnknownCommandError(f"Skill no encontrada: {command}")

        handler = self._handlers[command]
        return handler(payload)

    def can_handle(self, command: str) -> bool:
        return command in self._handlers
```

### 4.2 Arquitectura de Tres Niveles para Skills

Siguiendo el patron de OpenClaw, cada skill debe exponer tres niveles de informacion con diferente costo de carga:

**Nivel 1 - Metadata (siempre cargado, bajo costo):**
- Nombre, descripcion, triggers, version
- Usado para discovery y routing inicial

**Nivel 2 - Instructions (cargado cuando se activa):**
- Instrucciones detalladas de uso
- Parametros esperados, formato de respuesta
- Casos de uso y ejemplos basicos

**Nivel 3 - Resources (cargado bajo demanda, alto costo):**
- Templates de respuesta
- Ejemplos completos
- Documentacion de referencia

### 4.3 Estructura de una Skill para PIPA

```
pipa/skills/
└── gmail-monitor/
    ├── skill.yaml          # Nivel 1: metadata
    ├── instructions.md     # Nivel 2: como usar la skill
    ├── handler.py          # Logica de ejecucion
    └── templates/          # Nivel 3: templates de respuesta
        └── email-summary.md
```

```yaml
# skill.yaml
name: gmail-monitor
version: "1.0.0"
description: >
  Monitorea Gmail buscando emails no leidos y los clasifica
  por prioridad para el usuario.
author: PIPA
triggers:
  - schedule: "*/30 * * * *"    # Cada 30 minutos
  - event: "manual:check_email"
input_schema:
  type: object
  properties:
    max_results:
      type: integer
      default: 10
    labels:
      type: array
      items:
        type: string
      default: ["INBOX", "UNREAD"]
output_schema:
  type: object
  properties:
    emails_found:
      type: integer
    actions_required:
      type: array
    summary:
      type: string
```

### 4.4 Patron de Carga Dinamica

```python
import importlib.util
import yaml
import os
from pathlib import Path

class SkillLoader:
    def __init__(self, skills_dir: str):
        self.skills_dir = Path(skills_dir)
        self.loaded_skills = {}

    def discover(self) -> list[dict]:
        """Descubre todas las skills disponibles leyendo solo metadata."""
        skills = []
        for skill_dir in self.skills_dir.iterdir():
            if skill_dir.is_dir():
                yaml_file = skill_dir / "skill.yaml"
                if yaml_file.exists():
                    with open(yaml_file) as f:
                        meta = yaml.safe_load(f)
                    meta['_path'] = str(skill_dir)
                    skills.append(meta)
        return skills

    def load(self, skill_name: str):
        """Carga el handler de una skill especifica bajo demanda."""
        if skill_name in self.loaded_skills:
            return self.loaded_skills[skill_name]

        skill_dir = self.skills_dir / skill_name
        handler_file = skill_dir / "handler.py"

        spec = importlib.util.spec_from_file_location(
            f"skill_{skill_name}", handler_file
        )
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)

        self.loaded_skills[skill_name] = module
        return module
```

### 4.5 Sistema de Triggers

Para PIPA, los triggers son el mecanismo que dispara una skill:

| Tipo de Trigger | Descripcion | Ejemplo |
|----------------|-------------|---------|
| `schedule` | Cron-like, basado en tiempo | `every: 30m`, `cron: "0 8 * * *"` |
| `event` | Basado en evento del sistema | `gmail.new_email`, `calendar.upcoming` |
| `manual` | Disparado explicitamente por usuario | via Telegram/WhatsApp a OpenClaw |
| `chain` | Disparado por otra skill | email-monitor activa crm-updater |

---

## 5. Gmail API vs IMAP para Monitoreo

### 5.1 Resumen Comparativo

| Criterio | Gmail API | IMAP |
|----------|-----------|------|
| **Autenticacion** | OAuth 2.0 (mas seguro) | App Password o credenciales basicas |
| **Rate limits** | 250 unidades/seg por usuario, 1 evento/seg | Sin limites especificos de Google |
| **Notificaciones en tiempo real** | Si, via Pub/Sub (watch()) | Si, via IDLE command |
| **Polling simple** | Si, via history.list | Si, via IMAP SELECT |
| **Fiabilidad de notificaciones** | Alta, pero con expiración de 7 días | Moderada, IDLE puede desconectarse |
| **Complejidad de setup** | Alta (Google Cloud Console, Pub/Sub) | Baja (solo credenciales) |
| **Funcionalidades extra** | Labels, Drive adjuntos, audit pass | Basico: leer, mover, eliminar |
| **Riesgo de suspension** | Bajo (audit de seguridad requerido) | Alto si patrones automatizados son detectados |
| **Costo de acceso** | Gratis para uso personal | Gratis |
| **Apto para agente no-publico** | Si (app no verificada, uso propio) | Si |

### 5.2 Gmail API en Detalle

**Flujo de autenticacion para app de uso propio:**

1. Crear proyecto en Google Cloud Console
2. Habilitar Gmail API
3. Crear credenciales OAuth 2.0 tipo "Desktop application"
4. Primera ejecucion: flujo de autenticacion en browser, genera `token.json`
5. Ejecuciones subsiguientes: renovacion automatica del token

**Nota importante:** Google requiere un "audit de seguridad" ($15k-75k) solo para apps que solicitan el scope `gmail.readonly` Y tienen verificacion publica. Para uso personal/interno (agente corriendo en tu propia maquina), no se necesita pasar ese proceso.

**Dos modos de acceso:**

**Modo A - Push Notifications (watch + Pub/Sub):**

```python
service.users().watch(
    userId='me',
    body={
        'topicName': 'projects/mi-proyecto/topics/gmail-notifs',
        'labelIds': ['INBOX']
    }
).execute()
```

- Requiere Google Cloud Pub/Sub configurado
- Notificaciones llegan en segundos de recibir el email
- `watch()` expira cada 7 dias, debe renovarse (llamar `watch()` una vez al dia)
- Limitacion: max 1 evento/segundo por usuario (exceso se descarta)
- **Recomendacion oficial:** usar `history.list` como fallback periodico por si se pierden notificaciones

**Modo B - Polling con history.list (el approach mas simple para PIPA):**

```python
def get_new_emails_since(service, last_history_id: str) -> list:
    """Retorna emails nuevos desde el ultimo historyId conocido."""
    try:
        response = service.users().history().list(
            userId='me',
            startHistoryId=last_history_id,
            historyTypes=['messageAdded'],
            labelId='INBOX'
        ).execute()

        new_messages = []
        if 'history' in response:
            for record in response['history']:
                if 'messagesAdded' in record:
                    for msg in record['messagesAdded']:
                        new_messages.append(msg['message']['id'])

        # Guardar nuevo historyId para proxima ejecucion
        new_history_id = response.get('historyId', last_history_id)
        return new_messages, new_history_id

    except HttpError as e:
        if e.resp.status == 404:
            # historyId expirado, hacer full sync
            return full_sync(service)
        raise
```

**Ventaja clave del polling con history.list:** No requiere infraestructura Pub/Sub, funciona perfectamente para intervalos de 30 minutos, y el `historyId` actua como un "bookmark" que garantiza que no se pierdan emails entre ejecuciones.

### 5.3 IMAP en Detalle

**Setup para Gmail:**

```python
import imaplib
import email

def check_gmail_imap(email_address: str, app_password: str,
                     folder: str = 'INBOX') -> list:
    with imaplib.IMAP4_SSL('imap.gmail.com') as imap:
        imap.login(email_address, app_password)
        imap.select(folder)

        # Buscar emails no leidos
        _, message_ids = imap.search(None, 'UNSEEN')

        emails = []
        for msg_id in message_ids[0].split():
            _, msg_data = imap.fetch(msg_id, '(RFC822)')
            email_message = email.message_from_bytes(msg_data[0][1])
            emails.append({
                'id': msg_id,
                'from': email_message['From'],
                'subject': email_message['Subject'],
                'date': email_message['Date']
            })

        return emails
```

**IMAP IDLE para notificaciones real-time:**

IMAP tiene el comando IDLE que mantiene la conexion abierta y notifica cambios sin polling. Es mas eficiente en bandwidth que polling, pero:
- Requiere manejar desconexiones frecuentes (timeout tipico: 29 minutos en Gmail)
- El reconectar y re-autenticar agrega complejidad
- No es necesario para un agente que solo chequea cada 30 minutos

### 5.4 Recomendacion para PIPA

**Para el caso de uso de PIPA (agente personal, chequeo cada 30 minutos, en Windows):**

**Opcion recomendada: Gmail API con history.list polling**

Justificacion:
1. El `historyId` garantiza que no se pierden emails entre ejecuciones del heartbeat
2. No requiere infraestructura adicional (sin Pub/Sub, sin servidor HTTP para webhooks)
3. OAuth 2.0 es mas seguro que App Password
4. La API proporciona acceso a labels, permite marcar como leido, mover a labels
5. Sin riesgo de suspension por patrones automatizados

**Implementacion minimal para PIPA:**

```python
# pipa/skills/gmail-monitor/handler.py
from googleapiclient.discovery import build
from google.oauth2.credentials import Credentials
import json, os

STATE_FILE = "pipa/state/gmail-state.json"

def execute(context: dict) -> dict:
    creds = Credentials.from_authorized_user_file('token.json')
    service = build('gmail', 'v1', credentials=creds)

    # Cargar ultimo historyId conocido
    state = load_state()
    last_history_id = state.get('last_history_id')

    if not last_history_id:
        # Primera ejecucion: obtener historyId actual
        profile = service.users().getProfile(userId='me').execute()
        last_history_id = profile['historyId']
        save_state({'last_history_id': last_history_id})
        return {"emails_found": 0, "message": "Estado inicial registrado"}

    # Obtener cambios desde la ultima ejecucion
    new_emails, new_history_id = get_new_emails_since(service, last_history_id)
    save_state({'last_history_id': new_history_id})

    return {
        "emails_found": len(new_emails),
        "email_ids": new_emails,
        "new_history_id": new_history_id
    }

def load_state() -> dict:
    if os.path.exists(STATE_FILE):
        with open(STATE_FILE) as f:
            return json.load(f)
    return {}

def save_state(state: dict):
    os.makedirs(os.path.dirname(STATE_FILE), exist_ok=True)
    with open(STATE_FILE, 'w') as f:
        json.dump(state, f)
```

---

## Analisis Comparativo y Aplicacion a PIPA

### Que Puede Copiar PIPA de OpenClaw

| Patron de OpenClaw | Aplicacion en PIPA |
|-------------------|-------------------|
| Workspace de archivos Markdown | `pipa/workspace/` con SOUL.md, AGENTS.md, HEARTBEAT.md equivalentes |
| HEARTBEAT.md como checklist | Lista de tareas periodicas que Claude Code procesa en cada heartbeat |
| Separacion SOUL / AGENTS / USER | Separar instrucciones permanentes, operacionales y de preferencias del usuario |
| Skills como directorios autodescubiertos | `pipa/skills/[nombre]/skill.yaml + handler.py` |
| HEARTBEAT_OK como senal de silencio | Sistema de respuesta binario: accion requerida vs. sin novedades |
| memory/YYYY-MM-DD.md | Logs diarios + compresion periodica a MEMORY.md |

### Diferencias Clave PIPA vs OpenClaw

| Aspecto | OpenClaw | PIPA |
|---------|----------|------|
| Motor cognitivo | Claude, GPT, Gemini via Pi Agent Runtime | Claude Code CLI directo |
| Interfaz de usuario | WhatsApp, Telegram, Discord, etc. | A definir (posiblemente Telegram via OpenClaw, o propio) |
| Plataforma | macOS/Linux (recomendado), Windows via WSL2 | Windows nativo |
| Arquitectura | Gateway WebSocket + daemon Node.js | Python loop + NSSM service |
| Persistencia sesion | Manejo interno del Gateway | Archivo session-registry.json + `--resume` flag |

### Arquitectura Propuesta para PIPA

```
Windows Service (NSSM)
└── pipa/main.py (loop principal, cada 30min)
    ├── Estado: pipa/state/
    │   ├── agent-state.json      (tarea actual, session IDs)
    │   ├── gmail-state.json      (historyId para Gmail API)
    │   └── activity-YYYY-MM-DD.log
    ├── Workspace: pipa/workspace/
    │   ├── SOUL.md               (identidad PIPA)
    │   ├── AGENTS.md             (instrucciones operacionales)
    │   ├── HEARTBEAT.md          (checklist autonomo)
    │   ├── USER.md               (perfil Sebastian)
    │   └── MEMORY.md             (contexto persistente)
    ├── Skills: pipa/skills/
    │   ├── gmail-monitor/        (skill de email)
    │   ├── crm-updater/          (skill de CRM)
    │   └── calendar-sync/        (skill de calendario)
    └── Motor: ClaudeCodeEngine
        └── claude -p [prompt]
            --resume [session_id]
            --allowedTools "Read,Bash,Edit"
            --output-format json
```

---

## Conclusiones y Recomendaciones

### Conclusiones Principales

1. **OpenClaw es el referente de diseno mas relevante para PIPA.** Su arquitectura de archivos Markdown como memoria, el patron de heartbeat con HEARTBEAT.md, y la separacion de concerns entre SOUL/AGENTS/USER/MEMORY son directamente trasladables al proyecto.

2. **Claude Code headless (`-p`) con `--resume` resuelve el problema de contexto entre sesiones.** El sistema de session IDs permite mantener conversaciones coherentes entre ejecuciones separadas del heartbeat, sin necesidad de re-establecer contexto desde cero.

3. **Gmail API con `history.list` es la solucion correcta para PIPA.** El `historyId` funciona como bookmark garantizando que no se pierdan emails. Para uso personal no se requiere audit de seguridad de Google. IMAP es mas simple de configurar pero ofrece menos garantias.

4. **NSSM es la herramienta correcta para Windows.** Convierte el script Python en un servicio Windows con auto-restart, gestion de I/O y logs, sin necesidad de reescribir el agente como un Windows Service nativo.

5. **El error handling debe clasificar explicitamente que es retriable y que no.** Los timeouts son incertidumbre, no fallos. Las operaciones stateful necesitan idempotencia antes de poder reintentarse.

### Recomendaciones Inmediatas para PIPA

**Prioridad 1 - Infraestructura base:**
- Crear estructura de workspace con SOUL.md, AGENTS.md, HEARTBEAT.md, USER.md, MEMORY.md
- Implementar `ClaudeCodeEngine` con gestion de session IDs
- Configurar NSSM para correr el agente como servicio Windows

**Prioridad 2 - Skill de Gmail:**
- Implementar autenticacion OAuth 2.0 para Gmail API
- Skill `gmail-monitor` usando `history.list` con estado persistente en `gmail-state.json`
- Manejo de `historyId` expirado (full sync como fallback)

**Prioridad 3 - Sistema de Skills:**
- Implementar `SkillLoader` con discovery por directorio
- Formato `skill.yaml` con metadata, triggers y schemas de input/output
- Registry de skills para invocacion por nombre desde el heartbeat

**Prioridad 4 - Observabilidad:**
- Logs estructurados (JSON) con timestamp, trigger, skill ejecutada, resultado, duracion
- Metrica de ultima ejecucion exitosa
- Alert si el heartbeat no corre en 2x el intervalo configurado

---

## Referencias

- [OpenClaw GitHub Repository](https://github.com/openclaw/openclaw) - Codigo fuente y documentacion tecnica
- [OpenClaw - Wikipedia](https://en.wikipedia.org/wiki/OpenClaw) - Historia y contexto del proyecto
- [OpenClaw Heartbeat Documentation](https://docs.openclaw.ai/gateway/heartbeat) - Documentacion oficial del sistema de heartbeat
- [OpenClaw Installation Guide](https://docs.openclaw.ai/install) - Instalacion y requisitos del sistema
- [OpenClaw Memory Files Explained](https://openclaw-setup.me/blog/openclaw-memory-files/) - AGENTS.md, SOUL.md, HEARTBEAT.md y su uso
- [Schedule Proactive Tasks with Heartbeat](https://markaicode.com/openclaw-heartbeat-proactive-tasks/) - Guia practica de configuracion del heartbeat
- [OpenClaw Identity Architecture](https://www.mmntm.net/articles/openclaw-identity-architecture) - Como OpenClaw implementa identidad de agente
- [Run Claude Code Programmatically](https://code.claude.com/docs/en/headless) - Documentacion oficial de Claude Code headless mode y Agent SDK
- [Effective Harnesses for Long-Running Agents](https://www.anthropic.com/engineering/effective-harnesses-for-long-running-agents) - Anthropic Engineering: patrones para agentes de larga duracion
- [AI Agent Orchestration Patterns - Azure](https://learn.microsoft.com/en-us/azure/architecture/ai-ml/guide/ai-agent-design-patterns) - Microsoft: patrones de orquestacion de agentes
- [Choose a Design Pattern for Agentic AI - Google Cloud](https://docs.cloud.google.com/architecture/choose-design-pattern-agentic-ai-system) - Google Cloud: patrones de diseno para sistemas de agentes
- [Error Handling in Agentic Systems](https://agentsarcade.com/blog/error-handling-agentic-systems-retries-rollbacks-graceful-failure) - Retries, rollbacks y graceful failure en agentes
- [Retries, Fallbacks and Circuit Breakers in LLM Apps](https://portkey.ai/blog/retries-fallbacks-and-circuit-breakers-in-llm-apps/) - Patrones de resiliencia para aplicaciones LLM
- [Gmail API Push Notifications](https://developers.google.com/workspace/gmail/api/guides/push) - Documentacion oficial de Gmail API watch() y Pub/Sub
- [AgentMail vs Gmail for OpenClaw Agents](https://www.agentmail.to/blog/agentmail-vs-gmail-openclaw) - Comparativa de opciones de email para agentes AI
- [Gmail API vs IMAP - GMass](https://www.gmass.co/blog/gmail-api-vs-imap/) - Analisis comparativo Gmail API vs IMAP
- [NSSM - Non-Sucking Service Manager](http://nssm.cc/usage) - Herramienta para correr procesos Python como servicios Windows
- [Claude Agent Skills Deep Dive](https://leehanchung.github.io/blogs/2025/10/26/claude-skills-deep-dive/) - Arquitectura detallada del sistema de skills de Claude
- [Building a Plugin Architecture with Python](https://mwax911.medium.com/building-a-plugin-architecture-with-python-7b4ab39ad4fc) - Patrones de plugin architecture en Python
- [Runlayer OpenClaw Agentic Capabilities](https://venturebeat.com/orchestration/runlayer-is-now-offering-secure-openclaw-agentic-capabilities-for-large) - OpenClaw en contexto empresarial

# Guia de Aprendizaje: El Sistema Heartbeat

> De cero a arquitecto. Este documento te lleva paso a paso, desde la intuicion hasta el detalle tecnico, para que entiendas completamente como funciona un sistema Heartbeat para agentes de IA.

---

## Nivel 1: La Gran Idea (Sin codigo, solo intuicion)

### Imagina que tienes un asistente personal

Piensa en un asistente ejecutivo de los de antes. De traje, libreta en mano, sentado afuera de tu oficina.

**Sin Heartbeat** — tu asistente es como un empleado pasivo:
- Se sienta en su escritorio.
- Solo hace algo cuando TU le dices: "Oye, revisa mis emails".
- Si llega un email urgente a las 10am y tu no le preguntas hasta las 3pm, perdiste 5 horas.
- Es reactivo. Depende 100% de ti.

**Con Heartbeat** — tu asistente es proactivo:
- Cada 30 minutos, se levanta, va a tu bandeja de correo, la revisa.
- Si no hay nada importante, vuelve a sentarse en silencio. No te interrumpe.
- Si encuentra algo urgente, toca tu puerta: "Disculpa, llego esto de un cliente importante".
- Tu no tuviste que pedirle nada. El solito mantuvo el control.

**El Heartbeat es eso:** un latido periodico que mantiene vivo al agente. Cada "latido" es una revision autonoma del mundo. Igual que tu corazon late sin que le pidas, el agente revisa sin que le ordenes.

### La palabra clave: PROACTIVIDAD

| Sin Heartbeat | Con Heartbeat |
|---|---|
| El agente espera instrucciones | El agente busca trabajo |
| Tu eres el motor | El agente tiene su propio motor |
| Pierdes cosas por no preguntar | El agente encuentra cosas por ti |
| Solo trabaja cuando hablas con el | Trabaja incluso cuando duermes (dentro de tu horario) |

---

## Nivel 2: Los Tres Actos de Cada Latido

Cada vez que el "corazon" late, ocurren exactamente tres actos. Piensa en una obra de teatro muy corta que se repite cada 30 minutos:

### Acto 1: "¿Debo despertarme?" (Pre-flight)

Antes de hacer cualquier cosa, el agente se hace preguntas rapidas:

- ¿Estoy encendido? (quiza el humano me desactivo)
- ¿Es hora apropiada? (no voy a revisar cosas a las 3am)
- ¿Hay alguien mas usando el sistema? (no quiero chocar)
- ¿Tengo algo que revisar? (si mi checklist esta vacia, para que gastar energia)

**Metafora:** Es como cuando suena tu alarma en la manana. Antes de levantarte, haces un check rapido: ¿es dia laboral? ¿tengo cosas que hacer? Si es domingo y no tienes pendientes, le das snooze. El agente hace exactamente eso.

Si alguna respuesta es "no", el agente se vuelve a "dormir" y programa el siguiente latido. No gasta recursos.

### Acto 2: "Voy a revisar" (Ejecucion)

Si paso todas las verificaciones, el agente:

1. Lee su **checklist** (un archivo que le dice QUE revisar)
2. Usa sus herramientas (revisa Gmail, calendario, lo que sea)
3. Piensa: ¿algo de esto necesita atencion humana?

**Metafora:** Imagina un guardia de seguridad haciendo su ronda. Tiene una lista de puntos a revisar: puerta principal, ventanas, alarmas. Camina, revisa cada punto, y decide si hay algo fuera de lo normal.

### Acto 3: "¿Reporto o me callo?" (Respuesta)

Aqui viene la parte mas elegante. El agente tiene solo dos opciones:

- **"Todo bien"** → Dice la palabra magica `HEARTBEAT_OK` y se calla. No te interrumpe. No te manda email. Silencio absoluto.
- **"Hay algo"** → Redacta una alerta y te la envia (por Gmail, por ejemplo).

**Metafora:** El guardia de seguridad termina su ronda. Si todo esta bien, no te llama a las 2am para decirte "todo bien jefe". Simplemente sigue su ronda. Pero si encuentra una ventana rota, ahi si te llama. Eso es justo lo que hace HEARTBEAT_OK: es la senal de "no te molesto".

```
Latido #1: Reviso inbox → 3 emails, ninguno urgente → HEARTBEAT_OK (silencio)
Latido #2: Reviso inbox → Email del CEO → ALERTA: "El CEO te escribio hace 10 min"
Latido #3: Reviso inbox → Mismo email del CEO → Ya te avise, no repito (dedup)
Latido #4: Reviso inbox → Todo leido → HEARTBEAT_OK (silencio)
```

---

## Nivel 3: Los 6 Organos del Sistema

Si el Heartbeat fuera un cuerpo humano, tendria 6 organos. Cada uno con una funcion especifica. Vamos uno por uno:

### Organo 1: El Reloj (SCHEDULER)

**Que es:** El que decide CUANDO late el corazon.

**Metafora del despertador vs el cronometro:**

Hay dos formas de programar algo periodico:

- `setInterval` = Un despertador que suena cada 30 min sin importar nada. Si la primera alarma te tomo 45 minutos atender, la segunda ya sono y se acumulo. Caos.
- `setTimeout` = Un cronometro que se reinicia DESPUES de que terminas. Terminas a las 9:15 → se programa para las 9:45. Nunca se acumulan.

El Heartbeat usa `setTimeout`. Siempre. Es como decir: "Cuando termines de revisar, avisa, y ahi te programo la siguiente revision". Asi nunca hay dos revisiones al mismo tiempo.

**Active Hours** — El reloj tambien sabe cuando NO sonar:

```
Config: activeHours 08:00 - 22:00 (America/Mexico_City)

Situacion: Son las 21:45. El siguiente beat seria a las 22:15.
Pero 22:15 esta fuera de horario.
Entonces: Se programa para las 08:00 del dia siguiente.
```

Es como un asistente que sabe que despues de las 10pm no debe llamarte. Si tiene algo, espera a manana a las 8am.

### Organo 2: La Central de Llamadas (WAKE DISPATCHER)

**Que es:** El que recibe TODAS las razones por las que el corazon deberia latir, y decide cuando y como ejecutar el latido.

**Metafora del 911:**

Imagina una central telefonica del 911. Recibe llamadas de multiples fuentes:
- Una llamada del timer ("ya pasaron 30 minutos")
- Una llamada de un webhook ("llego un email nuevo ahora mismo")
- Una llamada del usuario ("revisalo ya, por favor")
- Una llamada de un cron job ("son las 9am, hora del reporte diario")

El dispatcher tiene tres superpoderes:

**Superpoder 1: Coalescencia (250ms)**

Si en un instante llegan 5 llamadas simultaneas (webhook de Gmail + timer + cron), no ejecuta 5 heartbeats. Espera 250 milisegundos, junta todas las llamadas, y ejecuta UN solo heartbeat que las atiende todas.

```
09:00:00.000  →  Llega trigger del timer
09:00:00.050  →  Llega trigger de webhook Gmail
09:00:00.100  →  Llega trigger de cron job
09:00:00.250  →  DISPATCH: Un solo heartbeat con los 3 triggers
```

**Metafora:** Es como cuando estas en una junta y alguien te toca la puerta tres veces en 10 segundos. No te levantas tres veces. Esperas un momento, abres una vez, y atiendes todo junto.

**Superpoder 2: Prioridades**

No todas las razones para latir son iguales:

| Prioridad | Quien llama | Ejemplo |
|---|---|---|
| Baja (0) | Reintento | "La vez pasada falle, dejame intentar de nuevo" |
| Normal (1) | Timer | "Ya pasaron 30 minutos, revision rutinaria" |
| Media (2) | Cron/Wake | "Es hora del reporte matutino" |
| Alta (3) | Webhook/Manual | "Acaba de llegar un email del CEO" o "El usuario pidio revision ahora" |

**Metafora:** En un hospital, no todos los pacientes se atienden igual. Un resfriado espera. Un infarto va primero. El dispatcher es el triaje.

**Superpoder 3: Anti-concurrencia**

Nunca hay dos heartbeats corriendo al mismo tiempo. Si llega un trigger mientras uno esta corriendo, se encola y espera su turno.

**Metafora:** Un bano de avion. Solo entra una persona a la vez. Si esta ocupado, esperas. No entran dos personas.

### Organo 3: El Corredor (HEARTBEAT RUNNER)

**Que es:** El que realmente EJECUTA la revision. Es el musculo del sistema.

Cuando el dispatcher dice "adelante", el runner hace esto:

```
1. PRE-FLIGHT   →  Las 4 preguntas de "¿debo despertarme?"
2. PROMPT       →  Construye la instruccion para el agente LLM
3. LLM TURN     →  El agente revisa todo (usa tools, lee emails, etc.)
4. PROCESAMIENTO →  ¿Es OK o es alerta? ¿Es duplicado?
5. POST          →  Entrega alerta o limpia el historial
6. RE-SCHEDULE   →  Programa el siguiente latido
```

**Metafora completa:** Piensa en un cartero que hace su ruta:
1. Sale de la oficina solo si la oficina esta abierta (pre-flight)
2. Recibe las cartas que debe entregar (prompt)
3. Hace su ruta, toca puertas, entrega paquetes (LLM turn)
4. Al volver, reporta: "Entregue 3, 2 no habia nadie" o "Sin novedades" (procesamiento)
5. La oficina archiva o descarta el reporte segun corresponda (post)
6. Se programa la siguiente ruta (re-schedule)

### Organo 4: La Checklist (HEARTBEAT.md)

**Que es:** Un archivo de texto simple que le dice al agente QUE revisar en cada latido.

**Por que es genial:**

Imagina que tu asistente tiene una libreta con una lista de cosas que debe vigilar:

```markdown
# Mi Checklist

## Emails
- Revisar inbox por emails no leidos de las ultimas 2 horas
- Priorizar: emails de clientes y proveedores
- Ignorar: newsletters, notificaciones de GitHub

## Seguimiento
- Si hay emails sin respuesta de mas de 24h de contactos importantes, avisarme

## Reglas
- Si todo esta bien, decir HEARTBEAT_OK
- No repetir alertas que ya mande hoy
```

Lo magico es que:
- **Tu puedes editar la libreta** (cambiar prioridades, agregar reglas)
- **El agente tambien puede editarla** (si nota que cierto tipo de email llega 3 veces por semana, puede agregarse una regla automatica)
- **Es solo un archivo de texto** — no necesitas ser programador para modificarlo

**Metafora:** Es el menu de un restaurante. El chef (agente) cocina lo que dice el menu. Pero tanto el dueno (tu) como el chef pueden actualizar el menu. Si un platillo no se vende, se quita. Si algo nuevo funciona, se agrega.

**Regla importante:** Si la checklist esta vacia (solo tiene titulos sin contenido), el agente ni se molesta en hacer la revision. ¿Para que gastar energia si no hay nada que revisar?

### Organo 5: El Contrato de Silencio (HEARTBEAT_OK)

**Que es:** El protocolo que permite al agente decir "todo bien" sin generar ruido.

Este es quiza el componente mas sutil pero mas importante. Sin el, cada latido generaria un mensaje/email/notificacion, y en un dia tendrias 48 interrupciones.

**Las reglas del contrato:**

1. Si no hay nada que reportar → responder exactamente `HEARTBEAT_OK`
2. Si `HEARTBEAT_OK` aparece al inicio o al final de la respuesta → se trata como "nada que reportar" (el agente puede agregar un comentario corto de <300 caracteres y aun asi cuenta como OK)
3. Si `HEARTBEAT_OK` aparece en medio del texto → no cuenta (es parte de una alerta real)
4. Si la respuesta NO tiene `HEARTBEAT_OK` → es una alerta real, hay que entregarla

**Metafora:** Piensa en un semaforo invertido:
- `HEARTBEAT_OK` = Luz verde para el silencio. No pasa nada, sigue dormido.
- Sin `HEARTBEAT_OK` = Luz roja. Algo paso. Hay que actuar.

**Proteccion anti-spam adicional — Deduplicacion:**

Incluso si el agente manda una alerta real, el sistema verifica: "¿Ya mande exactamente esta misma alerta en las ultimas 24 horas?" Si si, la suprime.

```
08:30  Alerta: "Email urgente de cliente@empresa.com"  → SE ENVIA
09:00  Alerta: "Email urgente de cliente@empresa.com"  → DUPLICADO, se suprime
09:30  Alerta: "Email urgente de cliente@empresa.com"  → DUPLICADO, se suprime
...
08:30 dia siguiente → Ya pasaron 24h → SE ENVIA de nuevo (recordatorio)
```

### Organo 6: El Mensajero (DELIVERY ENGINE)

**Que es:** El que lleva las alertas al humano. En este caso, via Gmail.

Cuando el sistema decide que hay una alerta real (paso el contrato, paso el dedup), el Delivery Engine la empaqueta y la envia.

**Comportamiento inteligente:**

- **Thread diario:** No te manda 10 emails separados en un dia. Agrupa todas las alertas del dia en un solo hilo de correo. Asi tu bandeja no explota.
- **Prefijo en subject:** `[PIPA Heartbeat]` para que puedas filtrar facilmente.
- **Formato configurable:** HTML para alertas bonitas o texto plano para simplicidad.

**Metafora:** Es como un servicio de paqueteria. No te toca el timbre 5 veces al dia. Junta todos los paquetes del dia y te hace una sola entrega. Ordenada, con etiqueta, y en horario razonable.

---

## Nivel 4: Los Trucos Avanzados (Patrones de Ingenieria)

Ahora que entiendes los 6 organos, vamos a los trucos de ingenieria que hacen que todo funcione sin problemas a largo plazo.

### Truco 1: Poda del Historial (Transcript Pruning)

**El problema:**

El agente vive en una "conversacion" continua. Cada latido agrega un intercambio:

```
[Prompt]: "Revisa tu checklist"
[Agente]: "HEARTBEAT_OK"
```

En un dia con latidos cada 30 minutos, eso son **48 intercambios vacios**. Si cada uno usa ~500 tokens, son 24,000 tokens de contexto desperdiciado. Es como si tu libreta de notas se llenara de paginas que solo dicen "nada que reportar, nada que reportar, nada que reportar..."

**La solucion:**

```
ANTES del latido:
    Anotar en que pagina va la libreta (posicion actual del historial)

DESPUES del latido, si fue HEARTBEAT_OK:
    Arrancar esas paginas de la libreta (volver a la posicion anterior)
    Como si el intercambio nunca hubiera existido
```

**Metafora:** Imagina que escribes en lapiz. Si el resultado fue "nada que reportar", borras lo que escribiste. La libreta queda como si nunca hubieras escrito. Pero si encontraste algo importante, lo dejas escrito con tinta.

**Resultado:** Solo los latidos que generaron alertas reales quedan en el historial. El contexto se mantiene limpio y relevante.

### Truco 2: Restauracion de Timestamp

**El problema:**

Las sesiones tienen un "timestamp de ultima actividad". Cada heartbeat actualiza ese timestamp, haciendo que la sesion parezca "activa" permanentemente. Esto impide que expire naturalmente cuando el usuario no esta.

**La solucion:**

```
ANTES del latido:
    Guardar el timestamp actual de la sesion

DESPUES del latido, si fue HEARTBEAT_OK:
    Restaurar el timestamp al valor guardado
    La sesion "no sabe" que hubo un heartbeat
```

**Metafora:** Es como entrar a una habitacion con sensor de movimiento. Si solo entras para verificar que todo esta bien y te vas, no quieres que el sistema registre "actividad detectada". Quieres que siga contando el tiempo desde la ultima vez que alguien estuvo ahi de verdad.

### Truco 3: Cola de Eventos del Sistema

**El problema:**

A veces pasan cosas ENTRE latidos que el agente necesita saber. Por ejemplo, un webhook de Gmail dice "llego un email nuevo" pero el siguiente latido es en 20 minutos.

**La solucion:**

Una cola en memoria que almacena eventos:

```
09:05  → Webhook: "Nuevo email de VP@empresa.com"
         Se guarda en la cola.
         Se dispara un latido inmediato (wake con prioridad alta).

El latido lee la cola:
  "Ah, llego un email nuevo del VP. Dejame revisarlo..."
  → Lee el email, decide si alertar o no.
  → Vacia la cola.
```

**Metafora:** Es como una bandeja de "mensajes mientras no estabas" que se pone en la puerta de tu oficina. Cuando vuelves (el proximo latido), revisas la bandeja, atiendes lo que sea necesario, y la vacias.

**Limites de seguridad:**
- Maximo 20 eventos en cola (no dejar que crezca infinitamente)
- No guardar duplicados consecutivos
- Se vacia despues de cada latido

### Truco 4: Backoff Exponencial

**El problema:**

Si la API de Gmail falla, no quieres que el sistema intente 48 veces en un dia con el mismo error.

**La solucion:**

Cada fallo consecutivo espera MAS tiempo antes de reintentar:

```
Fallo #1  →  Esperar 30 segundos
Fallo #2  →  Esperar 1 minuto
Fallo #3  →  Esperar 5 minutos
Fallo #4  →  Esperar 15 minutos
Fallo #5+ →  Esperar 1 hora (maximo)
```

**Metafora:** Imagina que tocas la puerta de una oficina y no abren. La primera vez esperas 30 segundos y vuelves a tocar. Si no abren, esperas un minuto. Luego 5 minutos. No te quedas golpeando la puerta como loco — das tiempo a que se resuelva el problema.

---

## Nivel 5: La Pelicula Completa (Un Dia en la Vida del Heartbeat)

Vamos a seguir al sistema durante una manana tipica, paso a paso. Esto integra TODO lo que aprendiste.

### 07:55 — El sistema esta dormido

El ultimo latido fue ayer a las 21:55. Active hours terminaron a las 22:00, asi que el siguiente latido se programo para las 08:00 de hoy.

### 08:00 — Primer latido del dia

```
SCHEDULER: Timer fire! Razon: "interval"

WAKE DISPATCHER:
  → Recibe trigger. Espera 250ms por si llega otro.
  → No llego nada mas. Despacha.

RUNNER PRE-FLIGHT:
  ✓ Sistema habilitado
  ✓ 08:00 esta dentro de 08:00-22:00
  ✓ Cola principal vacia
  ✓ HEARTBEAT.md tiene contenido

RUNNER LLM TURN:
  Agent lee HEARTBEAT.md
  Agent llama: gmail_check_inbox(query="is:unread newer_than:12h")
  → Resultado: 7 emails no leidos
  → 4 newsletters → Ignorar (segun checklist)
  → 2 notificaciones de GitHub → Ignorar (segun checklist)
  → 1 email de proveedor@logistica.com (hace 3 horas)
  Agent evalua: no es urgente, no es de contacto prioritario
  Agent responde: "HEARTBEAT_OK — 1 email de proveedor pendiente pero no urgente"

RESPONSE PROCESSING:
  → Contiene HEARTBEAT_OK al inicio
  → Texto restante: 52 caracteres (< 300 limite)
  → Clasificacion: OK

POST-PROCESSING:
  → No se envia nada
  → Transcript pruning: borrar este intercambio
  → Restaurar timestamp de sesion
  → Programar siguiente latido: 08:30
```

**Resultado:** Silencio total para el usuario. El agente hizo su trabajo y no molesto.

### 08:30 — Segundo latido

```
RUNNER LLM TURN:
  Agent revisa inbox
  → Mismo email de proveedor, nada nuevo
  Agent responde: "HEARTBEAT_OK"

POST: Prune, restore, schedule 09:00
```

### 09:07 — Evento entre latidos

```
WEBHOOK de Gmail PubSub:
  "Nuevo email de CEO@tuempresa.com"

SYSTEM EVENT QUEUE:
  → Encolar: { text: "Nuevo email de CEO@tuempresa.com", ts: 09:07 }

WAKE DISPATCHER:
  → requestHeartbeatNow(reason="hook:gmail:push")
  → Prioridad 3 (ALTA) — es un webhook
  → Espera coalescencia 250ms...
  → Despacha inmediatamente
```

### 09:07 — Latido reactivo (disparado por webhook)

```
RUNNER PRE-FLIGHT:
  ✓ Todo OK
  ✓ Hook bypass: no revisa si HEARTBEAT.md esta vacio

RUNNER PROMPT:
  "Se recibio un evento del sistema: Nuevo email de CEO@tuempresa.com.
   Revisa y decide si el humano necesita saberlo."

RUNNER LLM TURN:
  Agent llama: gmail_read(from="CEO@tuempresa.com", latest=true)
  → Subject: "Revision urgente: presupuesto Q2"
  → Body: "Necesito tu feedback antes de las 12pm de hoy"
  Agent decide: URGENTE. El CEO necesita respuesta antes de las 12.
  Agent responde:
    "Email urgente del CEO (CEO@tuempresa.com):
     Asunto: Revision urgente — presupuesto Q2
     Pide tu feedback antes de las 12pm de hoy.
     Recibido hace 2 minutos."

RESPONSE PROCESSING:
  → No contiene HEARTBEAT_OK → Es alerta real
  → Dedup check: primera vez que se envia → NUEVA
  → Clasificacion: ALERTA

DELIVERY ENGINE:
  → Canal: Gmail
  → To: tu-email@gmail.com
  → Subject: [PIPA Heartbeat] Alerta de Inbox
  → Body: (el texto de la alerta)
  → Thread: daily-2026-02-27 (se agrupa con otras alertas del dia)
  → ENVIADO

POST:
  → NO se hace pruning (la alerta queda en el historial)
  → NO se restaura timestamp (hubo actividad real)
  → Se re-calcula el proximo latido: 09:30 (sigue el intervalo normal)
```

**Resultado:** El usuario recibe un email a las 09:07 avisandole del email del CEO. Pasan solo segundos entre la llegada del email y la alerta.

### 09:30 — Latido normal

```
RUNNER LLM TURN:
  Agent revisa inbox
  → Email del CEO sigue ahi (sin leer por el usuario)
  Agent responde:
    "Email urgente del CEO (CEO@tuempresa.com):
     Asunto: Revision urgente — presupuesto Q2"

RESPONSE PROCESSING:
  → Es alerta, PERO...
  → Dedup check: mismo texto, enviado hace 23 minutos → DUPLICADO
  → Se suprime. No se envia.

POST: Prune transcript, schedule 10:00
```

**Resultado:** El sistema detecta que ya aviso de esto. No manda otro email.

### 11:45 — El usuario leyo y respondio el email del CEO

```
RUNNER LLM TURN:
  Agent revisa inbox
  → Email del CEO: LEIDO y RESPONDIDO
  → Email del proveedor: sigue sin leer (ya tiene 7 horas)
  → Segun checklist: proveedor no es contacto prioritario
  Agent responde: "HEARTBEAT_OK"

POST: Prune, restore, schedule 12:15
```

---

## Nivel 6: El Mapa Mental Completo

### Como se conecta todo

```
    TU (humano)
     │
     │ editas
     ▼
 ┌──────────────┐
 │ HEARTBEAT.md │ ← El agente tambien puede editarlo
 │ (la checklist)│
 └──────┬───────┘
        │ lee
        ▼
 ┌──────────────┐     ┌──────────────┐     ┌──────────────┐
 │  SCHEDULER   │────>│    WAKE      │────>│   RUNNER     │
 │  (el reloj)  │     │  DISPATCHER  │     │ (el ejecutor)│
 └──────────────┘     │ (la central) │     └──────┬───────┘
                      └──────┬───────┘            │
         Webhooks ──────────>│                    │ ejecuta LLM turn
         Cron jobs ─────────>│                    │
         Wake manual ───────>│                    ▼
                                          ┌──────────────┐
                                          │  ¿ALERTA o   │
                                          │ HEARTBEAT_OK?│
                                          └──────┬───────┘
                                                 │
                              ┌──────────────────┼──────────────────┐
                              │                                     │
                              ▼                                     ▼
                     ┌──────────────┐                      ┌──────────────┐
                     │  HEARTBEAT_OK │                      │   ALERTA     │
                     │  (silencio)   │                      │   (ruido)    │
                     └──────┬───────┘                      └──────┬───────┘
                            │                                     │
                            ▼                                     ▼
                     - Prune transcript                    - Dedup check
                     - Restore timestamp                   - Delivery (Gmail)
                     - Re-schedule                         - Thread diario
                                                           - Re-schedule
```

### Las 5 Capas de Proteccion Anti-Spam

El sistema tiene CINCO mecanismos para no molestarte innecesariamente:

```
Capa 1: ACTIVE HOURS      → No te busca fuera de tu horario
Capa 2: HEARTBEAT.md vacio → Si no hay nada que revisar, ni lo intenta
Capa 3: HEARTBEAT_OK      → Respuesta de "todo bien" = silencio
Capa 4: DEDUP 24h          → Misma alerta en <24h = se suprime
Capa 5: THREAD DIARIO      → Alertas agrupadas, no 48 emails separados
```

**Metafora final:** Es como un edificio con 5 puertas de seguridad. Cada alerta tiene que pasar las 5 puertas para llegar a tu bandeja. Si es ruido, alguna puerta la detiene. Solo lo realmente importante llega hasta ti.

### Las 3 Limpiezas Silenciosas

Despues de cada HEARTBEAT_OK, el sistema hace limpieza para mantenerse sano:

| Limpieza | Que hace | Por que |
|---|---|---|
| Transcript Pruning | Borra el intercambio del historial | Evita 24,000 tokens/dia de basura |
| Timestamp Restore | Restaura el reloj de la sesion | Evita que la sesion parezca eternamente activa |
| Re-schedule | Programa el siguiente latido | El ciclo continua |

---

## Nivel 7: Pensando como Arquitecto

### ¿Que necesitas para construir esto?

| Pieza | Para que | Ejemplo |
|---|---|---|
| Un timer | Disparar latidos periodicos | `setTimeout` en Node.js, `asyncio.sleep` en Python, cron en el OS |
| Una API de LLM | Que el agente "piense" | Claude API, GPT API |
| Gmail API | Leer inbox y enviar alertas | OAuth2 + Gmail API v1 |
| Un archivo de estado | Recordar dedup, timestamps, etc. | JSON file o SQLite |
| HEARTBEAT.md | La checklist editable | Archivo Markdown en tu proyecto |

### Dos caminos para monitorear Gmail

**Camino A: Polling (el simple)**
- Cada 30 minutos, el agente pregunta: "¿hay emails nuevos?"
- Facil de implementar. Sin setup extra.
- Desventaja: si llega un email urgente a las 09:01, no te enteras hasta las 09:30.

**Camino B: Push/Webhook (el reactivo)**
- Gmail te AVISA instantaneamente cuando llega un email.
- El webhook dispara un latido inmediato.
- Desventaja: necesitas configurar Google Cloud Pub/Sub.

**Consejo:** Empieza con A. Cuando necesites mas velocidad, migra a B. La arquitectura del sistema soporta ambos sin cambiar nada — solo agregas un nuevo trigger al Wake Dispatcher.

### Los 8 Errores que No Debes Cometer

| Error | Consecuencia | Solucion |
|---|---|---|
| No implementar HEARTBEAT_OK | 48 alertas vacias al dia | El contrato de silencio es obligatorio |
| No deduplicar | La misma alerta 48 veces | Ventana de 24 horas |
| No podar historial | Contexto lleno de basura | Transcript pruning |
| No respetar horarios | Alertas a las 3am | Active hours |
| Sesion aislada por latido | El agente pierde memoria | Sesion compartida |
| Checklist enorme | Tokens caros, respuestas lentas | Mantenerla concisa |
| No manejar errores | 48 errores iguales al dia | Backoff exponencial |
| Usar setInterval | Latidos se acumulan | Usar setTimeout |

---

## Resumen: De Principiante a Experto en una Pagina

| Nivel | Concepto Clave | En una frase |
|---|---|---|
| 1 | La Gran Idea | Un asistente que revisa cosas por ti cada 30 minutos sin que se lo pidas |
| 2 | Los Tres Actos | ¿Debo despertar? → Reviso → ¿Reporto o me callo? |
| 3 | Los 6 Organos | Reloj, Central, Corredor, Checklist, Contrato de Silencio, Mensajero |
| 4 | Trucos Avanzados | Poda de historial, restauracion de timestamp, cola de eventos, backoff |
| 5 | La Pelicula | Un dia completo mostrando como todo trabaja junto |
| 6 | Mapa Mental | Como se conectan los componentes, las 5 capas anti-spam |
| 7 | Pensando como Arquitecto | Que necesitas para construirlo y que errores evitar |

---

> **Nota:** Este documento es un companion de aprendizaje para `heartbeat-arquitectura.md`. Aquel es la referencia tecnica. Este es la guia para entenderla.

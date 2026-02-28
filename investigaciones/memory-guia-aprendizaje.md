# Guia de Aprendizaje: El Sistema de Memory

> De cero a arquitecto. Este documento te lleva paso a paso, desde la intuicion hasta el detalle tecnico, para que entiendas completamente como funciona la memoria persistente de un agente de IA.

---

## Nivel 1: La Gran Idea (Sin codigo, solo intuicion)

### El agente sin memoria

Imagina que contratas a un asistente brillante, pero que tiene amnesia total cada vez que se va a dormir.

Lunes le dices: "Me gusta que los reportes sean en bullet points, no en parrafos". Lo hace perfecto.
Martes vuelve y te entrega un reporte en parrafos. No recuerda nada. Le explicas de nuevo.
Miercoles, lo mismo. Jueves, lo mismo. Cada dia empiezas de cero.

**Eso es un agente sin memoria.** Cada conversacion nueva es borrón y cuenta nueva. No importa cuantas veces le expliques algo — al iniciar sesion nueva, lo olvida todo.

### El agente con memoria

Ahora imagina que ese asistente tiene una **libreta personal** que lleva a todos lados. Cada vez que aprende algo importante, lo anota:

```
Pagina 1: "Al jefe le gustan los reportes en bullet points"
Pagina 2: "El proyecto PIPA usa Python, no JavaScript"
Pagina 3: "El cliente principal es Acme Corp, contacto: María García"
```

Al dia siguiente, antes de empezar a trabajar, hojea su libreta. "Ah, bullet points. Python. Acme Corp." Y arranca con todo el contexto que necesita.

**El sistema de Memory es esa libreta.** Pero con superpoderes.

### ¿Que tiene de especial esta libreta?

| Libreta normal | Sistema de Memory |
|---|---|
| Hojas sueltas que se pierden | Archivos Markdown que viven en tu disco |
| Solo la lee el asistente | La puedes leer TU tambien (es texto plano) |
| Si se pierde, adios | Versionable con git (historial completo) |
| Buscar algo = hojear todo | Busqueda inteligente (sabe QUE buscas, no solo las palabras) |
| Crece sin control | Se auto-organiza por tipo y relevancia |

---

## Nivel 2: Los Tres Cajones de la Memoria

La memoria del agente no es un revoltijo. Esta organizada en **tres cajones**, cada uno con un proposito distinto.

### Cajon 1: La Pizarra Permanente (MEMORY.md)

**Metafora:** Piensa en la pizarra blanca que esta en la pared de tu oficina. Ahi anotas las cosas que SIEMPRE quieres tener a la vista:

- "Regla: nunca deployar los viernes"
- "Stack del proyecto: Python + FastAPI + PostgreSQL"
- "Preferencia: commits en ingles, comentarios en espanol"

Estas cosas no cambian con el tiempo. Son **hechos duraderos**. No importa si los escribiste hace 6 meses — siguen siendo verdad.

En el sistema, este cajon es un archivo llamado `MEMORY.md`. Lo pueden editar tanto el agente como tu. Es lo primero que el agente "ve" cuando se despierta.

### Cajon 2: El Diario (memory/YYYY-MM-DD.md)

**Metafora:** Piensa en un diario personal. Cada dia tiene su pagina:

```
2026-02-27.md
  - Hoy se resolvio el bug de autenticacion
  - Se decidio usar JWT en vez de sesiones
  - El cliente pidio cambios en el dashboard

2026-02-26.md
  - Se hizo deploy a staging
  - Fallo el test de integracion con Stripe
```

Lo que paso el martes es muy relevante el miercoles. Pero tres meses despues, probablemente ya no importa tanto. Este cajon tiene **fecha de caducidad natural** — las notas viejas van perdiendo importancia automaticamente.

**Metafora de la leche:** Las notas diarias son como la leche en el refrigerador. Hoy esta perfecta. En una semana, todavia sirve. En un mes, mejor tirarla. El sistema sabe esto y le baja el "puntaje de frescura" conforme pasan los dias.

### Cajon 3: La Enciclopedia Tematica (memory/nombre.md)

**Metafora:** Piensa en carpetas tematicas en un archivero:

```
memory/projects.md       → Todo sobre los proyectos activos
memory/api-design.md     → Decisiones de diseño de la API
memory/team-contacts.md  → Contactos del equipo
```

Estos archivos no tienen fecha. Son **tematicos**. Agrupan conocimiento por tema, no por cuando se aprendio. Como una enciclopedia: el articulo sobre "Fotosintesis" no pierde valor con el tiempo.

### La regla de oro

```
¿Tiene fecha en el nombre? (YYYY-MM-DD)
    │
    ├── SI  → Es temporal. Pierde relevancia con el tiempo.
    │        Ejemplo: memory/2026-02-27.md
    │
    └── NO  → Es evergreen. Mantiene su valor para siempre.
             Ejemplo: MEMORY.md, memory/projects.md
```

**Metafora del periodico vs el libro:**
- Los archivos con fecha son como el **periodico** — la noticia de hoy es importante hoy. La del mes pasado es historia.
- Los archivos sin fecha son como un **libro de referencia** — lo consultas cuando lo necesitas, sin importar cuando se escribio.

---

## Nivel 3: El Principio Sagrado — Markdown es la Verdad

Antes de entrar en detalles tecnicos, hay un principio que gobierna todo el sistema. Entenderlo es entender el alma de la arquitectura:

> **Los archivos Markdown son la fuente de verdad. Todo lo demas es un indice que se puede reconstruir.**

### ¿Que significa esto?

Imagina una biblioteca. Los libros son la fuente de verdad. El catalogo digital (esa computadora donde buscas por autor o titulo) es solo un **indice** — una herramienta para encontrar libros mas rapido.

Si la computadora del catalogo se quema, ¿perdiste los libros? No. Los libros siguen en los estantes. Puedes reconstruir el catalogo leyendo los libros de nuevo.

En este sistema:
- Los archivos `.md` = los libros (fuente de verdad)
- SQLite, vectores, FTS, cache = el catalogo (indices reconstruibles)

```
¿Se corrompio la base de datos SQLite?
    → Borrala. Re-indexa los archivos .md. Todo vuelve a funcionar.

¿Quieres migrar a otra maquina?
    → Copia la carpeta de archivos .md. El sistema re-indexa solo.

¿El agente recuerda algo mal?
    → Abre el .md con tu editor de texto. Corrige la linea. Listo.
```

### Por que esto es brillante

| Propiedad | Consecuencia |
|---|---|
| **Legible por humanos** | Abres el archivo y lo lees. No necesitas herramientas especiales |
| **Versionable con git** | Puedes ver que se agrego, cuando, y revertir si algo salio mal |
| **Portable** | Copiar la carpeta = migrar la memoria completa |
| **Debuggeable** | Si el agente dice algo raro, abres el archivo y ves de donde saco esa informacion |
| **Resiliente** | Si los indices se corrompen, se reconstruyen. La fuente de verdad nunca se pierde |

**Metafora del cuaderno vs la app de notas:**

Tus notas en un cuaderno de papel nunca van a dejar de funcionar. No necesitan actualizacion, no dependen de un servidor, no se vuelven incompatibles. Markdown es el equivalente digital del cuaderno: simple, duradero, universal.

---

## Nivel 4: Como el Agente Busca en su Memoria

Ahora viene la parte interesante. El agente tiene cientos (o miles) de notas. ¿Como encuentra lo que necesita?

### El problema de buscar

Imagina que tienes 500 notas en tu libreta y necesitas encontrar "aquella vez que decidimos usar JWT para la autenticacion". Tienes dos opciones:

**Opcion A: Buscar por palabras exactas (keyword search)**

Buscas la palabra "JWT" en todas las paginas. Simple. Rapido. Pero tiene un problema:

- Si escribiste "JSON Web Tokens" en vez de "JWT", no lo encuentra
- Si escribiste "decidimos usar tokens firmados para auth", tampoco — no tiene la palabra "JWT"
- Busca EXACTAMENTE lo que escribes, nada mas

**Opcion B: Buscar por significado (semantic/vector search)**

Le dices al sistema "busca cosas sobre autenticacion con tokens" y el entiende el SIGNIFICADO, no las palabras exactas. Puede encontrar:

- "Implementamos JWT para el login"
- "La autenticacion usa tokens firmados"
- "Auth: bearer tokens en header"

Aunque ninguna tenga exactamente tus palabras, todas hablan de lo mismo.

Pero tiene su propio problema:
- Si buscas "API key de produccion: sk-abc123", la busqueda semantica no entiende que "sk-abc123" es importante — para ella es ruido
- Los terminos tecnicos muy especificos se le escapan

### La solucion: Busqueda Hibrida

**Metafora del detective con dos cerebros:**

Imagina un detective que investiga un caso. Tiene dos metodos:

- **Cerebro izquierdo (keywords):** Busca coincidencias textuales exactas. "¿Donde aparece la palabra JWT?" Es preciso pero literal.
- **Cerebro derecho (semantica):** Entiende conceptos. "¿Donde se habla de autenticacion?" Es inteligente pero a veces vago.

El detective usa **ambos** y combina los resultados:

```
Score final = 70% cerebro derecho (semantica) + 30% cerebro izquierdo (keywords)
```

¿Por que 70/30? Porque la busqueda semantica es generalmente mas util (entiende lo que QUIERES decir), pero los keywords son cruciales para terminos especificos (nombres, codigos, IDs).

**Ejemplo concreto:**

Buscas: "configuracion de la API de Stripe"

| Resultado | Score Semantico | Score Keywords | Score Final |
|---|---|---|---|
| "Stripe API config: usar sk_live_xxx" | 0.85 | 0.90 | 0.87 |
| "La integracion de pagos usa Stripe" | 0.80 | 0.60 | 0.74 |
| "Configuramos la pasarela de cobros" | 0.75 | 0.10 | 0.56 |

El primer resultado gana porque tiene TANTO el significado correcto COMO las palabras clave exactas.

### La red de seguridad: Degradacion elegante

¿Que pasa si no tienes un servicio de embeddings (la parte semantica)? ¿Se rompe todo?

No. El sistema tiene tres niveles de busqueda, como un edificio con generador de respaldo:

```
Nivel 1: HIBRIDO (semantica + keywords)
    → Mejor calidad. Necesita embedding provider.
    → "Tengo luz principal y generador"

Nivel 2: SOLO VECTOR (semantica sin keywords)
    → Buena calidad. Provider disponible pero sin FTS5.
    → "Tengo generador pero no luz principal"

Nivel 3: SOLO KEYWORDS (BM25 puro)
    → Calidad basica. Sin provider de embeddings.
    → "No hay electricidad pero tengo velas"
```

**El sistema NUNCA se rompe completamente.** Siempre puede buscar, aunque sea de manera basica. Es como un auto que si se le acaba la gasolina puede funcionar con electricidad, y si se le acaba la electricidad puede funcionar a pedales. Lento, pero funciona.

---

## Nivel 5: Como se Indexa la Memoria (De Archivo a Buscable)

Tener archivos Markdown esta bien, pero para que la busqueda sea rapida, el sistema necesita **indexarlos**. Esto es como construir el catalogo de la biblioteca.

### El proceso completo, paso a paso

**Metafora de la fabrica de chocolate:**

Imagina una fabrica que recibe granos de cacao (archivos .md) y los transforma en bombones (chunks indexados) listos para vender (buscar).

```
PASO 1: DETECCION — El vigilante
    Un "vigilante" (file watcher) esta sentado mirando la carpeta memory/.
    Cuando alguien crea o modifica un archivo, el vigilante grita:
    "¡Ey, hay un archivo nuevo!"

PASO 2: VERIFICACION — El inspector de calidad
    Antes de procesar, se calcula una "huella digital" del archivo (hash SHA-256).
    Si la huella es identica a la ultima vez que se proceso → skip.
    "Ya procesamos estos granos, son los mismos de ayer. Siguiente."

PASO 3: CHUNKING — La maquina cortadora
    El archivo se corta en trozos pequeños de ~400 tokens cada uno.
    ¿Por que? Porque buscar en un documento de 5,000 palabras es lento
    e impreciso. Es mejor buscar en trozos del tamaño de un parrafo.

PASO 4: CACHE CHECK — El almacen de reciclaje
    Para cada trozo, se revisa: "¿Ya tengo el embedding de este trozo?"
    Si el texto no cambio, el embedding tampoco cambia.
    "Ya tengo el molde de este bombon, no necesito hacerlo de nuevo."

PASO 5: EMBEDDING — La transformacion magica
    Los trozos NUEVOS se envian a un servicio de IA que los convierte
    en vectores numericos (listas de numeros que representan el significado).
    "De grano de cacao a chocolate liquido."

PASO 6: NORMALIZACION — Control de calidad
    Los vectores se normalizan (L2-normalize) para que todos
    tengan la misma escala. Como poner todos los bombones en cajas
    del mismo tamaño.

PASO 7: ALMACENAMIENTO — La vitrina
    Todo se guarda en SQLite:
    - El texto del trozo (para busqueda por keywords)
    - El vector del trozo (para busqueda semantica)
    - Metadatos (archivo, linea, hash)

PASO 8: LIMPIEZA — El barrendero
    Si un archivo se borro, sus trozos tambien se eliminan.
    "Ese bombon ya no esta en el menu. Fuera de la vitrina."
```

### Chunking en detalle: Por que y como se corta

**Metafora del rompecabezas:**

Imagina que tienes un mural enorme (un archivo largo) y necesitas fotografiarlo para subirlo a internet. Si tomas UNA sola foto del mural completo, pierdes detalle. Si tomas 100 fotos de cada centimetro, pierdes contexto.

La solucion: tomar fotos de **secciones** del mural, con un poco de **traslape** entre cada foto para que las ideas no se corten a la mitad.

```
Archivo original:
┌─────────────────────────────────────────────────────────┐
│ Parrafo 1: Decidimos usar JWT para la autenticacion     │
│ porque es stateless y escala bien horizontalmente.      │
│ Parrafo 2: La implementacion usa la libreria jsonwebtoken│
│ con RS256. Las keys se rotan cada 90 dias...            │
│ Parrafo 3: Para refresh tokens, usamos una tabla en     │
│ PostgreSQL con TTL de 7 dias...                         │
└─────────────────────────────────────────────────────────┘

Despues del chunking (~400 tokens por chunk, 80 de overlap):

Chunk 1:                                    Chunk 2:
┌────────────────────────────┐    ┌────────────────────────────┐
│ Decidimos usar JWT para la │    │ jsonwebtoken con RS256.    │
│ autenticacion porque es    │    │ Las keys se rotan cada     │
│ stateless y escala bien    │    │ 90 dias...                 │
│ horizontalmente. La        │    │ Para refresh tokens,       │
│ implementacion usa la      │    │ usamos una tabla en        │
│ libreria jsonwebtoken      │    │ PostgreSQL con TTL de      │
│ con RS256. Las keys se     │◄──►│ 7 dias...                  │
│ rotan cada 90 dias...      │    │                            │
└────────────────────────────┘    └────────────────────────────┘
         ▲                  ▲
         │    OVERLAP       │
         │  (80 tokens)     │
         └──────────────────┘

El final del Chunk 1 y el inicio del Chunk 2 se SOLAPAN.
Asi, la idea de "RS256 con rotacion de keys" no se pierde
en la frontera entre chunks.
```

**¿Por que 400 tokens?** Es un balance:
- Muy chico (50 tokens) → Pierdes contexto. Un trozo de 50 tokens no dice mucho solo.
- Muy grande (2,000 tokens) → La busqueda se vuelve imprecisa. Devuelve demasiado texto irrelevante.
- 400 tokens ≈ un parrafo sustancioso. Suficiente contexto, suficiente precision.

**¿Por que 80 tokens de overlap?** Es el "seguro" contra la mala suerte de que una idea caiga justo en el borde entre dos chunks. Con overlap, la idea aparece completa en al menos uno de los dos.

---

## Nivel 6: Las Formulas que Gobiernan la Busqueda

Ahora que entiendes la intuicion, vamos a las formulas. No te asustes — cada una tiene una metafora para que la entiendas sin necesidad de ser matematico.

### Formula 1: BM25 → Score normalizado

```
score = 1 / (1 + max(0, bm25_rank))
```

**¿Que es BM25?** Es el algoritmo clasico de busqueda por keywords. Funciona como Google en los 90: cuenta cuantas veces aparece la palabra, penaliza documentos muy largos, y da un "ranking" donde **menor numero = mejor resultado**.

El problema: el ranking dice "el resultado #1 es el mejor, el #5 es el quinto". Pero no dice CUANTO mejor es el #1 que el #5. Y ademas, el sistema necesita un numero entre 0 y 1 para combinarlo con la busqueda semantica.

**La formula invierte y normaliza:**

```
Rank BM25 = 0 (el mejor)  → Score = 1/(1+0) = 1.00  ← Maximo
Rank BM25 = 1              → Score = 1/(1+1) = 0.50
Rank BM25 = 4              → Score = 1/(1+4) = 0.20
Rank BM25 = 99             → Score = 1/(1+99) = 0.01 ← Casi nada
```

**Metafora del podio:** Si BM25 dice que eres el campeon (rank 0), tu score es 1.0. Si eres el subcampeon (rank 1), tu score baja a 0.5. Cuanto mas lejos del podio, menor tu score.

### Formula 2: Fusion hibrida

```
score_final = 0.7 × score_semantico + 0.3 × score_keywords
```

**Metafora del jurado:** Imagina un concurso de cocina con dos jueces:
- **Juez Semantico** (70% del voto): Evalua sabor, creatividad, presentacion. Entiende el CONCEPTO del plato.
- **Juez Keywords** (30% del voto): Evalua si usaste los ingredientes especificos que pedian. Busca coincidencia EXACTA.

Un plato que tiene buen sabor Y usa los ingredientes correctos gana. Un plato con solo buen sabor pero ingredientes equivocados pierde puntos. Un plato con ingredientes correctos pero mal sabor tambien pierde.

### Formula 3: Temporal Decay (decaimiento exponencial)

```
multiplicador = e^(-lambda × edad_en_dias)

donde lambda = ln(2) / 30
```

Esta es la formula que hace que las notas con fecha pierdan relevancia con el tiempo.

**Metafora del helado derritiendose:**

Imagina que cada nota con fecha es un helado. El dia que se escribe esta perfecta (multiplicador = 1.0). Pero con cada dia que pasa, se va derritiendo:

```
Dia 0:   ████████████████████  1.00  (helado perfecto)
Dia 15:  ██████████████        0.71  (un poco derretido)
Dia 30:  ██████████            0.50  (a la mitad)
Dia 60:  █████                 0.25  (casi liquido)
Dia 90:  ██                    0.13  (un charco)
```

La **vida media** es de 30 dias: despues de un mes, la nota vale la mitad. Despues de dos meses, un cuarto. Y asi sucesivamente.

**Pero las notas evergreen (sin fecha) no se derriten.** Es como si estuvieran en un congelador permanente. `MEMORY.md` siempre vale 1.0, sin importar cuando se escribio.

**¿Por que esta apagado por default?** Porque no siempre quieres que las cosas pierdan valor. Si usas la memoria como una base de conocimiento (documentacion tecnica, guias de estilo), el decay perjudicaria. Solo lo activas cuando la frescura importa: emails, daily notes, logs.

### Formula 4: MMR Re-ranking (diversidad)

```
MMR(d) = 0.7 × relevancia(d) - 0.3 × max_similitud_con_ya_seleccionados(d)
```

**Metafora del buffet:**

Imagina que estas armando un plato en un buffet. Tienes 6 espacios. Los primeros 3 son obvios: la pasta, la ensalada, el pollo. Pero los siguientes 3... ¿pones MAS pasta? No. Buscas algo DIFERENTE: un postre, una sopa, pan.

MMR hace exactamente eso con los resultados de busqueda. Si ya selecciono un resultado sobre "JWT authentication", penaliza al siguiente resultado que tambien habla de JWT. Prefiere uno que hable de algo relacionado pero diferente, como "OAuth2 flow" o "session management".

```
Sin MMR:
  1. "JWT para autenticacion"
  2. "Implementacion de JWT"        ← Muy similar al #1
  3. "Configuracion de JWT tokens"  ← Muy similar al #1 y #2

Con MMR:
  1. "JWT para autenticacion"
  2. "OAuth2 como alternativa"      ← Diferente, aporta perspectiva
  3. "Configuracion del middleware" ← Diferente, aporta contexto
```

**¿Por que esta apagado por default?** Agrega latencia (tiempo de calculo) y solo es util cuando tus notas son muy redundantes. Si tus notas son diversas por naturaleza, el ranking normal ya funciona bien.

---

## Nivel 7: Mecanismos de Supervivencia

El sistema tiene dos mecanismos brillantes para no perder informacion importante. Son como reflejos de supervivencia.

### Reflejo 1: Memory Flush (Salvavidas pre-compactacion)

**El problema:**

El agente tiene un limite de "memoria de trabajo" (context window). Despues de una conversacion larga, se acerca al limite. Cuando eso pasa, el sistema "compacta" — resume los mensajes antiguos para hacer espacio. Pero al compactar, se pierden detalles.

**Metafora del examen:**

Imagina que estas en un examen de 3 horas. Llevas 2 horas y 50 minutos. El profesor dice: "En 10 minutos recojo los examenes y los destruyo. Lo que no hayan anotado en su HOJA DE RESPUESTAS, se pierde."

¿Que haces? En esos 10 minutos, anotas rapidamente todo lo importante en tu hoja de respuestas.

El Memory Flush es exactamente eso:

```
El contexto se acerca al limite
    │
    ▼
¿Debo hacer flush?
    ├── ¿Esta habilitado?       → Si
    ├── ¿No es un heartbeat?    → Si (heartbeats no lo disparan)
    ├── ¿Supere el umbral?      → Si
    └── ¿No lo hice ya?         → Si
    │
    ▼
Turno SILENCIOSO al agente:
    "Estas a punto de perder contexto. Escribe lo importante
     a memory/2026-02-27.md. Si no hay nada, di NO_REPLY."
    │
    ▼
El agente escribe a disco lo que considere valioso
(decisiones, hechos, preferencias descubiertas)
    │
    ▼
El usuario NO ve nada de esto (es silencioso)
    │
    ▼
La compactacion procede normalmente
(pero lo importante ya esta a salvo en disco)
```

**Resultado:** El agente nunca pierde informacion valiosa por compactacion. Antes de que se borre, la salva a disco. Es como el piloto que activa el boton de eyeccion antes del impacto — la informacion sobrevive aunque la conversacion se comprima.

### Reflejo 2: Session Memory (Archivo automatico al cerrar sesion)

**El problema:**

Cuando el usuario cierra la sesion (hace `/new` o `/reset`), todo el contexto de la conversacion desaparece. Si hubo decisiones importantes, se pierden.

**Metafora del acta de reunion:**

Al final de cada reunion, alguien toma nota de los acuerdos y las envia por email. Asi, aunque la reunion termino, los acuerdos quedan registrados.

```
Usuario hace /new (cierra la sesion)
    │
    ▼
El sistema lee los ultimos 15 mensajes de la sesion
    │
    ▼
Genera un nombre descriptivo para el archivo:
    "2026-02-27-api-design-decisions.md"
    │
    ▼
Escribe el archivo en memory/ con:
    - Metadatos (cuando, donde, quien)
    - Resumen de la conversacion
    │
    ▼
El file watcher detecta el archivo nuevo → lo indexa
    │
    ▼
En la proxima sesion, si el agente busca "API design",
encuentra este resumen automaticamente
```

**Resultado:** Cada sesion deja un rastro en la memoria. No se necesita que el usuario diga "guarda esto". El sistema lo hace automaticamente, como una grabadora que se enciende sola en cada reunion.

---

## Nivel 8: El Cache de Embeddings (Ahorro Inteligente)

Generar embeddings (convertir texto en vectores) cuesta dinero — cada llamada a OpenAI o similar tiene un precio. El sistema tiene un cache inteligente para no pagar dos veces por lo mismo.

**Metafora del traductor:**

Imagina que tienes un traductor profesional que cobra por palabra. Le mandas un parrafo a traducir. Dias despues, le mandas EL MISMO parrafo. ¿Deberia cobrarte de nuevo? No. Ya tiene la traduccion guardada.

```
Primer indexado de "memory/projects.md":
    Chunk 1: "El proyecto usa Python..."
        → Hash del texto: abc123
        → ¿Cache tiene abc123? NO → Llamar a OpenAI → Guardar resultado
        → Costo: $0.0001

    Chunk 2: "La base de datos es PostgreSQL..."
        → Hash: def456
        → ¿Cache tiene def456? NO → Llamar a OpenAI → Guardar resultado
        → Costo: $0.0001

Segundo indexado (archivo no cambio):
    → Hash del ARCHIVO completo no cambio → SKIP TOTAL
    → Costo: $0.0000

Tercer indexado (se edito solo el chunk 2):
    Chunk 1: "El proyecto usa Python..."
        → Hash: abc123
        → ¿Cache tiene abc123? SI → Usar cache
        → Costo: $0.0000

    Chunk 2: "La base de datos es MySQL..." (CAMBIO)
        → Hash: ghi789 (diferente)
        → ¿Cache tiene ghi789? NO → Llamar a OpenAI
        → Costo: $0.0001
```

**Invalidacion inteligente:**

El cache se invalida solo cuando es necesario:
- Texto cambia → hash cambia → cache miss (correcto: el significado puede ser diferente)
- Provider cambia (de OpenAI a local) → config hash cambia → cache miss (correcto: vectores incompatibles)
- Cache muy grande → se borran los mas viejos (espacio finito)

**Resultado:** Si tienes 100 notas y editas 3, solo pagas por re-embeddear esas 3. Las otras 97 usan cache. En la practica, despues del primer indexado, el costo diario es minimo.

---

## Nivel 9: Los Embedding Providers (La Maquinaria de Significado)

Los embeddings son el corazon de la busqueda semantica. Pero ¿de donde vienen?

### ¿Que es un embedding?

**Metafora de las coordenadas GPS:**

Imagina que cada concepto en el mundo tiene una "ubicacion" en un mapa multidimensional. Cosas similares estan cerca en el mapa:

```
Mapa conceptual (simplificado a 2D):

    "gato" ●               ● "perro"
                    ● "mascota"

                                        ● "auto"
    "felino" ●                    ● "vehiculo"
                                ● "camioneta"
```

"Gato" y "felino" estan cerca (son conceptos similares). "Gato" y "auto" estan lejos (no tienen relacion). Un embedding es la "coordenada GPS" de un trozo de texto en este mapa conceptual.

Cuando buscas "animales domesticos", el sistema calcula la coordenada de tu busqueda y encuentra los puntos mas cercanos: "gato", "perro", "mascota".

### Los 5 proveedores disponibles

El sistema tiene una cadena de proveedores, como una lista de numeros de emergencia:

```
Intento 1: LOCAL (node-llama-cpp con embeddinggemma-300m)
    → Gratis, rapido, sin internet
    → ¿Funciono? Si → Usar este. No → Siguiente.

Intento 2: OPENAI (text-embedding-3-small)
    → Excelente calidad, requiere API key
    → ¿Hay API key? Si → Usar este. No → Siguiente.

Intento 3: GEMINI (gemini-embedding-001)
    → Buena calidad, requiere API key de Google
    → ¿Hay API key? Si → Usar este. No → Siguiente.

Intento 4: VOYAGE (voyage-4-large)
    → Especializado en codigo, requiere API key
    → ¿Hay API key? Si → Usar este. No → Siguiente.

Intento 5: MISTRAL (mistral-embed)
    → Alternativa europea, requiere API key
    → ¿Hay API key? Si → Usar este. No → Siguiente.

Ningun provider disponible:
    → DEGRADAR a busqueda solo por keywords (FTS5)
    → Funciona, pero sin busqueda semantica
```

**Metafora del restaurante:** Es como pedir comida: "¿Tienen sushi? No. ¿Pasta? No. ¿Pizza? No. ¿Sandwich? Si." Siempre comes algo, aunque no sea lo ideal.

---

## Nivel 10: La Pelicula Completa — Un Dia en la Vida de la Memoria

Vamos a seguir al sistema durante un dia tipico, integrando TODO lo que aprendiste.

### 08:00 — El agente despierta

```
INICIO DE SESION
    │
    ▼
El agente lee MEMORY.md automaticamente:
    "Stack: Python + FastAPI + PostgreSQL"
    "Preferencia: commits en ingles"
    "Proyecto actual: PIPA"
    │
    ▼
El agente ya tiene contexto base. Sabe quien eres y que haces.
```

### 09:15 — Primera busqueda del dia

```
Usuario: "¿Que decidimos sobre la autenticacion?"

AGENT TOOL: memory_search(query="decisiones autenticacion")
    │
    ├── SYNC CHECK: ¿Hay archivos modificados desde el ultimo indexado?
    │   → memory/2026-02-26.md fue editado ayer → Re-indexar
    │   → Hash check: el hash cambio → Procesar
    │   → Chunking → Embedding (solo chunks nuevos) → Store
    │
    ├── BUSQUEDA HIBRIDA:
    │   │
    │   ├── Vector search: "decisiones autenticacion" → embed → cosine
    │   │   → Hit: memory/2026-02-20-auth-meeting.md (score: 0.82)
    │   │   → Hit: memory/api-design.md (score: 0.75)
    │   │
    │   └── FTS5 search: "decisiones autenticacion"
    │       → Hit: memory/2026-02-20-auth-meeting.md (score: 0.60)
    │       → Hit: memory/2026-02-10.md (score: 0.40)
    │
    ├── FUSION: 0.7 * vector + 0.3 * keywords
    │   → auth-meeting.md: 0.7*0.82 + 0.3*0.60 = 0.754
    │   → api-design.md:   0.7*0.75 + 0.3*0.15 = 0.570
    │   → 2026-02-10.md:   0.7*0.50 + 0.3*0.40 = 0.470
    │
    ├── TEMPORAL DECAY (si activado):
    │   → auth-meeting.md (7 dias): 0.754 * 0.85 = 0.641
    │   → api-design.md (evergreen): 0.570 * 1.00 = 0.570
    │   → 2026-02-10.md (17 dias): 0.470 * 0.67 = 0.315 (< 0.35 → FILTRADO)
    │
    ├── FILTER: score >= 0.35, max 6 resultados
    │   → 2 resultados pasan el filtro
    │
    └── RESPUESTA AL AGENTE:
        [
          { path: "memory/2026-02-20-auth-meeting.md",
            startLine: 5, endLine: 18, score: 0.641,
            snippet: "Decidimos usar JWT con RS256 porque..." },
          { path: "memory/api-design.md",
            startLine: 22, endLine: 35, score: 0.570,
            snippet: "La autenticacion del API usa bearer tokens..." }
        ]
```

### 11:30 — Conversacion larga, se acerca al limite

```
El agente lleva 2 horas de conversacion. El contexto tiene 180,000 tokens.
Limite: 200,000 tokens. Reserva: 15,000 tokens.
Umbral de flush: 200,000 - 15,000 - 4,000 = 181,000 tokens.

180,000 < 181,000 → Aun no.

... 10 minutos despues: 182,000 tokens.

182,000 > 181,000 → MEMORY FLUSH!

TURNO SILENCIOSO:
    Agente recibe: "Estas a punto de perder contexto.
                    Escribe lo importante a memory/2026-02-27.md"

    Agente escribe:
        ## Decisiones de hoy
        - Se aprobo migrar de REST a GraphQL para el endpoint de reportes
        - El deadline del MVP se movio al 15 de marzo
        - Se decidio NO usar Redis para cache (PostgreSQL con UNLOGGED tables)

    Agente responde: NO_REPLY (el usuario no ve nada)

COMPACTACION procede:
    Los mensajes antiguos se resumen. Se pierden detalles.
    Pero las decisiones YA estan a salvo en disco.
```

### 14:00 — El agente necesita las decisiones de la manana

```
Agente: memory_search("decision GraphQL reportes")
    │
    └── Encuentra: memory/2026-02-27.md, linea 3:
        "Se aprobo migrar de REST a GraphQL para el endpoint de reportes"

¡Funciono! Aunque la compactacion borro los detalles de la conversacion,
la decision sobrevivio gracias al Memory Flush.
```

### 17:30 — El usuario cierra la sesion

```
Usuario: /new

SESSION MEMORY:
    1. Lee los ultimos 15 mensajes
    2. Genera slug: "graphql-migration-planning"
    3. Escribe: memory/2026-02-27-graphql-migration-planning.md
        ## Sesion: Planificacion de migracion a GraphQL
        - Se discutio la migracion del endpoint de reportes
        - Se comparo REST vs GraphQL para este caso de uso
        - Decision: migrar a GraphQL
        - Proximo paso: crear esquema GraphQL del endpoint de reportes

    4. File watcher detecta el archivo → Indexa automaticamente

Manana, cuando el agente busque "GraphQL" o "migracion de reportes",
encontrara este resumen sin que nadie haya tenido que guardarlo manualmente.
```

---

## Nivel 11: El Mapa Mental Completo

### Como se conectan todos los componentes

```
    TU (humano)
     │
     │ escribes/editas                    AGENTE
     ▼                                      │
 ┌──────────────┐                           │ escribe
 │  Archivos    │◄──────────────────────────┘
 │  Markdown    │
 │              │
 │ MEMORY.md    │ ← Permanente. Hechos duraderos.
 │ memory/      │
 │  YYYY-MM-DD  │ ← Temporal. Se "derrite" con el tiempo.
 │  tematico.md │ ← Permanente. Conocimiento por tema.
 └──────┬───────┘
        │
        │ vigila cambios (file watcher)
        ▼
 ┌──────────────────────────────────────────┐
 │         PIPELINE DE INDEXADO              │
 │                                           │
 │  Detectar → Verificar hash → Cortar en   │
 │  chunks → Buscar en cache → Generar      │
 │  embeddings → Normalizar → Guardar       │
 └──────────────────┬───────────────────────┘
                    │
     ┌──────────────┼──────────────┐
     ▼              ▼              ▼
 ┌────────┐  ┌───────────┐  ┌──────────┐
 │  FTS5  │  │sqlite-vec │  │  Cache   │
 │Keywords│  │ Vectores  │  │Embeddings│
 └───┬────┘  └─────┬─────┘  └──────────┘
     │              │
     ▼              ▼
 ┌──────────────────────────────────────────┐
 │         BUSQUEDA HIBRIDA                  │
 │                                           │
 │  0.7 × semantica + 0.3 × keywords       │
 │  × decay temporal (si activado)          │
 │  + MMR diversidad (si activado)          │
 │  → filtrar score >= 0.35                 │
 │  → max 6 resultados                      │
 └──────────────────┬───────────────────────┘
                    │
                    ▼
 ┌──────────────────────────────────────────┐
 │         HERRAMIENTAS DEL AGENTE           │
 │                                           │
 │  memory_search(query) → snippets         │
 │  memory_get(path) → archivo completo     │
 └──────────────────────────────────────────┘
```

### Las 4 Capas de Proteccion de la Memoria

```
Capa 1: ARCHIVOS MARKDOWN
    → Fuente de verdad. Indestructible (salvo que borres los archivos).
    → Si todo lo demas falla, la informacion sigue ahi.

Capa 2: MEMORY FLUSH
    → Antes de compactar, guarda lo importante a disco.
    → Reflejo de supervivencia contra la perdida de contexto.

Capa 3: SESSION MEMORY
    → Al cerrar sesion, archiva un resumen automatico.
    → Ninguna conversacion se pierde completamente.

Capa 4: CACHE DE EMBEDDINGS
    → No re-calcula lo que ya calculo.
    → Protege tu bolsillo y acelera el indexado.
```

### Los 3 Modos de Busqueda (Degradacion Elegante)

```
         ¿Tienes embedding provider?
                │
         ┌──────┴──────┐
         SI            NO
         │              │
    ¿Tienes FTS5?      └──→ MODO 3: Solo keywords
         │                   (basico pero funciona)
    ┌────┴────┐
    SI        NO
    │          │
 MODO 1    MODO 2
 Hibrido   Solo vector
 (mejor)   (bueno)
```

---

## Nivel 12: Pensando como Arquitecto

### Las 5 Decisiones de Diseno y sus Razones

| Decision | ¿Por que? | Alternativa descartada |
|---|---|---|
| **Markdown como fuente de verdad** | Legible, portable, versionable, debuggeable | Base de datos como fuente principal — opaca, fragil |
| **Busqueda hibrida (70/30)** | Keywords exactos + comprension semantica | Solo vector — pierde terminos tecnicos especificos |
| **Overlap en chunking** | Ideas en fronteras no se pierden | Sin overlap — ideas cortadas a la mitad |
| **Temporal decay OFF por default** | No todo necesita recencia | ON por default — perjudica knowledge bases |
| **MMR OFF por default** | Agrega latencia sin beneficio para memorias diversas | ON por default — lento innecesariamente |

### Si tuvieras que construirlo desde cero

| Componente | Complejidad | Prioridad |
|---|---|---|
| Carpeta `memory/` con archivos .md | Minima | Fundamental |
| `MEMORY.md` como pizarra permanente | Minima | Fundamental |
| File watcher para detectar cambios | Baja | Necesario |
| Chunking con overlap | Media | Necesario |
| Embedding con provider (OpenAI o local) | Media | Para busqueda semantica |
| FTS5 para keywords | Baja | Fallback y complemento |
| Fusion hibrida 70/30 | Baja | Calidad de busqueda |
| Cache de embeddings | Media | Ahorro de costos |
| Memory Flush pre-compactacion | Media | Proteccion de informacion |
| Session Memory automatico | Media | Continuidad entre sesiones |
| Temporal Decay | Baja | Opcional, para notas temporales |
| MMR | Baja | Opcional, para redundancia |

### Errores que No Debes Cometer

| Error | Consecuencia | Solucion |
|---|---|---|
| Usar solo busqueda por keywords | "API key sk-abc" lo encuentra, "configuracion de autenticacion" no | Busqueda hibrida |
| Usar solo busqueda semantica | "autenticacion" lo encuentra, "sk-abc123" no | Busqueda hibrida |
| Chunks muy pequenos | Pierdes contexto. Un snippet de 50 tokens no dice nada solo | ~400 tokens |
| Chunks muy grandes | Busqueda imprecisa. Devuelves parrafos irrelevantes | ~400 tokens |
| Sin overlap | Ideas cortadas en la frontera entre chunks | 80 tokens de overlap |
| Sin cache de embeddings | Pagas el doble por el mismo texto | Cache por hash |
| Sin memory flush | Pierdes info al compactar | Flush pre-compactacion |
| La DB como fuente de verdad | Si se corrompe, pierdes todo | Markdown = verdad, DB = indice |

---

## Resumen: De Principiante a Experto en una Pagina

| Nivel | Concepto Clave | En una frase |
|---|---|---|
| 1 | La Gran Idea | Una libreta personal que el agente lleva a todos lados |
| 2 | Los 3 Cajones | Pizarra permanente, diario con fecha, enciclopedia tematica |
| 3 | Markdown es Verdad | Los archivos .md son la fuente real; todo lo demas es un indice reconstruible |
| 4 | Busqueda Hibrida | Dos cerebros: keywords exactos (30%) + significado (70%) |
| 5 | Indexado | De archivo a buscable: vigilar → verificar → cortar → embeddear → guardar |
| 6 | Las Formulas | BM25, fusion 70/30, decay temporal, MMR para diversidad |
| 7 | Supervivencia | Memory flush y session memory: nunca perder informacion |
| 8 | Cache | No pagar dos veces por el mismo embedding |
| 9 | Providers | Cadena de proveedores con degradacion elegante |
| 10 | La Pelicula | Un dia completo mostrando como todo trabaja junto |
| 11 | Mapa Mental | Como se conectan los componentes y las capas de proteccion |
| 12 | Arquitecto | Decisiones de diseno, prioridades de construccion, errores a evitar |

---

> **Nota:** Este documento es un companion de aprendizaje para `memory-arquitectura.md`. Aquel es la referencia tecnica. Este es la guia para entenderla.

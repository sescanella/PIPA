# Arquitectura del Sistema de MEMORY (basado en OpenClaw)

> Documento de referencia para entender como OpenClaw implementa memoria persistente para agentes de IA. Agnostico de stack. Enfocado en conceptos clave y decisiones de diseno.

## 1. Principio Fundamental

**Markdown es la fuente de verdad.** Todo lo demas (SQLite, vectores, FTS, cache) es un indice derivado que se puede reconstruir en cualquier momento.

Esto significa:
- La memoria es **legible por humanos** (puedes abrir el archivo y leerlo)
- Es **versionable** con git
- Es **portable** (copiar archivos = migrar memoria)
- Es **debuggeable** (si el agente recuerda algo mal, puedes ver y editar el archivo)

---

## 2. Los 3 Tipos de Memoria

```
workspace/
  MEMORY.md                    ← Memoria curada (evergreen)
  memory/
    2026-01-15.md              ← Log diario (temporal)
    2026-01-15-api-design.md   ← Sesion archivada (temporal)
    projects.md                ← Conocimiento tematico (evergreen)
```

| Tipo | Archivo | Decaimiento Temporal | Quien Escribe | Proposito |
|------|---------|---------------------|---------------|-----------|
| **Curada** | `MEMORY.md` | No (evergreen) | Agente + humano | Preferencias, decisiones, hechos duraderos |
| **Log diario** | `memory/YYYY-MM-DD.md` | Si (por fecha del nombre) | Agente | Lo que paso hoy, notas efimeras |
| **Tematica** | `memory/nombre.md` | No (evergreen) | Agente + humano | Conocimiento por tema sin fecha |

**Regla clave:** Los archivos con fecha en el nombre (`YYYY-MM-DD`) pierden relevancia con el tiempo. Los que no tienen fecha son "evergreen" y mantienen su score intacto.

---

## 3. Arquitectura del Sistema

```
┌─────────────────────────────────────────────────────────┐
│                   AGENT TOOLS                            │
│  memory_search(query) → snippets con scores             │
│  memory_get(path, from, lines) → contenido de archivo   │
└─────────────┬───────────────────────┬───────────────────┘
              │                       │
              v                       v
┌─────────────────────┐    ┌─────────────────────┐
│  SEARCH PIPELINE    │    │  FILE READER        │
│  Hybrid BM25+Vector │    │  Path validation    │
│  Temporal Decay     │    │  Traversal protection│
│  MMR Re-ranking     │    │  Line range slicing │
└─────────┬───────────┘    └─────────────────────┘
          │
          v
┌─────────────────────────────────────────────────────────┐
│                    STORAGE LAYER                         │
│                                                         │
│  ┌──────────┐  ┌───────────┐  ┌──────────────────┐    │
│  │  SQLite   │  │  FTS5     │  │  sqlite-vec      │    │
│  │  (chunks, │  │  (keyword │  │  (vector search) │    │
│  │   files,  │  │   search) │  │                  │    │
│  │   cache)  │  │           │  │                  │    │
│  └──────────┘  └───────────┘  └──────────────────┘    │
└─────────────────────────────────────────────────────────┘
          ^
          │
┌─────────┴───────────────────────────────────────────────┐
│                  INDEXING PIPELINE                        │
│                                                         │
│  Archivos MD → Chunking → Embeddings → SQLite           │
│                                                         │
│  ┌──────────┐  ┌──────────┐  ┌──────────────────┐     │
│  │File Watch │  │ Chunker  │  │ Embedding        │     │
│  │(chokidar)│→ │400 tokens│→ │Provider          │     │
│  │          │  │80 overlap│  │(OpenAI/local/etc)│     │
│  └──────────┘  └──────────┘  └──────────────────┘     │
└─────────────────────────────────────────────────────────┘
```

---

## 4. Pipeline de Indexado (Archivo → Buscable)

```
1. DETECCION      File watcher detecta cambio en memory/
2. HASH CHECK     SHA-256 del contenido vs lo guardado → si es igual, skip
3. CHUNKING       Partir en trozos de ~400 tokens con 80 tokens de overlap
4. CACHE LOOKUP   Buscar embeddings ya calculados por hash del chunk
5. EMBEDDING      Solo los chunks nuevos van al provider (OpenAI, etc.)
6. NORMALIZE      L2-normalize los vectores
7. STORAGE        Guardar en chunks, chunks_vec (vectores), chunks_fts (FTS5)
8. CLEANUP        Borrar chunks de archivos que ya no existen
```

### Chunking: Como se parten los documentos

- **Budget por chunk:** `tokens * 4` caracteres (heuristica de 4 chars/token)
- **Overlap:** Los ultimos N caracteres del chunk anterior se copian al inicio del siguiente
- **Lineas largas:** Se parten en segmentos del tamano maximo
- **Cada chunk registra:** `startLine`, `endLine`, `text`, `hash`

### Embedding Providers (en orden de auto-seleccion)

| Provider | Modelo Default | Requiere API Key |
|----------|---------------|-----------------|
| Local (node-llama-cpp) | embeddinggemma-300m | No |
| OpenAI | text-embedding-3-small | Si |
| Gemini | gemini-embedding-001 | Si |
| Voyage | voyage-4-large | Si |
| Mistral | mistral-embed | Si |

**Auto-seleccion:** Intenta local primero (si hay modelo en disco). Si no, prueba providers remotos en orden. Si ninguno tiene API key, degrada a busqueda solo por keywords (FTS).

---

## 5. Pipeline de Busqueda (Query → Resultados)

### Modo Hibrido (default)

```
Query del usuario
    │
    ├──→ Embed query → Vector search (cosine similarity)
    │                    score = 1 - cosine_distance
    │
    └──→ Tokenize → FTS5 keyword search (BM25)
                      score = 1 / (1 + bm25_rank)
    │
    v
MERGE: final_score = 0.7 * vector_score + 0.3 * text_score
    │
    v
TEMPORAL DECAY (opcional): score *= e^(-lambda * dias_de_edad)
    │                       lambda = ln(2) / 30 dias
    │
    v
MMR RE-RANKING (opcional): diversidad via Jaccard similarity
    │
    v
FILTER: score >= 0.35, max 6 resultados
```

### Tres niveles de busqueda (degradacion elegante)

| Nivel | Cuando aplica | Calidad |
|-------|--------------|---------|
| **Hibrido** | Embedding provider disponible + FTS5 | Mejor |
| **Solo vector** | Provider disponible, FTS5 no | Buena |
| **Solo keywords** | Sin provider de embeddings | Basica |

El sistema **nunca se rompe completamente**. Si no hay API key, degrada a keywords.

---

## 6. Las 4 Formulas Matematicas

### 6.1 BM25 → Score normalizado

```
score = 1 / (1 + max(0, bm25_rank))
```

Convierte el ranking de BM25 (donde menor = mejor) a un score [0, 1] donde mayor = mejor.

### 6.2 Fusion hibrida

```
final_score = W_v * vector_score + W_t * text_score

Defaults: W_v = 0.7, W_t = 0.3
```

Los pesos se normalizan para sumar 1.0.

### 6.3 Temporal Decay (decaimiento exponencial)

```
multiplier = e^(-lambda * age_days)
lambda = ln(2) / halfLifeDays

Default halfLifeDays = 30
```

| Edad del archivo | Multiplicador |
|-----------------|---------------|
| 0 dias | 1.00 |
| 15 dias | 0.71 |
| 30 dias | 0.50 |
| 60 dias | 0.25 |
| 90 dias | 0.13 |

**Archivos evergreen** (MEMORY.md, archivos sin fecha) reciben multiplicador = 1.0 siempre.

### 6.4 MMR Re-ranking

```
MMR(d) = lambda * relevance(d) - (1-lambda) * max_jaccard_similarity(d, selected)

Default lambda = 0.7
```

Seleccion greedy: elige el documento con mayor MMR, lo agrega al set seleccionado, repite.

Jaccard similarity = `|intersection(tokens_a, tokens_b)| / |union(tokens_a, tokens_b)|`

---

## 7. Memory Tools (lo que ve el agente)

### memory_search

```
Input:  query (string), maxResults? (6), minScore? (0.35)
Output: [{ path, startLine, endLine, score, snippet, citation? }]
```

- Los snippets tienen max ~700 caracteres
- Las citations se muestran en DMs y se ocultan en chats grupales
- Formato citation: `MEMORY.md#L5-L7`

### memory_get

```
Input:  path (string), from? (linea inicio), lines? (cuantas)
Output: { text, path }
```

- Proteccion contra path traversal (no permite `../`)
- Solo lee archivos `.md` dentro del workspace de memoria
- Si el archivo no existe, retorna texto vacio (no error)

---

## 8. Memory Flush (Pre-Compaction)

**Problema:** Cuando el contexto del agente se acerca al limite de tokens, el sistema compacta. Pero al compactar, se pierde informacion.

**Solucion:** Antes de compactar, inyectar un turno silencioso donde el agente escribe lo importante a disco.

```
Token usage se acerca al limite
    │
    v
shouldRunMemoryFlush() == true?
    │  - Habilitado? Si
    │  - No es heartbeat? Si
    │  - Threshold excedido? Si (contextWindow - reserve - 4000 tokens)
    │  - No se hizo ya en este ciclo? Si
    │
    v
Inyectar turno silencioso al agente:
    Prompt: "Estas a punto de perder contexto. Escribe lo importante
             a memory/YYYY-MM-DD.md. Si no hay nada, responde NO_REPLY."
    │
    v
Agente escribe a disco usando herramientas de archivo
    │
    v
Respuesta marcada como NO_REPLY (usuario no ve nada)
    │
    v
Compaction procede normalmente
```

**Punto clave:** El heartbeat NO dispara memory flush. Solo las sesiones de usuario lo hacen.

---

## 9. Session Memory (Archivo Automatico de Sesiones)

Cuando el usuario hace `/new` o `/reset`:

```
1. Leer ultimos 15 mensajes de la sesion anterior
2. Generar slug descriptivo via LLM (fallback: timestamp HHMM)
3. Escribir memory/YYYY-MM-DD-slug.md con:
   - Metadata (session key, ID, canal)
   - Resumen de la conversacion (user/assistant alternados)
4. El file watcher detecta el archivo nuevo → indexa automaticamente
```

---

## 10. Embedding Cache (Ahorro de API calls)

```
Cada embedding se cachea en SQLite:
    Key:   (provider, model, provider_config_hash, content_hash)
    Value: vector JSON + dimensiones + timestamp

Antes de llamar al provider:
    1. Calcular hash del texto del chunk
    2. Buscar en cache por hash
    3. Solo enviar al provider los cache misses

Invalidacion: implicita
    - Si el texto cambia → hash cambia → cache miss
    - Si el provider cambia → provider_config_hash cambia → cache miss
    - Poda por cantidad: si > maxEntries, borrar los mas viejos
```

---

## 11. Decisiones de Diseno Clave

### Por que Markdown y no una DB

| Markdown | Base de datos |
|----------|--------------|
| Legible por humanos | Requiere tooling |
| Versionable con git | Complejo de versionar |
| El agente ya sabe escribir MD | Necesita API especial |
| Portable (copiar archivos) | Requiere export/import |
| Debuggeable | Opaco |

### Por que busqueda hibrida y no solo vector

| Solo vector | Hibrido |
|-------------|---------|
| Pierde keywords exactos | Captura keywords + semantica |
| "API key de produccion" no matchea | Match exacto via BM25 |
| Depende 100% del embedding | Funciona sin embeddings (FTS fallback) |

### Por que el overlap en chunking

Sin overlap, una idea que cruza el limite de dos chunks se pierde en ambos. Con 80 tokens de overlap, el contexto se preserva en las fronteras.

### Por que temporal decay esta OFF por default

No todos los casos de uso necesitan recencia. Para knowledge bases estaticas, el decay perjudicaria. Se activa solo cuando la frescura temporal es relevante (daily notes, emails, logs).

### Por que MMR esta OFF por default

Agrega latencia y complejidad. Solo es util cuando los resultados son muy redundantes (muchos chunks diciendo lo mismo). Para memorias diversas, el ranking por score es suficiente.

---

## 12. Aplicacion a tus Fuentes (Obsidian + Gmail)

### Obsidian Notes

Los archivos `.md` de Obsidian **son identicos** al formato que usa OpenClaw. Puedes:
- Usar `MEMORY.md` como tu archivo de hechos duraderos
- Usar `memory/` para daily notes (Obsidian ya genera `YYYY-MM-DD.md`)
- Los links internos de Obsidian (`[[nota]]`) se indexan como texto

### Gmail

Los emails necesitan un paso de **normalizacion a Markdown** antes de indexarse:
```
Email (JSON/API) → Convertir a Markdown → Guardar en memory/emails/YYYY-MM-DD-subject.md → Indexar
```

El campo `From`, `Subject`, `Date` se ponen como frontmatter o headers. El body se convierte a MD. El file watcher los detecta automaticamente.

---

## 13. Parametros de Configuracion Clave

| Parametro | Default | Que controla |
|-----------|---------|-------------|
| `chunking.tokens` | 400 | Tamano de cada chunk |
| `chunking.overlap` | 80 | Overlap entre chunks |
| `query.maxResults` | 6 | Resultados maximos |
| `query.minScore` | 0.35 | Umbral minimo de relevancia |
| `hybrid.vectorWeight` | 0.7 | Peso de busqueda semantica |
| `hybrid.textWeight` | 0.3 | Peso de busqueda por keywords |
| `temporalDecay.halfLifeDays` | 30 | Vida media del decay |
| `mmr.lambda` | 0.7 | Balance relevancia/diversidad |
| `cache.enabled` | true | Cache de embeddings |
| `sync.onSearch` | true | Re-indexar antes de buscar si hay cambios |

---

## 14. Resumen Visual

```
                    ┌──────────────────────┐
                    │   ARCHIVOS MARKDOWN  │
                    │  MEMORY.md           │
                    │  memory/*.md         │
                    │  (emails convertidos)│
                    └──────────┬───────────┘
                               │
                    ┌──────────v───────────┐
                    │   INDEXING PIPELINE   │
                    │  Watch → Hash →      │
                    │  Chunk → Embed →     │
                    │  Store              │
                    └──────────┬───────────┘
                               │
              ┌────────────────┼────────────────┐
              v                v                v
     ┌──────────────┐ ┌──────────────┐ ┌──────────────┐
     │   FTS5       │ │  sqlite-vec  │ │  Cache       │
     │  (keywords)  │ │  (vectors)   │ │  (embeddings)│
     └──────┬───────┘ └──────┬───────┘ └──────────────┘
            │                │
            v                v
     ┌────────────────────────────────┐
     │      HYBRID SEARCH             │
     │  0.7 * vector + 0.3 * text    │
     │  + temporal decay (opcional)   │
     │  + MMR diversity (opcional)    │
     └──────────────┬─────────────────┘
                    │
                    v
     ┌────────────────────────────────┐
     │     AGENT TOOLS                │
     │  memory_search → snippets     │
     │  memory_get → archivo          │
     └────────────────────────────────┘
```

---

## 15. Referencias

- **Repositorio OpenClaw:** https://github.com/openclaw/openclaw
- **Memory docs:** `docs/concepts/memory.md`
- **Memory index manager:** `src/memory/manager.ts`
- **Hybrid search:** `src/memory/hybrid.ts`
- **Temporal decay:** `src/memory/temporal-decay.ts`
- **MMR:** `src/memory/mmr.ts`
- **Memory tools:** `src/agents/tools/memory-tool.ts`
- **Embedding providers:** `src/memory/embeddings.ts`
- **SQLite schema:** `src/memory/memory-schema.ts`

---

## Relacionado

- [[heartbeat-arquitectura]] - Sistema de Heartbeat (loop autonomo)
- [[links-de-interes]] - Links del proyecto

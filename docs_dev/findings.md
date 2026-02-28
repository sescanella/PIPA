# Findings — PIPA v1 Implementation

## Codigo Existente Reutilizable

### PDF-Listado-Materiales/ (prototipo funcional)
- **crop.py**: Motor de cropping completo con PyMuPDF. Usa `fitz.Matrix` para zoom y `page.get_pixmap` para renderizar. Salida a `output/crops/{stem}/`.
- **regions.py**: 4 regiones definidas como porcentajes de pagina. Dataclass `Region` con metodo `to_rect()`. Zoom 2.5x para tablas, 3.0x para cajetin.
- **schemas.py**: Modelos Pydantic completos: `MaterialRow`, `SoldaduraRow`, `CorteRow`, `CajetinData`, `SpoolRecord`. Ya usa `model_config = {"populate_by_name": True}` y alias para campo `of`.
- **assemble.py**: Lee 4 JSONs parciales, parsea con Pydantic, genera `SpoolRecord` validado. Maneja JSONs corruptos gracefully.
- **Skills Claude Code**: `extract-plano` y `read-region` ya existen como skills en `.claude/skills/`. Habria que migrarlos.

### Adaptaciones necesarias
1. **Paths**: Actualmente hardcoded a `output/crops/` y `output/json/`. Necesitan aceptar `tmp/` como directorio de trabajo.
2. **CLI args**: `crop.py` y `assemble.py` tienen `main()` con `sys.argv`. Funcional, no necesita cambio.
3. **Imports**: Usan `from src.X import Y`. Funcionaran si se ejecutan desde `skills/extract-plano/`.

## Configuracion Actual

### .env
- Tiene estructura base pero faltan valores reales:
  - `ANTHROPIC_API_KEY` no esta listado (necesario)
  - `GMAIL_CREDENTIALS_PATH` y `GMAIL_TOKEN_PATH` ya definidos
  - Tiene campos innecesarios (DB, Figma, OpenClaw) — limpiar

### .gitignore
- Actual: `.env`, `credentials.json`, `token.json`, `tmp/`, `*.lock`, `.DS_Store`
- Falta: `mcp.json`, `**/.venv/`, `__pycache__/`, `*.pyc` (segun §18.1)

## Decisiones Arquitectonicas Clave de la Spec

### Separacion de responsabilidades (§4.2)
- **Claude es stateless** — no escribe archivos de estado
- **Wrapper Python** — polling Gmail + invoca Claude + persiste estado
- **MCP Server** — solo para operaciones que Claude necesita durante procesamiento

### Seguridad (§18)
- Heartbeat principal: `--disallowedTools "Bash,Write,Edit,WebFetch,WebSearch"`
- Skills: `--disallowedTools "WebFetch,WebSearch"` (Bash y Write permitidos)
- Defensa en profundidad: usar AMBOS `--allowedTools` y `--disallowedTools`

### Deduplicacion ADR-006
- Orden: (1) estado local → (2) label Gmail → (3) reply
- Prefiere fallos de entrega sobre duplicados

## Desviaciones de la Spec

| Seccion | Spec dice | Decision real | Razon |
|---------|-----------|---------------|-------|
| §10.2 | `ANTHROPIC_API_KEY=sk-ant-...` en .env | Eliminado del .env | Claude Code CLI maneja su propia autenticacion. No necesita API key en .env |

## Dependencias Python por Componente

| Componente | Paquetes | Virtualenv |
|---|---|---|
| agent/ | google-api-python-client, google-auth-oauthlib, pydantic | agent/.venv/ |
| mcp_servers/gmail/ | mcp[cli], google-api-python-client, google-auth-oauthlib, google-auth | mcp_servers/gmail/.venv/ |
| skills/extract-plano/ | PyMuPDF, Pillow, pydantic | skills/extract-plano/.venv/ |

## Notas de Entorno de Desarrollo (macOS)

- macOS viene con Python 3.9.6 (system). El paquete `mcp` requiere Python 3.10+.
- Se instalo Python 3.12.12 via Homebrew (`brew install python@3.12`) para crear venvs en macOS.
- En Windows (produccion), se usara Python 3.11+ instalado normalmente.
- Path de Python 3.12 en macOS: `/opt/homebrew/opt/python@3.12/bin/python3.12`

# Automatización Gmail + Claude Code CLI: Guía Técnica Completa

**Fecha:** 2026-02-27
**Scope:** Integración Gmail API, Claude Code CLI headless, envío de emails con adjuntos, Task Scheduler Windows, manejo de PDFs, patrones de resiliencia.

---

## Executive Summary

Este documento cubre los seis pilares técnicos necesarios para construir un pipeline automatizado que monitorea una bandeja de Gmail, descarga PDFs adjuntos, los procesa con Claude Code CLI en modo no-interactivo, y responde al hilo original con un JSON resultante. Cada sección incluye código aplicable directamente.

Los puntos críticos son: (1) la autenticación OAuth2 requiere un paso manual inicial para generar el `token.json`, que luego se renueva automáticamente con el refresh token; (2) Claude Code CLI expone el flag `-p` / `--print` para uso headless, con `--output-format json` para parseo programático; (3) Windows Task Scheduler con PowerShell es la solución más robusta para intervalos de 30 minutos; (4) la librería `tenacity` es el estándar de facto para retry con exponential backoff.

---

## 1. Integración Gmail API con Python en Windows

### 1.1 Setup inicial: Google Cloud Console

1. Ir a [Google Cloud Console](https://console.cloud.google.com/) → crear proyecto
2. Habilitar **Gmail API** en "APIs & Services > Library"
3. Crear credenciales: "OAuth 2.0 Client ID" de tipo **Desktop application**
4. Descargar el JSON y guardarlo como `credentials.json`

**Instalación de dependencias:**

```bash
pip install google-auth google-auth-oauthlib google-auth-httplib2 google-api-python-client
```

### 1.2 Autenticación OAuth2 y generación de token.json

El flujo es: primera ejecución abre el browser para autorizar → genera `token.json` con access token + refresh token → las ejecuciones posteriores usan el refresh token automáticamente.

```python
# auth.py
import os
import json
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request

SCOPES = [
    'https://www.googleapis.com/auth/gmail.readonly',
    'https://www.googleapis.com/auth/gmail.send',
    'https://www.googleapis.com/auth/gmail.modify'
]

TOKEN_PATH = 'token.json'
CREDENTIALS_PATH = 'credentials.json'


def get_credentials() -> Credentials:
    """Obtiene credenciales válidas, renovando si es necesario."""
    creds = None

    if os.path.exists(TOKEN_PATH):
        creds = Credentials.from_authorized_user_file(TOKEN_PATH, SCOPES)

    # Si no hay creds válidas, renovar o hacer el flujo completo
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            # Primera vez: abre browser (solo necesario una vez)
            flow = InstalledAppFlow.from_client_secrets_file(
                CREDENTIALS_PATH, SCOPES
            )
            creds = flow.run_local_server(port=0)

        # Guardar para próximas ejecuciones
        with open(TOKEN_PATH, 'w') as token:
            token.write(creds.to_json())

    return creds
```

**Nota sobre servidores headless (sin browser):** para el primer token en Windows Server sin interfaz, usar `flow.run_console()` en lugar de `run_local_server()`. Esto imprime una URL que se visita en otro equipo y se pega el código de autorización.

### 1.3 Monitorear la bandeja: buscar emails no leídos con PDF

```python
# gmail_monitor.py
import base64
import os
from googleapiclient.discovery import build
from auth import get_credentials


def get_gmail_service():
    creds = get_credentials()
    return build('gmail', 'v1', credentials=creds)


def buscar_emails_con_pdf(service, query: str = 'is:unread has:attachment') -> list:
    """Busca emails no leídos que tengan adjuntos."""
    result = service.users().messages().list(
        userId='me',
        q=query
    ).execute()

    messages = result.get('messages', [])
    return messages


def obtener_mensaje_completo(service, msg_id: str) -> dict:
    """Obtiene los detalles completos de un mensaje."""
    return service.users().messages().get(
        userId='me',
        id=msg_id,
        format='full'
    ).execute()


def extraer_adjuntos_pdf(service, mensaje: dict, directorio_destino: str) -> list:
    """
    Descarga todos los PDFs adjuntos de un mensaje.
    Retorna lista de rutas de archivos descargados.
    """
    archivos_descargados = []
    msg_id = mensaje['id']

    partes = mensaje.get('payload', {}).get('parts', [])

    for parte in partes:
        nombre = parte.get('filename', '')
        mime_type = parte.get('mimeType', '')

        # Filtrar solo PDFs
        if not nombre.lower().endswith('.pdf') and 'pdf' not in mime_type:
            continue

        attachment_id = parte.get('body', {}).get('attachmentId')
        data = parte.get('body', {}).get('data')

        if attachment_id:
            # PDF grande: obtener por separado
            attachment = service.users().messages().attachments().get(
                userId='me',
                messageId=msg_id,
                id=attachment_id
            ).execute()
            data = attachment['data']

        if data:
            # Decodificar base64 URL-safe
            contenido = base64.urlsafe_b64decode(data + '==')

            ruta = os.path.join(directorio_destino, nombre)
            with open(ruta, 'wb') as f:
                f.write(contenido)

            archivos_descargados.append(ruta)

    return archivos_descargados


def marcar_como_leido(service, msg_id: str):
    """Marca el mensaje como leído para no reprocesarlo."""
    service.users().messages().modify(
        userId='me',
        id=msg_id,
        body={'removeLabelIds': ['UNREAD']}
    ).execute()
```

### 1.4 Polling vs Push Notifications

Para un pipeline que corre cada 30 minutos, el **polling simple** (buscar `is:unread has:attachment`) es la opción correcta. La alternativa de push notifications via Cloud Pub/Sub requiere un endpoint HTTPS público y tiene bugs documentados de sincronización.

**Patrón recomendado para polling:**

```python
# Usar una query específica para evitar falsos positivos
query = 'is:unread has:attachment filename:pdf -label:procesado'

# Después de procesar, aplicar label para no reprocesar
def aplicar_label_procesado(service, msg_id: str, label_id: str):
    service.users().messages().modify(
        userId='me',
        id=msg_id,
        body={
            'addLabelIds': [label_id],
            'removeLabelIds': ['UNREAD']
        }
    ).execute()
```

---

## 2. Claude Code CLI en Modo No-Interactivo

### 2.1 El flag -p / --print

El flag `-p` (equivalente a `--print`) es la clave para invocar Claude Code desde scripts. Ejecuta un prompt, escribe la respuesta en stdout, y termina. No requiere TTY ni interacción.

```bash
# Uso básico
claude -p "Analiza este texto y devuelve JSON"

# Con input desde archivo
claude -p "Extrae los ítems de este PDF" < documento.txt

# Con output estructurado
claude -p "Procesa el siguiente contenido" --output-format json

# Con herramientas específicas habilitadas
claude -p "Lee el archivo y analízalo" --allowedTools "Read,Bash"

# Limitar iteraciones para evitar loops
claude -p "Tarea de análisis" --max-turns 5
```

### 2.2 Formatos de output disponibles

| Formato | Uso | Descripción |
|---------|-----|-------------|
| `text` | Default | Texto plano en stdout |
| `json` | Scripting | Objeto JSON con metadata y result |
| `stream-json` | Streaming | JSON Lines, un objeto por línea |

**Estructura del output JSON:**

```json
{
  "type": "result",
  "subtype": "success",
  "result": "El contenido procesado aquí...",
  "session_id": "abc123",
  "total_cost_usd": 0.0045,
  "num_turns": 2,
  "is_error": false
}
```

### 2.3 Invocar Claude Code desde Python con subprocess

```python
# claude_invoker.py
import subprocess
import json
import os
from pathlib import Path


def invocar_claude(
    prompt: str,
    directorio_trabajo: str,
    archivos_contexto: list = None,
    max_turns: int = 10,
    timeout: int = 300
) -> dict:
    """
    Invoca Claude Code CLI en modo headless.
    Retorna el resultado parseado como dict.
    """
    cmd = [
        'claude',
        '-p', prompt,
        '--output-format', 'json',
        '--max-turns', str(max_turns),
        '--allowedTools', 'Read,Write,Bash',
    ]

    # Construir el input con contexto de archivos si se especifica
    stdin_content = None
    if archivos_contexto:
        partes = []
        for ruta in archivos_contexto:
            if os.path.exists(ruta):
                with open(ruta, 'r', encoding='utf-8', errors='ignore') as f:
                    partes.append(f"=== {ruta} ===\n{f.read()}")
        if partes:
            stdin_content = '\n\n'.join(partes)

    resultado = subprocess.run(
        cmd,
        input=stdin_content,
        capture_output=True,
        text=True,
        cwd=directorio_trabajo,
        timeout=timeout,
        env={**os.environ}
    )

    if resultado.returncode != 0:
        raise RuntimeError(
            f"Claude Code falló con código {resultado.returncode}:\n"
            f"STDERR: {resultado.stderr}"
        )

    # Parsear output JSON
    try:
        data = json.loads(resultado.stdout)
        return data
    except json.JSONDecodeError:
        # Fallback: retornar texto plano
        return {'result': resultado.stdout, 'is_error': False}


def invocar_claude_con_pdf(prompt: str, ruta_pdf: str, directorio_trabajo: str) -> str:
    """
    Caso específico: pasa la ruta de un PDF a Claude para que lo lea.
    Claude Code tiene capacidad nativa de leer PDFs via la herramienta Read.
    """
    prompt_completo = f"{prompt}\n\nArchivo a analizar: {ruta_pdf}"

    resultado = invocar_claude(
        prompt=prompt_completo,
        directorio_trabajo=directorio_trabajo,
        max_turns=5
    )

    return resultado.get('result', '')
```

### 2.4 Modo streaming para respuestas largas

```python
def invocar_claude_streaming(prompt: str, directorio_trabajo: str):
    """Usa stream-json para procesar tokens en tiempo real."""
    cmd = ['claude', '-p', prompt, '--output-format', 'stream-json']

    proceso = subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        cwd=directorio_trabajo
    )

    resultado_final = ''
    for linea in proceso.stdout:
        linea = linea.strip()
        if not linea:
            continue
        try:
            evento = json.loads(linea)
            if evento.get('type') == 'content_block_delta':
                delta = evento.get('delta', {}).get('text', '')
                resultado_final += delta
                print(delta, end='', flush=True)
            elif evento.get('type') == 'result':
                break
        except json.JSONDecodeError:
            pass

    proceso.wait()
    return resultado_final
```

### 2.5 Notas sobre --dangerously-skip-permissions

Para pipelines completamente automatizados en entornos controlados (servidor dedicado, no máquina de desarrollo):

```bash
claude -p "procesa el archivo" --dangerously-skip-permissions
```

Este flag omite todas las confirmaciones de permisos. Usar solo cuando:
- El entorno está aislado (no hay riesgo de que Claude modifique archivos del sistema)
- Se combina con `--allowedTools` para restringir las herramientas disponibles
- El directorio de trabajo es un sandbox dedicado

---

## 3. Envío de Emails con Adjuntos JSON

### 3.1 Responder a un hilo de Gmail con JSON adjunto

Para que Gmail agrupe la respuesta en el mismo hilo, son necesarios tres elementos:
- El `threadId` del mensaje original
- El header `In-Reply-To` con el Message-ID original
- El header `References` con la cadena de IDs del hilo

```python
# gmail_sender.py
import base64
import json
import os
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.application import MIMEApplication
from email.mime.base import MIMEBase
from email import encoders
from googleapiclient.discovery import build
from auth import get_credentials


def obtener_message_id(mensaje: dict) -> str:
    """Extrae el Message-ID del email original."""
    headers = mensaje.get('payload', {}).get('headers', [])
    for header in headers:
        if header['name'].lower() == 'message-id':
            return header['value']
    return ''


def obtener_asunto(mensaje: dict) -> str:
    """Extrae el asunto del email."""
    headers = mensaje.get('payload', {}).get('headers', [])
    for header in headers:
        if header['name'].lower() == 'subject':
            return header['value']
    return ''


def obtener_remitente(mensaje: dict) -> str:
    """Extrae el email del remitente."""
    headers = mensaje.get('payload', {}).get('headers', [])
    for header in headers:
        if header['name'].lower() == 'from':
            return header['value']
    return ''


def responder_con_json(
    service,
    mensaje_original: dict,
    cuerpo_respuesta: str,
    datos_json: dict,
    nombre_archivo_json: str = 'resultado.json'
):
    """
    Responde a un email en el mismo hilo, adjuntando un JSON.
    """
    thread_id = mensaje_original['threadId']
    message_id_original = obtener_message_id(mensaje_original)
    asunto_original = obtener_asunto(mensaje_original)
    destinatario = obtener_remitente(mensaje_original)

    # Asunto con Re: si no lo tiene ya
    asunto_respuesta = asunto_original
    if not asunto_respuesta.lower().startswith('re:'):
        asunto_respuesta = f"Re: {asunto_respuesta}"

    # Construir mensaje MIME multipart
    msg = MIMEMultipart()
    msg['To'] = destinatario
    msg['Subject'] = asunto_respuesta

    # Headers críticos para threading
    if message_id_original:
        msg['In-Reply-To'] = message_id_original
        msg['References'] = message_id_original

    # Cuerpo de texto
    msg.attach(MIMEText(cuerpo_respuesta, 'plain', 'utf-8'))

    # Adjuntar JSON
    json_bytes = json.dumps(datos_json, indent=2, ensure_ascii=False).encode('utf-8')
    adjunto = MIMEApplication(json_bytes, _subtype='json')
    adjunto.add_header(
        'Content-Disposition',
        'attachment',
        filename=nombre_archivo_json
    )
    msg.attach(adjunto)

    # Codificar en base64 URL-safe para la API de Gmail
    raw = base64.urlsafe_b64encode(msg.as_bytes()).decode('utf-8')

    # Enviar con threadId para mantener el hilo
    resultado = service.users().messages().send(
        userId='me',
        body={
            'raw': raw,
            'threadId': thread_id
        }
    ).execute()

    return resultado


# Ejemplo de uso completo
def procesar_y_responder(service, mensaje: dict, resultado_analisis: dict):
    """Flujo completo: analizar y responder."""
    cuerpo = (
        "Hola,\n\n"
        "Se procesó correctamente el PDF adjunto. "
        "Los resultados del análisis se encuentran en el archivo JSON adjunto.\n\n"
        "Saludos."
    )

    return responder_con_json(
        service=service,
        mensaje_original=mensaje,
        cuerpo_respuesta=cuerpo,
        datos_json=resultado_analisis,
        nombre_archivo_json='analisis_resultado.json'
    )
```

---

## 4. Task Scheduling en Windows

### 4.1 Windows Task Scheduler via PowerShell (método recomendado)

PowerShell ofrece más control que `schtasks.exe` para configurar repetición de 30 minutos.

```powershell
# Crear tarea que corre cada 30 minutos, indefinidamente
# Guardar como: crear_tarea.ps1

$nombreTarea = "PIPA-Pipeline"
$descripcion = "Pipeline de procesamiento de PDFs via Gmail + Claude"
$rutaBat = "C:\PIPA\run_pipeline.bat"

# Trigger: diario desde las 06:00, con repetición cada 30 minutos por 24 horas
$trigger = New-ScheduledTaskTrigger `
    -Daily `
    -At "06:00AM" `
    -RepetitionInterval (New-TimeSpan -Minutes 30) `
    -RepetitionDuration (New-TimeSpan -Hours 23 -Minutes 30)

# Acción: ejecutar el bat wrapper
$accion = New-ScheduledTaskAction `
    -Execute $rutaBat

# Configuración: correr aunque no haya usuario logueado
$configuracion = New-ScheduledTaskSettingsSet `
    -ExecutionTimeLimit (New-TimeSpan -Minutes 25) `
    -RestartInterval (New-TimeSpan -Minutes 5) `
    -RestartCount 2 `
    -RunOnlyIfNetworkAvailable $true `
    -StartWhenAvailable $true

# Principal: correr con permisos del sistema o usuario específico
$principal = New-ScheduledTaskPrincipal `
    -UserId "SYSTEM" `
    -RunLevel Highest

# Registrar la tarea
Register-ScheduledTask `
    -TaskName $nombreTarea `
    -Description $descripcion `
    -Trigger $trigger `
    -Action $accion `
    -Settings $configuracion `
    -Principal $principal `
    -Force

Write-Host "Tarea '$nombreTarea' registrada correctamente."
```

### 4.2 Wrapper .bat para el script Python

```batch
@echo off
REM run_pipeline.bat
REM Wrapper que asegura el entorno correcto para el script Python

SET SCRIPT_DIR=C:\PIPA
SET PYTHON_EXE=C:\Python311\python.exe
SET LOG_FILE=%SCRIPT_DIR%\logs\pipeline_%date:~-4,4%%date:~-7,2%%date:~-10,2%.log

REM Crear directorio de logs si no existe
if not exist "%SCRIPT_DIR%\logs" mkdir "%SCRIPT_DIR%\logs"

REM Ejecutar con timestamp en el log
echo [%date% %time%] Iniciando pipeline >> "%LOG_FILE%"
"%PYTHON_EXE%" "%SCRIPT_DIR%\pipeline_main.py" >> "%LOG_FILE%" 2>&1
echo [%date% %time%] Pipeline finalizado con codigo %ERRORLEVEL% >> "%LOG_FILE%"
```

### 4.3 Registrar via schtasks.exe (alternativa de línea de comandos)

```cmd
REM Crear tarea con repetición cada 30 minutos
schtasks /Create ^
    /TN "PIPA-Pipeline" ^
    /TR "C:\PIPA\run_pipeline.bat" ^
    /SC DAILY ^
    /ST 06:00 ^
    /RI 30 ^
    /DU 1440 ^
    /RL HIGHEST ^
    /RU SYSTEM ^
    /F

REM Verificar que se creó correctamente
schtasks /Query /TN "PIPA-Pipeline" /FO LIST /V
```

### 4.4 Alternativa: NSSM para procesos que no deben terminar

Si el pipeline necesita estar corriendo continuamente (con sleep interno en lugar de re-ejecución):

```bash
# Instalar NSSM (Non-Sucking Service Manager)
# Descargar desde https://nssm.cc/

nssm install PIPA-Service "C:\Python311\python.exe" "C:\PIPA\pipeline_loop.py"
nssm set PIPA-Service AppDirectory "C:\PIPA"
nssm set PIPA-Service AppStdout "C:\PIPA\logs\service.log"
nssm set PIPA-Service AppStderr "C:\PIPA\logs\service_err.log"
nssm set PIPA-Service Start SERVICE_AUTO_START
nssm start PIPA-Service
```

**Cuándo usar Task Scheduler vs NSSM:**
- Task Scheduler: el script corre, termina y libera recursos. Ideal para tareas periódicas con inicio/fin claro.
- NSSM: el proceso corre indefinidamente, con un loop interno. Mejor si necesitas estado persistente entre ciclos.

---

## 5. Manejo de Archivos PDF en Pipelines Automatizados

### 5.1 Estructura de directorios recomendada

```
C:\PIPA\
├── credentials.json        # Credenciales OAuth2 (NO commitear)
├── token.json              # Token de acceso (NO commitear)
├── pipeline_main.py
├── auth.py
├── gmail_monitor.py
├── gmail_sender.py
├── claude_invoker.py
├── tmp\                    # PDFs temporales (se limpian después)
│   └── .gitkeep
├── logs\                   # Logs rotativos
└── procesados\             # Opcional: PDFs archivados
```

### 5.2 Validación de integridad de PDFs

```python
# pdf_handler.py
import os
import tempfile
import hashlib
from pathlib import Path


def validar_pdf(ruta_pdf: str) -> tuple[bool, str]:
    """
    Valida que un archivo sea un PDF válido y legible.
    Retorna (es_valido, mensaje_error).
    """
    # Verificar que existe y no está vacío
    if not os.path.exists(ruta_pdf):
        return False, f"Archivo no encontrado: {ruta_pdf}"

    tamanio = os.path.getsize(ruta_pdf)
    if tamanio == 0:
        return False, "El archivo está vacío"

    # Verificar magic bytes del PDF
    with open(ruta_pdf, 'rb') as f:
        header = f.read(5)
        if header != b'%PDF-':
            return False, f"No es un PDF válido (header: {header})"

    # Intentar parsear con pypdf para verificar integridad estructural
    try:
        import pypdf
        with open(ruta_pdf, 'rb') as f:
            reader = pypdf.PdfReader(f)
            num_paginas = len(reader.pages)
            if num_paginas == 0:
                return False, "El PDF no tiene páginas"
            # Intentar leer primera página para verificar accesibilidad
            _ = reader.pages[0].extract_text()
        return True, f"PDF válido: {num_paginas} páginas"

    except pypdf.errors.PdfReadError as e:
        return False, f"PDF corrupto o cifrado: {e}"
    except Exception as e:
        return False, f"Error al leer PDF: {e}"


def calcular_hash(ruta_pdf: str) -> str:
    """Calcula MD5 para detectar duplicados."""
    hasher = hashlib.md5()
    with open(ruta_pdf, 'rb') as f:
        for chunk in iter(lambda: f.read(8192), b''):
            hasher.update(chunk)
    return hasher.hexdigest()


class GestorPDFTemporal:
    """
    Context manager para PDFs temporales.
    Garantiza limpieza automática incluso ante excepciones.
    """

    def __init__(self, directorio_tmp: str = None):
        self.directorio_tmp = directorio_tmp or tempfile.gettempdir()
        self.archivos = []

    def agregar(self, ruta: str):
        self.archivos.append(ruta)
        return ruta

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.limpiar()
        # No suprimir la excepción original
        return False

    def limpiar(self):
        for ruta in self.archivos:
            try:
                if os.path.exists(ruta):
                    os.remove(ruta)
            except OSError as e:
                print(f"Advertencia: no se pudo eliminar {ruta}: {e}")
        self.archivos.clear()


# Ejemplo de uso del context manager
def procesar_pdfs_con_limpieza(lista_pdfs: list) -> list:
    resultados = []

    with GestorPDFTemporal('C:\\PIPA\\tmp') as gestor:
        for ruta in lista_pdfs:
            gestor.agregar(ruta)

            es_valido, mensaje = validar_pdf(ruta)
            if not es_valido:
                resultados.append({'ruta': ruta, 'error': mensaje, 'valido': False})
                continue

            # Procesar aquí...
            resultados.append({'ruta': ruta, 'valido': True})

    # Al salir del with, todos los PDFs se eliminan automáticamente
    return resultados
```

### 5.3 Extraer texto de PDF para pasar a Claude

```python
import pypdf


def extraer_texto_pdf(ruta_pdf: str, max_chars: int = 50000) -> str:
    """
    Extrae texto de un PDF, con límite de caracteres para no saturar el contexto.
    """
    texto_total = []

    with open(ruta_pdf, 'rb') as f:
        reader = pypdf.PdfReader(f)
        for i, pagina in enumerate(reader.pages):
            texto = pagina.extract_text()
            if texto:
                texto_total.append(f"[Página {i+1}]\n{texto}")

    contenido = '\n\n'.join(texto_total)

    if len(contenido) > max_chars:
        contenido = contenido[:max_chars] + '\n\n[... texto truncado por límite ...]'

    return contenido
```

---

## 6. Patrones de Retry y Error Handling para Agentes

### 6.1 Instalación

```bash
pip install tenacity
```

### 6.2 Decoradores de retry para cada componente

```python
# resilience.py
import logging
import time
from functools import wraps
from tenacity import (
    retry,
    stop_after_attempt,
    wait_exponential,
    retry_if_exception_type,
    before_sleep_log,
    RetryError
)
from googleapiclient.errors import HttpError

logger = logging.getLogger(__name__)


# --- Retry para llamadas a Gmail API ---
@retry(
    stop=stop_after_attempt(4),
    wait=wait_exponential(multiplier=1, min=2, max=30),
    retry=retry_if_exception_type((HttpError, ConnectionError, TimeoutError)),
    before_sleep=before_sleep_log(logger, logging.WARNING),
    reraise=True
)
def llamar_gmail_api(funcion_api, *args, **kwargs):
    """Wrapper con retry para cualquier llamada a la Gmail API."""
    return funcion_api(*args, **kwargs)


# --- Retry para Claude Code CLI ---
class ClaudeCodigoFallo(Exception):
    """Claude Code retornó un error no recuperable."""
    pass

class ClaudeTimeout(Exception):
    """Claude Code excedió el tiempo límite."""
    pass


@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=2, min=5, max=60),
    retry=retry_if_exception_type((ClaudeTimeout, RuntimeError)),
    before_sleep=before_sleep_log(logger, logging.WARNING),
    reraise=False  # retorna None en vez de lanzar si agota intentos
)
def invocar_claude_con_retry(prompt: str, directorio: str, timeout: int = 300):
    """Invoca Claude Code con retry automático ante fallos."""
    import subprocess
    import json

    cmd = ['claude', '-p', prompt, '--output-format', 'json', '--max-turns', '5']

    try:
        resultado = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            cwd=directorio,
            timeout=timeout
        )
    except subprocess.TimeoutExpired:
        raise ClaudeTimeout(f"Claude Code no respondió en {timeout}s")

    if resultado.returncode != 0:
        stderr = resultado.stderr[:500]
        # Si es error de API (rate limit, etc), reintentar
        if 'rate limit' in stderr.lower() or '429' in stderr:
            raise RuntimeError(f"Rate limit de API: {stderr}")
        # Si es error de configuración, no reintentar
        raise ClaudeCodigoFallo(f"Error de configuración: {stderr}")

    try:
        return json.loads(resultado.stdout)
    except json.JSONDecodeError:
        return {'result': resultado.stdout}
```

### 6.3 Circuit Breaker para fallos consecutivos

```python
# circuit_breaker.py
import time
from enum import Enum
from dataclasses import dataclass, field
from typing import Callable


class Estado(Enum):
    CERRADO = "cerrado"       # Normal: las llamadas pasan
    ABIERTO = "abierto"       # Fallo: bloquea llamadas
    SEMI_ABIERTO = "semi_abierto"  # Probando recuperación


@dataclass
class CircuitBreaker:
    """
    Implementación simple de Circuit Breaker.
    Evita llamadas repetidas a un servicio que está fallando.
    """
    nombre: str
    umbral_fallos: int = 5
    timeout_recuperacion: int = 60  # segundos

    estado: Estado = field(default=Estado.CERRADO, init=False)
    conteo_fallos: int = field(default=0, init=False)
    ultimo_fallo: float = field(default=0.0, init=False)

    def puede_ejecutar(self) -> bool:
        if self.estado == Estado.CERRADO:
            return True

        if self.estado == Estado.ABIERTO:
            if time.time() - self.ultimo_fallo > self.timeout_recuperacion:
                self.estado = Estado.SEMI_ABIERTO
                return True
            return False

        # SEMI_ABIERTO: permite una llamada de prueba
        return True

    def registrar_exito(self):
        self.conteo_fallos = 0
        self.estado = Estado.CERRADO

    def registrar_fallo(self):
        self.conteo_fallos += 1
        self.ultimo_fallo = time.time()

        if self.conteo_fallos >= self.umbral_fallos:
            self.estado = Estado.ABIERTO
            import logging
            logging.getLogger(__name__).error(
                f"Circuit Breaker '{self.nombre}' ABIERTO tras {self.conteo_fallos} fallos"
            )

    def ejecutar(self, funcion: Callable, *args, **kwargs):
        if not self.puede_ejecutar():
            raise RuntimeError(
                f"Circuit Breaker '{self.nombre}' abierto. "
                f"Reintentando en {self.timeout_recuperacion}s."
            )
        try:
            resultado = funcion(*args, **kwargs)
            self.registrar_exito()
            return resultado
        except Exception as e:
            self.registrar_fallo()
            raise


# Instancias globales de circuit breakers
cb_gmail = CircuitBreaker("Gmail-API", umbral_fallos=5, timeout_recuperacion=120)
cb_claude = CircuitBreaker("Claude-Code", umbral_fallos=3, timeout_recuperacion=300)
```

### 6.4 Pipeline principal con manejo de errores completo

```python
# pipeline_main.py
import logging
import sys
import os
from datetime import datetime
from pathlib import Path

# Configurar logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(name)s: %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler(
            f'C:\\PIPA\\logs\\pipeline_{datetime.now().strftime("%Y%m%d")}.log',
            encoding='utf-8'
        )
    ]
)
logger = logging.getLogger('pipeline')

from gmail_monitor import get_gmail_service, buscar_emails_con_pdf, obtener_mensaje_completo, extraer_adjuntos_pdf, marcar_como_leido
from gmail_sender import responder_con_json
from claude_invoker import invocar_claude_con_retry
from pdf_handler import validar_pdf, GestorPDFTemporal, extraer_texto_pdf
from circuit_breaker import cb_gmail, cb_claude

TMP_DIR = Path('C:\\PIPA\\tmp')
TMP_DIR.mkdir(exist_ok=True)

PROMPT_ANALISIS = """
Analiza el siguiente listado de materiales de construcción extraído de un PDF.
Devuelve un JSON con esta estructura exacta:
{
  "items": [{"descripcion": "...", "cantidad": 0, "unidad": "...", "codigo": "..."}],
  "total_items": 0,
  "observaciones": "..."
}
Solo devuelve el JSON, sin texto adicional.

Contenido del PDF:
"""


def procesar_email(service, mensaje: dict) -> bool:
    """
    Procesa un único email: descarga PDF, llama a Claude, responde.
    Retorna True si el procesamiento fue exitoso.
    """
    msg_id = mensaje['id']
    logger.info(f"Procesando email ID: {msg_id}")

    with GestorPDFTemporal(str(TMP_DIR)) as gestor:
        # 1. Obtener mensaje completo
        try:
            mensaje_completo = cb_gmail.ejecutar(
                obtener_mensaje_completo, service, msg_id
            )
        except Exception as e:
            logger.error(f"No se pudo obtener el mensaje {msg_id}: {e}")
            return False

        # 2. Descargar PDFs
        try:
            pdfs = cb_gmail.ejecutar(
                extraer_adjuntos_pdf, service, mensaje_completo, str(TMP_DIR)
            )
        except Exception as e:
            logger.error(f"Error descargando adjuntos de {msg_id}: {e}")
            return False

        if not pdfs:
            logger.warning(f"Email {msg_id} no tiene PDFs válidos, ignorando.")
            marcar_como_leido(service, msg_id)
            return True

        for ruta_pdf in pdfs:
            gestor.agregar(ruta_pdf)

        # 3. Validar y procesar cada PDF
        for ruta_pdf in pdfs:
            es_valido, mensaje_error = validar_pdf(ruta_pdf)
            if not es_valido:
                logger.warning(f"PDF inválido {ruta_pdf}: {mensaje_error}")
                continue

            # 4. Extraer texto y llamar a Claude
            texto = extraer_texto_pdf(ruta_pdf)
            prompt = PROMPT_ANALISIS + texto

            try:
                resultado = cb_claude.ejecutar(
                    invocar_claude_con_retry,
                    prompt,
                    str(TMP_DIR)
                )
            except Exception as e:
                logger.error(f"Claude Code falló para {ruta_pdf}: {e}")
                continue

            if resultado is None:
                logger.error(f"Claude Code agotó los reintentos para {ruta_pdf}")
                continue

            # 5. Parsear el JSON del resultado de Claude
            import json
            texto_resultado = resultado.get('result', '')
            try:
                # Limpiar markdown si Claude envuelve en ```json
                if '```' in texto_resultado:
                    texto_resultado = texto_resultado.split('```')[1]
                    if texto_resultado.startswith('json'):
                        texto_resultado = texto_resultado[4:]

                datos_json = json.loads(texto_resultado.strip())
            except json.JSONDecodeError as e:
                logger.error(f"Resultado de Claude no es JSON válido: {e}")
                datos_json = {'raw_result': texto_resultado, 'parse_error': str(e)}

            # 6. Responder al email
            try:
                cb_gmail.ejecutar(
                    responder_con_json,
                    service,
                    mensaje_completo,
                    "PDF procesado correctamente. Ver adjunto.",
                    datos_json,
                    f"resultado_{Path(ruta_pdf).stem}.json"
                )
                logger.info(f"Respuesta enviada para {ruta_pdf}")
            except Exception as e:
                logger.error(f"Error al enviar respuesta para {ruta_pdf}: {e}")
                return False

        # 7. Marcar como leído para no reprocesar
        marcar_como_leido(service, msg_id)
        return True


def main():
    logger.info("=== Pipeline iniciado ===")

    try:
        service = get_gmail_service()
    except Exception as e:
        logger.critical(f"No se pudo conectar a Gmail: {e}")
        sys.exit(1)

    try:
        mensajes = buscar_emails_con_pdf(
            service,
            query='is:unread has:attachment filename:pdf'
        )
    except Exception as e:
        logger.error(f"Error buscando emails: {e}")
        sys.exit(1)

    if not mensajes:
        logger.info("No hay emails nuevos con PDFs.")
        return

    logger.info(f"Encontrados {len(mensajes)} emails para procesar.")

    exitosos = 0
    fallidos = 0

    for mensaje in mensajes:
        if procesar_email(service, mensaje):
            exitosos += 1
        else:
            fallidos += 1

    logger.info(f"=== Pipeline completado: {exitosos} exitosos, {fallidos} fallidos ===")


if __name__ == '__main__':
    main()
```

---

## Analysis

### Decisiones técnicas clave

**OAuth2 vs Service Account:** Para acceder al Gmail de una cuenta personal, OAuth2 con refresh token es la única opción. Las service accounts solo funcionan con Google Workspace (cuentas empresariales con dominio). El token.json debe protegerse como credencial sensible.

**Polling vs Push:** Con intervalos de 30 minutos, el polling es equivalente en práctica y mucho más simple que configurar Pub/Sub. La query `is:unread has:attachment filename:pdf` es eficiente y evita procesar emails sin PDF.

**Claude Code CLI vs API directa:** El CLI de Claude Code es preferible a la API REST cuando el procesamiento implica leer archivos del disco, ya que Claude Code puede invocar la herramienta `Read` nativa. Para texto puro, la API REST es más eficiente.

**Task Scheduler vs servicio Windows:** Para un pipeline de 30 minutos que corre y termina, Task Scheduler es la opción correcta. NSSM agrega complejidad innecesaria cuando no se necesita estado persistente.

### Riesgos a monitorear

1. **Expiración del refresh token:** en proyectos de OAuth con estado "Testing", los refresh tokens expiran en 7 días. Para producción, el proyecto debe pasar a estado "Published" (requiere verificación de Google) o usar una cuenta de Google Workspace.

2. **Rate limits de Gmail API:** 250 quota units por usuario por segundo. Descargar adjuntos grandes cuenta como múltiples unidades. El circuit breaker de `cb_gmail` mitiga esto.

3. **Tamaño del contexto de Claude:** PDFs muy largos (>100 páginas) pueden exceder el contexto. La función `extraer_texto_pdf` trunca a 50,000 caracteres. Para PDFs muy grandes, procesar por secciones.

4. **PDF cifrado o de imagen (scanned):** `pypdf` no puede extraer texto de PDFs que son imágenes escaneadas. En ese caso, usar `pytesseract` + `pdf2image` para OCR.

---

## Conclusions

El stack técnico concreto para el pipeline es:

| Componente | Librería/Herramienta |
|-----------|---------------------|
| Autenticación Gmail | `google-auth-oauthlib` |
| Lectura de emails | `google-api-python-client` |
| Validación PDF | `pypdf` |
| Extracción texto | `pypdf` |
| Análisis con IA | `claude` CLI con `-p --output-format json` |
| Envío respuesta | `google-api-python-client` + `email.mime` |
| Scheduling | Windows Task Scheduler + PowerShell |
| Retry | `tenacity` |
| Circuit Breaker | implementación custom (20 líneas) |

---

## References

- [Gmail API Python Quickstart - Google Developers](https://developers.google.com/gmail/api/quickstart/python)
- [Run Claude Code Programmatically - Official Docs](https://code.claude.com/docs/en/headless)
- [Claude Code CLI --print Flag - ClaudeLog](https://claudelog.com/faqs/what-is-print-flag-in-claude-code/)
- [What is --output-format in Claude Code - ClaudeLog](https://claudelog.com/faqs/what-is-output-format-in-claude-code/)
- [Claude Code --dangerously-skip-permissions Guide](https://pasqualepillitteri.it/en/news/141/claude-code-dangerously-skip-permissions-guide-autonomous-mode)
- [Sending Emails with Python - Real Python](https://realpython.com/python-send-email/)
- [Python Send Email Tutorial with Code Snippets - Mailtrap](https://mailtrap.io/blog/python-send-email/)
- [Schedule Python Script with Windows Task Scheduler - DataToFish](https://datatofish.com/python-script-windows-scheduler/)
- [New-ScheduledTaskTrigger - Microsoft Learn](https://learn.microsoft.com/en-us/powershell/module/scheduledtasks/new-scheduledtasktrigger?view=windowsserver2025-ps)
- [Tenacity - Python Retry Library](https://tenacity.readthedocs.io/)
- [How to Implement Retry Logic with Exponential Backoff - OneUptime](https://oneuptime.com/blog/post/2025-01-06-python-retry-exponential-backoff/view)
- [pypdf PDF Validation Discussion - GitHub](https://github.com/py-pdf/pypdf/discussions/2205)
- [Gmail API Push Notifications - Google Developers](https://developers.google.com/workspace/gmail/api/guides/push)
- [Managing Threads in Gmail API - Google Developers](https://developers.google.com/gmail/api/guides/threads)
- [Claude Code SDK - PyPI](https://pypi.org/project/claude-code-sdk/)
- [Gmail API Automation Guide 2026 - OutrightCRM](https://www.outrightcrm.com/blog/gmail-api-automation-guide/)
- [How to Use Gmail API in Python - ThePythonCode](https://thepythoncode.com/article/use-gmail-api-in-python)
- [NSSM Windows Service Automation - XDA Developers](https://www.xda-developers.com/nssm-service-automation-windows-pc/)
- [Running Claude Code from Windows CLI - dstreefkerk.github.io](https://dstreefkerk.github.io/2026-01-running-claude-code-from-windows-cli/)
- [Claude Code Best Practices - Official Docs](https://code.claude.com/docs/en/best-practices)

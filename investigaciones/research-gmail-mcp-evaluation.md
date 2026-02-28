# Evaluacion de MCP Servers de Gmail para PIPA

> **Fecha:** 2026-02-27
> **Decision final:** Construir MCP Server custom con FastMCP Python SDK
> **Referenciado desde:** docs/v1-spec.md §11.1 (ADR-002)

## Resumen Ejecutivo

Se evaluaron 15+ MCP servers de Gmail de la comunidad. Ningun servidor cumple las 5 operaciones criticas de PIPA sin bugs o gaps significativos. Se decidio construir un MCP server custom de ~250 lineas Python.

## Servidores Evaluados

### Top 3 Candidatos (descartados)

| Server | Stars | Razon de descarte |
|--------|-------|-------------------|
| **GongRzhe/Gmail-MCP-Server** | ~1,000 | Bug #66: replies no se quedan en hilo (falta In-Reply-To/References). Bug #48: label IDs incorrectos. |
| **taylorwilsdon/google_workspace_mcp** | ~1,600 | Funcional pero requiere base64 para adjuntos en replies (no file paths). Mas complejo de integrar. |
| **shinzo-labs/gmail-mcp** | ~41 | sendReply con threading no confirmado. Issue #65 de attachments abierto. |

### Otros evaluados

- baryhuang/mcp-headless-gmail: Solo 4 tools, sin search, sin labels, sin attachments
- Composio Gmail MCP: SaaS dependency, S3 attachments, deprecation warnings
- Workato Gmail MCP: Commercial/enterprise, draft-then-send model
- MarkusPfundstein/mcp-gsuite: Sin modifyLabels, reply-with-attachment no confirmado
- david-strejc/gmail-mcp-server: IMAP/SMTP, threading semantics unreliable
- Shravan1610/Gmail-mcp-server: Inactive since Nov 2025
- aaronsb/google-workspace-mcp: getAttachment underspecified
- theposch/gmail-mcp: No getAttachment
- tonykipkemboi/gmail-imap-mcp: No thread reply
- gnmahanth/gmail-attachment-mcp-server: Download only
- cafferychen777/gmail-mcp: Requires Chrome browser (incompatible)

### Hallazgo critico transversal

**Ningun MCP server de comunidad expone `users.history.list` (Gmail History API).** Esto ya esta cubierto en la arquitectura de PIPA — el wrapper Python hace el polling directamente.

## Decision: MCP Custom

- ~250 lineas Python con FastMCP SDK oficial
- Exactamente 5 tools: search, get_message, get_attachment, send_reply, modify_labels
- Scope OAuth2: `gmail.modify` (cubre las 5 operaciones)
- Comparte credenciales con el wrapper Python (mismo token.json)
- Threading correcto con In-Reply-To y References headers
- Adjuntos via file path local (no base64)
- Estimacion de esfuerzo: 4-8 horas

## Referencias de implementacion

- Template base: jeremyjordan/mcp-gmail (estructura FastMCP)
- Patron de adjuntos: GongRzhe/Gmail-MCP-Server (Gmail API patterns)
- SDK oficial: https://github.com/modelcontextprotocol/python-sdk
- FastMCP docs: https://gofastmcp.com

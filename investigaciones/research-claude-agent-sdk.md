# Claude Agent SDK: Programmatic Capabilities for Automated Agents

**Date:** 2026-02-27
**Research Focus:** Claude Code / Claude Agent SDK - programmatic use, hooks, headless mode, and MCP integration

---

## Executive Summary

Anthropic's Claude Code tool has evolved beyond a CLI coding assistant into a full-featured agent framework. The underlying SDK — originally called the Claude Code SDK (`@anthropic-ai/claude-code`) and recently rebranded as the **Claude Agent SDK** (`@anthropic-ai/claude-agent-sdk`) — exposes a TypeScript/Python API that allows developers to run Claude-powered agents programmatically, with complete control over tool permissions, session state, MCP server connections, and lifecycle hooks.

Key capabilities discovered:

- The `query()` function is the primary entry point, returning an async generator of typed messages. It accepts over 30 configuration options, covering models, tools, permissions, session resumption, MCP servers, and inline hook callbacks.
- Sessions are automatically persisted to disk and can be resumed or forked by session ID, enabling stateful multi-call workflows without re-sending the full conversation history.
- A rich hook system (17 event types) allows interception of every stage of agent execution — from `PreToolUse` and `PostToolUse` through `SessionStart`, `Notification`, and `SubagentStop` — including the ability to block, modify, or log tool calls and make outbound HTTP requests.
- The `--print` (`-p`) CLI flag enables headless, non-interactive invocation with structured JSON output, suitable for scripting and CI/CD pipelines.
- MCP (Model Context Protocol) servers can be injected at `query()` call time, loaded from a `.mcp.json` project file, or persisted globally in `~/.claude.json`, providing access to Gmail, Google Calendar, databases, GitHub, and hundreds of community-contributed services.

---

## Introduction

The Claude Agent SDK is the programmatic interface to the same agent loop that powers Claude Code in the terminal. It enables developers to build automated workflows, monitoring systems, background agents, and multi-agent architectures without any interactive user interface.

This research was conducted to answer four specific questions relevant to building a heartbeat/monitoring system ("PIPA"):

1. How do you import and control Claude programmatically from Node.js/TypeScript?
2. How does the hook system work and how can it integrate with external services?
3. How does the non-interactive (`--print`) mode work?
4. Which MCP servers are available for Gmail, Calendar, and task management?

---

## Methodology

Research was conducted via direct fetches of the official Anthropic documentation at `platform.claude.com/docs` and `code.claude.com/docs`, supplemented by web searches for community articles, GitHub repositories, and migration guides. Primary sources consulted include:

- Official Claude Agent SDK TypeScript reference
- Official hooks reference and hooks guide
- Official session management documentation
- Official MCP integration documentation
- Claude Code CLI headless mode documentation
- Migration guide from `@anthropic-ai/claude-code` to `@anthropic-ai/claude-agent-sdk`
- Community GitHub repositories and npm registry

---

## Part 1: Claude Agent SDK — Library Usage

### 1.1 Package Name Change and Installation

The SDK was renamed from `@anthropic-ai/claude-code` to `@anthropic-ai/claude-agent-sdk` in a breaking release (v0.1.0). The old package is deprecated but still functional. New projects should use the new name.

```bash
# Remove the old package if present
npm uninstall @anthropic-ai/claude-code

# Install the current SDK
npm install @anthropic-ai/claude-agent-sdk
```

Update imports:

```typescript
// OLD (deprecated)
import { query } from "@anthropic-ai/claude-code";

// NEW (current)
import { query } from "@anthropic-ai/claude-agent-sdk";
```

The Claude Code CLI itself is no longer installed via npm. It uses a dedicated installer:

```bash
# macOS / Linux
curl -fsSL https://claude.ai/install.sh | bash
```

### 1.2 The `query()` Function

`query()` is the primary function for interacting with Claude Code programmatically. It returns a `Query` object — an `AsyncGenerator<SDKMessage, void>` extended with control methods.

```typescript
function query({
  prompt,
  options
}: {
  prompt: string | AsyncIterable<SDKUserMessage>;
  options?: Options;
}): Query;
```

**Basic usage:**

```typescript
import { query } from "@anthropic-ai/claude-agent-sdk";

for await (const message of query({
  prompt: "Analyze the auth module and report any security issues",
  options: {
    model: "claude-opus-4-6",
    allowedTools: ["Read", "Grep", "Glob"],
    permissionMode: "bypassPermissions"
  }
})) {
  if (message.type === "result" && message.subtype === "success") {
    console.log(message.result);
  }
}
```

### 1.3 The `Options` Object — Full Parameter Reference

The `Options` type accepts over 30 fields. The most relevant for automated agents:

| Option | Type | Default | Purpose |
|---|---|---|---|
| `model` | `string` | CLI default | Claude model to use (e.g., `"claude-opus-4-6"`) |
| `allowedTools` | `string[]` | All tools | Explicit allowlist for tool usage |
| `disallowedTools` | `string[]` | `[]` | Explicit blocklist for tool usage |
| `permissionMode` | `PermissionMode` | `'default'` | Broad permission strategy |
| `allowDangerouslySkipPermissions` | `boolean` | `false` | Required when using `bypassPermissions` |
| `mcpServers` | `Record<string, McpServerConfig>` | `{}` | Inline MCP server definitions |
| `hooks` | `Partial<Record<HookEvent, HookCallbackMatcher[]>>` | `{}` | Lifecycle hook callbacks |
| `resume` | `string` | — | Session ID to resume |
| `forkSession` | `boolean` | `false` | When resuming, create a new branch |
| `continue` | `boolean` | `false` | Continue the most recent session |
| `sessionId` | `string` | Auto-generated | Pin a specific UUID for the session |
| `persistSession` | `boolean` | `true` | Set to `false` to disable disk persistence |
| `systemPrompt` | `string \| { type: 'preset', preset: 'claude_code', append?: string }` | Minimal | Override or extend system prompt |
| `settingSources` | `SettingSource[]` | `[]` | Which filesystem settings files to load |
| `maxTurns` | `number` | — | Cap agentic loop iterations |
| `maxBudgetUsd` | `number` | — | Cost cap for the query |
| `cwd` | `string` | `process.cwd()` | Working directory |
| `effort` | `'low' \| 'medium' \| 'high' \| 'max'` | `'high'` | Thinking depth |
| `thinking` | `ThinkingConfig` | adaptive | Control reasoning behavior |
| `betas` | `SdkBeta[]` | `[]` | Enable beta features (e.g., 1M context window) |
| `agents` | `Record<string, AgentDefinition>` | — | Programmatic subagent definitions |
| `enableFileCheckpointing` | `boolean` | `false` | Track file changes for rewinding |
| `outputFormat` | `{ type: 'json_schema', schema: JSONSchema }` | — | Structured output schema |
| `canUseTool` | `CanUseTool` | — | Custom per-tool permission callback |
| `env` | `Record<string, string>` | `process.env` | Environment variables |
| `debug` | `boolean` | `false` | Enable debug output |
| `debugFile` | `string` | — | Write debug logs to a file |
| `stderr` | `(data: string) => void` | — | Callback for stderr output |
| `spawnClaudeCodeProcess` | function | — | Custom process spawner (for containers/VMs) |

### 1.4 The `Query` Object — Control Methods

The `Query` object returned by `query()` provides real-time control beyond just iterating messages:

| Method | Description |
|---|---|
| `interrupt()` | Interrupt the running query (streaming mode only) |
| `setPermissionMode(mode)` | Change permission mode mid-stream |
| `setModel(model?)` | Swap models mid-stream |
| `mcpServerStatus()` | Get the connection status of all MCP servers |
| `reconnectMcpServer(name)` | Reconnect a failed MCP server |
| `toggleMcpServer(name, enabled)` | Enable or disable an MCP server |
| `setMcpServers(servers)` | Replace the full set of MCP servers dynamically |
| `streamInput(stream)` | Push new user messages for multi-turn conversations |
| `stopTask(taskId)` | Stop a running background task |
| `rewindFiles(messageId, options?)` | Restore files to their state at a given turn |
| `initializationResult()` | Get session init data (models, commands, account) |
| `accountInfo()` | Return account information |
| `supportedModels()` | List available models |
| `close()` | Terminate the underlying process |

### 1.5 Permission Modes

```typescript
type PermissionMode =
  | "default"             // Standard prompting behavior
  | "acceptEdits"         // Auto-accept file edits
  | "bypassPermissions"   // Skip all safety prompts (use with caution)
  | "plan"                // Planning only, no execution
  | "dontAsk";            // Deny anything not pre-approved
```

For fully automated headless agents, `bypassPermissions` combined with `allowDangerouslySkipPermissions: true` removes all interactive prompts. This should only be used in controlled environments.

**Granular tool allowlisting** is often safer:

```typescript
options: {
  allowedTools: [
    "Read", "Grep", "Glob",          // Read-only filesystem
    "Bash(git status *)",             // Restrict Bash to specific commands
    "mcp__gmail__list_messages",      // Specific MCP tools
  ]
}
```

The trailing space-star pattern (`Bash(git status *)`) enables prefix matching, allowing any command that starts with `git status`.

### 1.6 Additional Functions

**`tool()`** — Creates a type-safe inline tool definition using Zod schemas:

```typescript
import { tool, createSdkMcpServer } from "@anthropic-ai/claude-agent-sdk";
import { z } from "zod";

const heartbeatTool = tool(
  "record_heartbeat",
  "Records a heartbeat event for the monitoring system",
  { timestamp: z.string(), status: z.string() },
  async ({ timestamp, status }) => ({
    content: [{ type: "text", text: `Heartbeat recorded: ${status} at ${timestamp}` }]
  })
);
```

**`createSdkMcpServer()`** — Bundles tools into an in-process MCP server passed to `query()`:

```typescript
const monitoringServer = createSdkMcpServer({
  name: "monitoring",
  tools: [heartbeatTool]
});

for await (const message of query({
  prompt: "Record a heartbeat",
  options: {
    mcpServers: { monitoring: monitoringServer }
  }
})) { ... }
```

**`listSessions()`** — Enumerate past sessions with metadata:

```typescript
import { listSessions } from "@anthropic-ai/claude-agent-sdk";

const sessions = await listSessions({ dir: "/path/to/project", limit: 10 });
// Returns: sessionId, summary, lastModified, firstPrompt, gitBranch, cwd
```

---

## Part 2: Session Management

### 2.1 How Sessions Work

Every `query()` call creates (or continues) a session. Session data — including the full conversation history — is persisted to disk by default. The session ID appears in the initial `system` message:

```typescript
let sessionId: string | undefined;

for await (const message of query({ prompt: "Start a review" })) {
  if (message.type === "system" && message.subtype === "init") {
    sessionId = message.session_id;
  }
}
```

### 2.2 Resuming Sessions

Pass the captured `sessionId` to `resume` in a subsequent call. Claude loads the full prior context automatically:

```typescript
for await (const message of query({
  prompt: "Now focus on the database layer",
  options: { resume: sessionId }
})) { ... }
```

**CLI equivalent:**

```bash
session_id=$(claude -p "Start a review" --output-format json | jq -r '.session_id')
claude -p "Continue that review" --resume "$session_id"
```

### 2.3 Forking Sessions

`forkSession: true` creates a branch from the resumed point, preserving the original session:

```typescript
// Branch 1: try REST approach
const restQuery = query({
  prompt: "Design this as a REST API",
  options: { resume: sessionId, forkSession: true }
});

// Branch 2 (original preserved): try GraphQL approach
const gqlQuery = query({
  prompt: "Design this as a GraphQL API",
  options: { resume: sessionId, forkSession: true }
});
```

### 2.4 Settings Sources

By default in v0.1.0, no filesystem settings are loaded. This is intentional for isolation. Use `settingSources` to opt in:

```typescript
options: {
  settingSources: ["user", "project", "local"]
  // "user"    => ~/.claude/settings.json
  // "project" => .claude/settings.json
  // "local"   => .claude/settings.local.json
}
```

Note: to load CLAUDE.md project instructions, you must also set `systemPrompt: { type: "preset", preset: "claude_code" }`.

### 2.5 TypeScript V2 Interface (Preview)

A simplified V2 SDK interface is available in preview that replaces `query()` with `createSession()` / `resumeSession()` and separate `send()` / `stream()` calls per turn, removing the need for async generator management:

```typescript
// V2 preview (createSession / resumeSession / send / stream pattern)
// Reduces multi-turn complexity significantly
```

---

## Part 3: The Hooks System

### 3.1 Overview

Hooks are callback functions (or shell commands, HTTP endpoints, or LLM prompts) that execute at specific points in the agent lifecycle. They can inspect, modify, block, or simply observe agent activity.

There are four handler types:
- **Command hooks**: shell scripts receiving JSON on stdin
- **HTTP hooks**: POST requests to a URL (good for integrating with external services)
- **Prompt hooks**: single-turn LLM evaluation
- **Agent hooks**: spawn a subagent to verify conditions

### 3.2 All 17 Hook Events

| Event | Fires When | Python SDK | TypeScript SDK |
|---|---|---|---|
| `PreToolUse` | Before any tool call (can block/modify) | Yes | Yes |
| `PostToolUse` | After tool succeeds | Yes | Yes |
| `PostToolUseFailure` | After tool fails | Yes | Yes |
| `UserPromptSubmit` | When user submits a prompt | Yes | Yes |
| `Stop` | Agent finishes responding | Yes | Yes |
| `SubagentStart` | Subagent spawned | Yes | Yes |
| `SubagentStop` | Subagent finishes | Yes | Yes |
| `PreCompact` | Before context compaction | Yes | Yes |
| `PermissionRequest` | Permission dialog would appear | Yes | Yes |
| `Notification` | Agent sends a status notification | Yes | Yes |
| `SessionStart` | Session begins or resumes | No | Yes |
| `SessionEnd` | Session terminates | No | Yes |
| `Setup` | Session setup/maintenance | No | Yes |
| `TeammateIdle` | Teammate about to go idle | No | Yes |
| `TaskCompleted` | Background task completes | No | Yes |
| `ConfigChange` | Config file changes during session | No | Yes |
| `WorktreeCreate` | Git worktree being created | No | Yes |
| `WorktreeRemove` | Git worktree being removed | No | Yes |

### 3.3 Configuring Hooks in Settings Files

Hooks defined in settings JSON files fire for all sessions using that project. The schema is three levels deep: event → matcher group → handler array.

```json
{
  "hooks": {
    "PreToolUse": [
      {
        "matcher": "Bash",
        "hooks": [
          {
            "type": "command",
            "command": ".claude/hooks/validate-bash.sh"
          }
        ]
      }
    ],
    "PostToolUse": [
      {
        "matcher": "Write|Edit",
        "hooks": [
          {
            "type": "http",
            "url": "http://localhost:8080/hooks/file-changed",
            "timeout": 10
          }
        ]
      }
    ]
  }
}
```

Hooks can be placed in:
- `~/.claude/settings.json` — applies to all your projects
- `.claude/settings.json` — project-scoped, can be committed to git
- `.claude/settings.local.json` — project-scoped, gitignored

### 3.4 Programmatic Hooks in the SDK

When using `query()`, hooks are registered inline as TypeScript callback functions:

```typescript
import { query, HookCallback, PreToolUseHookInput } from "@anthropic-ai/claude-agent-sdk";

// Block writes to .env files
const protectEnvFiles: HookCallback = async (input, toolUseID, { signal }) => {
  const preInput = input as PreToolUseHookInput;
  const toolInput = preInput.tool_input as Record<string, unknown>;
  const filePath = toolInput?.file_path as string;

  if (filePath?.endsWith(".env")) {
    return {
      hookSpecificOutput: {
        hookEventName: preInput.hook_event_name,
        permissionDecision: "deny",
        permissionDecisionReason: "Cannot modify .env files"
      }
    };
  }
  return {}; // allow
};

for await (const message of query({
  prompt: "Update the config",
  options: {
    hooks: {
      PreToolUse: [{ matcher: "Write|Edit", hooks: [protectEnvFiles] }]
    }
  }
})) {
  console.log(message);
}
```

### 3.5 Hook Output Fields

Each hook callback can return:

**Top-level fields** (affect conversation):
- `systemMessage: string` — inject context visible to the model
- `continue: boolean` — whether the agent should keep running after this hook

**`hookSpecificOutput`** (affect the current operation):

For `PreToolUse`:
- `permissionDecision: "allow" | "deny" | "ask"` — gate the tool call
- `permissionDecisionReason: string` — explanation shown to the model
- `updatedInput: object` — modified tool arguments (requires `permissionDecision: "allow"`)

For `PostToolUse`:
- `additionalContext: string` — append information to the tool result

Return `{}` to allow without changes.

### 3.6 Asynchronous Hooks (Fire-and-Forget)

For side effects like logging or sending webhooks, return `{ async: true }` to let the agent continue without waiting:

```typescript
const asyncLogger: HookCallback = async (input, toolUseID, { signal }) => {
  // Fire and forget — don't await
  sendToLoggingService(input).catch(console.error);
  return { async: true, asyncTimeout: 30000 };
};
```

### 3.7 Using Hooks for a Heartbeat System

The `PostToolUse` and `Stop` hooks are particularly useful for a heartbeat/monitoring system:

```typescript
// Send a heartbeat after every tool execution
const heartbeatHook: HookCallback = async (input, toolUseID, { signal }) => {
  try {
    await fetch("https://heartbeat.example.com/ping", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        event: input.hook_event_name,
        tool: (input as any).tool_name,
        session: input.session_id,
        timestamp: new Date().toISOString()
      }),
      signal
    });
  } catch (err) {
    // Never let a failed heartbeat crash the agent
    if (!(err instanceof Error && err.name === "AbortError")) {
      console.error("Heartbeat failed:", err);
    }
  }
  return {};
};

// Also capture agent stop events
const stopHook: HookCallback = async (input, _id, { signal }) => {
  await fetch("https://heartbeat.example.com/stop", {
    method: "POST",
    body: JSON.stringify({ session: input.session_id }),
    signal
  }).catch(() => {});
  return {};
};

const options = {
  hooks: {
    PostToolUse: [{ hooks: [heartbeatHook] }],
    Stop: [{ hooks: [stopHook] }]
  }
};
```

### 3.8 HTTP Hooks for External Integration

HTTP hooks (defined in settings files) send events as POST requests directly to an endpoint without writing shell scripts:

```json
{
  "hooks": {
    "PostToolUse": [
      {
        "hooks": [
          {
            "type": "http",
            "url": "https://monitoring.example.com/claude-events",
            "timeout": 5,
            "headers": {
              "Authorization": "Bearer $MONITOR_TOKEN"
            },
            "allowedEnvVars": ["MONITOR_TOKEN"]
          }
        ]
      }
    ]
  }
}
```

Non-2xx responses are non-blocking errors by default — the agent continues even if the webhook fails.

### 3.9 Matcher Patterns

Matchers are regex strings filtering which events trigger a handler:

| Pattern | Matches |
|---|---|
| `"Bash"` | Only the Bash tool |
| `"Write\|Edit"` | Write or Edit tools |
| `"mcp__.*"` | All MCP tools |
| `"mcp__gmail__.*"` | All tools from the `gmail` MCP server |
| `"mcp__.*__write.*"` | Any MCP tool with "write" in its name |
| `""` or omitted | All occurrences of the event |

---

## Part 4: CLI Headless Mode (`--print` / `-p`)

### 4.1 Basic Usage

The `-p` (or `--print`) flag runs Claude Code non-interactively from any shell:

```bash
claude -p "What does the auth module do?"
```

This executes one prompt and prints the result. All CLI options work with `-p`.

### 4.2 Output Formats

**Plain text (default):**
```bash
claude -p "Summarize this project"
```

**JSON with metadata:**
```bash
claude -p "Summarize this project" --output-format json
# Returns: { result, session_id, cost_usd, usage, ... }
```

**JSON with custom schema (structured output):**
```bash
claude -p "Extract function names from auth.py" \
  --output-format json \
  --json-schema '{"type":"object","properties":{"functions":{"type":"array","items":{"type":"string"}}},"required":["functions"]}' \
  | jq '.structured_output'
```

**Streaming JSON (real-time token stream):**
```bash
claude -p "Write a summary" \
  --output-format stream-json \
  --verbose \
  --include-partial-messages \
  | jq -rj 'select(.type == "stream_event" and .event.delta.type? == "text_delta") | .event.delta.text'
```

### 4.3 Tools in Print Mode

Tools work fully in `-p` mode. Use `--allowedTools` to auto-approve specific tools:

```bash
claude -p "Run the test suite and fix any failures" \
  --allowedTools "Bash,Read,Edit"

# With fine-grained Bash restrictions
claude -p "Look at staged changes and create an appropriate commit" \
  --allowedTools "Bash(git diff *),Bash(git log *),Bash(git status *),Bash(git commit *)"
```

### 4.4 Continuing Conversations in Print Mode

```bash
# First call — starts a session
claude -p "Review this codebase for performance issues"

# Continue the most recent session
claude -p "Now focus on the database queries" --continue

# Resume a specific session
session_id=$(claude -p "Start a review" --output-format json | jq -r '.session_id')
claude -p "Continue the review" --resume "$session_id"
```

### 4.5 System Prompt Customization

```bash
# Append to the default system prompt
gh pr diff "$1" | claude -p \
  --append-system-prompt "You are a security engineer. Review for vulnerabilities." \
  --output-format json

# Full system prompt replacement
claude -p "Review this code" \
  --system-prompt "You are a strict code reviewer focused only on security."
```

### 4.6 Other Useful Flags

| Flag | Description |
|---|---|
| `--max-turns N` | Limit agentic loop iterations |
| `--model MODEL` | Specify model |
| `--verbose` | Show full event stream |
| `--include-partial-messages` | Include streaming tokens |
| `--output-format json\|text\|stream-json` | Output format |
| `--json-schema SCHEMA` | Enforce a JSON output schema |
| `--allowedTools TOOLS` | Comma-separated list of allowed tools |
| `--disallowedTools TOOLS` | Tools to block |
| `--resume SESSION_ID` | Resume a specific session |
| `--continue` | Continue most recent session |

---

## Part 5: MCP Server Integration

### 5.1 What is MCP

The Model Context Protocol (MCP) is an open standard from Anthropic for connecting AI agents to external tools and data sources. An MCP server exposes a set of named tools. Claude calls these tools using the naming convention `mcp__<server-name>__<tool-name>`.

### 5.2 Transport Types

| Type | Config Key | Use Case |
|---|---|---|
| stdio (local process) | `command` + `args` | Locally installed packages (e.g., `npx @modelcontextprotocol/server-github`) |
| HTTP | `type: "http"` + `url` | Cloud-hosted REST endpoints |
| SSE | `type: "sse"` + `url` | Cloud-hosted streaming endpoints |
| SDK in-process | `createSdkMcpServer()` | Custom tools defined in your own application code |

### 5.3 Configuring MCP Servers Programmatically

**stdio server:**
```typescript
options: {
  mcpServers: {
    github: {
      command: "npx",
      args: ["-y", "@modelcontextprotocol/server-github"],
      env: { GITHUB_TOKEN: process.env.GITHUB_TOKEN }
    }
  },
  allowedTools: ["mcp__github__list_issues", "mcp__github__search_issues"]
}
```

**HTTP server:**
```typescript
options: {
  mcpServers: {
    "remote-api": {
      type: "http",
      url: "https://api.example.com/mcp",
      headers: {
        Authorization: `Bearer ${process.env.API_TOKEN}`
      }
    }
  },
  allowedTools: ["mcp__remote-api__*"]
}
```

**Wildcard permission** — allow all tools from a server:
```typescript
allowedTools: ["mcp__gmail__*"]
```

### 5.4 MCP Configuration Persistence

MCP servers can be configured at multiple scopes:

| Scope | Location | Persists | Shared |
|---|---|---|---|
| User (global) | `~/.claude.json` | Yes, all projects | No (machine-local) |
| Project | `.mcp.json` (repo root) | Yes | Yes (can commit to git) |
| Local (per-project override) | `~/.claude.json` | Yes | No |
| Programmatic | `options.mcpServers` | Only for that `query()` call | N/A |

**`.mcp.json` example (project-level):**
```json
{
  "mcpServers": {
    "filesystem": {
      "command": "npx",
      "args": ["-y", "@modelcontextprotocol/server-filesystem", "/Users/me/projects"]
    },
    "github": {
      "command": "npx",
      "args": ["-y", "@modelcontextprotocol/server-github"],
      "env": {
        "GITHUB_TOKEN": "${GITHUB_TOKEN}"
      }
    }
  }
}
```

**Settings to control which .mcp.json servers are active:**
```json
{
  "enableAllProjectMcpServers": true,
  "enabledMcpjsonServers": ["github", "filesystem"],
  "disabledMcpjsonServers": ["experimental-server"]
}
```

### 5.5 MCP Servers for Gmail

Several community implementations exist for Gmail via MCP:

**GongRzhe Gmail-MCP-Server** (Node.js, OAuth2):
- GitHub: `GongRzhe/Gmail-MCP-Server`
- Auto authentication support
- Credentials stored in `~/.gmail-mcp/` after first auth
- Requires Google Cloud Console project with Gmail API enabled

**jeremyjordan/mcp-gmail** (Python):
- Uses MCP Python SDK
- Full Gmail access via natural language

**Google Workspace MCP (taylorwilsdon)**:
- `taylorwilsdon/google_workspace_mcp`
- Covers Gmail, Calendar, Docs, Sheets, Slides, Drive, Chat, Forms, Tasks
- Comprehensive single-server solution for all Google Workspace needs

**Configuration in `.mcp.json`:**
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
    }
  }
}
```

**OAuth setup steps:**
1. Create a project in Google Cloud Console
2. Enable the Gmail API (and Calendar API if needed)
3. Create OAuth 2.0 credentials (Client ID + Client Secret)
4. On first run, a browser-based OAuth consent flow completes and saves tokens to `~/.gmail-mcp/`
5. Subsequent runs use the stored refresh token automatically

### 5.6 MCP Servers for Google Calendar

**nspady/google-calendar-mcp**:
- Multi-account support
- Multi-calendar support
- Event management, recurring events
- Free/busy queries and smart scheduling

**takumi0706/google-calendar-mcp**:
- Claude Desktop integration focused
- OAuth2 authentication

**ngs/google-mcp-server** (Homebrew installable):
- Covers Calendar, Drive, Gmail, Sheets, Docs, Slides
- Single server for full Google integration

**Composio Google Calendar integration**:
- `composio.dev/toolkits/googlecalendar/framework/claude-code`
- Managed OAuth, no manual credential setup
- Available as an MCP endpoint

### 5.7 Community MCP Servers for Monitoring and Task Management

| Server | Use Case |
|---|---|
| `@modelcontextprotocol/server-github` | GitHub issues, PRs, repositories |
| `@modelcontextprotocol/server-postgres` | Database queries |
| `@modelcontextprotocol/server-filesystem` | File system access |
| `Shrimp Task Manager` | Coding-focused task management with memory and dependency tracking |
| `Buildable MCP` | Software project task tracking and collaboration |
| `Opik-MCP` | LLM observability, traces, and monitoring data |
| `netops-mcp` | Network monitoring, system diagnostics, infrastructure management |
| `memory` (Anthropic reference server) | Persistent agent memory via knowledge graphs |

**Discovering MCP tools at runtime:**
```typescript
for await (const message of query({ prompt: "...", options })) {
  if (message.type === "system" && message.subtype === "init") {
    console.log("Available MCP tools:", message.mcp_servers);
  }
}
```

### 5.8 MCP Tool Search (Large Tool Sets)

When many MCP servers are connected, tool descriptions can consume significant context. MCP tool search addresses this:

```typescript
options: {
  env: {
    ENABLE_TOOL_SEARCH: "auto"    // activates when tools exceed 10% of context
    // or "auto:5"               // activate at 5% threshold
    // or "true"                 // always on
  }
}
```

Tool search requires Sonnet 4+ or Opus 4+. Haiku models do not support it.

---

## Part 6: Subagents and Multi-Agent Architecture

### 6.1 Defining Subagents Programmatically

The `agents` option lets you define specialized subagents inline:

```typescript
options: {
  agents: {
    "security-reviewer": {
      description: "Use for security vulnerability analysis",
      prompt: "You are a security engineer. Analyze code for vulnerabilities.",
      tools: ["Read", "Grep", "Glob"],
      model: "opus",
      maxTurns: 20
    },
    "test-writer": {
      description: "Use for writing unit tests",
      prompt: "You are an expert at writing comprehensive tests.",
      tools: ["Read", "Write", "Edit", "Bash"],
      mcpServers: ["github"]  // reference parent mcpServers by name
    }
  }
}
```

### 6.2 Agent Definition Fields

| Field | Required | Description |
|---|---|---|
| `description` | Yes | When the orchestrator should delegate to this agent |
| `prompt` | Yes | System prompt for the subagent |
| `tools` | No | Tool allowlist (inherits from parent if omitted) |
| `disallowedTools` | No | Tools to explicitly block |
| `model` | No | `"sonnet" \| "opus" \| "haiku" \| "inherit"` |
| `mcpServers` | No | MCP servers (string references to parent or inline configs) |
| `maxTurns` | No | Cap on API round-trips |

---

## Analysis

### Strengths for Automated Agent Builds

The Claude Agent SDK is architecturally well-suited for building a PIPA-style heartbeat/monitoring system:

**Session continuity** is first-class. Sessions persist to disk automatically, can be resumed by ID, and forked for branching workflows. This means a heartbeat agent that checks in on a project can maintain full context across daily runs without re-reading the entire codebase each time.

**Hook system granularity** is exceptional. The 17 distinct lifecycle events, combined with regex matchers and four handler types (command, HTTP, prompt, agent), allow very fine-grained observation and intervention. HTTP hooks are particularly valuable for a heartbeat system — they forward agent activity directly to an external monitoring endpoint without any glue code in the agent itself.

**MCP ecosystem maturity** is substantial. The Google Workspace family of MCP servers covers Gmail, Calendar, Drive, and more with OAuth2 support. The fact that these can be injected at `query()` call time (or loaded from a persistent `.mcp.json`) means an automated agent can send emails, create calendar events, or update task trackers as part of its normal tool calls.

**Headless mode completeness**: the `-p` flag supports JSON output, session resumption, tool auto-approval, and system prompt customization — everything needed for scripted invocations from cron jobs, CI pipelines, or orchestration systems.

### Limitations and Gotchas

**Breaking change in v0.1.0**: The default system prompt changed. Old code that relied on Claude Code's system prompt now gets a minimal prompt. Agents that used CLAUDE.md or settings.json instructions must explicitly opt in via `settingSources` and `systemPrompt: { type: 'preset', preset: 'claude_code' }`.

**MCP server persistence edge cases**: A GitHub issue (`#24657`) documents that `enabledMcpjsonServers` in `.claude/settings.local.json` does not always persist between sessions. The most reliable approach is to configure MCP servers either programmatically in each `query()` call, or in the `.mcp.json` project file combined with `enableAllProjectMcpServers: true` in settings.

**SessionStart / SessionEnd hooks are TypeScript-only**: Python SDK users cannot use these as SDK callbacks; they must use shell command hooks defined in settings files and then opt in with `setting_sources: ["project"]`.

**Async hooks cannot block**: Fire-and-forget hooks (returning `async: true`) cannot modify tool inputs or deny operations. For a heartbeat system, this is usually the right behavior (the heartbeat should not block the agent), but it means the monitoring endpoint must accept write-only events.

**OAuth complexity for Gmail/Calendar**: While several MCP servers exist for Google services, they all require an initial OAuth consent flow that is browser-based. This cannot be fully automated. The initial credential capture must be done manually once, after which the stored refresh token enables fully automated subsequent runs.

---

## Conclusions

The Claude Agent SDK (formerly Claude Code SDK) is a mature, production-grade framework for building automated agents. As of early 2026, it provides:

- A rich TypeScript/Python API centered on `query()` with over 30 configuration options
- Full session persistence and resumption by session ID
- A 17-event hook system with four handler types (command, HTTP, prompt, agent), fully programmable from TypeScript callbacks or settings JSON
- A headless CLI mode (`claude -p`) that supports structured JSON output and session resumption
- An MCP ecosystem with hundreds of community servers including multiple options for Gmail, Google Calendar, GitHub, databases, and monitoring tools
- In-process custom tool creation via `tool()` and `createSdkMcpServer()`
- Subagent definition and multi-agent orchestration via the `agents` option

For a heartbeat/monitoring system, the recommended architecture is:

1. Use `query()` with `resume` and persistent sessions for continuity
2. Register `PostToolUse` and `Stop` SDK hooks to fire HTTP heartbeat pings
3. Use `allowedTools` with specific patterns rather than `bypassPermissions` for safety
4. Connect Gmail/Calendar via the `taylorwilsdon/google_workspace_mcp` server (or equivalent) loaded from `.mcp.json`
5. Use `claude -p --output-format json` for scripted invocations from cron or CI

---

## Recommendations

1. **Migrate to `@anthropic-ai/claude-agent-sdk`** immediately. The old `@anthropic-ai/claude-code` npm package is deprecated. The migration requires only changing the import path and explicitly opting in to any filesystem settings.

2. **Use HTTP hooks for external monitoring integration**. They require no shell scripting, support environment variable interpolation for auth headers, and have configurable timeouts. They are the simplest path to connecting Claude agent activity to an external heartbeat system.

3. **Persist MCP servers in `.mcp.json`** rather than per-call configuration for services used in all sessions (Gmail, Calendar). Combine with `enableAllProjectMcpServers: true` in `.claude/settings.json` for automatic activation.

4. **Complete OAuth flows once and cache tokens**. For Gmail and Calendar MCP servers, run the initial OAuth consent flow manually once per machine, then automate everything thereafter. Store tokens in a secure location and reference them via environment variables.

5. **Monitor MCP connection status**. Check `message.mcp_servers` in the `system/init` message at the start of each query to detect failed MCP connections before the agent starts working.

6. **Evaluate the V2 TypeScript interface** for multi-turn agents. The `send()` / `stream()` pattern is simpler to reason about than async generators for conversational workflows with multiple back-and-forth exchanges.

---

## References

- [Agent SDK TypeScript Reference - platform.claude.com](https://platform.claude.com/docs/en/agent-sdk/typescript)
- [Agent SDK TypeScript V2 Preview - platform.claude.com](https://platform.claude.com/docs/en/agent-sdk/typescript-v2-preview)
- [Agent SDK Overview - platform.claude.com](https://platform.claude.com/docs/en/agent-sdk/overview)
- [Session Management - platform.claude.com](https://platform.claude.com/docs/en/agent-sdk/sessions)
- [MCP Integration - platform.claude.com](https://platform.claude.com/docs/en/agent-sdk/mcp)
- [SDK Hooks Guide - platform.claude.com](https://platform.claude.com/docs/en/agent-sdk/hooks)
- [SDK Permissions - platform.claude.com](https://platform.claude.com/docs/en/agent-sdk/permissions)
- [Migrate to Claude Agent SDK - platform.claude.com](https://platform.claude.com/docs/en/agent-sdk/migration-guide)
- [Hooks Reference - code.claude.com](https://code.claude.com/docs/en/hooks)
- [Run Claude Code Programmatically (CLI / Headless) - code.claude.com](https://code.claude.com/docs/en/headless)
- [Claude Code Settings - code.claude.com](https://code.claude.com/docs/en/settings)
- [@anthropic-ai/claude-agent-sdk - npm](https://www.npmjs.com/package/@anthropic-ai/claude-agent-sdk)
- [GitHub anthropics/claude-agent-sdk-typescript](https://github.com/anthropics/claude-agent-sdk-typescript)
- [Claude Code Hooks: A Practical Guide - DataCamp](https://www.datacamp.com/tutorial/claude-code-hooks)
- [What is the --print Flag in Claude Code - ClaudeLog](https://claudelog.com/faqs/what-is-print-flag-in-claude-code/)
- [Google Calendar MCP - nspady/google-calendar-mcp](https://github.com/nspady/google-calendar-mcp)
- [Google Workspace MCP - taylorwilsdon/google_workspace_mcp](https://github.com/taylorwilsdon/google_workspace_mcp)
- [Gmail-MCP-Server - GongRzhe/Gmail-MCP-Server](https://github.com/GongRzhe/Gmail-MCP-Server)
- [Awesome MCP Servers - punkpeye/awesome-mcp-servers](https://github.com/punkpeye/awesome-mcp-servers)
- [MCP Server Directory - mcpservers.org](https://mcpservers.org/)
- [Claude Code Hooks Multi-Agent Observability - disler/claude-code-hooks-multi-agent-observability](https://github.com/disler/claude-code-hooks-multi-agent-observability)
- [Claude Agent SDK Migration Guide - kane.mx](https://kane.mx/posts/2025/claude-agent-sdk-update/)

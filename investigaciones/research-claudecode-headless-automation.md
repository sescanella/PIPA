# Claude Code Headless Automation: Building an Always-On Agent

**Navigation:** This is a single-part report.

---

## Executive Summary

Claude Code (the CLI tool installed via `npm install -g @anthropic-ai/claude-code`) supports a robust headless, non-interactive execution mode via the `-p` / `--print` flag. This mode enables fully automated, unattended operation from shell scripts, cron jobs, launchd agents, and systemd timers — without ever requiring the interactive terminal UI.

The ecosystem around this capability has grown significantly. Anthropic has released a full Agent SDK (`@anthropic-ai/claude-agent-sdk`, formerly `@anthropic-ai/claude-code` used as a library), offering Python and TypeScript APIs for programmatic agent construction. The community has built schedulers, notification hooks, MCP integrations for Gmail and Google Calendar, and "always-on" patterns using macOS launchd — precisely the architecture needed for a 30-minute heartbeat system that checks email, tasks, and calendars, alerting a human only when action is required.

The key insight from this research: **the `-p` flag is not just a convenience shortcut; it is the official entry point to a production-grade automation interface**, with structured JSON output, session persistence via `--resume`, granular tool permissions via `--allowedTools`, and rich hooks that fire at every lifecycle point. This report maps everything a builder needs to go from zero to a working heartbeat agent.

---

## Introduction

The goal is to build a "heartbeat" system: a computer that is always on, running Claude Code from the terminal every 30 minutes to check emails, tasks, and calendars, and that only alerts the human when something needs attention. The constraint is to use the Claude Code CLI tool itself rather than the Anthropic API directly, avoiding direct `anthropic.messages.create()` calls in favor of the `claude` binary or the Agent SDK that wraps it.

This research investigates five interconnected questions:

1. What CLI flags enable non-interactive / headless execution?
2. How do cron, launchd (macOS), and systemd (Linux) connect to the `claude` binary?
3. What does the Agent SDK offer beyond the raw CLI for Node.js / Python scripts?
4. How does session persistence work between separate invocations?
5. What community projects already implement "always-on" Claude Code agents?

---

## Methodology

Research was conducted through targeted web searches and direct fetching of primary sources including official Anthropic documentation (`code.claude.com`, `platform.claude.com`), the npm package registry, GitHub repositories, Hacker News discussions, community blog posts, and tool documentation pages. Sources were cross-referenced to distinguish confirmed behavior from community speculation.

---

## Main Findings

### 1. Headless / Non-Interactive Mode

#### The `-p` / `--print` Flag

The single entry point to headless operation is the `-p` flag (long form `--print`). When passed, Claude Code:

- Disables the interactive TUI (terminal user interface)
- Accepts the prompt as a string argument or from stdin via pipe
- Writes output to stdout
- Exits with code `0` on success, non-zero on error

```bash
# Simplest possible headless invocation
claude -p "What does the auth module do?"

# Pipe a file into Claude
cat src/auth.py | claude -p "Find security issues in this file"

# Reference a file by path
claude -p "Review @src/api/auth.ts and suggest improvements"
```

The official documentation at `code.claude.com/docs/en/headless` notes: "The CLI was previously called 'headless mode.' The `-p` flag and all CLI options work the same way."

#### `--output-format` for Machine-Readable Output

Three output formats are available (requires Claude Code v1.0.33+):

| Format | Description | Use Case |
|---|---|---|
| `text` | Plain text (default) | Human-readable logs |
| `json` | Full JSON with `result`, `session_id`, `cost`, `duration_ms` | Parsing in scripts |
| `stream-json` | Newline-delimited JSON events as they arrive | Real-time streaming |

```bash
# Get JSON output and extract just the text result
claude -p "Summarize this project" --output-format json | jq -r '.result'

# Capture session ID for later resumption
SESSION=$(claude -p "Analyze the codebase" --output-format json | jq -r '.session_id')

# Stream tokens in real time
claude -p "Write a report" --output-format stream-json --verbose --include-partial-messages \
  | jq -rj 'select(.type == "stream_event" and .event.delta.type? == "text_delta") | .event.delta.text'
```

#### `--allowedTools` for Permission-Free Automated Operation

Rather than bypassing the entire permission system, `--allowedTools` pre-approves specific tools. This is the recommended approach for production automation:

```bash
# Allow reading files and running git commands only
claude -p "Review staged changes and commit" \
  --allowedTools "Bash(git diff *),Bash(git log *),Bash(git status *),Bash(git commit *)"

# Allow read-only operations for an audit agent
claude -p "Check emails and summarize urgent items" \
  --allowedTools "Read,Glob,Grep,mcp__gmail__*,mcp__calendar__*"

# Allow broader operations for a maintenance agent
claude -p "Run the test suite and fix failures" \
  --allowedTools "Bash,Read,Edit,Write"
```

The `Bash(git diff *)` syntax uses prefix matching: the trailing space before `*` is important. Without the space, `Bash(git diff*)` would also match `git diff-index`.

#### `--dangerously-skip-permissions` for Fully Unattended Execution

This flag bypasses all permission prompts entirely — file operations, shell commands, network access, everything. Anthropic's documentation explicitly states it is "intended only for Docker containers with no internet."

**Real-world incidents documented in the community:**
- A developer running Claude Code with this flag had it execute `rm -rf` starting from `/`, generating thousands of "Permission denied" errors for system paths.
- A Reddit incident involved Claude generating `rm -rf tests/ patches/ plan/ ~/` — the trailing `~/` expanded to the entire home directory, deleting files, Keychain passwords, and application data.

**For the heartbeat use case, `--allowedTools` is strongly preferred.** It limits Claude to only the MCP tools needed (Gmail, Calendar, task manager) without granting arbitrary shell access. Reserve `--dangerously-skip-permissions` for containerized, isolated environments.

#### `--max-turns` to Cap Iteration Depth

In headless mode, Claude Code performs up to 10 agent turns by default. The `--max-turns` flag overrides this:

```bash
# Limit to 3 agent turns (read emails, summarize, done)
claude -p "Check my inbox and summarize anything urgent" \
  --allowedTools "mcp__gmail__*" \
  --max-turns 5 \
  --output-format json
```

This caps both token consumption and execution time per run — important for a 30-minute heartbeat where you need the run to complete well before the next trigger.

#### System Prompt Customization

```bash
# Append instructions to the default system prompt
claude -p "Check my calendar for today" \
  --append-system-prompt "You are a personal assistant. Be concise. Only flag items needing human action. Output as JSON with fields: urgent_items, fyi_items, action_required (boolean)."

# Fully replace the system prompt
claude -p "Triage my inbox" \
  --system-prompt "You are an email triage assistant. Rules: never send emails, only draft. Flag emails from VIPs or deadlines as urgent. Everything else mark as informational."
```

---

### 2. Scheduling: cron, launchd, and systemd

#### The Core Challenge: Environment Variables in Scheduled Jobs

All three schedulers (cron, launchd, systemd) run in a minimal shell environment that does not inherit the user's `~/.zshrc` or `~/.bashrc`. This means `PATH`, `ANTHROPIC_API_KEY`, `NVM_DIR`, and other variables are typically absent.

**The solution:** Always use explicit `export` statements at the top of the wrapper script, or configure environment variables directly in the scheduler's configuration.

#### cron (Cross-Platform)

The `crontab -e` format uses five time fields: `minute hour day month weekday`.

```bash
# Every 30 minutes
*/30 * * * * /bin/zsh -l -c '/Users/yourname/scripts/claude-heartbeat.sh'
```

The `-l` flag on the shell invocation loads the login shell configuration, which helps with PATH. However, cron is notoriously unreliable on macOS (it requires explicit disk access grants and can be suspended by power management). **For macOS, launchd is strongly preferred.**

**Minimal wrapper script for cron:**

```bash
#!/bin/bash
# /Users/yourname/scripts/claude-heartbeat.sh
set -euo pipefail

# Explicit environment setup (cron has no user environment)
export PATH="/usr/local/bin:/usr/bin:/bin:/opt/homebrew/bin:$HOME/.local/bin"
export ANTHROPIC_API_KEY="$(security find-generic-password -a "$USER" -s "ANTHROPIC_API_KEY" -w)"

LOG_DIR="$HOME/logs/claude-heartbeat"
mkdir -p "$LOG_DIR"
LOG_FILE="$LOG_DIR/$(date +%Y%m%d-%H%M%S).log"

# Verify claude is available
which claude || { echo "claude not found in PATH" >> "$LOG_FILE"; exit 1; }

# Run the heartbeat
claude -p "Check my email, tasks, and calendar. Output JSON with urgent_items array and action_required boolean." \
  --allowedTools "mcp__gmail__*,mcp__calendar__*,mcp__tasks__*" \
  --output-format json \
  --max-turns 10 \
  >> "$LOG_FILE" 2>&1

echo "Completed at $(date)" >> "$LOG_FILE"
```

#### launchd (macOS — Recommended)

launchd is the macOS-native scheduler. It is more reliable than cron on macOS, handles network dependency, and persists across reboots. Save the plist to `~/Library/LaunchAgents/` (user-level agent, runs when the user is logged in).

**Plist for a 30-minute heartbeat:**

```xml
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN"
  "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key>
  <string>com.pipa.claude-heartbeat</string>

  <key>ProgramArguments</key>
  <array>
    <string>/bin/zsh</string>
    <string>-l</string>
    <string>-c</string>
    <string>/Users/yourname/scripts/claude-heartbeat.sh</string>
  </array>

  <!-- Run every 1800 seconds = 30 minutes -->
  <key>StartInterval</key>
  <integer>1800</integer>

  <!-- Or use StartCalendarInterval for specific times:
  <key>StartCalendarInterval</key>
  <array>
    <dict><key>Minute</key><integer>0</integer></dict>
    <dict><key>Minute</key><integer>30</integer></dict>
  </array>
  -->

  <key>StandardOutPath</key>
  <string>/Users/yourname/logs/claude-heartbeat/launchd-stdout.log</string>

  <key>StandardErrorPath</key>
  <string>/Users/yourname/logs/claude-heartbeat/launchd-stderr.log</string>

  <key>EnvironmentVariables</key>
  <dict>
    <key>PATH</key>
    <string>/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin</string>
    <key>HOME</key>
    <string>/Users/yourname</string>
  </dict>

  <!-- Restart if the script crashes -->
  <key>KeepAlive</key>
  <false/>

  <!-- Run even if on battery power -->
  <key>ProcessType</key>
  <string>Background</string>
</dict>
</plist>
```

**Load and manage the agent:**

```bash
# Load (enable) the agent
launchctl load ~/Library/LaunchAgents/com.pipa.claude-heartbeat.plist

# Verify it is loaded
launchctl list | grep pipa

# Trigger manually for testing
launchctl start com.pipa.claude-heartbeat

# Unload (disable)
launchctl unload ~/Library/LaunchAgents/com.pipa.claude-heartbeat.plist
```

**Important macOS permission notes:** The script process may need Full Disk Access granted in System Settings > Privacy & Security > Full Disk Access. Add the terminal application (Terminal.app or iTerm2) or the `zsh` binary.

#### systemd Timers (Linux)

On Linux, systemd timers are the modern equivalent of cron. Create two files: a service unit and a timer unit.

**Service unit** (`~/.config/systemd/user/claude-heartbeat.service`):

```ini
[Unit]
Description=Claude Code Heartbeat Agent
After=network-online.target

[Service]
Type=oneshot
ExecStart=/home/yourname/scripts/claude-heartbeat.sh
Environment="PATH=/usr/local/bin:/usr/bin:/bin:/home/yourname/.local/bin"
Environment="HOME=/home/yourname"
StandardOutput=append:/home/yourname/logs/claude-heartbeat.log
StandardError=append:/home/yourname/logs/claude-heartbeat-error.log
```

**Timer unit** (`~/.config/systemd/user/claude-heartbeat.timer`):

```ini
[Unit]
Description=Run Claude Code Heartbeat every 30 minutes

[Timer]
OnBootSec=5min
OnUnitActiveSec=30min
Persistent=true

[Install]
WantedBy=timers.target
```

**Enable and start:**

```bash
systemctl --user daemon-reload
systemctl --user enable claude-heartbeat.timer
systemctl --user start claude-heartbeat.timer
systemctl --user status claude-heartbeat.timer
```

---

### 3. The Claude Agent SDK

#### Overview and Naming

The `@anthropic-ai/claude-code` npm package used as a library has been superseded by the **Claude Agent SDK**, now available as:

- **TypeScript/Node.js:** `npm install @anthropic-ai/claude-agent-sdk`
- **Python:** `pip install claude-agent-sdk`

The SDK gives programmatic access to the same agent loop, tools, and context management that power the Claude Code CLI. It is appropriate when you need structured callbacks, streaming message objects, hooks, subagents, or MCP integration in code rather than shell scripts.

#### TypeScript Example: Basic Query

```typescript
import { query } from "@anthropic-ai/claude-agent-sdk";

async function runHeartbeat() {
  const results = {
    urgent_items: [] as string[],
    action_required: false,
    summary: ""
  };

  for await (const message of query({
    prompt: "Check email, tasks, and calendar. Identify anything needing human attention today.",
    options: {
      allowedTools: ["mcp__gmail__list_emails", "mcp__calendar__list_events", "mcp__tasks__list_tasks"],
      permissionMode: "bypassPermissions",
      mcpServers: {
        gmail: { command: "npx", args: ["@modelcontextprotocol/server-gmail"] },
        calendar: { command: "npx", args: ["@modelcontextprotocol/server-google-calendar"] }
      }
    }
  })) {
    if ("result" in message) {
      results.summary = message.result;
      // Parse result to check if action is required
      results.action_required = message.result.includes("ACTION REQUIRED");
    }
  }

  return results;
}

// Entry point
runHeartbeat().then(results => {
  if (results.action_required) {
    // Send macOS notification or push alert
    const { execSync } = require("child_process");
    execSync(`osascript -e 'display notification "${results.urgent_items[0]}" with title "PIPA Alert"'`);
  }
  console.log(JSON.stringify(results, null, 2));
});
```

#### Python Example: Async Query with Hooks

```python
import asyncio
import json
import subprocess
from datetime import datetime
from claude_agent_sdk import query, ClaudeAgentOptions, HookMatcher

async def log_tool_use(input_data, tool_use_id, context):
    """Log every tool call to an audit file."""
    tool_name = input_data.get("tool_name", "unknown")
    with open(f"{os.environ['HOME']}/logs/claude-audit.log", "a") as f:
        f.write(f"{datetime.now().isoformat()}: {tool_name}\n")
    return {}

async def run_heartbeat():
    result_text = ""

    async for message in query(
        prompt="""
        Check my email inbox, tasks, and calendar for today and tomorrow.

        Respond ONLY with valid JSON in this exact format:
        {
          "action_required": true or false,
          "urgent_items": ["item1", "item2"],
          "fyi_items": ["item1"],
          "summary": "one sentence summary"
        }

        Mark action_required=true only for: deadlines in <24h, messages from key contacts needing reply,
        blocked tasks, or calendar conflicts.
        """,
        options=ClaudeAgentOptions(
            allowed_tools=[
                "mcp__gmail__list_messages",
                "mcp__gmail__get_message",
                "mcp__calendar__list_events",
                "mcp__tasks__list_tasks"
            ],
            permission_mode="bypassPermissions",
            max_turns=15,
            mcp_servers={
                "gmail": {"command": "npx", "args": ["@modelcontextprotocol/server-gmail"]},
                "calendar": {"command": "npx", "args": ["google-calendar-mcp"]}
            },
            hooks={
                "PostToolUse": [
                    HookMatcher(matcher="mcp__.*", hooks=[log_tool_use])
                ]
            }
        )
    ):
        if hasattr(message, "result"):
            result_text = message.result

    return json.loads(result_text)

async def main():
    try:
        result = await run_heartbeat()

        if result.get("action_required"):
            # macOS native notification
            items = result.get("urgent_items", [])
            msg = items[0] if items else "Check PIPA agent output"
            subprocess.run([
                "osascript", "-e",
                f'display notification "{msg}" with title "PIPA Heartbeat" sound name "Ping"'
            ])

        # Save state for next run
        with open(f"{os.environ['HOME']}/.claude/heartbeat-last-run.json", "w") as f:
            json.dump({"timestamp": datetime.now().isoformat(), **result}, f, indent=2)

    except Exception as e:
        # Notify on error too
        subprocess.run([
            "osascript", "-e",
            f'display notification "Heartbeat error: {str(e)[:60]}" with title "PIPA Error" sound name "Basso"'
        ])
        raise

if __name__ == "__main__":
    asyncio.run(main())
```

#### SDK vs CLI: When to Use Which

| Scenario | CLI (`claude -p`) | Agent SDK |
|---|---|---|
| Simple check + output to log file | Preferred | Overkill |
| Need to parse structured JSON output | Both work | Slightly easier |
| Need hooks / callbacks during execution | Not available | Required |
| Need subagents for parallel work | Not available | Use SDK |
| Scripting in bash/zsh | Preferred | Not applicable |
| Need to react mid-stream to events | Not available | Required |
| Production automation with error handling | Works | More robust |

---

### 4. Session Persistence Between Runs

#### How Sessions Work

Every Claude Code invocation creates a session identified by a UUID. Session data — including the full conversation history and tool call results — is stored locally at `~/.claude/`. Each session retains up to 200,000 tokens of context (~150,000 words).

Sessions persist indefinitely on disk until manually cleared. A new invocation without session flags always starts a fresh session.

#### Continuing the Most Recent Session

```bash
# First run — starts a new session
claude -p "Read and analyze the codebase structure" --output-format json

# Immediately follow up — continues the same session
claude -p "Now focus specifically on the authentication module" --continue
```

The `--continue` flag (`-c`) resumes the most recent session regardless of when it occurred.

#### Resuming a Specific Session by ID

```bash
# Capture session ID from the first run
SESSION_ID=$(claude -p "Start analysis" --output-format json | jq -r '.session_id')
echo "$SESSION_ID" > ~/.claude/heartbeat-session.txt

# In a later run, resume that specific session
SAVED_SESSION=$(cat ~/.claude/heartbeat-session.txt)
claude -p "Continue from where we left off" --resume "$SAVED_SESSION" --output-format json
```

#### In the Agent SDK

```typescript
import { query } from "@anthropic-ai/claude-agent-sdk";
import { readFileSync, writeFileSync } from "fs";

async function runWithSessionPersistence(prompt: string) {
  const sessionFile = `${process.env.HOME}/.claude/heartbeat-session-id.txt`;

  let sessionId: string | undefined;
  try {
    sessionId = readFileSync(sessionFile, "utf8").trim();
  } catch { /* first run, no saved session */ }

  let newSessionId: string | undefined;

  for await (const message of query({
    prompt,
    options: {
      resume: sessionId,  // undefined = new session
      allowedTools: ["mcp__gmail__*", "mcp__calendar__*"]
    }
  })) {
    // Capture session ID from init message
    if (message.type === "system" && message.subtype === "init") {
      newSessionId = message.session_id;
    }
    if ("result" in message) {
      console.log(message.result);
    }
  }

  // Save session ID for next run
  if (newSessionId) {
    writeFileSync(sessionFile, newSessionId);
  }
}
```

#### Session Strategy for a Heartbeat Agent

For a heartbeat that runs every 30 minutes, **starting fresh each run is usually better** than resuming. Here is why:

- Each 30-minute run should be independent: "What needs attention right now?"
- Resuming a session means carrying context from 30 minutes ago, which consumes tokens without benefit
- The heartbeat's memory across runs should be stored in a file (e.g., `CLAUDE.md` or a JSON state file), not in the conversation session

**The exception:** If the heartbeat detects an urgent item and you want Claude to remember that context when you interact with it manually, capturing and persisting that session ID is useful. The human can then open Claude Code and `--resume` into the session that found the urgent item for full context.

---

### 5. Community Projects and Patterns

#### `runCLAUDErun` — Native macOS Scheduler App

A free, native macOS application that provides a GUI for scheduling Claude Code tasks. No cron knowledge required. Features include:

- Run tasks once, daily, weekly, or on custom intervals
- Background processing with task history logs
- Requires active Claude subscription and installed Claude Code
- Compatible with Apple Silicon and Intel Macs
- Download at: [runclauderun.com](https://runclauderun.com)

This is the fastest path to a working scheduler if you want to avoid manual plist/cron configuration.

#### `claude-code-scheduler` Plugin

A Claude Code plugin by `jshchnz` that adds scheduling capability directly inside Claude Code:

```
/plugin marketplace add jshchnz/claude-code-scheduler
/plugin install scheduler@claude-code-scheduler
```

Tasks are stored in `~/.claude/schedules.json` with cron expressions. When a task fires, it executes `claude -p "your prompt"` and optionally appends `--dangerously-skip-permissions` for autonomous tasks. Logs output to `~/.claude/logs/<task-id>.log`. Supports worktree isolation (creates a branch, commits, pushes, cleans up).

#### `claude-mcp-scheduler` (GitHub: `tonybentley/claude-mcp-scheduler`)

A Node.js project that combines cron scheduling with MCP server integration. Architecture:

1. `config/config.json` defines schedules (cron expressions, prompts, output paths)
2. On trigger, sends prompt to Claude via the Anthropic API with MCP context
3. MCP filesystem server provides Claude with restricted directory access
4. Results saved to configurable output paths

Note: This project uses the Anthropic API directly (not the Claude Code CLI), which differs from the heartbeat goal. However, it illustrates the MCP + cron pattern well.

#### Harper Reed's Email Triage System

A production setup using Claude Code + MCP servers for email management:

- **MCP servers:** Pipedream (Gmail + Google Calendar + Contacts), Toki (todo tracker), Chronicle (action logging), Pagen (CRM)
- **Skills directory:** `.claude/skills/email-management/` contains prompt templates
- **Key rule in `CLAUDE.md`:** "Always draft, never send. Match writing voice — ultra-concise, casual, no signatures."
- **Plugin:** Available as `harperreed/office-admin-claude` in the marketplace

This is the closest existing example to the PIPA heartbeat goal.

#### The "Always-On" Relay Architecture (godagoo)

A more complex architecture using Claude Code as the backend intelligence in a Telegram bot:

- **Flow:** Telegram → Bun relay (grammy framework) → `claude -p "[prompt]" --output-format json --allowedTools "..."` → response
- **Memory:** Supabase PostgreSQL + pgvector for semantic search over 4,000+ messages
- **Deployment:** launchd daemon for 24/7 macOS operation
- **Cost:** ~$200/month using Claude Max 20x subscription (fixed, not per-token)

#### The `continuous-claude` Loop Pattern

From Anand Chowdhary's blog, a continuous while-loop with external memory:

```bash
while true; do
  claude --dangerously-skip-permissions \
    "Read TASKS.md for context from the previous iteration.
    Make meaningful progress on one thing.
    Update TASKS.md with what you did and what the next iteration should focus on.
    Think of it as a relay race — pass the baton clearly."
  sleep 1
done
```

**The key insight:** Use a markdown file (`TASKS.md`, `CONTEXT.md`, `HEARTBEAT_STATE.md`) as external memory between iterations. This decouples state from session context and survives restarts.

#### The Ralph Loop Pattern

A stop-hook-based loop that prevents premature exit:

```json
{
  "hooks": {
    "Stop": [
      {
        "hooks": [
          {
            "type": "prompt",
            "prompt": "Check if all requested tasks are complete. If not, respond with {\"ok\": false, \"reason\": \"what remains to be done\"}."
          }
        ]
      }
    ]
  }
}
```

With `--max-iterations 20` to prevent infinite loops. This is useful for ensuring the heartbeat agent fully completes its triage before exiting.

---

### 6. Authentication for Automated Runs

#### The Subscription vs. API Key Choice

This is a **critical consideration** for the heartbeat use case. Claude Code supports two authentication paths:

| Method | Works Headless? | Cost Model | Reliability |
|---|---|---|---|
| `ANTHROPIC_API_KEY` | Yes, always | Per-token (pay-as-you-go) | Fully reliable |
| Claude Pro/Max subscription (OAuth) | Mostly, with caveats | Flat monthly rate | OAuth tokens expire |

**The critical caveat:** If `ANTHROPIC_API_KEY` is set as an environment variable, Claude Code uses it and charges per token, ignoring the subscription. For the heartbeat use case running every 30 minutes, the API key approach is cleaner and more predictable.

#### OAuth Token Issues in Long-Running Automation

The community has documented that OAuth tokens (used when running via subscription) expire after 8-12 hours and are not refreshed in non-interactive headless mode. This causes 401 errors in automation after the first day.

**Workaround: `claude setup-token`**

Anthropic added `claude setup-token` to generate a 1-year long-lived subscription token for automated use:

```bash
# Run once interactively to generate the long-lived token
claude setup-token
# Follow prompts, token is stored in ~/.claude/.credentials and macOS Keychain
```

After this, subsequent headless runs using the subscription will use the long-lived token. This is the recommended approach when using a Max subscription for automation (to avoid per-token API charges).

**Important note (early 2026):** Anthropic restricted third-party tools from using OAuth tokens, implementing client fingerprinting. The official `claude` CLI binary continues to work with `setup-token`. Third-party scripts trying to forge Claude Code sessions no longer work.

#### The `apiKeyHelper` Setting

For dynamic API key rotation or fetching from a secrets manager:

```json
// ~/.claude/settings.json
{
  "apiKeyHelper": "/path/to/get-api-key.sh"
}
```

The script must print the API key to stdout. Claude Code calls it every 5 minutes by default, or on a 401 response. Set `CLAUDE_CODE_API_KEY_HELPER_TTL_MS` for a custom refresh interval.

#### Credentials Storage

On macOS, credentials are stored in the encrypted macOS Keychain. The credential file is at `~/.claude/.credentials`. Scheduled jobs running under the same user account have access to Keychain items if the Keychain is unlocked (which it is after login in standard setups).

---

### 7. macOS Notifications for Human Alerting

The heartbeat's core value is "only alert when action is required." Claude Code's hooks system provides the notification infrastructure.

#### Simple osascript Hook (No Dependencies)

```json
// ~/.claude/settings.json
{
  "hooks": {
    "Stop": [
      {
        "matcher": "",
        "hooks": [
          {
            "type": "command",
            "command": "jq -r '.last_assistant_message' | grep -q 'ACTION REQUIRED' && osascript -e 'display notification \"Check PIPA — action required\" with title \"PIPA Heartbeat\" sound name \"Ping\"' || true"
          }
        ]
      }
    ]
  }
}
```

#### Script-Based Conditional Notification

A more robust approach using a dedicated script at `~/.claude/hooks/heartbeat-notify.sh`:

```bash
#!/bin/bash
# Read hook data from stdin
INPUT=$(cat)

# Extract the assistant's last message
LAST_MSG=$(echo "$INPUT" | jq -r '.last_assistant_message // ""')

# Check if action is required (Claude should output "ACTION_REQUIRED" in its response)
if echo "$LAST_MSG" | grep -q "ACTION_REQUIRED"; then
    # Extract the first urgent item for the notification body
    URGENT=$(echo "$LAST_MSG" | grep -o '"[^"]*"' | head -1 | tr -d '"')

    osascript -e "display notification \"$URGENT\" with title \"PIPA Heartbeat\" subtitle \"Action Required\" sound name \"Ping\""

    # Optional: also log to a file
    echo "$(date): ACTION REQUIRED — $URGENT" >> "$HOME/logs/pipa-alerts.log"
fi

exit 0
```

Register the hook:

```json
{
  "hooks": {
    "Stop": [
      {
        "matcher": "",
        "hooks": [
          {
            "type": "command",
            "command": "bash ~/.claude/hooks/heartbeat-notify.sh"
          }
        ]
      }
    ]
  }
}
```

Make it executable: `chmod +x ~/.claude/hooks/heartbeat-notify.sh`

**Note:** `PermissionRequest` hooks do not fire in non-interactive mode (`-p`). Use `PreToolUse` hooks for automated permission decisions in headless runs.

#### MCP Servers for Gmail and Google Calendar

Multiple community MCP servers provide Claude access to Google Workspace:

| Server | Source | Capabilities |
|---|---|---|
| `google-calendar-mcp` | github.com/nspady/google-calendar-mcp | List events, create, update, delete, free/busy queries |
| Composio Google Calendar | composio.dev | Events, meeting scheduling, calendar management |
| Pipedream GSuite | playbooks.com/mcp | Gmail + Calendar + Drive + Contacts |
| Google Workspace MCP | Community | Full Workspace integration |

**Configuration in `~/.mcp.json`:**

```json
{
  "mcpServers": {
    "gmail": {
      "command": "node",
      "args": ["/path/to/gmail-mcp-server/index.js"],
      "env": {
        "GMAIL_CREDENTIALS": "/path/to/credentials.json"
      }
    },
    "calendar": {
      "command": "npx",
      "args": ["google-calendar-mcp"],
      "env": {
        "GOOGLE_CALENDAR_CREDENTIALS": "/path/to/calendar-credentials.json"
      }
    }
  }
}
```

---

## Analysis

### The Architecture Is Sound

The technical foundation for a 30-minute heartbeat agent is entirely validated. Every required primitive exists and is documented:

- **The trigger mechanism** (launchd with `StartInterval: 1800`) is a standard macOS pattern working since macOS 10.4
- **The execution mechanism** (`claude -p "..." --allowedTools "mcp__gmail__*,mcp__calendar__*" --output-format json`) is Anthropic's official interface for automation
- **The notification mechanism** (Stop hook + `osascript`) is well-documented with multiple community implementations
- **The data access layer** (MCP servers for Gmail, Calendar, tasks) has mature community implementations

### The Key Design Decisions

**1. Fresh session per run vs. session continuity**

For a 30-minute heartbeat, starting fresh is correct. The stateful memory should live in a file (`~/.claude/heartbeat-state.json` or `CLAUDE.md`), not in session context. Sessions are expensive in tokens and the context from 30 minutes ago is rarely relevant to the current check.

**2. Subscription vs. API key for cost**

At 30-minute intervals (48 runs/day), a Max subscription ($100/month) is almost certainly cheaper than pay-as-you-go API charges, assuming each run uses a moderate amount of tokens (email reading + calendar queries + response). The subscription also provides predictable costs. Use `claude setup-token` to make the subscription work reliably in headless mode.

**3. `--allowedTools` scope**

The heartbeat agent should be granted only the tools it needs: MCP tools for Gmail, Calendar, and task management. It should NOT have `Bash` or file-write access unless specifically needed. This limits the blast radius of any unexpected Claude behavior.

**4. Output format discipline**

Instructing Claude to respond in a specific JSON format (with `action_required: boolean` and `urgent_items: string[]`) makes the notification logic simple and reliable. Combine with `--output-format json` to get the full metadata envelope, then parse `result` for the structured response.

### Known Risks and Mitigations

| Risk | Mitigation |
|---|---|
| OAuth token expiry after 8-12 hours | Use `claude setup-token` for 1-year token |
| Claude exceeds expected token budget | Use `--max-turns` to cap iterations |
| PATH not found in scheduled context | Hardcode PATH in wrapper script |
| Stop hook fires and blocks exit | Check `stop_hook_active` in hook script |
| MCP server fails to start | Add error handling in wrapper; check logs |
| `~/.zshrc` echos pollute JSON output | Wrap echo statements in `if [[ $- == *i* ]]` |

---

## Conclusions

1. Claude Code's `-p` / `--print` flag is a fully supported, production-ready interface for unattended automation. It is not a hack or workaround — it is the officially documented headless mode.

2. The Claude Agent SDK (`@anthropic-ai/claude-agent-sdk`) extends the CLI's capabilities with native TypeScript/Python APIs, hooks, subagents, and streaming — appropriate when the automation logic is complex enough to warrant code over shell scripts.

3. On macOS, launchd is the correct scheduler for a 30-minute heartbeat. It is more reliable than cron, handles the user environment better, and integrates with macOS power management.

4. Session persistence is available (`--continue`, `--resume`, `resume` option in SDK) but is generally not the right choice for a periodic heartbeat. File-based external memory (`CLAUDE.md`, JSON state files) is the better pattern.

5. A community ecosystem of notification hooks, scheduler plugins, and MCP server integrations exists, making it unnecessary to build every component from scratch.

6. The `--allowedTools` flag, combined with MCP servers scoped to specific services (Gmail, Calendar, tasks), provides the right security model: Claude can access the data it needs without being granted arbitrary system access.

---

## Recommendations

### Immediate Next Steps for PIPA Heartbeat

**Step 1: Authentication setup**

```bash
# If using Max subscription (recommended for flat cost)
claude setup-token
# If using API key (simpler, per-token cost)
export ANTHROPIC_API_KEY="sk-ant-..."
```

**Step 2: Install and configure MCP servers**

```bash
npm install -g google-calendar-mcp
# Configure OAuth credentials per server docs
# Add to ~/.mcp.json
```

**Step 3: Write the heartbeat prompt**

Create `~/.claude/heartbeat-prompt.md`:

```markdown
Check my Gmail inbox (last 4 hours), Google Calendar (today and tomorrow), and task list.

Respond with ONLY valid JSON in this exact format:
{
  "action_required": true/false,
  "urgent_items": ["item description 1", "item description 2"],
  "fyi_items": ["informational item 1"],
  "summary": "One sentence overview",
  "checked_at": "ISO timestamp"
}

Mark action_required=true ONLY for:
- Email from [list key contacts] requiring reply in <24h
- Calendar conflict or missing prep for meeting in <2h
- Task with deadline today that is not done
- Any blocking issue on current project

Everything else is FYI or can wait.
```

**Step 4: Create the wrapper script**

```bash
#!/bin/zsh
# ~/.claude/scripts/heartbeat.sh
export PATH="/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin"
export HOME="/Users/yourname"

LOG="$HOME/logs/pipa/$(date +%Y%m%d-%H%M%S).json"
mkdir -p "$(dirname "$LOG")"

PROMPT=$(cat "$HOME/.claude/heartbeat-prompt.md")

claude -p "$PROMPT" \
  --allowedTools "mcp__gmail__*,mcp__calendar__*,mcp__tasks__*" \
  --output-format json \
  --max-turns 10 \
  --output-format json \
  > "$LOG" 2>&1

# Check result and notify if needed
RESULT=$(jq -r '.result' "$LOG" 2>/dev/null || echo '{}')
ACTION=$(echo "$RESULT" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('action_required','false'))" 2>/dev/null || echo "false")

if [ "$ACTION" = "True" ] || [ "$ACTION" = "true" ]; then
  ITEM=$(echo "$RESULT" | python3 -c "import sys,json; d=json.load(sys.stdin); items=d.get('urgent_items',[]); print(items[0] if items else 'Check logs')" 2>/dev/null)
  osascript -e "display notification \"$ITEM\" with title \"PIPA Alert\" sound name \"Ping\""
fi
```

**Step 5: Install the launchd agent**

Save the plist from Section 2 (launchd) to `~/Library/LaunchAgents/com.pipa.claude-heartbeat.plist`, update paths, then:

```bash
launchctl load ~/Library/LaunchAgents/com.pipa.claude-heartbeat.plist
launchctl start com.pipa.claude-heartbeat  # test immediately
```

**Step 6: Verify with logs**

```bash
tail -f ~/logs/pipa/*.json | jq '.'
```

---

## References

- [Run Claude Code programmatically — Official Docs](https://code.claude.com/docs/en/headless)
- [Agent SDK Overview — Official Docs](https://platform.claude.com/docs/en/agent-sdk/overview)
- [Agent SDK TypeScript Reference](https://platform.claude.com/docs/en/agent-sdk/typescript)
- [Agent SDK Session Management](https://platform.claude.com/docs/en/agent-sdk/sessions)
- [Automate workflows with hooks — Official Docs](https://code.claude.com/docs/en/hooks-guide)
- [Claude Code Authentication — Official Docs](https://code.claude.com/docs/en/authentication)
- [claude --dangerously-skip-permissions Guide (ksred.com)](https://www.ksred.com/claude-code-dangerously-skip-permissions-when-to-use-it-and-when-you-absolutely-shouldnt/)
- [Claude Code + Cron Automation Guide (SmartScope)](https://smartscope.blog/en/generative-ai/claude/claude-code-cron-schedule-automation-complete-guide-2025/)
- [Building Automated Claude Code Workers with Cron and MCP (blle.co)](https://www.blle.co/blog/automated-claude-code-workers)
- [Scheduled Autonomous Claude Agents using launchd — Hacker News](https://news.ycombinator.com/item?id=47118300)
- [Getting Claude Code to do my emails — Harper Reed](https://harper.blog/2025/12/03/claude-code-email-productivity-mcp-agents/)
- [Claude Code Always-On Architecture (godagoo)](https://godagoo.github.io/claude-code-always-on/)
- [runCLAUDErun — macOS Scheduler App](https://runclauderun.com)
- [claude-code-scheduler Plugin (GitHub)](https://github.com/jshchnz/claude-code-scheduler)
- [claude-mcp-scheduler (GitHub)](https://github.com/tonybentley/claude-mcp-scheduler)
- [Running Claude Code in a Loop — Anand Chowdhary](https://anandchowdhary.com/blog/2025/running-claude-code-in-a-loop)
- [Claude Code Notifications with terminal-notifier (Andrea Grandi)](https://www.andreagrandi.it/posts/using-terminal-notifier-claude-code-custom-notifications/)
- [macOS Setup Guide for Claude Automation Hub (GitHub Gist)](https://gist.github.com/jack-arturo/6b010a3ed6a3d1e53a8c1216abf92e7f)
- [Long-lived Claude Token Script (GitHub Gist)](https://gist.github.com/matthewevans/a1d8b49a02f56aa2d866cc2044af1990)
- [Claude Code CLI Environment Variables (GitHub Gist)](https://gist.github.com/unkn0wncode/f87295d055dd0f0e8082358a0b5cc467)
- [OAuth token expiration issue — Auto-Claude GitHub](https://github.com/AndyMik90/Auto-Claude/issues/1518)
- [OAuth token refresh fails in headless mode — anthropics/claude-code GitHub](https://github.com/anthropics/claude-code/issues/28827)
- [google-calendar-mcp (GitHub)](https://github.com/nspady/google-calendar-mcp)
- [claude-agent-sdk-typescript (GitHub)](https://github.com/anthropics/claude-agent-sdk-typescript)
- [claude-agent-sdk-python (GitHub)](https://github.com/anthropics/claude-agent-sdk-python)
- [Claude Code: A Simple Loop — Medium](https://medium.com/@aiforhuman/claude-code-a-simple-loop-that-produces-high-agency-814c071b455d)
- [CI/CD and Headless Mode — Angelo Lima](https://angelo-lima.fr/en/claude-code-cicd-headless-en/)
- [Headless Mode Cheatsheet — SFEIR Institute](https://institute.sfeir.com/en/claude-code/claude-code-headless-mode-and-ci-cd/cheatsheet/)
- [What is --max-turns in Claude Code (ClaudeLog)](https://claudelog.com/mechanics/dangerous-skip-permissions/)
- [anthropic-ai/claude-agent-sdk npm](https://www.npmjs.com/package/@anthropic-ai/claude-agent-sdk)

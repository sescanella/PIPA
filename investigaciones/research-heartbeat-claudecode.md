# Heartbeat System Architecture Using Claude Code CLI

**Research Date:** February 27, 2026
**Scope:** Architecture, implementation patterns, cost analysis, and security for a scheduled autonomous Claude Code agent running on a dedicated Mac Mini

---

## Executive Summary

A Claude Code CLI-based heartbeat system is technically viable and well-supported by the platform's current feature set. The core pattern — a scheduled process invoking `claude -p` in headless mode every 30 minutes, reading a checklist file, querying external services via MCP, and conditionally sending alerts — maps cleanly onto documented Claude Code capabilities.

The principal tradeoffs to understand before building are: (1) Claude Code's subscription plans (Pro/Max) effectively cap token spend at a flat monthly fee and may be more economical than raw API access for frequent scheduled runs; (2) headless sessions do not carry context between invocations by default, which is intentional and beneficial for a heartbeat pattern since each run should be self-contained; (3) macOS `launchd` is strictly superior to `cron` for this use case because it handles sleep/wake cycles correctly and integrates with the Keychain.

The estimated cost for a well-optimized heartbeat — fresh session, focused prompt, MCP tool calls, short output — runs approximately $0.02–$0.06 per invocation with pay-as-you-go API billing, translating to roughly $30–$90 per month at 48 runs per day. A Claude Max plan at $100/month often undercuts this for single-user deployments.

---

## Introduction

The heartbeat concept borrows from infrastructure monitoring: a background process that wakes at regular intervals, checks the health of a system, and raises an alert only when something requires human attention. Applied to personal productivity and task management, the "system" being monitored is not a server but a person's inbox, calendar, and task queue.

The proposed implementation uses a Mac Mini as the always-on host, the Claude Code CLI (`claude`) as the AI reasoning engine, and a curated set of MCP servers to connect Claude to Gmail, Google Calendar, and task management tools. A `HEARTBEAT.md` file acts as the living checklist — the source of truth for what Claude should check and what constitutes an alert condition.

This research addresses six architectural domains: session management, repository structure, automation script design, cost modeling, security hardening, and alert delivery mechanisms.

---

## Methodology

Research was conducted via targeted web searches against official Anthropic documentation, community GitHub repositories, independent developer blogs, and pricing comparison analyses published between late 2025 and February 2026. All findings were cross-referenced against the official Claude Code documentation at `code.claude.com/docs`. Where community findings conflicted with documentation, the official source was prioritized and the discrepancy noted.

---

## Main Findings

### 1. Session Management

#### 1.1 Headless Mode Is the Correct Paradigm

Claude Code's `--print` (or `-p`) flag is the official mechanism for non-interactive automation. It disables the conversational interface, sends the response to stdout, then terminates. This is the fundamental entry point for any scheduled automation.

```bash
claude -p "Check HEARTBEAT.md and report status" \
  --output-format json \
  --allowedTools "Read,Bash,mcp__gmail__list_emails,mcp__calendar__list_events"
```

The `--output-format` flag supports three modes:
- `text` — plain human-readable output (default)
- `json` — structured JSON suitable for `jq` parsing
- `stream-json` — streaming JSON tokens for real-time processing

For a heartbeat system, `json` is the recommended format because the orchestration script needs to parse the result and branch on `HEARTBEAT_OK` vs. an alert condition.

#### 1.2 Fresh Sessions vs. Resumed Sessions

Claude Code supports session resumption via `--continue` (most recent session in directory) and `--resume` (named session or picker). Full context — message history, tool calls, and results — is restored.

However, for a heartbeat pattern, **fresh sessions are strongly preferred over resumed sessions** for the following reasons:

- Each heartbeat is a discrete, idempotent check. Carrying forward context from 30 minutes ago adds tokens without adding value.
- Accumulated context grows the input token cost with each run. A 10-turn session costs significantly more than 10 single-turn sessions.
- A stale resumed context may cause Claude to anchor on outdated information.
- The headless session lifetime is 15 minutes by default, making resume across 30-minute intervals unreliable without explicit management.

The correct model: **each heartbeat invocation is a stateless, fresh session**. State that must persist (last alert sent, dedup hashes, previously seen email IDs) is stored in files on disk, not in the Claude session.

#### 1.3 Multi-Turn Headless Sessions

If a heartbeat scenario genuinely requires multi-turn interaction (e.g., first query Gmail, then conditionally query Calendar based on the result), Claude Code supports this via the `--max-turns` flag:

```bash
claude -p "Initial prompt" --max-turns 5 --output-format stream-json
```

Limit multi-turn depth aggressively. Each additional turn multiplies the input token cost by carrying the full conversation history forward.

---

### 2. Repository Structure

A well-organized repository separates concerns cleanly: instructions for Claude, state managed by the orchestration script, logs, and configuration.

```
heartbeat/
├── HEARTBEAT.md              # Claude's checklist (version controlled)
├── CLAUDE.md                 # Project-level system prompt for Claude
├── config/
│   ├── mcp-servers.json      # MCP server configuration
│   ├── active-hours.json     # When the heartbeat is active
│   └── alert-thresholds.json # What constitutes alert-worthy conditions
├── scripts/
│   ├── heartbeat-runner.sh   # Main orchestration script
│   ├── send-alert.sh         # Alert delivery (Pushover, email, etc.)
│   └── prune-logs.sh         # Log rotation
├── state/
│   ├── last-run.json         # Timestamp and result of last run
│   ├── alert-hashes.json     # SHA hashes of alerts already sent (dedup)
│   └── email-watermark.json  # Last-seen Gmail message ID (pagination anchor)
├── logs/
│   ├── heartbeat-YYYY-MM-DD.log   # Daily log files
│   └── alerts-YYYY-MM-DD.log      # Alert-specific log
└── com.heartbeat.claude.plist     # launchd agent plist
```

#### 2.1 HEARTBEAT.md Design

The checklist file is read by Claude at the start of each run. Keep it precise and structured. Claude performs best when instructions are explicit and avoid ambiguity.

```markdown
# HEARTBEAT CHECKLIST

## Identity
You are a silent monitoring agent. Your job is to check the items below
and output EXACTLY one of two things:
- The string "HEARTBEAT_OK" if nothing requires attention.
- A structured alert block if any item requires attention.

## Rules
- Do not explain your reasoning unless generating an alert.
- An alert is only warranted if action is required TODAY.
- Deduplicate: check state/alert-hashes.json before sending any alert.

## Checks

### 1. Email (Gmail)
- Retrieve unread emails from the last 60 minutes.
- Flag if any email is from a VIP sender (see config/alert-thresholds.json).
- Flag if any email contains the words: "urgent", "ASAP", "deadline today".

### 2. Calendar
- Check events in the next 90 minutes.
- Flag if any event has no video conference link and is scheduled with
  external participants.
- Flag if a meeting starts within 15 minutes.

### 3. Tasks
- Check Notion for tasks marked "Today" with status "Not Started".
- Flag if any task is overdue by more than 1 day.

## Output Format for Alerts
```json
{
  "status": "ALERT",
  "alerts": [
    {
      "type": "email|calendar|task",
      "priority": "high|medium",
      "summary": "one line description",
      "action": "what the human should do"
    }
  ]
}
```
```

#### 2.2 CLAUDE.md Design

The `CLAUDE.md` file at the project root provides persistent context to Claude without being part of the checklist prompt. Keep it minimal.

```markdown
# Heartbeat Agent Context

This project directory is a monitoring agent. You have read-only access
to state/ and config/ files. Do not write to any file unless explicitly
instructed. Do not use web search. Do not execute shell commands
unless they are in the approved list in config/mcp-servers.json.
```

#### 2.3 State File Design

The `state/alert-hashes.json` file prevents duplicate alerts. The orchestration script — not Claude — is responsible for writing to this file after a successful alert delivery.

```json
{
  "sent_alerts": [
    {
      "hash": "sha256:abc123...",
      "type": "email",
      "sent_at": "2026-02-27T14:00:00Z",
      "expires_at": "2026-02-28T14:00:00Z"
    }
  ]
}
```

Expire hashes after 24 hours to prevent indefinite accumulation. The hash should be computed over the unique identifier of the alert source (e.g., Gmail message ID, Calendar event ID), not over the alert text, which may vary.

---

### 3. Automation Script Design

#### 3.1 The Orchestration Shell Script

The main runner script handles: active hours enforcement, invoking Claude, parsing output, deduplication, and alert delivery.

```bash
#!/bin/bash
# heartbeat-runner.sh

set -euo pipefail

REPO_DIR="/Users/yourname/heartbeat"
LOG_FILE="$REPO_DIR/logs/heartbeat-$(date +%Y-%m-%d).log"
STATE_FILE="$REPO_DIR/state/last-run.json"
CLAUDE_BIN="/usr/local/bin/claude"

log() {
  echo "[$(date -u +%Y-%m-%dT%H:%M:%SZ)] $*" | tee -a "$LOG_FILE"
}

# --- Active Hours Enforcement ---
CURRENT_HOUR=$(date +%H)
if [[ "$CURRENT_HOUR" -lt 7 || "$CURRENT_HOUR" -ge 23 ]]; then
  log "Outside active hours. Skipping."
  exit 0
fi

# --- Run Heartbeat ---
log "Starting heartbeat run..."

RESULT=$("$CLAUDE_BIN" \
  --print "$(cat "$REPO_DIR/HEARTBEAT.md")" \
  --output-format json \
  --max-turns 3 \
  --allowedTools "Read,mcp__gmail__list_emails,mcp__gmail__get_email,mcp__calendar__list_events,mcp__notion__query_database" \
  --disallowedTools "Bash,Write,Edit" \
  2>>"$LOG_FILE") || {
    log "ERROR: Claude invocation failed with exit code $?"
    exit 1
  }

STATUS=$(echo "$RESULT" | jq -r '.result // "HEARTBEAT_OK"' 2>/dev/null || echo "$RESULT")

# --- Update State ---
echo "{\"last_run\": \"$(date -u +%Y-%m-%dT%H:%M:%SZ)\", \"status\": \"$STATUS\"}" \
  > "$STATE_FILE"

# --- Branch on Result ---
if echo "$STATUS" | grep -q "HEARTBEAT_OK"; then
  log "Status: OK. No action required."
else
  log "Status: ALERT. Dispatching notification..."
  echo "$STATUS" | "$REPO_DIR/scripts/send-alert.sh"
fi
```

#### 3.2 Error Handling and Retry Logic

The script above uses `set -euo pipefail` which causes it to exit on any error. For a monitoring system, silent failure is worse than noisy failure — the launchd configuration should email or log failures through a separate channel.

For transient API errors, implement exponential backoff in a wrapper:

```bash
run_with_retry() {
  local max_attempts=3
  local delay=10
  local attempt=1

  while [[ $attempt -le $max_attempts ]]; do
    if "$@"; then
      return 0
    fi
    log "Attempt $attempt failed. Retrying in ${delay}s..."
    sleep "$delay"
    delay=$((delay * 2))
    attempt=$((attempt + 1))
  done

  log "All $max_attempts attempts failed."
  return 1
}
```

#### 3.3 launchd Configuration (macOS)

`launchd` is the correct scheduler for macOS — it handles system sleep/wake cycles that cron does not. Use `StartCalendarInterval` rather than `StartInterval` to run at predictable clock times (e.g., :00 and :30 of every hour).

```xml
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN"
  "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key>
  <string>com.heartbeat.claude</string>

  <key>ProgramArguments</key>
  <array>
    <string>/bin/bash</string>
    <string>/Users/yourname/heartbeat/scripts/heartbeat-runner.sh</string>
  </array>

  <key>StartCalendarInterval</key>
  <array>
    <dict><key>Minute</key><integer>0</integer></dict>
    <dict><key>Minute</key><integer>30</integer></dict>
  </array>

  <key>EnvironmentVariables</key>
  <dict>
    <key>ANTHROPIC_API_KEY</key>
    <string>loaded-from-keychain-at-runtime</string>
    <key>PATH</key>
    <string>/usr/local/bin:/usr/bin:/bin</string>
  </dict>

  <key>StandardOutPath</key>
  <string>/Users/yourname/heartbeat/logs/launchd-stdout.log</string>

  <key>StandardErrorPath</key>
  <string>/Users/yourname/heartbeat/logs/launchd-stderr.log</string>

  <key>RunAtLoad</key>
  <false/>
</dict>
</plist>
```

Install via:
```bash
cp com.heartbeat.claude.plist ~/Library/LaunchAgents/
launchctl load ~/Library/LaunchAgents/com.heartbeat.claude.plist
```

**Critical note on SSH and Keychain:** Claude Code stores OAuth tokens in the macOS Keychain. When running via launchd or SSH, Keychain access may fail unless the Keychain is unlocked. The documented workaround is:

```bash
security unlock-keychain -p "$KEYCHAIN_PASSWORD" ~/Library/Keychains/login.keychain-db
```

However, hardcoding the Keychain password in a plist is insecure. The better approach (see Section 5) is to use `ANTHROPIC_API_KEY` as an environment variable from a secrets file rather than relying on Keychain-stored OAuth.

#### 3.4 Logging Strategy

- One log file per day, rotated by a `prune-logs.sh` cron job that deletes files older than 30 days.
- Log HEARTBEAT_OK runs at DEBUG level; suppress them from the default view but retain them for audit.
- Log ALERT runs at INFO level with the full JSON payload.
- Send launchd stdout/stderr to separate files to avoid mixing orchestration logs with Claude output.

---

### 4. Cost Considerations

#### 4.1 Token Usage per Heartbeat

A single optimized heartbeat run has the following token budget:

| Component | Estimated Tokens |
|---|---|
| HEARTBEAT.md checklist prompt | 800–1,200 tokens (input) |
| CLAUDE.md system context | 200–400 tokens (input) |
| MCP tool responses (emails, calendar, tasks) | 1,000–3,000 tokens (input) |
| Claude reasoning and output | 200–500 tokens (output) |
| **Total per run** | **~2,200–5,100 tokens** |

At Claude Sonnet 4.6 pay-as-you-go pricing ($3.00/M input, $15.00/M output):

- Minimum case: ~2,200 input + 200 output = **$0.0096/run**
- Typical case: ~3,500 input + 350 output = **$0.016/run**
- Heavy case (many emails, long summaries): ~5,100 input + 500 output = **$0.023/run**

At 48 runs/day (every 30 min, 24 hours), the monthly cost:
- Minimum: $0.0096 × 48 × 30 = **~$13.80/month**
- Typical: $0.016 × 48 × 30 = **~$23.04/month**
- Heavy: $0.023 × 48 × 30 = **~$33.12/month**

With active hours limited to 7:00–23:00 (32 runs/day instead of 48):
- Typical: $0.016 × 32 × 30 = **~$15.36/month**

**Prompt caching dramatically reduces costs.** The HEARTBEAT.md and CLAUDE.md content is identical every run, making it a perfect candidate for cached input. Cache reads cost $0.30/M (90% less than fresh input). If 70% of input tokens are cache hits, the effective input cost drops from $3.00/M to approximately $1.11/M, reducing the typical monthly cost to approximately **$9–12/month**.

#### 4.2 Subscription vs. Pay-as-You-Go

| Option | Monthly Cost | Best For |
|---|---|---|
| Claude Pro ($20/mo) | $20 flat | Rate limits likely hit at 48 runs/day |
| Claude Max ($100/mo) | $100 flat | Generous limits, no per-token anxiety |
| API Pay-as-You-Go | $9–33/month (estimated) | Most economical if usage is moderate |
| Claude Max 5x ($200/mo) | $200 flat | Heavy multi-agent workloads |

For a single heartbeat agent with 32 optimized runs/day, **API pay-as-you-go is likely the most economical option** when prompt caching is properly configured. However, if Claude Code is also used interactively during the day, the Max plan's flat rate becomes more attractive.

#### 4.3 Claude Code CLI vs. Direct API

Claude Code CLI adds overhead (session initialization, tool scaffolding, larger system prompts) compared to a raw API call. For a heartbeat that only needs to read data and make a binary decision, a direct Anthropic API call with a hand-crafted prompt would cost 30–50% less per invocation by eliminating Claude Code's internal scaffolding tokens.

The tradeoff: direct API requires building your own tool-calling layer, MCP client, and error handling from scratch. Claude Code CLI provides these out of the box. Unless cost is a critical constraint, Claude Code CLI is the correct choice for initial implementation.

---

### 5. Security

#### 5.1 API Key Storage

Never store `ANTHROPIC_API_KEY` in a `.env` file committed to version control. The recommended pattern for macOS automation:

**Option A: Keychain via `security` CLI**

```bash
# Store once
security add-generic-password \
  -a "heartbeat-agent" \
  -s "anthropic-api-key" \
  -w "sk-ant-..."

# Retrieve at runtime in the script
ANTHROPIC_API_KEY=$(security find-generic-password \
  -a "heartbeat-agent" \
  -s "anthropic-api-key" \
  -w 2>/dev/null)
export ANTHROPIC_API_KEY
```

**Option B: Environment file with restricted permissions**

```bash
# Create secrets file
echo 'ANTHROPIC_API_KEY=sk-ant-...' > ~/.heartbeat-secrets
chmod 600 ~/.heartbeat-secrets

# Source in the runner script
source ~/.heartbeat-secrets
```

This file must not be inside the git repository. Add it to `.gitignore`.

**Critical SSH issue:** When running headless via launchd, the macOS Keychain may not be accessible. Known bug in Claude Code (GitHub issue #5515, #9403). The environment file approach (Option B) is more reliable for launchd-based automation.

#### 5.2 OAuth Token Management for MCP Servers

Gmail and Google Calendar MCP servers require OAuth 2.0 tokens. These must be pre-authorized interactively, then stored. The token files are typically located at:

```
~/.config/mcp-servers/gmail/token.json
~/.config/mcp-servers/google-calendar/token.json
```

Restrict file permissions:
```bash
chmod 600 ~/.config/mcp-servers/*/token.json
```

Tokens must be refreshed periodically. Build refresh logic into the orchestration script, or use a dedicated OAuth library that handles refresh automatically.

#### 5.3 Permission Sandboxing

Use `--allowedTools` to restrict what Claude can do during a heartbeat run. The principle of least privilege applies strictly:

```bash
# Good: explicit allowlist
--allowedTools "Read,mcp__gmail__list_emails,mcp__gmail__get_email,mcp__calendar__list_events,mcp__notion__query_database"

# Avoid: too broad
--allowedTools "Bash,Write,Edit,WebFetch"
```

Use `--disallowedTools` as a secondary defense layer:

```bash
--disallowedTools "Bash,Write,Edit,WebFetch,WebSearch"
```

Note: A documented issue (GitHub #12232) shows `--allowedTools` may be ignored when combined with `--permission-mode bypassPermissions`. Always use `--disallowedTools` as the defense-in-depth layer.

Claude Code also supports native sandboxing via macOS Seatbelt (`sandbox-exec`), which can restrict file system access to specific directories. For the heartbeat agent, the working directory should be limited to the repo directory and the MCP server token directories.

#### 5.4 What the Agent Should Never Have Access To

- SSH private keys (`~/.ssh/`)
- `.env` files in other projects
- The ability to make arbitrary HTTP requests
- Write access to any directory outside the heartbeat repo's `state/` and `logs/` subdirectories

---

### 6. Delivery Mechanisms

#### 6.1 Pushover (Recommended for iOS Push Notifications)

Pushover is the simplest path from a shell script to an iPhone notification. Requires a $5 one-time app purchase.

```bash
#!/bin/bash
# send-alert.sh
# Reads JSON alert payload from stdin

ALERT_JSON=$(cat)
SUMMARY=$(echo "$ALERT_JSON" | jq -r '.alerts[0].summary // "Heartbeat Alert"')
PRIORITY=$(echo "$ALERT_JSON" | jq -r '.alerts[0].priority == "high" | if . then 1 else 0 end')

curl -s \
  --form-string "token=$PUSHOVER_API_TOKEN" \
  --form-string "user=$PUSHOVER_USER_KEY" \
  --form-string "title=Heartbeat Alert" \
  --form-string "message=$SUMMARY" \
  --form-string "priority=$PRIORITY" \
  --form-string "sound=siren" \
  https://api.pushover.net/1/messages.json
```

A dedicated MCP server (`pushover-mcp-rs`) also exists, allowing Claude to send Pushover notifications directly as a tool call rather than through a post-processing script.

#### 6.2 Email via Gmail API (MCP)

If Gmail is already configured as an MCP server for reading, it can also be used for sending alerts. This creates a closed loop: Claude reads from Gmail via MCP and sends the alert back to a dedicated monitoring email address via the same MCP server.

Drawback: email alerts have latency and are easy to miss. Reserve for low-priority alerts or digests.

#### 6.3 macOS Native Notifications

For alerts that only need to be visible when sitting at the Mac Mini:

```bash
osascript -e 'display notification "'"$SUMMARY"'" with title "Heartbeat Alert" sound name "Blow"'
```

This works without any external service or API key. Combine with a dock badge or menu bar indicator for passive monitoring.

#### 6.4 Telegram Bot

Telegram offers free push notifications through a bot API with no per-message cost.

```bash
curl -s \
  -X POST "https://api.telegram.org/bot${TELEGRAM_BOT_TOKEN}/sendMessage" \
  -d "chat_id=${TELEGRAM_CHAT_ID}" \
  -d "text=${SUMMARY}" \
  -d "parse_mode=Markdown"
```

Setup requires creating a bot via @BotFather and obtaining the chat ID from the first message.

#### 6.5 Alert Deduplication Logic

Before dispatching any alert, compute a hash of the alert's source identifier and check it against `state/alert-hashes.json`:

```bash
ALERT_ID=$(echo "$ALERT_JSON" | jq -r '.alerts[0].source_id // empty')
HASH=$(echo -n "$ALERT_ID" | sha256sum | cut -d' ' -f1)

if jq -e --arg h "$HASH" '.sent_alerts[] | select(.hash == $h)' \
    state/alert-hashes.json > /dev/null 2>&1; then
  log "Alert already sent for hash $HASH. Skipping."
  exit 0
fi

# Send alert, then record hash
jq --arg h "$HASH" --arg t "$(date -u +%Y-%m-%dT%H:%M:%SZ)" \
  '.sent_alerts += [{"hash": $h, "sent_at": $t}]' \
  state/alert-hashes.json > /tmp/hashes.json && mv /tmp/hashes.json state/alert-hashes.json
```

---

## Analysis

### Session Architecture: The Stateless Heartbeat Model

The most counterintuitive finding is that the correct pattern deliberately discards Claude's session memory after every run. This is the right design for several reasons that compound:

Claude Code's context window grows linearly with every turn retained. A heartbeat that resumes its session accumulates context from every previous check — email summaries, calendar data, task states — all of which are irrelevant 30 minutes later. The token cost of a resumed session after 48 hours would be enormous relative to a fresh session.

Additionally, state managed by Claude (in its context window) is invisible to the orchestration layer. The shell script cannot inspect, modify, or audit Claude's memory. State managed in files is transparent, version-controllable, and survives Claude Code upgrades and crashes.

The correct architecture is: **Claude is stateless; the file system is stateful.** Claude reads state from files at the start of each run, makes decisions, and the orchestration script writes state back to files after the run.

### Tool Permission Discipline Is Non-Negotiable

The heartbeat agent operates autonomously, without human confirmation for each action. An incorrectly scoped tool list is a significant risk vector: if Claude has Bash tool access, a prompt injection attack via a malicious email subject line could potentially cause arbitrary code execution.

The allowedTools list should be treated like a firewall ruleset: deny by default, allow only what is explicitly required for the current checklist.

### Cost Optimization Compounds

Three optimizations together can reduce API cost by 70–80%:
1. Fresh sessions (no accumulated context from previous runs)
2. Prompt caching for the static HEARTBEAT.md and CLAUDE.md content
3. Active hours enforcement (reduces runs from 48/day to 32/day)

The residual cost is dominated by the MCP tool responses — the actual email and calendar data Claude needs to process. This cannot be easily cached because it changes every run.

### The runCLAUDErun Alternative

For users who want a GUI instead of a shell script, **runCLAUDErun** (`runclauderun.com`) is a native macOS app that wraps exactly this use case: schedule Claude Code tasks at intervals, run them in the background, log results. It is free, runs locally, and requires an existing Claude subscription. It is a reasonable alternative to the custom shell script approach, particularly for less technical users, but it provides less control over tool permissions, deduplication logic, and alert routing.

---

## Conclusions

1. **Headless mode (`claude -p`) is the correct API surface** for this use case. It is well-documented, actively maintained, and designed for non-interactive automation.

2. **Fresh sessions are architecturally superior to resumed sessions** for a heartbeat pattern. State should live in files, not in Claude's context window.

3. **launchd is the correct scheduler on macOS**, not cron. `StartCalendarInterval` provides predictable execution at :00 and :30 regardless of sleep/wake cycles.

4. **The cost model is favorable.** A well-optimized heartbeat with prompt caching and active hours enforcement costs approximately $9–15/month at pay-as-you-go API rates, competitive with a Claude Max subscription.

5. **Security must be layered.** `--allowedTools` + `--disallowedTools` + file permission hardening + Keychain/environment-file API key storage form the minimum viable security posture for an autonomous agent.

6. **MCP servers for Gmail and Google Calendar are mature and documented.** Multiple options exist ranging from official Anthropic integrations to open-source servers (nspady/google-calendar-mcp, Composio).

7. **Pushover is the optimal alert delivery mechanism** for personal use: cheap, reliable, no rate limits, native iOS/Android app, and trivially invoked from a shell script.

---

## Recommendations

### Immediate Actions

1. **Install and test Claude Code headless mode first.** Run `claude -p "Say hello" --output-format json` and verify the JSON output structure before building any orchestration.

2. **Start with a minimal HEARTBEAT.md.** Begin with one check (e.g., calendar events in the next 60 minutes) and one alert condition. Expand after validating end-to-end.

3. **Configure MCP servers interactively before automating.** Gmail and Google Calendar OAuth flows require browser interaction. Complete these in interactive mode first, then automate.

4. **Use API pay-as-you-go billing initially.** Monitor actual costs for two weeks before committing to a subscription plan.

### Implementation Sequence

```
Phase 1: Core Loop
  - launchd plist with 30-min interval
  - heartbeat-runner.sh invoking claude -p
  - Basic HEARTBEAT.md (calendar check only)
  - macOS notification for alerts

Phase 2: Integration
  - Gmail MCP server
  - Google Calendar MCP server
  - JSON output parsing
  - alert-hashes.json deduplication

Phase 3: Polish
  - Pushover integration
  - Active hours enforcement
  - Log rotation
  - Prompt caching verification
  - Notion/task MCP server
```

### Operational Guardrails

- Set a monthly API spend alert at $30 in the Anthropic console.
- Review `state/last-run.json` weekly to verify the agent is running.
- Rotate API keys every 90 days.
- Keep the `allowedTools` list in version control and review it whenever HEARTBEAT.md changes.
- Test the alert path monthly by temporarily lowering the alert threshold to trigger a notification.

---

## References

- [Claude Code Headless Mode Documentation](https://code.claude.com/docs/en/headless)
- [Claude Code Common Workflows](https://code.claude.com/docs/en/common-workflows)
- [Claude Code Hooks Guide](https://code.claude.com/docs/en/hooks-guide)
- [Claude Code Sandboxing](https://code.claude.com/docs/en/sandboxing)
- [Claude Code Cost Management](https://code.claude.com/docs/en/costs)
- [Claude API Pricing](https://platform.claude.com/docs/en/about-claude/pricing)
- [Mastering Claude Code Sessions (Vibe Sparking AI)](https://www.vibesparking.com/en/blog/ai/claude-code/docs/cli/2025-08-28-mastering-claude-code-sessions-continue-resume-automate/)
- [Claude Code Headless Mode Tutorial (SFEIR Institute)](https://institute.sfeir.com/en/claude-code/claude-code-headless-mode-and-ci-cd/tutorial/)
- [Google Calendar MCP Server (nspady)](https://github.com/nspady/google-calendar-mcp)
- [Gmail and Google Calendar MCP Integration Guide](https://support.claude.com/en/articles/11088742-using-the-gmail-and-google-calendar-integrations)
- [Claude Code Security Best Practices (Backslash)](https://www.backslash.security/blog/claude-code-security-best-practices)
- [API Key Management in Claude Code](https://support.claude.com/en/articles/12304248-managing-api-key-environment-variables-in-claude-code)
- [Claude Code CLI Over SSH Keychain Fix](https://phoenixtrap.com/2025/10/26/claude-code-cli-over-ssh-on-macos-fixing-keychain-access/)
- [Claude Code Permissions Guide (claudefa.st)](https://claudefa.st/blog/guide/development/permission-management)
- [Building Automated Claude Code Workers with Cron and MCP (blle.co)](https://www.blle.co/blog/automated-claude-code-workers)
- [runCLAUDErun macOS Scheduler](https://runclauderun.com)
- [Pushover Bash Script](https://github.com/akusei/pushover-bash)
- [Pushover MCP Server (pushover-mcp-rs)](https://lobehub.com/mcp/chrstnwhlrt-pushover-mcp-rs)
- [Claude Code Token Optimization (claudefa.st)](https://claudefa.st/blog/guide/development/usage-optimization)
- [Writing a Good CLAUDE.md (HumanLayer)](https://www.humanlayer.dev/blog/writing-a-good-claude-md)
- [launchd Tutorial](https://www.launchd.info/)
- [macOS launchd Plist Examples](https://alvinalexander.com/mac-os-x/launchd-plist-examples-startinterval-startcalendarinterval/)
- [Claude Code Scheduler (GitHub)](https://github.com/jshchnz/claude-code-scheduler)
- [Session Resumption Feature Request (GitHub Issue #1340)](https://github.com/anthropics/claude-code/issues/1340)
- [allowedTools with bypassPermissions Bug (GitHub Issue #12232)](https://github.com/anthropics/claude-code/issues/12232)
- [SSH/Keychain Bug (GitHub Issue #5515)](https://github.com/anthropics/claude-code/issues/5515)
- [Northflank: Claude Code Rate Limits and Pricing](https://northflank.com/blog/claude-rate-limits-claude-code-pricing-cost)
- [Notion MCP Server (Official)](https://github.com/makenotion/notion-mcp-server)

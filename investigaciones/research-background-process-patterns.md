# Background Process Patterns for Periodic AI CLI Tool Execution

**Navigation:** This is a single-part report.

---

## Executive Summary

Running AI CLI tools like Claude Code as scheduled or persistent background processes requires careful selection of the right execution model. Six primary approaches exist across macOS and Linux: launchd (LaunchAgent/LaunchDaemon), systemd timers, cron jobs, tmux/screen persistent sessions, Node.js daemon managers (pm2, forever), and Docker containers with embedded schedulers.

Each approach presents distinct trade-offs in complexity, reliability, logging capability, and compatibility with the TTY requirements of interactive CLI tools. A critical finding is that Claude Code and similar AI CLI tools have a partial TTY dependency: the `--print` (`-p`) flag enables true headless operation, which is the required foundation for any daemon or scheduled execution pattern to work correctly.

The most operationally mature choice for macOS is a LaunchAgent with `StartInterval`, while Linux users benefit from systemd timers for their integrated logging and dependency management. For teams already using Node.js tooling, pm2 with its ecosystem file and `max_memory_restart` offers the lowest adoption friction. Docker-based patterns using `supercronic` provide the strongest isolation and portability for production environments.

---

## Introduction

Modern AI CLI tools such as Claude Code are increasingly used for autonomous tasks: automated code review on push, periodic repository health checks, background refactoring passes, and continuous documentation generation. To unlock these use cases, teams need a reliable mechanism to:

1. Execute the tool on a schedule (e.g., every 30 minutes) or on a trigger
2. Ensure the process restarts if it crashes or the machine reboots
3. Capture logs for debugging and auditing
4. Securely inject API keys and environment configuration
5. Prevent resource accumulation over long-running sessions

This report surveys six execution patterns, analyzes their suitability for AI CLI workloads specifically, and provides production-ready configuration examples.

---

## Methodology

Research was conducted via targeted web searches across official documentation (Apple Developer, systemd.io, pm2.io, Docker Hub), community resources (ArchWiki, DigitalOcean, DEV Community), and real-world reports of teams running Claude Code and similar tools in CI/CD and daemon contexts. GitHub issues for Claude Code's TTY behavior were also consulted. All configuration examples are derived from verified working patterns in the sources cited.

---

## The TTY Problem: Foundation for All Patterns

Before examining individual approaches, understanding the TTY constraint is essential. Claude Code was designed as an interactive terminal tool. When invoked without a terminal attached (as happens in all daemon contexts), it may hang, error with `stdin is not a TTY`, or refuse to produce output.

**The solution:** Use the `-p` (or `--print`) flag. This flag activates Claude Code's headless mode, disabling the interactive TUI and sending output directly to stdout. It is the single prerequisite for any automated execution pattern.

```bash
# Headless execution - safe for daemons, cron, systemd
claude -p "Review the last git diff and summarize any issues" --output-format text

# With specific tool restrictions (reduces attack surface in automation)
claude -p "Run tests and report failures" --allowedTools Bash,Read

# JSON output for programmatic parsing
claude -p "Check for security issues in src/" --output-format json
```

The `ANTHROPIC_API_KEY` environment variable must also be set — there is no interactive login flow in headless mode. A known bug (GitHub issue #9026) documents cases where the `-p` flag still hangs without a TTY in some versions; the workaround is the `script` utility on macOS: `script -q /dev/null claude -p "..."`.

---

## Approach 1: macOS LaunchAgent / LaunchDaemon

### Overview

`launchd` is the macOS process supervisor that replaces `cron`, `init`, and `inetd`. It manages two categories of jobs relevant here:

| Type | Location | Runs As | Starts When |
|------|----------|---------|-------------|
| **LaunchAgent** (per-user) | `~/Library/LaunchAgents/` | Logged-in user | User session opens |
| **LaunchAgent** (system-wide) | `/Library/LaunchAgents/` | Logged-in user | Any user logs in |
| **LaunchDaemon** | `/Library/LaunchDaemons/` | root (or specified user) | System boot |

For AI CLI tools that need GUI/keychain access (e.g., reading credentials), a user-level LaunchAgent is the correct choice. LaunchDaemons run before any user logs in and cannot access user keychains or display GUIs.

### Process Lifecycle

launchd uses two scheduling mechanisms:

- **`StartInterval`**: Fires every N seconds from the last run start. Use `1800` for 30 minutes.
- **`StartCalendarInterval`**: Fires at specific calendar times (like cron). Can target minute, hour, day, weekday, month.

**`KeepAlive`** is a separate concept: it tells launchd to keep a process running continuously (not just periodically), restarting it immediately if it exits. For periodic AI tasks that should run and exit, do not use `KeepAlive: true`. For a long-running loop process, `KeepAlive` with `ThrottleInterval` is appropriate.

**`ThrottleInterval`**: The minimum number of seconds between respawns. Default is 10. Set it to something like `1800` if using `KeepAlive` to prevent a crashing process from respawning in a tight loop.

### Production-Ready Plist: Periodic 30-Minute Execution

```xml
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN"
  "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>

  <!-- Unique reverse-domain label -->
  <key>Label</key>
  <string>com.pipa.claude-agent.periodic</string>

  <!-- The command to run -->
  <key>ProgramArguments</key>
  <array>
    <string>/bin/bash</string>
    <string>/Users/youruser/scripts/run-claude-agent.sh</string>
  </array>

  <!-- Run every 30 minutes (1800 seconds) -->
  <key>StartInterval</key>
  <integer>1800</integer>

  <!-- Redirect stdout and stderr to log files -->
  <key>StandardOutPath</key>
  <string>/Users/youruser/logs/claude-agent.log</string>
  <key>StandardErrorPath</key>
  <string>/Users/youruser/logs/claude-agent-error.log</string>

  <!-- Environment variables - CRITICAL for PATH and API key -->
  <key>EnvironmentVariables</key>
  <dict>
    <key>PATH</key>
    <string>/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin:/opt/homebrew/bin</string>
    <key>ANTHROPIC_API_KEY</key>
    <string>sk-ant-YOUR-KEY-HERE</string>
    <key>HOME</key>
    <string>/Users/youruser</string>
  </dict>

  <!-- Working directory for relative paths in the script -->
  <key>WorkingDirectory</key>
  <string>/Users/youruser/projects/my-project</string>

  <!-- Do NOT auto-restart on exit for periodic tasks -->
  <!-- Remove this key or set to false for interval-based jobs -->

</dict>
</plist>
```

### Wrapper Script (`run-claude-agent.sh`)

```bash
#!/bin/bash
# run-claude-agent.sh - Wrapper for headless Claude Code execution
set -euo pipefail

LOG_FILE="$HOME/logs/claude-agent.log"
TIMESTAMP=$(date '+%Y-%m-%d %H:%M:%S')

echo "[$TIMESTAMP] Starting Claude agent run" >> "$LOG_FILE"

# Load nvm or node version managers if needed
export NVM_DIR="$HOME/.nvm"
[ -s "$NVM_DIR/nvm.sh" ] && source "$NVM_DIR/nvm.sh"

# Run Claude Code in headless mode
OUTPUT=$(claude -p "Analyze new commits since last run and flag any issues" \
  --allowedTools Bash,Read \
  --output-format text \
  2>&1)

EXIT_CODE=$?
echo "[$TIMESTAMP] Exit code: $EXIT_CODE" >> "$LOG_FILE"
echo "[$TIMESTAMP] Output: $OUTPUT" >> "$LOG_FILE"

exit $EXIT_CODE
```

### Loading and Managing the Agent

```bash
# Load (register) the agent - modern macOS syntax
launchctl bootstrap gui/$(id -u) ~/Library/LaunchAgents/com.pipa.claude-agent.periodic.plist

# Unload (unregister) the agent
launchctl bootout gui/$(id -u) ~/Library/LaunchAgents/com.pipa.claude-agent.periodic.plist

# Check status
launchctl print gui/$(id -u)/com.pipa.claude-agent.periodic

# Force an immediate run
launchctl kickstart -k gui/$(id -u)/com.pipa.claude-agent.periodic

# Legacy load syntax (still works on most macOS versions)
launchctl load ~/Library/LaunchAgents/com.pipa.claude-agent.periodic.plist
```

### Logging

Logs go to the files specified in `StandardOutPath` / `StandardErrorPath`. For rotation, use `newsyslog` or add a second launchd job that runs `logrotate`. Note that launchd appends to log files — they will grow indefinitely without rotation.

### Pros and Cons

| Pros | Cons |
|------|------|
| Native macOS, no extra dependencies | macOS-only |
| Survives reboots automatically | plist XML syntax is verbose |
| Integrates with Keychain (via agent) | Limited to StartInterval or calendar-based scheduling |
| Fine-grained environment control | Log rotation must be managed separately |
| `launchctl` gives process status | PATH must be set explicitly in the plist |

---

## Approach 2: systemd Timers (Linux)

### Overview

systemd timers are the modern Linux equivalent of cron, offering tighter integration with the init system, structured logging via `journald`, and dependency management between units. A timer always pairs with a service unit: the timer defines *when* to run, the service defines *what* to run.

### Two-Unit Architecture

**Service unit** (`/etc/systemd/system/claude-agent.service` or `~/.config/systemd/user/claude-agent.service`):

```ini
[Unit]
Description=Claude Code Periodic Agent Run
After=network-online.target
Wants=network-online.target

[Service]
Type=oneshot
# Path to the wrapper script
ExecStart=/home/youruser/scripts/run-claude-agent.sh
# Environment file keeps secrets out of the unit file
EnvironmentFile=/home/youruser/.config/claude-agent/env
# Run as specific user (for system-level units)
User=youruser
Group=youruser
# Working directory
WorkingDirectory=/home/youruser/projects/my-project
# Resource limits
MemoryMax=512M
CPUQuota=50%
# Stdout and stderr go to journald by default
StandardOutput=journal
StandardError=journal
# Add metadata tag for filtering logs
SyslogIdentifier=claude-agent
```

**Timer unit** (`/etc/systemd/system/claude-agent.timer` or `~/.config/systemd/user/claude-agent.timer`):

```ini
[Unit]
Description=Run Claude Agent every 30 minutes
Requires=claude-agent.service

[Timer]
# Run 5 minutes after boot, then every 30 minutes
OnBootSec=5min
OnUnitActiveSec=30min

# Alternative: calendar-based (like cron)
# OnCalendar=*:0/30

# Run missed executions on next boot
Persistent=true

# Randomize start by up to 2 minutes to avoid thundering herd
RandomizedDelaySec=120

# Ensure accuracy within 1 minute
AccuracySec=1min

[Install]
WantedBy=timers.target
```

**Environment file** (`/home/youruser/.config/claude-agent/env`):

```
ANTHROPIC_API_KEY=sk-ant-YOUR-KEY-HERE
PATH=/usr/local/bin:/usr/bin:/bin:/home/youruser/.nvm/versions/node/v20/bin
HOME=/home/youruser
```

```bash
# Secure the environment file
chmod 600 /home/youruser/.config/claude-agent/env
```

### Managing the Timer

```bash
# Enable and start the timer (system-level)
sudo systemctl daemon-reload
sudo systemctl enable --now claude-agent.timer

# For user-level (no sudo required)
systemctl --user daemon-reload
systemctl --user enable --now claude-agent.timer

# Check timer status and next run time
systemctl list-timers claude-agent.timer
systemctl status claude-agent.timer

# Manually trigger a run immediately
systemctl start claude-agent.service

# View logs (last 50 lines)
journalctl -u claude-agent.service -n 50

# Follow logs in real time
journalctl -u claude-agent.service -f

# Logs since last hour
journalctl -u claude-agent.service --since "1 hour ago"
```

### Crash Handling and Restart Policies

For a timer-triggered oneshot service, systemd records failures in the journal. To add automatic retry for transient failures, add to the `[Service]` section:

```ini
# Restart on failure (useful if the service is Type=simple, not oneshot)
Restart=on-failure
RestartSec=30s
# Maximum restart attempts in a time window
StartLimitIntervalSec=300
StartLimitBurst=3
```

For `Type=oneshot`, systemd does not auto-restart between timer intervals. The timer itself will retry at the next scheduled interval. If you need immediate retry on failure, switch to `Type=simple` with a persistent loop in the script.

### Resource Management

```ini
[Service]
# Memory ceiling - kills process if exceeded
MemoryMax=512M
# Soft memory limit - triggers swap pressure
MemoryHigh=400M
# CPU time cap (50% of one core)
CPUQuota=50%
# Prevent runaway I/O
IOWeight=50
```

### Pros and Cons

| Pros | Cons |
|------|------|
| Built-in `journald` logging with filtering | Linux-only (systemd distributions) |
| `Persistent=true` catches missed runs | Two files required per task |
| `RandomizedDelaySec` prevents thundering herd | More initial setup than cron |
| Dependency management via `After=`, `Wants=` | User-level timers need `loginctl enable-linger` |
| Resource limits via cgroups | Not available on non-systemd distros |
| `systemctl status` gives rich diagnostics | |

---

## Approach 3: Cron Jobs

### Overview

Cron is the oldest and most universally available Unix scheduler. Present on macOS, all Linux distributions, BSD, and WSL, it requires no installation. For simple interval-based tasks where systemd is unavailable, cron remains a practical choice.

### Critical Environment Issue

Cron runs in a stripped environment. The default `PATH` is only `/usr/bin:/bin`. NVM, Homebrew, npm globals, and the `claude` binary are almost certainly not in this path. **This is the most common failure mode** when migrating interactive scripts to cron.

### Production-Ready Crontab

```bash
# Edit user crontab
crontab -e
```

```cron
# Set a complete PATH at the top
PATH=/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin

# Set the shell explicitly
SHELL=/bin/bash

# Log all cron output to a file (append mode)
# Individual job logging is handled in the wrapper script

# Run Claude agent every 30 minutes
*/30 * * * * /bin/bash /Users/youruser/scripts/run-claude-agent.sh >> /Users/youruser/logs/cron-claude.log 2>&1

# Alternative: run at specific times (9am and 3pm on weekdays)
0 9,15 * * 1-5 /bin/bash /Users/youruser/scripts/run-claude-agent.sh >> /Users/youruser/logs/cron-claude.log 2>&1
```

### Wrapper Script for Cron

```bash
#!/bin/bash
# run-claude-agent.sh - Cron-safe wrapper
# Source user profile to get NVM, rbenv, pyenv, etc.
source "$HOME/.bashrc" 2>/dev/null || source "$HOME/.bash_profile" 2>/dev/null || true

# Explicit API key (or source from a secrets file)
export ANTHROPIC_API_KEY="$(cat $HOME/.config/claude-agent/api-key)"

TIMESTAMP=$(date '+%Y-%m-%d %H:%M:%S')
echo "[$TIMESTAMP] Cron trigger: starting Claude agent"

claude -p "Summarize open issues and suggest priorities" \
  --output-format text \
  --allowedTools Read

echo "[$TIMESTAMP] Completed with exit code $?"
```

### Cron on macOS Specifics

On macOS, cron requires Full Disk Access permission in `System Settings > Privacy & Security > Full Disk Access`. Grant access to `/usr/sbin/cron`. Without this, cron silently fails to access files in common directories.

```bash
# Verify cron is running on macOS
sudo launchctl list | grep cron

# Test the exact environment cron sees
* * * * * env > /tmp/cron-env.txt
```

### Pros and Cons

| Pros | Cons |
|------|------|
| Universal - works on all Unix systems | Minimal environment requires explicit PATH |
| Simple one-line syntax | No built-in logging (must redirect manually) |
| No additional dependencies | Missed runs are silently skipped |
| Familiar to most system administrators | No dependency or ordering control |
| macOS, Linux, BSD compatible | macOS needs Full Disk Access permission |
| | No built-in crash recovery between runs |

---

## Approach 4: tmux / screen Persistent Sessions

### Overview

tmux and screen are terminal multiplexers that maintain session state independent of the SSH connection or terminal window that created them. For AI CLI tools, this approach is less about scheduling and more about maintaining a persistent interactive-adjacent environment where a loop script runs continuously.

This is the most developer-friendly approach for local development and experimentation. It does not require system-level configuration and gives full visibility into what the agent is doing at any time.

### Architecture: Detached Session with Loop

```bash
#!/bin/bash
# start-agent-session.sh - Creates a persistent tmux agent session

SESSION_NAME="claude-agent"

# Don't create a duplicate session
if tmux has-session -t "$SESSION_NAME" 2>/dev/null; then
  echo "Session '$SESSION_NAME' already exists. Attaching..."
  tmux attach-session -t "$SESSION_NAME"
  exit 0
fi

# Create new detached session
tmux new-session -d -s "$SESSION_NAME" -x 220 -y 50

# Window 0: The agent loop
tmux send-keys -t "$SESSION_NAME:0" \
  "bash ~/scripts/agent-loop.sh" Enter

# Window 1: Logs tail
tmux new-window -t "$SESSION_NAME"
tmux send-keys -t "$SESSION_NAME:1" \
  "tail -f ~/logs/claude-agent.log" Enter

# Window 2: Project directory for manual intervention
tmux new-window -t "$SESSION_NAME"
tmux send-keys -t "$SESSION_NAME:2" \
  "cd ~/projects/my-project && bash" Enter

echo "Agent session started. Attach with: tmux attach -t $SESSION_NAME"
```

### The Agent Loop Script

```bash
#!/bin/bash
# agent-loop.sh - Persistent loop for periodic AI agent execution
set -euo pipefail

export ANTHROPIC_API_KEY="$(cat $HOME/.config/claude-agent/api-key)"
INTERVAL_SECONDS=1800  # 30 minutes
LOG_FILE="$HOME/logs/claude-agent.log"

log() {
  echo "[$(date '+%Y-%m-%d %H:%M:%S')] $*" | tee -a "$LOG_FILE"
}

log "Agent loop starting. Interval: ${INTERVAL_SECONDS}s"

while true; do
  log "--- Run starting ---"

  # Capture output and exit code robustly
  if OUTPUT=$(claude -p "Check for new TODO comments added since last run and create GitHub issues" \
       --allowedTools Bash,Read \
       --output-format text 2>&1); then
    log "SUCCESS: $OUTPUT"
  else
    EXIT_CODE=$?
    log "FAILURE (exit $EXIT_CODE): $OUTPUT"
    # Optional: send notification on failure
    # osascript -e "display notification \"Claude agent failed\" with title \"PIPA Agent\""
  fi

  log "--- Run complete. Sleeping ${INTERVAL_SECONDS}s ---"
  sleep "$INTERVAL_SECONDS"
done
```

### Process Lifecycle Management

```bash
# Start the session (detached)
bash ~/scripts/start-agent-session.sh

# Attach to watch it live
tmux attach -t claude-agent

# Detach without stopping (press these keys while attached)
# Ctrl+B, then D

# Stop the agent (kill the session entirely)
tmux kill-session -t claude-agent

# List all sessions
tmux ls

# Restart just the loop (from within the session or via send-keys)
tmux send-keys -t "claude-agent:0" "C-c" ""
tmux send-keys -t "claude-agent:0" "bash ~/scripts/agent-loop.sh" Enter
```

### Automatic Session Recovery on Reboot

tmux sessions die on reboot unless combined with another mechanism. Options:

1. **tmux-resurrect plugin**: Saves and restores sessions across reboots
2. **LaunchAgent / systemd service**: Runs `start-agent-session.sh` at login/boot
3. **`.bashrc` check**: Source a script that checks for and recreates the session

```bash
# Add to ~/.bashrc or ~/.zshrc - auto-recreate session if missing
if ! tmux has-session -t "claude-agent" 2>/dev/null; then
  bash ~/scripts/start-agent-session.sh
fi
```

### Pros and Cons

| Pros | Cons |
|------|------|
| Full TTY — no headless mode required | Not a true daemon; requires tmux installed |
| Can watch the agent run in real time | Sessions die on reboot without extra config |
| Easy to pause, inspect, or intervene | Not suitable for server-only (headless) hosts |
| No special permissions needed | Manual recovery if machine restarts |
| Great for development and testing | Memory usage grows if loop leaks resources |

---

## Approach 5: Node.js Daemon Patterns (pm2, forever)

### Overview

Since Claude Code is itself a Node.js tool, process managers from the Node.js ecosystem are a natural fit. pm2 is the production standard; `forever` is a simpler, older alternative. Both provide crash recovery, log management, and startup registration.

### pm2: The Production Choice

pm2 manages processes via an **ecosystem config file** (`ecosystem.config.js`), which supports cron-based restart scheduling, environment-specific configs, and memory-based restart policies.

**Installation:**

```bash
npm install -g pm2
```

**Ecosystem Config for Periodic Execution:**

```javascript
// ecosystem.config.js
module.exports = {
  apps: [
    {
      // Option A: Cron-restart pattern
      // pm2 restarts the process on schedule; the script runs and exits
      name: 'claude-agent-cron',
      script: '/home/youruser/scripts/run-claude-agent.sh',
      interpreter: '/bin/bash',

      // Restart at :00 and :30 of every hour
      cron_restart: '0,30 * * * *',

      // Don't auto-restart on normal exit between cron triggers
      autorestart: false,

      // Run as single instance
      instances: 1,
      exec_mode: 'fork',

      // Environment variables
      env: {
        NODE_ENV: 'production',
        ANTHROPIC_API_KEY: process.env.ANTHROPIC_API_KEY,
        PATH: '/usr/local/bin:/usr/bin:/bin:/opt/homebrew/bin'
      },

      // Logging
      out_file: '/home/youruser/logs/pm2-claude-out.log',
      error_file: '/home/youruser/logs/pm2-claude-error.log',
      log_date_format: 'YYYY-MM-DD HH:mm:ss',
      merge_logs: true,

      // Memory-based restart (prevents leaks in long-running mode)
      max_memory_restart: '256M',

      // Watch for config changes (disable in production)
      watch: false
    },

    {
      // Option B: Long-running loop pattern
      // The script itself contains the while/sleep loop
      name: 'claude-agent-loop',
      script: '/home/youruser/scripts/agent-loop.sh',
      interpreter: '/bin/bash',

      // Auto-restart if the loop script crashes unexpectedly
      autorestart: true,
      restart_delay: 5000,  // 5 second delay before restart

      // Restart if memory exceeds 512MB
      max_memory_restart: '512M',

      // Exponential backoff: 100ms, 200ms, 400ms... up to 16s
      exp_backoff_restart_delay: 100,

      env: {
        ANTHROPIC_API_KEY: process.env.ANTHROPIC_API_KEY
      },

      out_file: '/home/youruser/logs/pm2-loop-out.log',
      error_file: '/home/youruser/logs/pm2-loop-error.log',
      log_date_format: 'YYYY-MM-DD HH:mm:ss'
    }
  ]
}
```

### Managing pm2 Processes

```bash
# Start from ecosystem file
pm2 start ecosystem.config.js

# Start specific app
pm2 start ecosystem.config.js --only claude-agent-cron

# Register pm2 to start on system boot
pm2 startup   # Outputs a command to run as root/sudo
pm2 save      # Saves current process list for restoration

# Process management
pm2 list                        # List all processes with status
pm2 status claude-agent-cron    # Detailed status
pm2 stop claude-agent-cron      # Stop without removing
pm2 restart claude-agent-cron   # Restart
pm2 delete claude-agent-cron    # Remove from pm2

# Trigger immediate execution (cron_restart mode)
pm2 restart claude-agent-cron

# Logs
pm2 logs claude-agent-cron          # All logs
pm2 logs claude-agent-cron --lines 50  # Last 50 lines
pm2 logs --err                      # Error logs only

# Monitoring dashboard
pm2 monit
```

### Securing API Keys with pm2

**Never hardcode secrets in `ecosystem.config.js`** if that file is in version control. The correct pattern:

```javascript
// ecosystem.config.js — safe for git commit
env: {
  ANTHROPIC_API_KEY: process.env.ANTHROPIC_API_KEY  // read from shell env at start time
}
```

```bash
# Set the key in shell before starting pm2
export ANTHROPIC_API_KEY="sk-ant-..."
pm2 start ecosystem.config.js

# OR: Load from a .env file (never commit this)
# .env file:
# ANTHROPIC_API_KEY=sk-ant-...
set -a; source .env; set +a
pm2 start ecosystem.config.js
```

### forever: The Simpler Alternative

`forever` lacks cron scheduling, but excels at simple "keep this script running" scenarios:

```bash
npm install -g forever

# Start a loop script as a daemon
forever start -l ~/logs/forever.log --append -o ~/logs/out.log -e ~/logs/err.log \
  ~/scripts/agent-loop.sh

# List running processes
forever list

# Stop
forever stop ~/scripts/agent-loop.sh

# Restart on file change (useful for script updates)
forever start -w ~/scripts/agent-loop.sh
```

### Pros and Cons

| Pros | Cons |
|------|------|
| Excellent crash recovery with backoff | Requires Node.js runtime |
| Memory-based restart prevents leaks | pm2 is feature-heavy for simple tasks |
| `pm2 startup` integrates with launchd/systemd | `cron_restart` restarts the whole process |
| Rich monitoring dashboard (`pm2 monit`) | Ecosystem file adds configuration overhead |
| Works on both macOS and Linux | `forever` is less maintained in 2025 |
| Handles env vars gracefully | |

---

## Approach 6: Docker Containers

### Overview

Docker provides the strongest isolation for running AI CLI tools. The approach packages the tool, its dependencies, and the schedule into a self-contained image. The key challenge is environment variable injection and the TTY requirement, both of which have clean solutions.

### Architecture Options

**Option A: Container with supercronic** (recommended)

supercronic is a cron replacement built for containers. Unlike traditional cron, it inherits all Docker `ENV` variables and writes to stdout/stderr rather than requiring a mail daemon.

**Dockerfile:**

```dockerfile
FROM node:20-alpine

# Install Claude Code globally
RUN npm install -g @anthropic-ai/claude-code

# Install supercronic
ARG SUPERCRONIC_URL=https://github.com/aptible/supercronic/releases/download/v0.2.29/supercronic-linux-amd64
ARG SUPERCRONIC_SHA1SUM=cd48d45c4b10f3f0bfdd3a57d054cd05ac96812b

RUN apk add --no-cache curl ca-certificates && \
    curl -fsSLo /usr/local/bin/supercronic "${SUPERCRONIC_URL}" && \
    echo "${SUPERCRONIC_SHA1SUM}  /usr/local/bin/supercronic" | sha1sum -c - && \
    chmod +x /usr/local/bin/supercronic

# Copy the crontab
COPY crontab /etc/crontab

# Copy agent scripts
COPY scripts/ /app/scripts/

WORKDIR /app

# Supercronic is the entrypoint - it inherits all ENV vars
CMD ["/usr/local/bin/supercronic", "/etc/crontab"]
```

**crontab** (same format as standard cron):

```cron
# Run every 30 minutes
*/30 * * * * /bin/sh /app/scripts/run-claude-agent.sh >> /proc/1/fd/1 2>> /proc/1/fd/2
```

Writing to `/proc/1/fd/1` and `/proc/1/fd/2` redirects output to the container's PID 1 stdout/stderr, which Docker captures in `docker logs`.

**Run the container:**

```bash
docker run -d \
  --name claude-agent \
  --restart unless-stopped \
  -e ANTHROPIC_API_KEY="sk-ant-..." \
  -v $(pwd)/project:/app/project:ro \
  -v $(pwd)/logs:/app/logs \
  your-image:latest
```

**Option B: docker-compose with restart policy:**

```yaml
# docker-compose.yml
version: '3.8'

services:
  claude-agent:
    build: .
    restart: unless-stopped
    environment:
      - ANTHROPIC_API_KEY=${ANTHROPIC_API_KEY}
    volumes:
      - ./project:/app/project:ro
      - ./logs:/app/logs
    # Resource limits
    deploy:
      resources:
        limits:
          memory: 512M
          cpus: '0.50'
```

```bash
# Start with env from .env file
docker-compose up -d

# View logs
docker logs claude-agent -f

# Stop
docker-compose down
```

**Option C: Host cron + `docker exec`**

If a container is already running for other purposes, the host's cron or systemd timer can inject commands into it:

```bash
# Crontab entry
*/30 * * * * docker exec my-app-container claude -p "Run health check" >> /var/log/claude-exec.log 2>&1
```

### Resource Management in Docker

```yaml
# Strict resource enforcement
deploy:
  resources:
    limits:
      memory: 512M
      cpus: '0.50'
    reservations:
      memory: 128M
```

For detecting leaks over time:

```bash
# Monitor container stats
docker stats claude-agent --no-stream

# Set a restart policy with memory limit (docker run)
docker run --memory="512m" --memory-swap="512m" --restart on-failure:5 ...
```

### Pros and Cons

| Pros | Cons |
|------|------|
| Strong isolation from host | Docker overhead; heavier than native approaches |
| Consistent environment across machines | More complex setup |
| Supercronic inherits all env vars cleanly | Claude Code npm install in image adds build time |
| `docker logs` centralizes output | Volume mounts needed for project file access |
| Restart policies for crash recovery | Updating Claude Code requires image rebuild |
| Works identically on macOS and Linux | |

---

## Cross-Cutting Analysis

### Environment Variable Security Comparison

| Approach | Risk Level | Recommended Method |
|----------|-----------|-------------------|
| LaunchAgent plist | Medium (file on disk) | `EnvironmentVariables` dict; restrict file permissions to 600 |
| systemd timer | Low | `EnvironmentFile` with `chmod 600`; consider systemd credentials |
| cron | High | Source from a 600-permission secrets file in wrapper |
| tmux loop | Low-Medium | Export in shell; consider `pass` or macOS Keychain |
| pm2 | Medium | Read from shell env at startup; never commit ecosystem.config.js secrets |
| Docker | Low | Docker secrets or runtime `-e` injection; use `.env` file never committed |

### Crash Recovery Comparison

| Approach | Auto-Restart | Backoff | Missed Run Recovery |
|----------|-------------|---------|-------------------|
| LaunchAgent (KeepAlive) | Yes | ThrottleInterval | No |
| systemd timer | Timer-based | StartLimitBurst | Yes (Persistent=true) |
| cron | No | N/A | No (silent skip) |
| tmux loop | No (manual) | N/A | No |
| pm2 | Yes | Exponential | No |
| Docker (`--restart`) | Yes | Configurable | No |

### Suitability for Claude Code Specifically

All approaches require Claude Code's `-p` flag for headless execution. The tmux approach is the only one where this is optional (since it provides a real TTY). Key considerations:

1. **Node.js runtime dependency**: Claude Code requires Node.js. Docker and pm2 handle this naturally. LaunchAgent/systemd/cron must ensure the node binary is in their `PATH`.

2. **First-run authentication**: Claude Code needs `ANTHROPIC_API_KEY` set. On first launch in a new environment, it may also attempt to open a browser for OAuth. Using the API key environment variable bypasses this entirely.

3. **Working directory**: Most Claude Code operations are relative to the project directory. Always set `WorkingDirectory` (systemd), `WorkingDirectory` (plist), `cd` in wrapper scripts, or `WORKDIR` in Docker.

4. **Execution duration**: Claude Code calls may take 30-120 seconds per prompt. Ensure your scheduler does not fire a new instance while the previous one is still running. systemd handles this natively (only one oneshot instance runs at a time). For cron, use a lockfile:

```bash
#!/bin/bash
# Lockfile pattern for cron
LOCKFILE="/tmp/claude-agent.lock"

if [ -f "$LOCKFILE" ]; then
  echo "Previous run still in progress. Exiting."
  exit 0
fi

trap "rm -f $LOCKFILE" EXIT
touch "$LOCKFILE"

claude -p "your prompt here" ...
```

---

## Recommendations

### Decision Matrix

| Scenario | Recommended Approach |
|----------|---------------------|
| macOS, personal machine, developer use | LaunchAgent with StartInterval |
| macOS, need to watch agent live | tmux session with loop script |
| Linux server, production workload | systemd timer + service |
| Linux server, team already uses Node | pm2 with ecosystem.config.js |
| CI/CD, cloud, or multi-environment | Docker + supercronic |
| Quick prototype on any platform | cron with wrapper script |

### Immediate Action Items

1. **Start with the `-p` flag**. Verify `claude -p "Hello" --output-format text` works in a plain bash script before attempting any daemon configuration.

2. **Use a wrapper script**. Never put the `claude` invocation directly in a plist or crontab. A wrapper script allows sourcing nvm, setting PATH, handling lockfiles, and adding timestamps — all impossible in a one-liner.

3. **Test in a minimal shell first**. Run `env -i HOME=$HOME PATH=/usr/bin:/bin bash --norc your-wrapper.sh` to simulate the stripped environment that cron and launchd provide. Fix any "command not found" errors before registering the daemon.

4. **Implement a lockfile**. Prevent concurrent runs with `flock` or a manual lockfile pattern, especially if the agent performs write operations on the project.

5. **Set memory limits**. Use `max_memory_restart` in pm2, `MemoryMax` in systemd, or `--memory` in Docker. Claude Code's Node.js runtime can accumulate memory over repeated runs.

6. **Rotate logs**. launchd, cron, and forever do not rotate logs. Set up `newsyslog` (macOS), `logrotate` (Linux), or pm2's log rotation module to prevent disk exhaustion.

---

## Conclusions

The landscape for running AI CLI tools as background processes is mature and well-supported, but the TTY requirement of interactive tools like Claude Code adds a layer of configuration that is absent from traditional scripts. The `--print` / `-p` flag is the key that unlocks all six patterns examined here.

For macOS developer workstations, LaunchAgents provide the best balance of simplicity, reliability, and native integration. On Linux servers, systemd timers are the clear winner for their logging, dependency management, and missed-run recovery. Teams with Docker-based infrastructure should adopt the supercronic pattern for its clean environment variable handling and container-native design.

The tmux pattern, while not a true daemon, remains the most practical choice for development environments where real-time observability of the agent's actions is important. pm2 occupies a valuable middle ground for teams already embedded in the Node.js ecosystem who want a single tool managing both their application servers and scheduled AI tasks.

---

## References

- [Apple Developer: Creating Launch Daemons and Agents](https://developer.apple.com/library/archive/documentation/MacOSX/Conceptual/BPSystemStartup/Chapters/CreatingLaunchdJobs.html)
- [launchd.info: A launchd Tutorial](https://www.launchd.info/)
- [alvinalexander.com: MacOS launchd plist StartInterval examples](https://alvinalexander.com/mac-os-x/launchd-plist-examples-startinterval-startcalendarinterval/)
- [GitHub Gist: Overview of launchd on macOS](https://gist.github.com/johndturn/09a5c055e6a56ab61212204607940fa0)
- [GitHub: tjluoma/launchd-keepalive](https://github.com/tjluoma/launchd-keepalive)
- [ArchWiki: systemd/Timers](https://wiki.archlinux.org/title/Systemd/Timers)
- [Entroware: Managing Scheduled Tasks with Systemd Timers](https://docs.entroware.com/posts/linux-systemd-timers/)
- [Blunix: Ultimate Tutorial About Linux Systemd Timers](https://www.blunix.com/blog/ultimate-tutorial-about-systemd-timers.html)
- [opensource.com: Use systemd timers instead of cronjobs](https://opensource.com/article/20/7/systemd-timers)
- [Thomas Stringer: Why I Prefer systemd Timers Over Cron](https://trstringer.com/systemd-timer-vs-cronjob/)
- [Baeldung: The PATH Variable for Cron Jobs](https://www.baeldung.com/linux/cron-jobs-path)
- [Baeldung: How to Load Environment Variables in a Cron Job](https://www.baeldung.com/linux/load-env-variables-in-cron-job)
- [Cronitor: Crontab Environment Variables Guide](https://cronitor.io/guides/cron-environment-variables)
- [tao-of-tmux: Scripting tmux](https://tao-of-tmux.readthedocs.io/en/latest/manuscript/10-scripting.html)
- [Princeton Handbook: Using tmux for persistent sessions](https://brainhack-princeton.github.io/handbook/content_pages/hack_pages/tmux.html)
- [PM2 Documentation: Ecosystem File](https://pm2.keymetrics.io/docs/usage/application-declaration/)
- [PM2 Documentation: Environment Variables Best Practices](https://pm2.io/docs/runtime/best-practices/environment-variables/)
- [bitdoze.com: Mastering Environment Variables in PM2](https://www.bitdoze.com/pm2-env-vars/)
- [oneuptime.com: How to Use PM2 for Process Management](https://oneuptime.com/blog/post/2026-01-22-nodejs-pm2-process-management/view)
- [GitHub: aptible/supercronic](https://github.com/aptible/supercronic)
- [oneuptime.com: How to Run Cron Jobs Inside Docker Containers](https://oneuptime.com/blog/post/2026-01-06-docker-cron-jobs/view)
- [Claude Code Docs: Run Claude Code programmatically (headless)](https://code.claude.com/docs/en/headless)
- [ClaudeLog: What is the --print Flag in Claude Code](https://claudelog.com/faqs/what-is-print-flag-in-claude-code/)
- [GitHub: Claude Code TTY bug issue #9026](https://github.com/anthropics/claude-code/issues/9026)
- [angelo-lima.fr: CI/CD and Headless Mode with Claude Code](https://angelo-lima.fr/en/claude-code-cicd-headless-en/)
- [SFEIR Institute: Headless Mode and CI/CD Tutorial](https://institute.sfeir.com/en/claude-code/claude-code-headless-mode-and-ci-cd/tutorial/)
- [GitHub Blog: Automate repository tasks with GitHub Agentic Workflows](https://github.blog/ai-and-ml/automate-repository-tasks-with-github-agentic-workflows/)
- [betterstack.com: Preventing and Debugging Memory Leaks in Node.js](https://betterstack.com/community/guides/scaling-nodejs/high-performance-nodejs/nodejs-memory-leaks/)
- [freedesktop.org: systemd.service documentation](https://www.freedesktop.org/software/systemd/man/latest/systemd.service.html)
- [lucaspin.medium.com: Where is my PATH, launchD?](https://lucaspin.medium.com/where-is-my-path-launchd-fc3fc5449864)

---

*Report generated: 2026-02-27*

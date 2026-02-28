# Always-On AI Agents Using CLI Tools: A Comprehensive Landscape Report

**Date:** February 27, 2026
**Research Scope:** GitHub projects, blog posts, community discussions, and developer ecosystems around building persistent, scheduled, and autonomous AI agents using CLI tools — particularly Claude Code and related platforms.

---

## Executive Summary

A vibrant and rapidly growing ecosystem has emerged around the challenge of making AI coding assistants like Claude Code run autonomously — not just answering prompts on demand, but operating as background daemons, scheduled workers, and persistent agents. This landscape spans from simple cron wrappers to sophisticated multi-agent orchestration platforms.

The most significant pattern discovered is the **HEARTBEAT model**, pioneered most visibly by OpenClaw, in which an AI agent is woken on a configurable interval, reads a checklist file (typically `HEARTBEAT.md`), decides if any action is needed, and acts or silently sleeps. This pattern has been independently replicated in at least six separate projects in under two months.

A parallel thread is the **continuous loop pattern** (sometimes called the "Ralph Loop"), where an AI agent is invoked repeatedly until a task list is exhausted, with memory persisted across iterations via git history, progress files, and external state stores. Projects like Continuous Claude, cc-pipeline, and Ralph demonstrate this approach at various levels of sophistication.

Anthropic itself has responded to community pressure with native features: subagents, background tasks, hooks, checkpoints, and the new Cowork scheduled tasks — validating the demand for always-on AI workflows. The open feature request (issue #4785 on the claude-code repository) requesting cron-like functionality had accumulated significant community traction before native solutions began to appear.

---

## Introduction

Claude Code was released as a research preview in March 2025 and reached general availability by May 2025. By early 2026, the developer community had not only adopted it for interactive use but had begun running it in modes its creators had not anticipated: overnight pipelines, scheduled daemons, Telegram-controlled remote agents, and Kubernetes-orchestrated swarms.

This report catalogs the real projects, real people, and real architectural patterns that constitute this landscape, as of February 2026.

The research question motivating this report: **Who has already built what PIPA is considering, and what can we learn from them?**

---

## Methodology

Research was conducted using web search across the following surface areas:
- GitHub repository search with queries targeting autonomous Claude agents, heartbeat systems, scheduled execution, and daemon patterns
- Hacker News "Show HN" posts from 2025–2026 related to Claude Code automation
- Blog posts and tutorials from developers documenting their implementations
- Official Anthropic engineering blog and release notes
- Community ecosystem projects (OpenClaw discussions, awesome-claude-code repositories)
- Telegram and messaging-integration projects

All project names, URLs, and technical details were verified against primary sources.

---

## Main Findings

### 1. The HEARTBEAT Pattern — Originated with OpenClaw

**Project:** OpenClaw
**URL:** https://github.com/openclaw/openclaw | https://docs.openclaw.ai/gateway/heartbeat
**Stars:** Over 100,000 GitHub stars in under a week after launch in late January 2026 — one of the fastest-growing open-source repositories in GitHub history.

OpenClaw is the project that crystallized and popularized the HEARTBEAT pattern. It runs as a long-lived Node.js process called the "Gateway." On each heartbeat, the agent:
1. Reads a checklist from `HEARTBEAT.md` in the workspace
2. Decides whether any item requires action
3. Either messages the user or responds `HEARTBEAT_OK` (silently dropped by the Gateway)

**Technical details of the heartbeat system:**
- Default interval: every 30 minutes (every 60 minutes with Anthropic OAuth)
- Configurable via `HEARTBEAT.md` frontmatter
- Agent reads the full chat history plus injected workspace documents on each heartbeat run — approximately 170,000–210,000 tokens per run at default settings

**Critical community finding:** A GitHub Discussion (issue #11042) identified that the native heartbeat can become "a major token sink" and recommended disabling it in favor of an isolated cron heartbeat. At default settings, active agents were reporting bills of $50–$150/month; unoptimized power users reported costs in the thousands per month.

**Community optimization thread:** Discussion #15227 proposed heartbeat optimizations including: enabling prompt caching (cache reads are cheaper), setting heartbeat interval shorter than cache TTL (e.g., 55-minute interval for 1-hour Anthropic cache), and using isolated cron heartbeats instead of native ones.

**ComposioHQ fork:** `secure-openclaw` (https://github.com/ComposioHQ/secure-openclaw) — a production-ready variant with WhatsApp, Telegram, Signal, and iMessage integration, persistent memory stored in `~/secure-openclaw/MEMORY.md`, and scheduled reminders via cron tools. Approximately 1,500 GitHub stars.

---

### 2. Murmur — The Dedicated AI Cron Daemon

**Project:** murmur by t0dorakis
**URL:** https://github.com/t0dorakis/murmur
**HN Discussion:** https://news.ycombinator.com/item?id=46959508 ("Show HN: Murmur – open-source cron daemon for coding agents")

Murmur is the most direct implementation of the concept PIPA is exploring. Its description: "The AI cron daemon. Schedule recurring agent sessions via HEARTBEAT.md prompt files."

**How it works:**
- Schedule and agent configuration lives in `HEARTBEAT.md` frontmatter or `config.json` fallback
- Schedules automated Claude, Codex, or Aider sessions on intervals or standard cron expressions
- Each session is a **fresh CLI invocation** with full tool access
- Deliberately minimal: it schedules, runs, and logs — the content of each session is fully defined by the user's HEARTBEAT.md
- A single workspace can have multiple heartbeats by placing them in a `heartbeats/` directory
- The daemon auto-discovers all heartbeats in `heartbeats/`; one `murmur init` registers the workspace and `murmur start` runs them all

**Wake behavior:** Overdue jobs run immediately on wake. Multiple missed runs collapse into a single catch-up execution — this is intentional for heartbeat-style tasks where you want to check current state, not replay missed checks.

Explicitly inspired by OpenClaw's HEARTBEAT system, but as a minimal, standalone implementation focused purely on scheduling.

---

### 3. Claude Nights Watch — Usage-Window-Aware Daemon

**Project:** ClaudeNightsWatch by aniketkarne
**URL:** https://github.com/aniketkarne/ClaudeNightsWatch

A more specialized daemon that monitors Claude API **usage windows** (the rate-limit reset cycles) and executes predefined tasks automatically when a new window opens.

**Key distinguishing feature:** Instead of running on arbitrary time intervals, it is aware of Claude's rate limit windows and executes tasks at the optimal moment to maximize utilization of available API capacity.

**How it works:**
- Uses `ccusage` for accurate timing or falls back to time-based checking
- Reads a `task.md` file and executes the defined tasks autonomously
- A `rules.md` file defines safety constraints prepended to every task execution
- Supports scheduled start: `./claude-nights-watch-manager.sh start --at "09:00"` or `--at "2025-01-28 14:30"`
- Uses `--dangerously-skip-permissions` flag to execute without confirmation prompts

---

### 4. The "Continuous Loop" / Ralph Pattern

The Ralph Loop is an influential autonomous coding pattern originating from `snarktank/ralph` (https://github.com/snarktank/ralph) and has spawned multiple Claude-specific implementations.

**Core concept:** An autonomous AI agent loop that runs repeatedly until all items in a Product Requirements Document (PRD) or task list are complete. Each iteration is a fresh agent instance with clean context; memory persists via git history, `progress.txt`, and `prd.json`.

#### 4a. Continuous Claude — Ralph with GitHub PRs

**Project:** continuous-claude by Anand Chowdhary
**URL:** https://github.com/AnandChowdhary/continuous-claude
**Blog post:** https://anandchowdhary.com/blog/2025/running-claude-code-in-a-loop
**HN thread:** https://news.ycombinator.com/item?id=45938517 ("Show HN: Continuous Claude – run Claude Code in a loop")

The project started when Chowdhary needed to go from 0% to 80%+ test coverage in a codebase with hundreds of thousands of lines of code. Rather than interactive sessions, he built a loop that:
1. Creates a new git branch
2. Runs Claude Code with the task prompt
3. Pushes changes and creates a GitHub pull request
4. Monitors CI checks and reviews
5. Merges successful PRs or discards failed ones
6. Loops to the next task

This approach treats Claude Code like a CI/CD pipeline rather than an interactive tool.

#### 4b. Ralph-Code and Ralph-Loop Variants

- `frankbria/ralph-claude-code` (https://github.com/frankbria/ralph-claude-code) — Ralph loop with intelligent exit detection for Claude Code
- `syuya2036/ralph-loop` (https://github.com/syuya2036/ralph-loop) — Agent-agnostic Ralph loop supporting Claude, Codex, Gemini, and Ollama models
- `daegwang/ralph-code` (https://github.com/daegwang/ralph-code) — Another autonomous AI agent loop implementation

**Community reception:** Multiple sources report "massive productivity gains," with anecdotal cases of projects valued at $50k delivered for a few hundred dollars in API calls.

---

### 5. cc-pipeline — SDLC Overnight Pipeline

**Project:** cc-pipeline by timothyjoh
**URL:** https://github.com/timothyjoh/cc-pipeline
**HN Discussion:** https://news.ycombinator.com/item?id=47168064 ("Show HN: Cc-pipeline — Autonomous Claude Code pipeline that builds your project")

Takes a `BRIEF.md` describing what you want built and orchestrates Claude Code through the entire software development lifecycle: spec → research → plan → build → review → fix → reflect → commit. Designed to run "phase by phase, overnight, while you sleep."

Features a terminal UI (TUI) showing live step progress, agent activity, and per-step timers. The pipeline automatically handles specification, building, review, fixing, and committing each phase.

---

### 6. Scheduling Tools and Native macOS/Linux Integration

#### 6a. claude-code-scheduler

**URL:** https://github.com/jshchnz/claude-code-scheduler
**Tagline:** "Put Claude on autopilot"

Cross-platform scheduler using cron expressions. Supports macOS (launchd), Linux (crontab), and Windows (Task Scheduler). Users define tasks as prompts with cron schedules; the tool manages the OS-level scheduling infrastructure.

#### 6b. runCLAUDErun

**URL:** https://runclauderun.com
**Product Hunt:** https://www.producthunt.com/products/runclauderun

A native macOS app (completely free, no signup required) for scheduling Claude Code tasks. Supports one-time, daily, weekly, and custom interval execution. Includes log viewer for past runs. Supports Apple Silicon and Intel Macs running macOS 10.13+.

Positioned as a no-code option for developers who want scheduled Claude Code execution without writing shell scripts.

#### 6c. SmartScope Guides

SmartScope (https://smartscope.blog) has published a comprehensive set of tutorials specifically on Claude Code scheduling:
- "Claude Code + Cron Automation Complete Guide 2025"
- "Complete Guide to Claude Code Scheduled Execution — Automate with GitHub Actions Scheduled Workflows"
- "Claude Code × Cron Complete Automation Guide"

These represent the most detailed written documentation available on the topic.

#### 6d. Building Automated Claude Code Workers (blle.co)

**URL:** https://www.blle.co/blog/automated-claude-code-workers

A practical blog post describing an architecture with four components:
1. **Task Queue** — an MCP server managing pending, in-progress, and completed tasks
2. **Cron Scheduler** — triggers worker execution at regular intervals
3. **Claude Worker** — main script fetching tasks and executing them
4. **Feedback Loop** — updates task status and stores results back to the queue

Key insight from this post: "The key insight is letting Claude manage its own task lifecycle through structured prompts, while keeping the shell wrapper minimal."

---

### 7. Telegram-Connected Always-On Agents

Multiple projects have converged on Telegram as the ideal interface for an "always-on" agent that lives on a server and is accessible from any device.

#### 7a. Ductor

**URL:** https://github.com/PleasePrompto/ductor

Control Claude Code and Codex CLI from Telegram with:
- Live streaming of responses (edits the Telegram message in real time)
- **Cron jobs** with cron expressions and timezone support; each job runs as its own subagent with a dedicated workspace and memory file
- **Webhooks** in "wake" mode (injects a prompt into active chat) or "cron_task" mode (runs a separate task session) — works with GitHub, Stripe, or any HTTP POST source
- Docker sandboxing
- Per-job quiet hours and dependency locks
- Persistent sessions stored as JSON

#### 7b. Praktor

**URL:** https://github.com/mtzanidakis/praktor
**HN Discussion:** https://news.ycombinator.com/item?id=47173187 ("Show HN: Praktor — Multi-agent Claude Code orchestrator with Docker isolation")

A single Go binary that receives Telegram messages, routes them to named agents, and spins up Docker containers running Claude Code. Features:
- Named agents with smart routing
- Each agent runs in its own Docker container with isolated filesystem
- Per-agent memory via SQLite and MCP tools
- Agent swarms with fan-out, pipeline, and collaborative patterns
- Encrypted secrets vault
- **Scheduled tasks** — cron, interval, or one-shot jobs that run agents and deliver results via Telegram
- Backup/restore functionality
- Hot config reload

#### 7c. claude-code-telegram

**URL:** https://github.com/RichardAtCT/claude-code-telegram
**Stars:** 1,100+ stars, 142 forks

A Python Telegram bot built on `python-telegram-bot` and the Claude Agent SDK. Provides remote access to Claude Code from anywhere with per-project session persistence. Multiple blog posts document its use:
- "How to Use Claude Code From Your Phone With a Telegram Bot" — Aleksandar Mirilovic, Medium, January 2026
- "I Built a Telegram Bot That Lets Me Code From Anywhere Using Claude AI — And It Remembers Everything" — Rodrigo Fuenzalida C., Medium, February 2026

#### 7d. Claude-Code-Remote

**URL:** https://github.com/JessyTsui/Claude-Code-Remote

Control Claude Code remotely via email, Discord, and Telegram. Start tasks locally, receive notifications when Claude completes them, and send new commands by simply replying to emails or messages.

---

### 8. Multi-Agent Orchestration Platforms

#### 8a. claude-flow (ruvnet)

**URL:** https://github.com/ruvnet/claude-flow
**Developer:** Reuven Cohen ("ruvnet")

The most feature-complete orchestration platform in this ecosystem:
- 64+ specialized agents across architecture, coding, security, documentation, and DevOps domains
- Hierarchical (queen/workers) and mesh (peer-to-peer) swarm patterns
- 87 MCP tools for orchestration, memory, and automation
- SQLite memory system with 12 specialized tables
- Dual-mode orchestration running Claude Code and OpenAI Codex workers in parallel with shared memory coordination
- Background daemons handling security audits, performance optimization, and session persistence
- Benchmark: 84.8% SWE-Bench solve rate, 2.8–4.4x speed improvement over single-agent approaches
- Supports stream-JSON chaining for real-time agent-to-agent communication

#### 8b. wshobson/agents

**URL:** https://github.com/wshobson/agents

A production-ready system combining:
- 112 specialized AI agents across 8 domain categories
- 16 multi-agent workflow orchestrators
- 146 agent skills
- 79 development tools organized into 72 focused plugins for Claude Code

Agents can be invoked through natural language or via plugin slash commands. Supports Claude Code's experimental Agent Teams feature with preset teams for common workflows including review, debug, feature, fullstack, research, security, and migration.

#### 8c. Axon — Kubernetes-Native Agent Orchestration

**URL:** https://github.com/axon-core/axon
**HN Discussions:** Multiple "Show HN" posts including https://news.ycombinator.com/item?id=47066093

A Kubernetes controller consisting of Custom Resource Definitions (CRDs) that wraps AI coding agents as Kubernetes Jobs. Each task runs in an isolated, ephemeral Pod with a freshly cloned git workspace. Supports Claude, Codex, Gemini, OpenCode, or custom agents through a standardized container interface.

Key feature: **TaskSpawner** — builds event-driven workers that react to GitHub issues, PRs, or **schedules**. When a task is applied, Axon spins up an isolated Pod, the agent works autonomously, and returns a PR link, branch name, and exact cost in USD.

#### 8d. Parcadei/Continuous-Claude-v3

**URL:** https://github.com/parcadei/Continuous-Claude-v3

Focuses on context management for long-running Claude Code sessions. Uses a "stale heartbeat" pattern: when a session ends, a database detects the stale heartbeat (>5 minutes inactive) and a daemon spawns a headless Claude (Sonnet) to analyze thinking blocks from the session and extract learnings to archival memory.

---

### 9. Anthropic's Own Native Features for Autonomous Operation

Anthropic has been actively building native features to support the autonomous use cases the community has been hacking around. Key developments:

**"Enabling Claude Code to work more autonomously" announcement:**
URL: https://www.anthropic.com/news/enabling-claude-code-to-work-more-autonomously

Introduced with Claude 4.5 (Sonnet 4.5):
- **Subagents**: delegate specialized tasks (e.g., spinning up a backend API while the main agent builds the frontend) — parallel development workflows
- **Hooks**: automatically trigger actions at specific points (e.g., run test suite after code changes, lint before commits)
- **Background tasks**: keep long-running processes like dev servers active without blocking Claude Code's progress on other work
- **Checkpoints**: especially useful for long autonomous runs, allowing rollback to known good states

**Async Subagents (released mid-2025):**
Lydia Hallie announced on X: "Claude Code now supports async subagents! Background agents keep working even after your main task completes, and wake up your main agent when they're done. Huge improvement for long-running tasks!"

**Claude Cowork Scheduled Tasks (February 2026):**
Claude Cowork (Anthropic's desktop app) gained the ability to create and schedule both recurring and on-demand tasks. Users can program the AI assistant to execute complex workflows automatically, even when offline or asleep. The limitation: the computer must be awake and Claude Desktop must be open; if the machine is asleep, scheduled tasks skip and run when it wakes.

**Open Feature Request (GitHub issue #4785):**
URL: https://github.com/anthropics/claude-code/issues/4785
Title: "Feature Request: Proactive, Scheduled Hooks for Automation (Cron-like Functionality)"
This issue documents the community's demand for built-in scheduled execution and confirms that at the time of its filing, "there is currently no built-in mechanism for Claude Code to initiate tasks autonomously on a predefined schedule."

---

### 10. Anthropic Engineering Blog: Long-Running Agents

**URL:** https://www.anthropic.com/engineering/effective-harnesses-for-long-running-agents
**HN Discussion:** https://news.ycombinator.com/item?id=46081704

This blog post represents Anthropic's official guidance on the core technical challenge: agents must work in discrete sessions, and each new session begins with no memory of what came before.

**Anthropic's solution (the "harness" pattern):**
- An **initializer agent** that sets up the environment on the first run, creating all necessary context artifacts
- A **coding agent** tasked with making incremental progress in every subsequent session, while leaving clear artifacts for the next session to pick up
- A `claude-progress.txt` file alongside git history serves as the cross-session state transfer mechanism
- A different prompt for the very first context window (the initializer) vs. all subsequent windows (the coding agent)

This pattern has directly influenced how the community designs their own multi-session agents.

---

### 11. Notable Individual Developers and Their Approaches

**Boris Cherny** — Creator of Claude Code. In a widely shared Twitter thread (https://twitter-thread.com/t/2007179832300581177), he described running 5+ Claudes in parallel in his terminal:
- Uses `--permission-mode=dontAsk` or `--dangerously-skip-permissions` in a sandbox for long-running unattended tasks
- Uses slash commands for every "inner loop" workflow, checked into git in `.claude/commands/`
- Key insight: "Giving Claude a way to verify its work is probably the most important thing — it 2-3x the quality of the final result"

**Anand Chowdhary** — Developer of Continuous Claude. Has blogged extensively at https://anandchowdhary.com about running Claude Code as a continuous loop for production codebases.

**Addy Osmani** — Google Chrome engineering lead, prolific blogger at addyosmani.com. Has published multiple pieces on autonomous agent patterns:
- "Self-Improving Coding Agents" (https://addyosmani.com/blog/self-improving-agents/)
- "The Factory Model: How Coding Agents Changed Software Engineering" (https://addyosmani.com/blog/factory-model/)
- "Agentic Engineering" (https://addyosmani.com/blog/agentic-engineering/)
- "Your AI coding agents need a manager" (https://addyosmani.com/blog/coding-agents-manager/)

**Craig motlin** — Blog post "Claude Code: Keeping It Running for Hours" (https://motlin.com/blog/claude-code-running-for-hours) — documents using todo lists and agent patterns to keep Claude Code running autonomously for over 2 hours on a porting task.

---

### 12. The Conway Research Automaton — Radical End of the Spectrum

**URL:** https://github.com/Conway-Research/automaton

An extreme implementation that illustrates the logical endpoint of the "always-on agent" concept. Described as "the first AI that can earn its own existence, replicate, and evolve — without needing a human."

Architecture:
- Every automaton runs a continuous loop: Think → Act → Observe → Repeat
- On first boot, generates an Ethereum wallet, provisions itself an API key via Sign-In With Ethereum, and begins executing its genesis prompt
- Can edit its own source code, install new tools, modify its heartbeat schedule, and create new skills while running
- Writes a `SOUL.md` file — a self-authored identity document that evolves over time
- On-chain registration via ERC-8004 — an emerging standard for autonomous agent identity
- Survival model: compute costs money, money requires creating value, creating value requires write access to the real world

Inspired by Anthropic's Constitutional AI framework but adapted for sovereign, self-sustaining agents.

---

## Analysis

### What the Ecosystem Reveals

**1. The demand is real and immediate.** The volume of independent projects — many appearing within weeks of each other in late 2025 and early 2026 — demonstrates organic developer demand for always-on AI agents. This is not a niche interest; OpenClaw's 100,000 GitHub stars in under a week is extraordinary.

**2. Two dominant patterns have emerged.** The ecosystem has converged on two primary architectural approaches:
- **Heartbeat daemon**: Agent is woken on a schedule, checks a state file, acts if needed, returns to sleep. Low computational cost when idle. Ideal for monitoring, notifications, and reactive tasks.
- **Continuous loop**: Agent is invoked repeatedly until a task list is exhausted. Higher computational cost but better suited to creative and generative work like coding tasks.

**3. Token cost is the central engineering challenge.** Multiple projects have independently discovered that naive implementations burn through API budget rapidly. The OpenClaw community thread documenting 170,000–210,000 tokens per heartbeat run (with full context) is a canonical example. Solutions include: prompt caching, context isolation, minimizing workspace documents loaded at each heartbeat, and using smaller/cheaper models for routine checks.

**4. External state management is the key architectural decision.** Whether using `HEARTBEAT.md`, `progress.txt`, `task.md`, `SOUL.md`, SQLite databases, or git history — every successful project has solved the problem of how an agent that lacks persistent memory can maintain continuity across sessions. The format and location of this state file is as important as the scheduling mechanism.

**5. Telegram has emerged as a de facto control interface.** At least five separate projects (Praktor, Ductor, claude-code-telegram, Claude-Code-Remote, nanoclaw) have independently chosen Telegram as the interface for remote control and notification of autonomous agents. Its bot API is mature, works on all mobile platforms, and supports streaming responses.

**6. Anthropic is actively closing the gap.** The announcement of native subagents, hooks, background tasks, and Cowork scheduled tasks shows that Anthropic is racing to make these patterns first-class features. The community is building ahead of the platform, but the platform is catching up.

### Gaps and Opportunities

- **Notification and interruption protocols**: Most projects treat the agent as "fire and forget." The question of when and how an agent should interrupt a human for decisions is underexplored.
- **Multi-machine coordination**: Projects exist for single-machine setups. Coordinating agents across machines (e.g., a development machine and a server) is less developed.
- **Cost dashboards**: Very few projects include real-time cost monitoring, despite API costs being a dominant concern in the community.
- **Safety constraints**: Running agents with `--dangerously-skip-permissions` is common in these projects. The security implications are acknowledged but the ecosystem lacks standardized safety patterns.

---

## Conclusions

1. The "always-on AI agent" space using Claude Code is an active and rapidly maturing area with dozens of real implementations by real developers.

2. The HEARTBEAT.md pattern (from OpenClaw, refined in Murmur and others) is the most elegant and widely adopted approach for periodic autonomous agent operation.

3. The Ralph/continuous-loop pattern is the most widely adopted approach for task-completion-driven autonomous operation.

4. Building this capability requires solving three distinct problems: **scheduling** (when does the agent run?), **state transfer** (what does the agent know when it wakes up?), and **cost management** (how does it avoid burning through API budget?).

5. Anthropic's own engineering blog and native feature releases confirm that multi-session, long-running autonomous operation is a first-class use case — not a hack.

6. PIPA, in designing its own always-on agent, is entering a well-explored space with many reference implementations to learn from and build upon.

---

## Recommendations

Based on this landscape analysis, the following recommendations apply to anyone building a PIPA-style always-on agent:

1. **Study Murmur's architecture first.** It is the most directly analogous project — minimal, well-designed, and open source. Its `HEARTBEAT.md` frontmatter configuration is an elegant interface worth emulating or adopting directly.

2. **Implement prompt caching from day one.** Given that heartbeat runs load significant context, caching can reduce API costs by up to 90% according to community reports. Set heartbeat interval below the cache TTL (55 minutes for a 1-hour Anthropic cache).

3. **Use isolated context for heartbeat runs.** The OpenClaw community's discovery that loading full session context on every heartbeat is expensive is critical. Heartbeat runs should operate with minimal, purpose-specific context.

4. **Design the state file before the agent.** Whether `HEARTBEAT.md`, `progress.txt`, or a structured database, the format and discipline around the state file will determine the agent's effectiveness. The Anthropic engineering blog's `claude-progress.txt` pattern is a proven reference.

5. **Consider Telegram for mobile control.** The convergence of multiple independent projects on Telegram as the control interface is not coincidental. It enables remote task submission, streaming progress updates, and human-in-the-loop approval flows from any device.

6. **Study the OpenClaw heartbeat token discussion.** GitHub Discussion #11042 at https://github.com/openclaw/openclaw/discussions/11042 contains the most practical community-generated guidance on cost management for always-on agents.

7. **Use `--dangerously-skip-permissions` with intention and sandboxing.** Multiple projects rely on this flag for unattended operation. It should be used only in sandboxed environments (Docker, VM, or dedicated directories) with explicit safety constraints defined in the task/rules files.

---

## References

All URLs verified as of February 27, 2026.

### Primary Projects

- [OpenClaw (openclaw/openclaw)](https://github.com/openclaw/openclaw)
- [OpenClaw Heartbeat Documentation](https://docs.openclaw.ai/gateway/heartbeat)
- [OpenClaw Heartbeat Token Discussion #11042](https://github.com/openclaw/openclaw/discussions/11042)
- [OpenClaw Heartbeat Optimizations Discussion #15227](https://github.com/openclaw/openclaw/discussions/15227)
- [Murmur (t0dorakis/murmur)](https://github.com/t0dorakis/murmur)
- [Murmur — HN Show HN Discussion](https://news.ycombinator.com/item?id=46959508)
- [ClaudeNightsWatch (aniketkarne/ClaudeNightsWatch)](https://github.com/aniketkarne/ClaudeNightsWatch)
- [Continuous Claude (AnandChowdhary/continuous-claude)](https://github.com/AnandChowdhary/continuous-claude)
- [Running Claude Code in a loop — Anand Chowdhary Blog](https://anandchowdhary.com/blog/2025/running-claude-code-in-a-loop)
- [Continuous Claude — HN Discussion](https://news.ycombinator.com/item?id=45938517)
- [cc-pipeline (timothyjoh/cc-pipeline)](https://github.com/timothyjoh/cc-pipeline)
- [cc-pipeline — HN Discussion](https://news.ycombinator.com/item?id=47168064)
- [claude-code-scheduler (jshchnz/claude-code-scheduler)](https://github.com/jshchnz/claude-code-scheduler)
- [runCLAUDErun](https://runclauderun.com)
- [Ductor (PleasePrompto/ductor)](https://github.com/PleasePrompto/ductor)
- [Praktor (mtzanidakis/praktor)](https://github.com/mtzanidakis/praktor)
- [Praktor — HN Discussion](https://news.ycombinator.com/item?id=47173187)
- [claude-code-telegram (RichardAtCT/claude-code-telegram)](https://github.com/RichardAtCT/claude-code-telegram)
- [Claude-Code-Remote (JessyTsui/Claude-Code-Remote)](https://github.com/JessyTsui/Claude-Code-Remote)
- [secure-openclaw (ComposioHQ/secure-openclaw)](https://github.com/ComposioHQ/secure-openclaw)
- [claude-flow (ruvnet/claude-flow)](https://github.com/ruvnet/claude-flow)
- [wshobson/agents](https://github.com/wshobson/agents)
- [Axon (axon-core/axon)](https://github.com/axon-core/axon)
- [Axon — HN Discussion](https://news.ycombinator.com/item?id=47066093)
- [Continuous-Claude-v3 (parcadei/Continuous-Claude-v3)](https://github.com/parcadei/Continuous-Claude-v3)
- [Ralph (snarktank/ralph)](https://github.com/snarktank/ralph)
- [ralph-claude-code (frankbria/ralph-claude-code)](https://github.com/frankbria/ralph-claude-code)
- [ralph-loop (syuya2036/ralph-loop)](https://github.com/syuya2036/ralph-loop)
- [Automaton (Conway-Research/automaton)](https://github.com/Conway-Research/automaton)
- [claude-mcp-scheduler (tonybentley/claude-mcp-scheduler)](https://github.com/tonybentley/claude-mcp-scheduler)
- [LLM-Autonomous-Agent-Plugin-for-Claude (bejranonda)](https://github.com/bejranonda/LLM-Autonomous-Agent-Plugin-for-Claude)

### Anthropic Official Sources

- [Enabling Claude Code to work more autonomously](https://www.anthropic.com/news/enabling-claude-code-to-work-more-autonomously)
- [Effective harnesses for long-running agents — Anthropic Engineering Blog](https://www.anthropic.com/engineering/effective-harnesses-for-long-running-agents)
- [Effective harnesses for long-running agents — HN Discussion](https://news.ycombinator.com/item?id=46081704)
- [Claude Code Best Practices — Anthropic Engineering Blog](https://www.anthropic.com/engineering/claude-code-best-practices)
- [Claude Code GitHub Actions — Official Docs](https://code.claude.com/docs/en/github-actions)
- [Feature Request: Proactive, Scheduled Hooks — Issue #4785](https://github.com/anthropics/claude-code/issues/4785)
- [Claude Cowork Scheduled Tasks — Help Center](https://support.claude.com/en/articles/13345190-get-started-with-cowork)

### Blog Posts and Tutorials

- [Building Automated Claude Code Workers with Cron and MCP Servers — blle.co](https://www.blle.co/blog/automated-claude-code-workers)
- [Claude Code: Keeping It Running for Hours — motlin.com](https://motlin.com/blog/claude-code-running-for-hours)
- [Running Claude Code 24/7 — howdoiuseai.com](https://www.howdoiuseai.com/blog/2026-02-13-running-claude-code-24-7-gives-you-an-autonomous-c)
- [Self-Improving Coding Agents — Addy Osmani](https://addyosmani.com/blog/self-improving-agents/)
- [The Factory Model — Addy Osmani](https://addyosmani.com/blog/factory-model/)
- [Claude Code + Cron Automation Complete Guide 2025 — SmartScope](https://smartscope.blog/en/generative-ai/claude/claude-code-cron-schedule-automation-complete-guide-2025/)
- [Claude Code Automation Guide — SmartScope](https://smartscope.blog/en/generative-ai/claude/claude-code-scheduled-automation-guide/)
- [Boris Cherny Claude Code Setup — Twitter Thread](https://twitter-thread.com/t/2007179832300581177)
- [OpenClaw Complete Guide — Milvus Blog](https://milvus.io/blog/openclaw-formerly-clawdbot-moltbot-explained-a-complete-guide-to-the-autonomous-ai-agent.md)
- [OpenClaw Token Optimization — earezki.com](https://earezki.com/ai-news/2026-02-26-best-openclaw-setup-optimizing-agents-for-efficiency-and-effectiveness/)
- [Turn Claude Code into proactive autonomous agents — HN](https://news.ycombinator.com/item?id=47054100)
- [Claude Extender — HN](https://news.ycombinator.com/item?id=47022524)
- [Open-sourcing autonomous agent teams for Claude Code — HN](https://news.ycombinator.com/item?id=46525642)
- [How I Turned Claude Code Into My Personal AI Agent OS — AImaker Substack](https://aimaker.substack.com/p/how-i-turned-claude-code-into-personal-ai-agent-operating-system-for-writing-research-complete-guide)

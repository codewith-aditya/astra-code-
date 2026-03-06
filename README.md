<div align="center">

```
╔══════════════════════════════════════════════════════════╗
║                        A S T R A                        ║
║         Elite AI Software Engineering Agent             ║
║              12 Tools · 34 Commands · 21 Modules        ║
╚══════════════════════════════════════════════════════════╝
```

**Not a chatbot. A principal engineer that lives in your terminal.**

> 🥊 *Built to challenge Claude Code. Open source. Python. Yours.*

[![Python](https://img.shields.io/badge/Python-3.10+-blue?style=for-the-badge&logo=python&logoColor=white)](https://python.org)
[![Claude](https://img.shields.io/badge/Claude-Sonnet%20%7C%20Opus-orange?style=for-the-badge&logo=anthropic&logoColor=white)](https://anthropic.com)
[![OpenAI](https://img.shields.io/badge/OpenAI-GPT--4o-412991?style=for-the-badge&logo=openai&logoColor=white)](https://openai.com)
[![License](https://img.shields.io/badge/License-MIT-green?style=for-the-badge)](LICENSE)
[![Version](https://img.shields.io/badge/Version-1.0.0-red?style=for-the-badge)]()
[![Status](https://img.shields.io/badge/Status-Active-brightgreen?style=for-the-badge)]()
[![Claude Code Killer](https://img.shields.io/badge/Claude%20Code-Challenger%20👊-black?style=for-the-badge)]()

</div>

---

## 🧠 What is ASTRA?

ASTRA is a **Claude Code-style AI coding agent** that runs entirely in your terminal. Give it a task — it explores your codebase, makes a plan, executes changes, verifies the result, and reports back. No hand-holding. No fluff.

It thinks like a **principal engineer**: reads before touching, plans before executing, verifies before reporting.

---

## 🥊 ASTRA vs Claude Code

| Feature | ASTRA | Claude Code |
|---------|-------|-------------|
| **Open Source** | ✅ MIT License | ❌ Closed source |
| **Self-hosted** | ✅ Runs on your machine | ❌ Anthropic servers |
| **Multi-LLM** | ✅ Claude + GPT-4o + custom proxy | ⚠️ Claude only |
| **Custom API Proxy** | ✅ Any base URL | ❌ No |
| **Plugin System** | ✅ Drop `.py` → auto-registered | ❌ No |
| **MCP Support** | ✅ Full MCP server management | ✅ Yes |
| **Subagents** | ✅ Foreground + background | ✅ Yes |
| **Plan Mode** | ✅ `/plan` — read-only, zero writes | ✅ Yes |
| **Sandbox Mode** | ✅ Fully isolated execution | ⚠️ Limited |
| **Checkpoint / Rewind** | ✅ Any prior state, instant | ❌ No |
| **Session Save/Load** | ✅ Save, load, fork, rename | ⚠️ Limited |
| **Git Worktree** | ✅ Parallel branches built-in | ❌ No |
| **Hooks System** | ✅ pre/post tool, on-error | ❌ No |
| **Rules System** | ✅ `.astra/rules/*.md` | ✅ CLAUDE.md |
| **Persistent Memory** | ✅ Cross-session memory | ✅ Yes |
| **Cost Tracking** | ✅ Real-time tokens + $ | ✅ Yes |
| **Slash Commands** | ✅ **34 commands** | ⚠️ Fewer |
| **Tools** | ✅ **12 tools** | ✅ Similar |
| **Headless / Pipe Mode** | ✅ `--pipe` flag | ✅ Yes |
| **JSON Output** | ✅ `--output-format json` | ✅ Yes |
| **Price** | ✅ **Free** (your API key) | ❌ Paid subscription |

> ASTRA is what Claude Code would be if it were **open, extensible, and yours.**

```
$ python astra "add JWT authentication to the FastAPI app"

╔══════════════════════════════════════════════════════════╗
║                        A S T R A                   v1.0 ║
╚══════════════════════════════════════════════════════════╝

🔍 ANALYSIS     Scanning project structure...
                Found: FastAPI app, no auth middleware detected

📂 FILES        CREATE  • src/auth/jwt.py
                CREATE  • src/middleware/auth_middleware.py
                MODIFY  • src/main.py
                MODIFY  • requirements.txt

📋 PLAN         5 steps identified

⚙️  EXECUTING   [1/5] glob_search → located FastAPI entry point
                [2/5] read_file   → read src/main.py (142 lines)
                [3/5] write_file  → created src/auth/jwt.py ✓
                [4/5] multi_edit  → patched src/main.py ✓
                [5/5] run_command → pytest passed (12/12) ✓

✅ RESULT       JWT auth added. All tests passing.
                Tokens: 4,821 in / 1,203 out — $0.0041
```

---

## ⚡ Quickstart

### 1. Clone & Install

```bash
git clone https://github.com/yourusername/astra.git
cd astra
pip install -r requirements.txt
```

### 2. Set API Key

```bash
# For Claude (recommended)
export ANTHROPIC_API_KEY=sk-ant-...

# For GPT-4o
export OPENAI_API_KEY=sk-...
```

### 3. Run ASTRA

```bash
python astra
```

That's it. You're in. 🔥

---

## 🚀 How to Use

### ▶ Basic — Just Talk to It

Navigate to any project and run:

```bash
cd your-project/
python astra
```

Then type your task naturally:

```
You: fix the bug in the payment module where decimal rounding fails
You: refactor the database layer to use async SQLAlchemy
You: add unit tests for all functions in src/utils.py
You: find all places where we're not handling None and fix them
```

ASTRA will explore, plan, execute, and verify — all on its own.

---

### ▶ One-Shot Mode — Single Task, Then Exit

```bash
python astra "add input validation to all API endpoints"
```

---

### ▶ Pipe Mode — Headless / CI Friendly

```bash
echo "update all dependencies to latest versions" | python astra --pipe
```

Perfect for CI/CD pipelines and automation scripts.

---

### ▶ JSON Output — For Scripting & Integrations

```bash
python astra --output-format json "list all TODO comments in the codebase"
```

---

### ▶ Limit Agent Turns — Cost Control

```bash
python astra --max-turns 5 "cleanup unused imports across the project"
```

---

### ▶ Plan Mode — See the Plan, Don't Execute

```bash
/plan add Redis caching to the product listing endpoint
```

ASTRA produces a full implementation plan — files, steps, risks — without touching a single file.

```
📂 FILES IMPACTED
  MODIFY  • src/api/products.py
  CREATE  • src/cache/redis_client.py
  MODIFY  • requirements.txt

📋 IMPLEMENTATION PLAN
  1. Install redis-py dependency
     → Tool:    write_file
     → Where:   requirements.txt
     → Outcome: redis>=5.0 added

  2. Create Redis client module
     → Tool:    write_file
     → Where:   src/cache/redis_client.py
     → Outcome: Singleton Redis client with connection pooling

  3. Wrap product listing with cache decorator
     → Tool:    edit_file
     → Where:   src/api/products.py → get_products()
     → Outcome: Cache hit returns in <5ms, miss fetches DB + stores

⚠️  RISKS
  • Redis not running → graceful fallback to DB needed
  • Cache invalidation on product update → hook into update endpoint

📌 SUMMARY
  Adds Redis caching to get_products() with 5min TTL and graceful
  fallback. Two files created, one modified. Watch for stale cache
  on product updates.
```

---

### ▶ Sandbox Mode — Safe Experimentation

```bash
/sandbox
```

Runs commands in an isolated environment. Nothing escapes. Safe for untrusted or destructive scripts.

---

### ▶ Subagents — Parallel Execution

```
You: split this — agent 1 write tests, agent 2 write docs
```

```
🤖 Agent "write-tests"  → running in background
🤖 Agent "write-docs"   → running in background
✅ Agent "write-tests"  → completed (47 tests written)
✅ Agent "write-docs"   → completed (README + docstrings done)
```

---

### ▶ Memory — Persistent Instructions

```bash
/remember always use async functions in this project
/remember this codebase uses snake_case everywhere
/forget always use async functions
```

Saves to `.astra/memory.json` — survives every restart.

---

### ▶ Checkpoint & Rewind

ASTRA auto-checkpoints before every risky operation.

```bash
/rewind       # go back one step
/rewind 3     # go back 3 checkpoints
```

---

### ▶ Git Workflow

```bash
/diff         # see what changed
/commit       # git add + commit in one shot
/pr           # push branch + open GitHub PR instantly
/worktree     # spin up parallel git branch
```

---

### ▶ Switch Models Anytime

```bash
/model sonnet     # Claude Sonnet — fast, smart (default)
/model opus       # Claude Opus  — most powerful
/model haiku      # Claude Haiku — fastest, cheapest
/model gpt4o      # GPT-4o       — OpenAI alternative
/model llama3     # Ollama local — free, offline
/model codellama  # Ollama local — best for code
```

---

### ▶ 🦙 Ollama — Run 100% Locally, Zero API Cost

ASTRA connects to Ollama via `ANTHROPIC_BASE_URL`. No subscription. No cloud. Fully offline.

**Step 1 — Install & pull a model:**
```bash
# Install Ollama
curl -fsSL https://ollama.ai/install.sh | sh

# Pull your model
ollama pull llama3       # general purpose
ollama pull codellama    # best for coding tasks
ollama pull mistral      # fast + smart
```

**Step 2 — Set env vars:**
```bash
export ANTHROPIC_BASE_URL=http://localhost:11434/v1
export ANTHROPIC_API_KEY=ollama    # any string — Ollama ignores it
```

**Step 3 — Run ASTRA:**
```bash
python astra
/model codellama    # switch to local model
```

**One-shot inline:**
```bash
ANTHROPIC_BASE_URL=http://localhost:11434/v1 \
ANTHROPIC_API_KEY=ollama \
python astra "refactor this function to be async"
```

**Or put it in `.env`:**
```dotenv
ANTHROPIC_BASE_URL=http://localhost:11434/v1
ANTHROPIC_API_KEY=ollama
```

> 💡 `codellama` for coding. `llama3` for reasoning. `mistral` for speed.

---

### ▶ 🔌 Custom API Proxy (LiteLLM, Orbit, OpenRouter)

Any OpenAI-compatible proxy works:

```dotenv
ANTHROPIC_BASE_URL=https://your-proxy.com/v1
ANTHROPIC_API_KEY=your_key_here
```

Works with LiteLLM, Orbit, OpenRouter, LocalAI — anything with an OpenAI-compatible endpoint.

---

## 🛠️ All 12 Tools

| # | Tool | What it does |
|---|------|-------------|
| 1 | `read_file` | Read any file with line numbers, offset + limit |
| 2 | `write_file` | Create a new file or fully overwrite |
| 3 | `edit_file` | Surgical search-and-replace with ambiguity detection |
| 4 | `multi_edit` | Multiple edits to one file in a single call |
| 5 | `list_files` | Directory listing with glob filter + depth limit |
| 6 | `search_code` | Semantic search across entire codebase |
| 7 | `grep_search` | Regex/literal search — fast, precise, line-level |
| 8 | `glob_search` | Find files by pattern (`**/*.test.ts`) |
| 9 | `run_command` | Execute shell commands (safety blocklist enforced) |
| 10 | `web_search` | Search the web for docs, errors, or solutions |
| 11 | `web_fetch` | Fetch and read a specific URL |
| 12 | `ask_user` | Ask you a question when intent is ambiguous |

> **Tool Priority:** `glob_search` → `grep_search` → `read_file` — always in this order.

---

## ⌨️ All 34 Slash Commands

### Core
| Command | What it does |
|---------|-------------|
| `/help` | Show all available commands |
| `/init` | Generate `ASTRA.md` project config |
| `/model` | Switch model (`sonnet` / `opus` / `haiku` / `gpt4o`) |
| `/clear` | Clear conversation + screen |
| `/compact` | Compress context to save tokens |
| `/cost` | Show token usage + dollar cost estimate |
| `/status` | Show repo, model, plugins, memory status |
| `/config` | View or change config live |
| `/exit` | Exit ASTRA |

### Git & Version Control
| Command | What it does |
|---------|-------------|
| `/diff` | Show uncommitted git diff |
| `/commit` | `git add` + commit in one command |
| `/pr` | Push branch + open GitHub PR |
| `/worktree` | Manage git worktrees for parallel branches |
| `/fork` | Fork current session into a new branch |

### Session Management
| Command | What it does |
|---------|-------------|
| `/save` | Save conversation to disk |
| `/load` | Load a saved conversation |
| `/resume` | Resume last session |
| `/rename` | Rename current session |
| `/rewind` | Restore to any prior checkpoint |
| `/export` | Export conversation to file |

### Planning & Execution
| Command | What it does |
|---------|-------------|
| `/plan` | Generate plan without executing anything |
| `/sandbox` | Run next command in isolated sandbox |
| `/agents` | View and manage running subagents |

### Memory & Rules
| Command | What it does |
|---------|-------------|
| `/remember` | Save a permanent instruction (persists across sessions) |
| `/forget` | Remove an entry from memory |
| `/rules` | View active rules from `.astra/rules/` |
| `/permissions` | View + manage what ASTRA can and cannot do |
| `/hooks` | View + configure lifecycle hooks |

### Context & Diagnostics
| Command | What it does |
|---------|-------------|
| `/context` | Visualize live context window token usage |
| `/doctor` | Run full diagnostics — tools, keys, config |
| `/telemetry` | View historical usage stats |

### Extensibility
| Command | What it does |
|---------|-------------|
| `/plugins` | List all loaded plugins |
| `/mcp` | Manage MCP servers + discover external tools |

---

## 🧩 Smart Features

| Feature | Description |
|---------|-------------|
| **ASTRA.md Auto-load** | Project config auto-loads every startup |
| **Persistent Memory** | `/remember` saves across sessions to `.astra/memory.json` |
| **File Backup** | Every edit auto-backed up to `.astra_backups/` |
| **Checkpoint / Rewind** | Restore any prior state instantly |
| **Subagent System** | Foreground + background parallel agents |
| **Plugin System** | Drop `.py` in `.astra/plugins/` — auto-registered |
| **MCP Server Support** | External tool discovery via `/mcp` |
| **Sandbox Mode** | Isolated execution — nothing escapes |
| **Hooks System** | `pre_tool`, `post_tool`, `on_error` lifecycle events |
| **Git Worktree** | Parallel branches without touching main workspace |
| **Context Trimming** | Auto-trim + `/compact` to preserve quality |
| **Cost Tracking** | Real-time tokens + dollar estimate after every run |
| **Dual LLM Support** | Anthropic Claude + OpenAI GPT-4o |
| **Streaming Output** | Real-time token-by-token in terminal |
| **Auto Retry** | 3x retry with exponential backoff on API failure |
| **Safety Blocklist** | `rm -rf /`, `mkfs`, `shutdown` — hard blocked |
| **`.gitignore` Respect** | Search + list tools never touch ignored files |
| **Diff Generation** | Unified diff generated for every edit |

---

## 🔒 Safety

```
⛔ Never deletes files without your explicit confirmation
⛔ Never runs rm -rf, mkfs, shutdown, or any destructive command
⛔ Never overwrites a file without reading it first
⛔ Never executes multi-file refactors without showing you the plan
⛔ Never bypasses the tool approval gate
⛔ Never exceeds your granted permissions
✅ Auto-backs up every file to .astra_backups/ before editing
✅ Checkpoints before every risky operation
✅ When in doubt — STOPS, EXPLAINS, ASKS
```

---

## 📁 Project Structure

```
astra/
├── agent/
│   ├── controller.py       # Main agent loop (max 30 iterations)
│   ├── context.py          # Context management + auto-trim
│   ├── planner.py          # Planning engine
│   ├── plan_mode.py        # Read-only plan mode
│   └── subagent.py         # Foreground + background subagents
├── llm/
│   ├── client.py           # Streaming LLM client + retry logic
│   └── prompts.py          # SYSTEM_PROMPT + PLAN_PROMPT_TEMPLATE
├── systems/
│   ├── hooks.py            # Lifecycle hooks
│   ├── permissions.py      # Permission modes + rules
│   ├── sandbox.py          # Isolated execution environment
│   ├── checkpoint.py       # Checkpoint + rewind system
│   ├── session.py          # Session save/load/fork/rename
│   ├── telemetry.py        # Token + cost tracking
│   ├── worktree.py         # Git worktree management
│   ├── rules.py            # Rules engine (.astra/rules/*.md)
│   ├── mcp.py              # MCP server management
│   └── plugins.py          # Plugin auto-discovery
├── tools/
│   ├── read_file.py        write_file.py     edit_file.py
│   ├── multi_edit.py       list_files.py     search_code.py
│   ├── grep_search.py      glob_search.py    run_command.py
│   ├── web_search.py       web_fetch.py      ask_user.py
├── cli/
│   └── main.py             # --pipe, --output-format, --max-turns
├── .astra/
│   ├── memory.json         # Persistent memory store
│   ├── rules/              # Custom rules (.md files)
│   ├── plugins/            # Custom plugins (.py files)
│   └── hooks/              # Hook config templates
├── .astra_backups/         # Auto-generated file backups
├── ASTRA.md                # Project config (run /init to generate)
└── requirements.txt
```

---

## 📊 v1.0 — By the Numbers

| Metric | Count |
|--------|-------|
| 🛠️ Agent Tools | 12 |
| ⌨️ Slash Commands | 34 |
| 🧩 Core Modules | 21 |
| 🚀 Features Shipped | 30+ |
| 🤖 LLM Providers | 2 |
| 🔁 Max Agent Iterations | 30 |
| 💾 Auto Retry | 3x exponential backoff |
| ⏱️ Built in | 17 minutes 38 seconds |

---

## 🛣️ Roadmap

- [ ] Web UI / Dashboard
- [ ] VS Code Extension
- [ ] Gemini + Mistral support
- [ ] Multi-repo support
- [ ] Voice input mode
- [ ] ASTRA Cloud (remote agent execution)

---

## 🤝 Contributing

PRs welcome. Read `ASTRA.md` before contributing — it explains the full architecture.

```bash
git clone https://github.com/yourusername/astra.git
cd astra
pip install -r requirements.txt
python astra
```

---

## 📄 License

MIT © 2025

---

<div align="center">

**Built in 17 minutes. Powered by obsession. 🔥**

*ASTRA — Open source. Self-hosted. Built to challenge Claude Code.*

<br/>

⭐ **Star this repo if ASTRA saved your day**

*If Claude Code charges you, ASTRA is free. Your API key. Your machine. Your rules.*

</div>

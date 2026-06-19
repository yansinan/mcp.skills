---
name: hermes-multi-instance-coordination
description: "Decision framework and patterns for coordinating multiple independent Hermes Agent instances across different machines — MCP coordination server, Kanban limitations, SSH profile pitfalls, and when to use each."
version: 1.0.0
author: agent
platforms: [linux, macos]
metadata:
  hermes:
    tags: [hermes, multi-instance, cross-machine, coordination, mcp, kanban, ssh]
    related_skills: [hermes-ssh-backend, kanban-orchestrator, kanban-worker]
---

# Hermes Multi-Instance Coordination

Design patterns for running multiple independent Hermes instances on different machines that need to work together — e.g. a desktop Hermes (X1 Tablet) coordinating with a server Hermes (serverhome) that has Docker, services, and 24/7 availability.

## Decision Framework

Three approaches exist. Pick based on your constraints:

```
You want Hermes-A to ask Hermes-B to do work?
│
├─ A and B are on the SAME machine (different profiles)
│   └─ ➜ Kanban Board (native, zero config, profile→profile dispatch)
│       ✅ kanban_create/kanban_claim/kanban_complete
│       ✅ Dispatcher handles retry, crash recovery, blocking
│       ✅ SQLite is local → locking is reliable
│       ⚠️ Profiles are on same host
│
├─ A and B are on DIFFERENT machines, but share no filesystem
│   └─ ➜ MCP Coordination Server (recommended)
│       ✅ HTTP-based, no filesystem sharing needed
│       ✅ Both instances talk to same server via existing LiteLLM
│       ✅ Zero file ownership concerns
│       ✅ Can be as simple as ~100 lines of Python
│       ⚠️ Need to build or deploy the coordination server
│
├─ A and B are on DIFFERENT machines, A SSHs into B
│   └─ ➜ SSH Terminal Backend (profile-based)
│       ✅ Hermes built-in, no extra services
│       ⚠️ FileSyncManager overwrites remote ~/.hermes/
│       ⚠️ File ownership mismatch if different SSH user
│       ⚠️ See hermes-ssh-backend for full pitfall list
│
└─ A and B need to share a Kanban board across machines
    └─ ➜ ❌ NOT RECOMMENDED
        SQLite WAL mode uses fcntl byte-range locks and mmap that
        don't work reliably on network filesystems (NFS, SMB, CIFS).
        Confirmed bug: github.com/NousResearch/hermes-agent/issues/33334
```

## Approach 1: MCP Coordination Server (Recommended)

### Architecture

Run a lightweight MCP server on one machine (typically the server). Both Hermes instances connect to it through their respective MCP clients (via LiteLLM proxy or direct).

```
Hermes-A (desktop) ──HTTP──► LiteLLM ──► coordinator MCP ──► SQLite/JSON
Hermes-B (server)   ──HTTP──► LiteLLM ──► coordinator MCP ──► SQLite/JSON
```

The coordination server exposes tools like:

```
post_task(goal, context, assignee, priority)   → task_id
claim_next_task(agent_id)                       → {task_id, goal, context} | null
complete_task(task_id, result, summary)         → status
get_task_status(task_id)                        → {status, result, owner}
list_pending(agent_id)                          → [tasks]
send_message(from_agent, to_agent, text)        → ok
```

### Deployment

- Runs as a standalone Python process on the server (e.g. under s6/supervisor)
- Uses SQLite for durable task storage (local to the server, not shared)
- No file system sharing between instances
- Can be as simple as a Flask/FastAPI app implementing the MCP Streamable HTTP protocol
- Or follow the pattern in `references/existing-mcp-projects.md`

### What's Missing from Hermes

Hermes's `kanban_*` toolset only works for profiles on the same machine (reads the local SQLite board). Cross-machine kanban operations would require an MCP-based bridge that translates `kanban_*` calls into HTTP requests to the remote board — see the existing `orchestrator-server` project for a reference implementation.

## Approach 2: Kanban Board (Same-Machine Only)

**Kanban is single-host by design.** The SQLite backing store (`~/.hermes/kanban.db`) uses WAL mode with `mmap` and `fcntl` byte-range locks that don't work on network filesystems. This is documented in the Hermes source:

> `hermes_state.py`: "SQLite's WAL mode requires shared-memory (mmap) coordination and fcntl byte-range locks that don't reliably work on network filesystems (NFS, SMB/CIFS...)"
> `kanban.md`: "Kanban is single-host by design."

**Do NOT put `kanban.db` on a network mount** (NFS, Tailscale Funnel, Samba, S3 FUSE, etc.).

### When to Use Kanban

- Multiple profiles on the same machine that need to collaborate
- Worker tasks need to survive crashes (dispatcher auto-reclaims)
- Audit trail matters (SQLite rows persist forever)
- Human-in-the-loop needed (block/unblock/comment)

### When NOT to Use Kanban (reach for MCP instead)

- Instances are on different machines
- Instances have different terminal backends (one local, one Docker)
- Network latency or filesystem locking is a concern

## Approach 3: SSH Profile (Use with Caution)

Covered in depth by `hermes-ssh-backend`. Key constraints:

- FileSyncManager auto-syncs skills/credentials/cache to remote `~/.hermes/`, overwriting any existing Hermes install there
- File ownership issues if SSH user differs from file owner (see the File Ownership section in `hermes-ssh-backend`)
- No native task handoff — the profile is just a terminal, not a coordinated worker
- Use for simple "run this command on that machine" scenarios, not for multi-step orchestration

## Research: Existing MCP Coordination Projects

A survey of open-source MCP task coordination servers (conducted June 2026):

| Project | Stars | Storage | Fit for cross-machine |
|---------|-------|---------|----------------------|
| [mokafari/orchestrator-server](https://github.com/mokafari/orchestrator-server) | ~50 | JSON/memory | ✅ Closest to needs — `create_task/get_next_task/complete_task` pattern |
| [bsmi021/mcp-task-manager-server](https://github.com/bsmi021/mcp-task-manager-server) | ~80 | SQLite | ⚠️ Single-instance, no multi-agent handoff |
| [cyanheads/atlas-mcp-server](https://github.com/cyanheads/atlas-mcp-server) | 477★ | Neo4j | ❌ Heavy (Neo4j), overkill for 2 agents |
| [dmmulroy/overseer](https://github.com/dmmulroy/overseer) | 221★ | SQLite+Git | 🔴 Archived, but good task hierarchy reference (milestone→task→subtask) |
| [blizzy78/mcp-task-manager](https://github.com/blizzy78/mcp-task-manager) | ~30 | None | ❌ Too minimal |
| [scopecraft/command](https://github.com/scopecraft/command) | ~170 | Markdown | ❌ Offline, not real-time |
| [agentrq/agentrq](https://github.com/agentrq/agentrq) | 451★ | In-memory | ❌ Human-in-loop focused |

`orchestrator-server`'s API pattern (`create_task` → `get_next_task` → `complete_task`) is the simplest reference model for building a custom coordination MCP.

## User Preference (dr@x1tablet + serverhome)

This specific setup has strong opinions that inform any coordination design:

- **No file ownership mixing** — "文件属主混乱不能接受." If a coordination approach creates mixed-ownership files (e.g. SSH profile with a different system user), it will be rejected.
- **Prefer non-invasive patterns** — solutions that don't touch the remote's existing Hermes install or file hierarchy.
- **Existing LiteLLM/MCP infrastructure on serverhome** — the server already runs LiteLLM with 4+ MCP services behind nginx. Adding another MCP is trivial.
- **Low tolerance for complexity** — simple, practical solutions over elaborate architectures.

The MCP Coordination Server fits all these constraints. SSH profile does not.

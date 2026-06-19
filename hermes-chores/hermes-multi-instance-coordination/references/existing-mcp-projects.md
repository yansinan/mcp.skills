# Existing MCP Coordination Projects — Survey (June 2026)

Survey conducted during the "cross-machine Hermes coordination" design discussion.
Goal: find existing open-source MCP servers that support task handoff between independent AI agent instances.

## Candidates Evaluated

### mokafari/orchestrator-server
- **URL**: https://github.com/mokafari/orchestrator-server
- **Stars**: ~50
- **Language**: TypeScript (Node.js)
- **Storage**: JSON / in-memory
- **MCP Protocol**: Yes (stdio)
- **Core API**: `create_task(task)`, `get_next_task(instance_id)`, `complete_task(task_id, result)`, `list_tasks(task_id)`
- **Key features**: Dependency enforcement, cycle detection, multi-instance coordination, basic task status tracking
- **Fit**: ✅ Closest to needs. Simple API surface that maps directly to cross-agent handoff. The `get_next_task` pattern is exactly what two Hermes instances need to poll for work.

### bsmi021/mcp-task-manager-server
- **URL**: https://github.com/bsmi021/mcp-task-manager-server
- **Stars**: ~80
- **Language**: TypeScript (Node.js)
- **Storage**: SQLite
- **MCP Protocol**: Yes (stdio)
- **Core API**: `createProject`, `addTask`, `listTasks`, `setTaskStatus`, `expandTask` (into subtasks), `getNextTask`, `deleteTask`
- **Key features**: Projects → Tasks → Subtasks, dependency chains, priority, `next actionable task` resolution, JSON import/export
- **Fit**: ⚠️ Well-built but single-instance oriented. No concept of "agent/worker" ownership. Could be adapted.

### cyanheads/atlas-mcp-server
- **URL**: https://github.com/cyanheads/atlas-mcp-server
- **Stars**: **477★**
- **Language**: TypeScript
- **Storage**: Neo4j
- **MCP Protocol**: Yes (stdio)
- **Core API**: Three-tier: Projects, Tasks, Knowledge. Deep Research feature.
- **Key features**: Most feature-rich — knowledge graph, project-level context, complex dependency resolution
- **Fit**: ❌ Requires Neo4j database. Overkill for coordinating two Hermes instances. The project-level context + knowledge graph feature suggests a different use case (long-running research).

### dmmulroy/overseer
- **URL**: https://github.com/dmmulroy/overseer
- **Stars**: **221★**
- **Language**: Rust CLI + Node.js MCP
- **Storage**: SQLite + VCS (jj/git)
- **MCP Protocol**: Yes (codemode pattern)
- **Core API**: Tasks with hierarchy (Milestone → Task → Subtask), progress tracking, blocking/unblocking, search, tree view
- **Key features**: VCS integration (bookmarks for branches), learning bubbling (learnings propagate to parent tasks), progressive context inheritance
- **Fit**: 🔴 **Archived** (no longer maintained by author). Interesting structural reference: the milestone→task→subtask hierarchy and learning bubbling pattern could inspire coordination design.

### blizzy78/mcp-task-manager
- **URL**: https://github.com/blizzy78/mcp-task-manager
- **Stars**: ~30
- **Language**: Go
- **Storage**: None specified
- **Core API**: Basic task CRUD
- **Fit**: ❌ Too minimal. No multi-agent awareness.

### scopecraft/command
- **URL**: https://github.com/scopecraft/command
- **Stars**: ~170
- **Language**: TypeScript
- **Storage**: Markdown files
- **Core API**: MDTM (Markdown-Driven Task Management)
- **Fit**: ❌ Offline/local-first design, no real-time coordination. A file-based approach that doesn't suit agent-to-agent handoff.

### agentrq/agentrq
- **URL**: https://github.com/agentrq/agentrq
- **Stars**: **451★**
- **Language**: Python
- **Storage**: In-memory
- **Core API**: Human-in-the-loop realtime conversational task manager
- **Fit**: ❌ Focused on human-agent interaction, not agent-agent coordination. Good reference for the notification/push pattern if needed.

## Key Takeaway

No existing MCP project directly solves "two independent Hermes instances on different machines coordinating work." The closest is:

1. **`orchestrator-server`** — simplest, closest API to what we need. ~300 lines.
2. **`atlas-mcp-server`** — most complete but overkill (Neo4j dependency).

For this specific use case (Hermes A sends task → Hermes B does it → reports back), building a ~100-line MCP server on top of the existing LiteLLM infrastructure is likely simpler and more maintainable than adapting any of these projects.

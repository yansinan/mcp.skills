# GitHub Copilot MCP — Full Tool Reference

Discovered 2026-05-29 via LiteLLM gateway at `http://serverhome.tail2e6efb.ts.net/litellm/hermes/github/mcp`.
Auth: `Authorization: Bearer <GitHub PAT>` (or proxied via LiteLLM `x-litellm-api-key`).

## Connection Details

| Field | Value |
|-------|-------|
| Endpoint | `https://api.githubcopilot.com/mcp/` |
| Transport | Streamable HTTP |
| Response format | SSE (`event: message` / `data: {...}`) |
| Required headers | `Accept: application/json, text/event-stream` |
| MCP Protocol Version | `2025-11-25` |

## Complete Tool Inventory (21 tools)

### Code & Repository Search
- `github-search_code` — Fast code search across ALL GitHub repos. Supports qualifiers: `repo:`, `org:`, `language:`, `path:`, `filename:`, `extension:`.
- `github-search_commits` — Commit search (default branch only). Qualifiers: `author:`, `committer:`, `author-date:`, `merge:true|false`.
- `github-search_repositories` — Find repos by name, description, readme, topics. Sort by stars/forks/updated.
- `github-search_issues` — Issue search (auto-scoped `is:issue`). Sort by comments/reactions/created/updated.
- `github-search_pull_requests` — PR search (auto-scoped `is:pr`). Same sort options.
- `github-search_users` — Find users by name, location, followers count.

### File/Branch Operations
- `github-create_or_update_file` — Create or update a single file. Requires `sha` for updates (`git rev-parse <branch>:<path>`).
- `github-create_branch` — Create branch from an optional source branch.

### Pull Request Management
- `github-create_pull_request` — Create PR with title, body, head/base branches, draft flag.
- `github-update_pull_request` — Update PR (title, body, base branch, state, draft, reviewers).
- `github-update_pull_request_branch` — Update PR branch with latest base changes.
- `github-add_comment_to_pending_review` — Add review comment to pending PR review. Supports LINE/FILE level.
- `github-add_reply_to_pull_request_comment` — Reply to existing PR comment.
- `github-list_pull_requests` — List PRs with filters.
- `github-list_pull_request_comments` — List PR review comments.

### Issue Management
- `github-add_issue_comment` — Add comment to issue (works for PRs too, but prefer review comments for PRs).

### Sub-Issues
- `github-sub_issue_write` — Add/remove/reprioritize sub-issues. Uses issue `number` + sub-issue `id` (not same as number).

### Copilot Agent
- `github-assign_copilot_to_issue` — Assign Copilot to work on an issue. Creates PR with changes.
- `github-create_pull_request_with_copilot` — Delegate task to Copilot coding agent (background PR creation).
- `github-request_copilot_review` — Request Copilot to review a PR.

### Security
- `github-run_secret_scanning` — Scan files/content/diffs for secrets (API keys, passwords, tokens). Accepts raw content strings.

## Notes
- All tools require `owner` and `repo` parameters (except search tools which have their own query syntax).
- Tool names are prefixed with `github-` by the Copilot MCP server.
- The tools are functionally equivalent to what `@modelcontextprotocol/server-github` (npx package) provides, but with additional Copilot agent features.
- When proxied through LiteLLM, the same `Accept` header requirement applies.

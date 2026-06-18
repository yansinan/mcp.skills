# SEP-986: MCP Tool Name Format Specification

**Source:** https://github.com/modelcontextprotocol/modelcontextprotocol/issues/986
**Author:** kentcdodds
**Status:** Proposal (MCP community)

## Background

The Model Context Protocol (MCP) lacked a standardized format for tool names, causing inconsistencies across clients. SEP-986 establishes a clear standard to maximize compatibility, clarity, and interoperability.

LiteLLM applies SEP-986 rules to **MCP server names** because it prefixes each tool name with the server name for namespace isolation (e.g., server `github` → tools named `github_getUser`).

## Specification

### Constraints

- **Length:** 1–64 characters (inclusive)
- **Case sensitivity:** Case-sensitive
- **Allowed characters:**
  - ASCII uppercase letters: `A-Z`
  - ASCII lowercase letters: `a-z`
  - Digits: `0-9`
  - Underscore: `_`
  - Dash (hyphen): `-`
  - Dot: `.`
  - Forward slash: `/`
- **Forbidden:** Spaces, commas, and all other special characters

### Valid Examples

```
getUser
user-profile/update
DATA_EXPORT_v2
admin.tools.list
github_mcp
my.mcp.server
```

### Invalid Examples

```
get user        # space
get,user        # comma
你好_mcp        # non-ASCII
a               # too short? No — "a" is 1 char, valid
a...b...c...d...e...f...g...h...i...j...k...l...m...n...o...p...q...r...s...t...u...v...w...x...y...z...a...b...c...d...e...f...g...h...i...j...k...l...m...n...o...p...q...r...s...t...u...v...w...x...y...z   # 128+ chars, too long
```

## Backward Compatibility

- Non-conforming existing tools SHOULD be supported as aliases for at least one major version with a deprecation warning
- Tool authors SHOULD update to the new format

## LiteLLM Enforcement

- **v1.80.18+:** New MCP servers must comply with SEP-986 — noncompliant names cannot be added via UI
- Existing noncompliant servers: warnings only (for now)
- Future: MCP-side enforcement may block noncompliant names entirely
- Recommendation: update legacy server names proactively

## Tool Name Prefix Structure

When LiteLLM prefixes tool names with the server name, the combined name must also comply. This is generally automatic if the server name itself is SEP-986 compliant, but note:

- Server: `github` → tool: `github_getUser` → valid (`_` is allowed)
- Server: `git-hub` → tool: `git-hub_getUser` → valid (`-` is allowed)
- Server: `my.server` → tool: `my.server_getUser` → valid (`.` and `_` are allowed)
- Server: `github api` → tool: `github api_getUser` → **INVALID** (space)

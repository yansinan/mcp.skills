# read-down — Concrete implementation of Readability + Turndown pipeline

Created as a Node.js module within a Hermes user plugin (`cdp_extract/read_down/`). Called from Python via subprocess (stdin/stdout JSON).

## Repository

`~/.hermes/plugins/web/cdp_extract/read_down/`

## Architecture

```
Python (provider.py)                          Node.js (read_down/index.js)
                                               ┌───────────────────────────────┐
CDP → get outerHTML ──stdin JSON──►          │ linkedom.parseHTML(html)     │
                                               │   → new Readability(doc)    │
                                               │     → { title, content,     │
                                               │         textContent, ... }  │
                                               │   → turndown.turndown(html) │
                                               │     → markdown              │
                                               └────────┬────────────────────┘
                                                        │ stdout JSON
                                               ◄─────────┘
Python ← PageExtractionResult {text, markdown?, html?, title?, byline?, dir?, length?, lang?, error?}
```

Key notes:
- Turndown takes HTML strings directly — no DOM wrapper needed
- Readability needs a DOM: `linkedom` (light) or `jsdom` (heavier)
- `linkedom` is preferred: 2.7M vs jsdom's 4.3M, 60 fewer transitive deps

## Interface (CLI)

```bash
echo '{"html":"<html>...</html>","url":"https://example.com","options":{}}' \
  | node index.js
# → {"markdown":"...","title":"...","text":"...","html":"...","length":3632}
```

## Interface (Library)

```js
const { readDown } = require('./index.js');
const result = readDown(html, { url, headingStyle: 'atx', useReadability: true, debugTrace: false });
# → PageExtractionResult { text, markdown?, html?, title?, byline?, dir?, length?, lang?, error? }
```

## PageExtractionResult (matched to hermes-sidebar for parallel replacement)

| Field | Type | Always present? | Source |
|-------|------|----------------|--------|
| `text` | string | Yes | Readability textContent or raw body |
| `markdown` | string | No (undefined on failure) | Turndown output |
| `html` | string | No (undefined on failure) | Readability article HTML |
| `title` | string | No | Readability parse result |
| `byline` | string | No | Readability parse result |
| `dir` | string | No | Readability parse result |
| `length` | number | No | Readability parse result |
| `lang` | string | No | Readability parse result |
| `error` | string | No | Error code: empty-html / readability-error / parse-returned-null / turndown-error |

## Options

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `url` | string | `undefined` | Base URL for relative link resolution |
| `useReadability` | boolean | `true` | `false` → skip Readability, use raw DOM + fallbackHtmlToMarkdown |
| `debugTrace` | boolean | `false` | Print flow nodes + Readability debug to stderr |
| `headingStyle` | `'atx'` or `'setext'` | `'atx'` | Turndown heading format |
| `skipTurndown` | boolean | `false` | Return Readability HTML only |
| `extraRemovals` | string[] | `[]` | Extra CSS selectors to strip before Turndown |

## Dependencies

```json
{
  "@mozilla/readability": "^0.5.0",
  "linkedom": "^0.18.0",
  "turndown": "^7.2.0",
  "turndown-plugin-gfm": "^1.0.2"
}
```

Readability is zero-dependency (requires external DOM for Node.js).
Turndown has its own HTML parser (no DOM needed).

## Removed Elements (Turndown — matches hermes-sidebar exactly)

Always stripped: `script`, `style`, `noscript`, `nav`, `footer`, `iframe`

## Fallback Function

When Readability returns null or useReadability=false, the raw HTML goes through `fallbackHtmlToMarkdown()`:

```js
// Regex-based HTML → Markdown (mirrors hermes-sidebar exactly)
// Preserves: h1-6 → #,##..., strong → **, b → **, em → _, i → _,
// code → `, a → [text](url), p → \n\n, br → \n, li → - \n
function fallbackHtmlToMarkdown(html) { ... }
```

Also exported as `module.exports = { readDown, fallbackHtmlToMarkdown }`.

## Key Design Decisions

1. **Node.js subprocess, not in-process Python** — Readability/Turndown are JS-only; calling via subprocess avoids jsdom-in-Python complexity.
2. **Readability runs first, Turndown second** — Turndown MUST receive cleaned article HTML, not raw page HTML (or markdown will include nav/ads).
3. **CLI via stdin/stdout JSON** — avoids filesystem temp files, keeps the call atomic.
4. **Fallback on Readability null** — non-article pages fall through to `fallbackHtmlToMarkdown()` which preserves basic markdown structure via regex.
5. **Interface matched to hermes-sidebar EXACTLY** — for parallel replacement, every optional field is `undefined` not `""` when absent.

## Pitfalls (Node.js specific)

- `Page.loadEventFired` is deprecated in Chrome 148+. Page navigation events arrive between CDP commands — no explicit wait needed before Runtime.evaluate.
- CDP sends events (no `id` field) interleaved with responses. Always filter by `msg.get("id") == our_msg_id`.
- `package-lock.json` should be committed for deterministic installs.
- Turndown `remove()` rules only apply during `.turndown()` call, not to pre-parsed DOM. Pass HTML strings, not DOM nodes, to Turndown.
- linkedom's `parseHTML(html, url)` second arg sets the document's base URL for Readability's relative URI fixing.

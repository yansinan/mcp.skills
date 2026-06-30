# Browser automation when /tmp is full (chrome RSS-driven workaround)

## Symptom

`browser_navigate` returns `code 101` even when the target server is up
(`ss -tlnp` shows LISTEN, `curl` to the same URL works from terminal).
`/tmp` tmpfs is 100% full even though `du -sh /tmp/*` shows only a few MB of
named files. Browser tool can't spawn a new chrome because the process can't
allocate shared memory in tmpfs.

## Root cause

x1tablet uses tmpfs for `/tmp` (`df -T /tmp` shows `tmpfs`). Chrome's
renderer + GPU + utility processes hold anonymous shmem pages in tmpfs that
are NOT visible to `du` (only to `lsof` / `/proc/*/smaps` for deleted files).
When 50+ chrome processes accumulate, RSS totals 7+ GB and tmpfs saturates.
The CDP-host chrome process (the one user's own browser tab lives in) is
*also* affected — even reading a tab via the browser tool fails.

The CDP-host chrome is the user's primary debug browser (per memory:
"chrome-cdp-profile 吃光 严禁写/tmp"). **Do not kill it.**

## Recovery path

1. **Confirm diagnosis**: `df /tmp` → 100% full. `pgrep chrome | wc -l` →
   50+. `du -sh /tmp/*` → small. If both true, this is the symptom.

2. **Enumerate existing tabs via CDP HTTP** (does not require a new chrome):
   ```
   curl -sS http://127.0.0.1:9222/json/list
   ```
   Output: JSON array of `{targetId, type, title, url, webSocketDebuggerUrl, ...}`.

3. **Drive an existing tab via `browser_cdp`**:
   - `target_id` = the targetId from step 2 (NOT the short id, the full
     32-char hex).
   - `method: Target.getTargets` to confirm and see all tabs.
   - `method: Runtime.evaluate` to read DOM/JS state.

## `Runtime.evaluate` gotcha (binding parser)

The browser_cdp tool's binding parser is strict — it fails
(`Invalid parameters ... BINDINGS: bool value expected at position N`) on
multi-key object literals. The **only reliable form** is single-line
`JSON.stringify(...)` with no nested object literals:

```python
# WORKS:
browser_cdp(method="Runtime.evaluate", params={
    "expression": "JSON.stringify({title: document.title, url: location.href})",
    "returnByValue": True,
}, target_id=TAB)

# FAILS (binding parser rejects):
browser_cdp(method="Runtime.evaluate", params={
    "expression": "JSON.stringify({a: 1, b: 2, c: {nested: 3}})",
    "returnByValue": True,
}, target_id=TAB)
```

If you need multiple pieces of state, do multiple single-key calls or
flatten with `"|"` separator. Don't retry the failing form — it will
reliably fail again on the same input.

## After a successful injection

Read the response `result.result.value` — it's the JSON string from your
expression. If it's compressed in the tool output, save it to
`<workspace>/.cache-uv/tmp/cdp_result.json` and read with `read_file` or
`python3 -c "import json,sys; print(json.load(open(sys.argv[1])))"`.

## When to give up

If even `browser_cdp` returns `Failed to attach to target` or
`Invalid parameters` on every call, the CDP session is poisoned. Stop,
report the blocker explicitly to the user, and ask whether to restart the
CDP chrome (their call, not yours — killing the CDP chrome breaks their
own browser session).

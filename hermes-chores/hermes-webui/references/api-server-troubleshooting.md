# API Server Troubleshooting

Hermes WebUI depends on the gateway's `api_server` platform listening on port
8643. If the API server isn't up, WebUI can't connect.

## Debugging Workflow

When port 8643 is not responding:

1. **Check if port is listening:**
   ```bash
   ss -tlnp | grep 8643
   ```
   Empty = nothing bound.

2. **Check gateway service status:**
   ```bash
   systemctl --user status hermes-gateway
   ```
   Note: the service can be `active` (running) without the API server actually
   listening — they are separate platforms within the gateway.

3. **Search journal for the specific error:**
   ```bash
   journalctl --user -u hermes-gateway --no-pager -n 100 | grep -i "api_server"
   ```
   The key error to look for:
   ```
   ERROR gateway.platforms.api_server: [Api_Server] Refusing to start:
   API_SERVER_KEY is a placeholder or too short (<16 chars) for a
   network-accessible bind.
   ```

4. **Check `.env` for the key:**
   ```bash
   grep API_SERVER_KEY ~/.hermes/.env
   ```

5. **Fix:**
   - **If binding to `0.0.0.0`** (network-accessible, e.g. via Tailscale): key
     must be **≥ 16 characters**. Hermes enforces this as a security measure.
   - **If binding to `127.0.0.1`** (loopback only, same machine): no length
     constraint (but short keys are still poor practice).

## Common Configuration (from `.env`)

```
API_SERVER_ENABLED=true
API_SERVER_PORT=8643
API_SERVER_HOST=0.0.0.0       # ← network-facing: key ≥ 16 chars required
API_SERVER_KEY=<key>
```

## Root Cause Pattern

The symptom ("port 8643 not open") is misleading because the gateway service
reports `active` in systemd. The api_server platform silently refuses to bind
and logs an ERROR that you must explicitly grep for. Always check the journal
when port bindings seem missing.

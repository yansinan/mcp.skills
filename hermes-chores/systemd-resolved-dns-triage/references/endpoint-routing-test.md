# Endpoint Routing Test Patterns

When a self-hosted service (SearXNG, Seafile, etc.) is accessible via multiple hostnames behind a reverse proxy, DNS resolution alone doesn't tell you which service you'll reach. The Host header determines the backend. This reference documents the systematic approach to finding the correct endpoint.

## The Problem

```
http://searxng.home/           → 200 OK (SearXNG)
http://search.home/            → 302 ./login (Seafile)
http://searxng.serverhome/     → 302 ./login (Seafile)

All three resolve to 100.66.66.203 (serverhome via nginx)
```

The difference is which nginx `server_name` matches the Host header.

## The Test Matrix

For each candidate URL, test three levels:

```bash
# Level 1: DNS resolution
getent hosts <candidate>
dig <candidate> +short

# Level 2: Base URL (routing check)
curl -svo /dev/null 'http://<candidate>/' 2>&1 | head -10
# → 200 = root page served
# → 302 = redirect to login/somewhere else
# → 000 = unreachable (DNS or connection failed)
# → 401/403 = reached but requires auth/wrong backend

# Level 3: Service-specific API
# For SearXNG:
curl -s 'http://<candidate>/search?q=test&format=json' | head -c 200
# Expected: JSON with "number_of_results" key
# Unexpected: {"error":"Unauthorized"}, {"detail":"Not Found"}, HTML
```

## Systematic Scanning

When the correct URL is unknown, generate candidates from the DNS namespace:

```bash
# Pattern: <service>.<search-domain> or <service>.<host>.<search-domain>
# For a tailnet with search domains:
#   tail2e6efb.ts.net
#   home.z-core.cn
#   serverhome.z-core.cn
#   z-core.cn

# Test from the most specific to most generic:
for h in \
  searxng.serverhome.z-core.cn \
  searxng.home.z-core.cn \
  searxng.z-core.cn \
  searxng.serverhome \
  searxng.home \
  search.serverhome.z-core.cn \
  search.home.z-core.cn \
  search.serverhome \
  search.home; do
  code=$(curl -s -o /dev/null -w '%{http_code}' "http://$h/" 2>&1)
  echo "$code  $h"
done
```

## Interpret Results

| Base URL code | /search API | Likely backend |
|---|---|---|
| `200` | JSON results | ✅ **Correct — SearXNG** |
| `302 ./login` | HTML login / `401` | ❌ Seafile or other auth-required app |
| `000` | N/A | ❌ DNS didn't resolve |
| `307` | N/A | Redirect — may need to follow |
| `405` | N/A | Method not allowed (expected for base URL) |

## The Host Header Trap

```bash
# These LOOK like they should be the same but they're NOT:
curl http://searxng.home.home.z-core.cn/  # Host: searxng.home.home.z-core.cn → 403
curl http://searxng.home/                 # Host: searxng.home              → 200

# The FQDN form resolves correctly but nginx doesn't recognize the Host header.
# The short name form resolves via search domain expansion but sends the right Host header.
```

When a machine can only resolve the FQDN form (foreign resolv.conf mode) and the FQDN doesn't match the nginx virtual host, you have a "circle cannot be squared" situation: the only working combination (short-name URL + stub mode DNS) is not available. Solution: use the direct port access instead:

```bash
SEARXNG_URL=http://serverhome:8786  # direct port, no Host header dependency
```

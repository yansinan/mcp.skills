#!/usr/bin/env bash
# =============================================================================
# Headroom container management
# Usage: ./run.sh [start|stop|restart|logs|status|update|shell|verify]
# =============================================================================

CMD=${1:-status}

case "$CMD" in
  start)
    echo "▶️  Starting Headroom..."
    docker compose up -d
    echo "   Health: curl http://localhost:3999/health"
    ;;
  stop)
    echo "⏹  Stopping Headroom..."
    docker compose down
    ;;
  restart)
    echo "🔄 Restarting Headroom..."
    docker compose restart
    sleep 3
    docker compose ps
    ;;
  logs)
    docker compose logs -f --tail=50
    ;;
  status)
    docker compose ps
    echo "---"
    curl -sf http://localhost:3999/health 2>/dev/null \
      | python3 -c "import sys,json;d=json.load(sys.stdin);print(f'Status: {d[\"status\"]}  Version: {d[\"version\"]}  Upstream: {d[\"config\"][\"openai_api_url\"]}')" \
      || echo "⚠️  Headroom not running, or health endpoint unreachable"
    ;;
  update)
    echo "⬇️  Pulling latest image..."
    docker compose pull
    echo "🔄 Recreating container..."
    docker compose up -d --force-recreate
    docker image prune -f
    ;;
  shell)
    docker compose exec headroom sh
    ;;
  verify)
    echo "=== Smoke test ==="
    echo -n "1) Health: "; curl -sf http://localhost:3999/health >/dev/null && echo "✅" || echo "❌"
    echo -n "2) Chat:   "; curl -sf http://localhost:3999/v1/chat/completions \
      -H "Content-Type: application/json" \
      -d '{"model":"deepseek-v4-flash","messages":[{"role":"user","content":"hi"}],"max_tokens":10}' \
      | python3 -c "import sys,json;d=json.load(sys.stdin);print('✅' if 'choices' in d else '❌')" 2>/dev/null || echo "❌"
    echo -n "3) Resp:   "; curl -sf http://localhost:3999/v1/responses \
      -H "Content-Type: application/json" \
      -d '{"model":"deepseek-v4-flash","input":"hi","max_output_tokens":10}' \
      | python3 -c "import sys,json;d=json.load(sys.stdin);print('✅' if 'output' in d else '❌')" 2>/dev/null || echo "❌"
    echo -n "4) Stats:  "; curl -sf http://localhost:3999/stats \
      | python3 -c "import sys,json;d=json.load(sys.stdin);print(f'{d.get(\"total_requests\",0)} requests, {d.get(\"tokens_saved\",0)} tokens saved')" 2>/dev/null || echo "⚠️"
    echo "=== Done ==="
    ;;
  *)
    echo "Usage: $0 [start|stop|restart|logs|status|update|shell|verify]"
    exit 1
    ;;
esac

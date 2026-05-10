#!/usr/bin/env bash
# start_mac.sh — รัน LINE Bot server + ngrok พร้อมกัน (สำหรับ Mac/Linux)
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")"

VENV_PY=".venv/bin/python"

# ── ตรวจ venv ─────────────────────────────────────────────────────────────────
if [ ! -f "$VENV_PY" ]; then
    echo ""
    echo "  ยังไม่ได้ setup — รัน: bash scripts/setup_mac.sh"
    echo ""
    exit 1
fi

# ── อ่าน LINE token จาก config.json ──────────────────────────────────────────
LINE_TOKEN=""
if [ -f "config.json" ]; then
    LINE_TOKEN=$(python3 -c "
import json, sys
try:
    d = json.load(open('config.json'))
    print(d.get('line_channel_access_token',''))
except:
    print('')
" 2>/dev/null || echo "")
fi

if [ -z "$LINE_TOKEN" ]; then
    echo ""
    echo "  ⚠️  ยังไม่ได้ตั้งค่า LINE Token"
    echo "  หลัง server ขึ้นแล้วไปตั้งที่ http://localhost:8000/admin → Credentials"
    echo ""
fi

# ── cleanup เมื่อกด Ctrl+C ────────────────────────────────────────────────────
SERVER_PID=""
NGROK_PID=""

cleanup() {
    echo ""
    echo "  กำลังปิด..."
    [ -n "$SERVER_PID" ] && kill "$SERVER_PID" 2>/dev/null || true
    [ -n "$NGROK_PID"  ] && kill "$NGROK_PID"  2>/dev/null || true
    wait 2>/dev/null || true
    echo "  ปิดเรียบร้อย ✓"
}
trap cleanup EXIT INT TERM

# ── รัน uvicorn ────────────────────────────────────────────────────────────────
echo ""
echo "  ╔══════════════════════════════════════╗"
echo "  ║     LINE Bot — กำลังเริ่มระบบ       ║"
echo "  ╚══════════════════════════════════════╝"
echo ""

"$VENV_PY" -m uvicorn main:app --host 0.0.0.0 --port 8000 &
SERVER_PID=$!

# รอ server ขึ้น (ลอง 30 วินาที)
echo "  ⏳ รอ server พร้อม..."
READY=0
for i in $(seq 1 30); do
    if curl -sf http://localhost:8000/health >/dev/null 2>&1; then
        READY=1
        break
    fi
    sleep 1
done

if [ $READY -eq 1 ]; then
    echo "  ✅ Server พร้อมที่ http://localhost:8000"
    echo "  🌐 Admin Panel: http://localhost:8000/admin"
else
    echo "  ⚠️  Server ยังไม่ขึ้นหลัง 30 วินาที — ดู log ด้านบน"
fi

# ── รัน ngrok ──────────────────────────────────────────────────────────────────
if command -v ngrok &>/dev/null; then
    # ใส่ auth token ถ้ามีใน .env
    if [ -f ".env" ]; then
        NGROK_TOKEN=$(grep "^NGROK_AUTH_TOKEN=" .env 2>/dev/null | cut -d= -f2 | tr -d ' \r' || echo "")
        if [ -n "$NGROK_TOKEN" ]; then
            ngrok config add-authtoken "$NGROK_TOKEN" >/dev/null 2>&1 || true
        fi
    fi

    echo "  ▶ เริ่ม ngrok..."
    ngrok http 8000 > /dev/null 2>&1 &
    NGROK_PID=$!

    # รอ ngrok ขึ้นแล้ว poll URL
    sleep 3
    NGROK_URL=""
    for i in $(seq 1 15); do
        NGROK_URL=$(curl -sf http://localhost:4040/api/tunnels 2>/dev/null \
            | python3 -c "
import json,sys
try:
    d=json.load(sys.stdin)
    tunnels=d.get('tunnels',[])
    for t in tunnels:
        if t.get('proto')=='https':
            print(t['public_url'])
            break
except:
    pass
" 2>/dev/null || echo "")
        [ -n "$NGROK_URL" ] && break
        sleep 1
    done

    if [ -n "$NGROK_URL" ]; then
        WEBHOOK="${NGROK_URL}/webhook"
        echo ""
        echo "  ╔══════════════════════════════════════════════════════════╗"
        echo "  ║  Webhook URL (ใส่ใน LINE Developers Console):            ║"
        echo "  ║  $WEBHOOK"
        echo "  ╚══════════════════════════════════════════════════════════╝"
        echo ""

        # Auto-sync ไปที่ LINE API
        if [ -n "$LINE_TOKEN" ]; then
            SYNC_HTTP=$(curl -s -o /dev/null -w "%{http_code}" \
                -X PUT "https://api.line.me/v2/bot/channel/webhook/endpoint" \
                -H "Authorization: Bearer $LINE_TOKEN" \
                -H "Content-Type: application/json" \
                -d "{\"webhookEndpointUrl\":\"$WEBHOOK\"}" 2>/dev/null || echo "000")
            if [ "$SYNC_HTTP" = "200" ]; then
                echo "  ✅ LINE webhook อัปเดตอัตโนมัติแล้ว"
            else
                echo "  ⚠️  Auto-sync ไม่สำเร็จ (HTTP $SYNC_HTTP) — ใส่ URL เองใน LINE Console"
            fi
        else
            echo "  📋 Copy URL ด้านบนใส่ใน LINE Developers Console → Messaging API → Webhook URL"
        fi
        echo ""
    else
        echo "  ⚠️  ไม่พบ ngrok URL — ตรวจสอบ http://localhost:4040"
    fi
else
    echo ""
    echo "  ⚠️  ไม่พบ ngrok — ติดตั้งด้วย: brew install ngrok"
    echo ""
fi

echo "  กด Ctrl+C เพื่อปิดทั้งหมด"
echo ""

# รอ server จบ
wait $SERVER_PID || true

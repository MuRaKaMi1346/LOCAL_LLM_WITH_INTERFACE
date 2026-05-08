# 🌸 LINE Bot

ระบบ LINE Bot สำหรับตอบคำถามเกี่ยวกับคณะ โดยใช้ Ollama (LLM ท้องถิ่น) และ RAG (Retrieval-Augmented Generation)  
มี Admin Panel สำหรับจัดการทุกอย่างผ่าน Web UI โดยไม่ต้องแก้โค้ด

---

## โครงสร้างโปรเจกต์

```
local ai minnie/
│
├── main.py               ← FastAPI entry point
├── config.py             ← การตั้งค่า (pydantic-settings)
├── state.py              ← สถานะ runtime (bot on/off, นับข้อความ)
├── launcher.py           ← GUI launcher (Windows / macOS)
│
├── bot/                  ← ลอจิก LINE Bot
│   ├── handler.py        ← รับ event (follow / ข้อความ / unfollow)
│   ├── prompts.py        ← สร้าง system prompt + ข้อความต้อนรับ
│   └── sessions.py       ← ประวัติการสนทนาต่อผู้ใช้
│
├── services/             ← ไคลเอนต์ service ภายนอก
│   ├── ollama.py         ← Ollama LLM + embedding
│   └── rag.py            ← ChromaDB vector store + ค้นหา
│
├── admin/                ← Web Admin Panel
│   ├── router.py         ← FastAPI routes (/admin/api/*)
│   └── index.html        ← UI (glassmorphism dark theme)
│
├── data/                 ← Knowledge base (.md / .txt)
│   └── faculty_knowledge.md
│
├── scripts/              ← ตัวช่วย setup (รันครั้งเดียว)
│   ├── setup_ollama.py   ← ดาวน์โหลด Ollama models
│   └── setup_mac.sh      ← ติดตั้ง venv + สร้าง .app (macOS)
│
├── LineBot.app/           ← macOS app bundle (ดับเบิลคลิกเพื่อเปิด)
├── start.bat             ← Windows quick-start
│
├── Dockerfile
├── docker-compose.yml
├── requirements.txt
├── .env.example          ← template สำหรับ credentials
└── .gitignore
```

---

## เริ่มต้นใช้งาน

### Windows

1. ติดตั้ง [Python 3.10+](https://www.python.org/downloads/) และ [Ollama](https://ollama.com)
2. ดาวน์โหลด models:
   ```bat
   python scripts\setup_ollama.py
   ```
3. คัดลอกและกรอก credentials:
   ```bat
   copy .env.example .env
   ```
4. ดับเบิลคลิก **`start.bat`** — เซิร์ฟเวอร์เริ่ม + Admin Panel เปิดอัตโนมัติ

> หรือใช้ **`launcher.py`** สำหรับ GUI แบบ app (Wizard + Control Panel)

---

### macOS

1. ติดตั้ง [Python 3.10+](https://www.python.org/downloads/) และ [Ollama](https://ollama.com)
2. รัน setup ครั้งเดียว:
   ```bash
   bash scripts/setup_mac.sh
   ```
3. ดับเบิลคลิก **`LineBot.app`** ทุกครั้งที่ต้องการเปิด

---

## Admin Panel

เปิด [http://localhost:8000/admin](http://localhost:8000/admin) หลังรันเซิร์ฟเวอร์

| Tab | ทำอะไร |
|-----|--------|
| Dashboard | สถานะ Ollama, RAG, จำนวนข้อความ, เปิด/ปิด Bot |
| Config | แก้ URL, model, chunk size โดยไม่ต้องรีสตาร์ท |
| Knowledge | อัปโหลด / ลบ / ดูเอกสาร, rebuild RAG index |
| Persona | แก้ system prompt, ข้อความต้อนรับ, Quick Reply topics |
| Chat | ทดสอบ bot โดยตรงจาก browser |
| Sessions | ดูผู้ใช้ที่คุยอยู่, ล้างประวัติ, broadcast ข้อความ |
| Logs | ดู server log แบบ real-time |

---

## Docker

```bash
docker-compose up -d

# Pull models หลัง Ollama รันแล้ว
docker exec ollama ollama pull llama3.2
docker exec ollama ollama pull nomic-embed-text
```

---

## คำสั่งใน LINE Chat

| พิมพ์ | ผล |
|-------|-----|
| `รีเซ็ต` / `reset` / `/clear` | ล้างประวัติการสนทนา |
| `help` / `เมนู` / `/help` | แสดงเมนูและ Quick Reply |

---

## Architecture

```
LINE User ──► LINE Platform ──► POST /webhook
                                      │
                              ┌───────▼────────┐
                              │   RAG Service  │  ChromaDB + Ollama Embed
                              └───────┬────────┘
                                      │ context chunks
                              ┌───────▼────────┐
                              │  Ollama (LLM)  │  typhoon2 / llama3.2
                              └───────┬────────┘
                                      │
                              ┌───────▼────────┐
                              │ LINE Reply API │
                              └────────────────┘
```

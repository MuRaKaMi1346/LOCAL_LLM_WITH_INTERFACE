# 🌸 LINE Bot — Local AI

ระบบ LINE Bot สำหรับตอบคำถาม โดยใช้ Ollama (LLM ท้องถิ่น) และ RAG (Retrieval-Augmented Generation)  
มี Admin Panel สำหรับจัดการทุกอย่างผ่าน Web UI โดยไม่ต้องแก้โค้ด

---

## เริ่มต้นใช้งาน

### Windows — ดับเบิลคลิกเดียวจบ

1. ดาวน์โหลดโปรเจกต์และแตกไฟล์
2. ดับเบิลคลิก **`start.bat`**

`start.bat` จะติดตั้งทุกอย่างอัตโนมัติ:
- ✅ Python 3.12 (ถ้ายังไม่มี)
- ✅ Ollama (ถ้ายังไม่มี)
- ✅ ngrok (ถ้ายังไม่มี — สำหรับ webhook URL สาธารณะ)
- ✅ Python dependencies ทั้งหมด
- ✅ เปิด GUI Control Panel

> **หมายเหตุ:** ถ้าติดตั้ง Python หรือ Ollama ใหม่ จะมีข้อความให้ปิด-เปิด window แล้วรัน `start.bat` อีกครั้ง

> **ngrok Auth Token (แนะนำ):** สมัครฟรีที่ [ngrok.com](https://ngrok.com) แล้วใส่ token ใน `.env`:
> ```
> NGROK_AUTH_TOKEN=your_token_here
> ```
> GUI จะ set token ให้อัตโนมัติเมื่อ Start — ไม่มี token ก็ใช้งานได้แต่ URL จะเปลี่ยนทุกครั้ง

---

### macOS — รันครั้งเดียว

1. ดาวน์โหลดโปรเจกต์
2. รัน setup script ครั้งเดียว:

```bash
bash scripts/setup_mac.sh
```

setup script จะติดตั้งทุกอย่างอัตโนมัติ:
- ✅ Homebrew (ถ้ายังไม่มี)
- ✅ Python 3.12 + tkinter (ถ้ายังไม่มี)
- ✅ Ollama (ถ้ายังไม่มี)
- ✅ ngrok (ถ้ายังไม่มี — สำหรับ webhook URL สาธารณะ)
- ✅ Python dependencies ทั้งหมด
- ✅ ตั้งค่า LineBot.app

3. เปิดแอพครั้งต่อไปด้วย:
   - `bash start.sh`
   - หรือดับเบิลคลิก **`LineBot.app`**

---

## โครงสร้างโปรเจกต์

```
LINE Bot/
│
├── main.py               ← FastAPI entry point
├── config.py             ← การตั้งค่า (pydantic-settings)
├── state.py              ← สถานะ runtime (bot on/off, นับข้อความ)
├── launcher.py           ← GUI launcher (Windows / macOS)
├── start.bat             ← Windows one-click starter (auto-installs everything)
├── start.sh              ← macOS/Linux quick launcher
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
├── scripts/
│   ├── setup_mac.sh      ← macOS setup (auto-installs Homebrew/Python/Ollama)
│   └── setup_ollama.py   ← ดาวน์โหลด Ollama models แยก
│
├── LineBot.app/          ← macOS app bundle (ดับเบิลคลิกเพื่อเปิด)
│
├── Dockerfile
├── docker-compose.yml
├── requirements.txt
├── .env.example          ← template สำหรับ credentials
└── .gitignore
```

---

## Admin Panel

หลังกด Start ใน Control Panel แล้ว Admin Panel จะเปิดอัตโนมัติ  
หรือเปิดที่ [http://localhost:8000/admin](http://localhost:8000/admin)

| Tab | ทำอะไร |
|-----|--------|
| Dashboard | สถานะ Ollama, RAG, จำนวนข้อความ, เปิด/ปิด Bot |
| Config | แก้ URL, model, chunk size — Hot Reload ไม่ต้องรีสตาร์ท |
| Knowledge | อัปโหลด / ลบ / ดูเอกสาร, rebuild RAG index |
| Persona | แก้ system prompt, ข้อความต้อนรับ, Quick Reply topics |
| Chat | ทดสอบ bot โดยตรงจาก browser |
| Sessions | ดูผู้ใช้ที่คุยอยู่, ล้างประวัติ, broadcast ข้อความ |
| Logs | ดู server log แบบ real-time |

---

## Docker

```bash
# 1. สร้าง .env จาก template แล้วกรอก LINE credentials
cp .env.example .env

# 2. รัน Ollama + linebot พร้อมกัน
docker-compose up -d

# 3. รอ Ollama พร้อม (~30s) แล้ว pull models
docker exec ollama ollama pull llama3.2
docker exec ollama ollama pull nomic-embed-text

# 4. เปิด Admin Panel
open http://localhost:8000/admin
```

```bash
docker-compose logs -f linebot   # ดู logs
docker-compose down               # หยุด
docker-compose up -d --build      # rebuild หลังแก้โค้ด
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
                              │  Ollama (LLM)  │  llama3.2 / typhoon2 / etc.
                              └───────┬────────┘
                                      │
                              ┌───────▼────────┐
                              │ LINE Reply API │
                              └────────────────┘
```

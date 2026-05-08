
"""
วิธีใช้: python setup.py
ช่วย pull Ollama models ที่จำเป็นและตรวจสอบการติดตั้ง
"""
import subprocess
import sys


def run(cmd: list[str]) -> int:
    print(f"\n>>> {' '.join(cmd)}")
    result = subprocess.run(cmd)
    return result.returncode


def main():
    print("=" * 60)
    print("  Faculty LINE Bot — Setup")
    print("=" * 60)

    # Check Ollama
    ret = run(["ollama", "list"])
    if ret != 0:
        print("\n[ERROR] Ollama ไม่ได้ติดตั้งหรือไม่ได้รันอยู่")
        print("ดาวน์โหลด Ollama ได้ที่ https://ollama.com")
        sys.exit(1)

    print("\nPulling chat model (typhoon2-8b-instruct หรือ llama3.2)...")
    # Typhoon is great for Thai — fall back to llama3.2 if not available
    if run(["ollama", "pull", "llama3.2"]) != 0:
        print("[WARN] Failed to pull llama3.2, trying llama3...")
        run(["ollama", "pull", "llama3"])

    print("\nPulling embedding model (nomic-embed-text)...")
    run(["ollama", "pull", "nomic-embed-text"])

    print("\n[OK] Setup complete!")
    print("\nขั้นตอนถัดไป:")
    print("  1. Copy .env.example → .env และกรอก LINE credentials")
    print("  2. python main.py  (หรือ uvicorn main:app --reload)")
    print("  3. ตั้งค่า Webhook URL ใน LINE Developers Console")
    print("     https://developers.line.biz/console/")


if __name__ == "__main__":
    main()

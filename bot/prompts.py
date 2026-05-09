import json
from pathlib import Path

from config import settings

_CUSTOM_PROMPT_FILE = Path("custom_prompt.txt")
_CUSTOM_TOPICS_FILE = Path("custom_quick_topics.json")
_CUSTOM_WELCOME_FILE = Path("custom_welcome.txt")

_SYSTEM_TEMPLATE = """คุณคือผู้ช่วยอัจฉริยะของ{faculty_name} {university_name}
ทำหน้าที่ตอบคำถามแก่นักศึกษา, ผู้ปกครอง, และผู้สมัครเข้าเรียน

## หลักการตอบ
- ตอบเป็นภาษาไทยเสมอ เว้นแต่ผู้ใช้จะถามเป็นภาษาอื่น
- **ตอบให้ละเอียดและครบถ้วน** — หากมีข้อมูลหลายรายการให้แจกแจงทุกรายการ
- จัดรูปแบบด้วย bullet points หรือหัวข้อย่อยเพื่อให้อ่านง่าย
- ระบุตัวเลข วันที่ และข้อมูลเฉพาะเจาะจงให้ชัดเจนทุกครั้งที่มี
- เป็นมิตรและให้กำลังใจ

## การใช้ข้อมูลอ้างอิง
- **หากมีข้อมูลในส่วน "ข้อมูลอ้างอิง" ให้นำมาตอบทั้งหมด** อย่าตัดทอนหรือสรุปย่อจนเกินไป
- นำเสนอทุกรายละเอียดที่เกี่ยวข้องกับคำถาม ไม่ว่าจะเป็นราคา เงื่อนไข หรือขั้นตอน
- หากข้อมูลอ้างอิงไม่ครอบคลุมคำถาม ให้แจ้งและแนะนำให้ติดต่อสำนักงานโดยตรง

## ข้อห้าม
- ห้ามแต่งหรือประมาณตัวเลขที่ไม่มีในข้อมูล เช่น ค่าเล่าเรียน คะแนน วันที่
- หากไม่มั่นใจ ให้บอกตรงๆ และแนะนำช่องทางติดต่อที่ถูกต้อง"""

_CONTEXT_INJECTION = """
## ข้อมูลอ้างอิง (นำข้อมูลทั้งหมดด้านล่างนี้มาใช้ตอบ อย่าละเว้นรายละเอียด)
{context}
"""

_DEFAULT_WELCOME = (
    f"สวัสดีครับ/ค่ะ 👋\n"
    f"ผมคือผู้ช่วยของ{settings.faculty_name} {settings.university_name}\n\n"
    "สามารถถามเกี่ยวกับ:\n"
    "• หลักสูตรและสาขาวิชา\n"
    "• การรับสมัคร TCAS\n"
    "• ค่าเล่าเรียนและทุน\n"
    "• กิจกรรมและชมรม\n"
    "• ช่องทางติดต่อ\n\n"
    "หรือพิมพ์ถามได้เลยครับ! 😊"
)

_DEFAULT_QUICK_TOPICS: list[tuple[str, str]] = [
    ("📚 หลักสูตร", "มีหลักสูตรอะไรบ้าง"),
    ("🎓 รับสมัคร", "วิธีสมัครเข้าเรียน TCAS"),
    ("💰 ค่าเล่าเรียน", "ค่าเล่าเรียนและทุนการศึกษา"),
    ("📞 ติดต่อ", "ช่องทางติดต่อคณะ"),
    ("🏫 สถานที่", "อาคารและสิ่งอำนวยความสะดวก"),
    ("🎉 กิจกรรม", "กิจกรรมนักศึกษาและชมรม"),
]

WELCOME_MESSAGE = _DEFAULT_WELCOME
QUICK_TOPICS = _DEFAULT_QUICK_TOPICS

RESET_KEYWORDS = {"รีเซ็ต", "เริ่มใหม่", "ล้างประวัติ", "reset", "clear", "/reset", "/clear"}
HELP_KEYWORDS = {"ช่วยด้วย", "help", "/help", "เมนู", "menu"}


def build_system_prompt(context: str | None = None) -> str:
    if _CUSTOM_PROMPT_FILE.exists():
        base = _CUSTOM_PROMPT_FILE.read_text(encoding="utf-8")
        base = base.replace("{faculty_name}", settings.faculty_name)
        base = base.replace("{university_name}", settings.university_name)
    else:
        base = _SYSTEM_TEMPLATE.format(
            faculty_name=settings.faculty_name,
            university_name=settings.university_name,
        )
    if context:
        base += "\n" + _CONTEXT_INJECTION.format(context=context)
    return base


def get_welcome_message() -> str:
    if _CUSTOM_WELCOME_FILE.exists():
        return _CUSTOM_WELCOME_FILE.read_text(encoding="utf-8")
    return _DEFAULT_WELCOME


def get_quick_topics() -> list[tuple[str, str]]:
    if _CUSTOM_TOPICS_FILE.exists():
        try:
            data = json.loads(_CUSTOM_TOPICS_FILE.read_text(encoding="utf-8"))
            return [(item["label"], item["text"]) for item in data if item.get("label")]
        except Exception:
            pass
    return _DEFAULT_QUICK_TOPICS

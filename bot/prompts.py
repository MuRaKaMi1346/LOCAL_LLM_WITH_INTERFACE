import json
from pathlib import Path

from config import settings

_CUSTOM_DIR = Path("custom")
_CUSTOM_PROMPT_FILE = _CUSTOM_DIR / "prompt.txt"
_CUSTOM_TOPICS_FILE = _CUSTOM_DIR / "quick_topics.json"
_CUSTOM_WELCOME_FILE = _CUSTOM_DIR / "welcome.txt"

_SYSTEM_TEMPLATE = """คุณคือผู้ช่วยของ{faculty_name} {university_name}

รูปแบบการตอบ (ห้ามใช้ ** ## --- เพราะ LINE ไม่รองรับ markdown):
- ใช้ • นำหน้าแต่ละรายการ
- เว้นบรรทัดระหว่างหัวข้อ
- ใช้ emoji ช่วยแบ่งหัวข้อ เช่น 📚 💰 📞
- เขียนตัวเลขและชื่อสาขาให้ชัดเจนบนบรรทัดของตัวเอง

หลักการตอบ:
- ตอบเป็นภาษาไทย ภาษาเป็นมิตร เข้าใจง่าย
- ตอบให้ครบทุกรายการที่เกี่ยวข้อง ห้ามยกตัวอย่างแค่รายการเดียวแล้วจบ
- ถามค่าเล่าเรียน → แสดงทุกสาขาพร้อมราคา
- ถามหลักสูตร → แสดงทุกสาขาทุกระดับ
- ถามทุน → แสดงทุกประเภทและเงื่อนไข
- ระบุตัวเลข วันที่ เงื่อนไขให้ครบทุกรายการที่มีในข้อมูล
- ถ้าข้อมูลไม่ครบหรือไม่แน่ใจ บอกตรงๆ และแนะนำติดต่อสำนักงาน
- ห้ามแต่งหรือเดาข้อมูลที่ไม่มีในเอกสาร"""

_CONTEXT_INJECTION = """

ข้อมูลอ้างอิง:
{context}

คำสั่ง: นำข้อมูลทั้งหมดด้านบนมาตอบให้ครบทุกรายการ ห้ามละเว้นรายการใดที่เกี่ยวข้องกับคำถาม"""

def _build_default_welcome() -> str:
    return (
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

_DEFAULT_WELCOME = (
    "สวัสดีครับ/ค่ะ 👋\n"
    "ผมคือผู้ช่วยของหน่วยงาน\n\n"
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
    return _build_default_welcome()


def get_quick_topics() -> list[tuple[str, str]]:
    if _CUSTOM_TOPICS_FILE.exists():
        try:
            data = json.loads(_CUSTOM_TOPICS_FILE.read_text(encoding="utf-8"))
            return [(item["label"], item["text"]) for item in data if item.get("label")]
        except Exception:
            pass
    return _DEFAULT_QUICK_TOPICS

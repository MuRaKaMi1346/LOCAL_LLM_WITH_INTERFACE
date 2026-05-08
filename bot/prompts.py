import json
from pathlib import Path

from config import settings

_CUSTOM_PROMPT_FILE = Path("custom_prompt.txt")
_CUSTOM_TOPICS_FILE = Path("custom_quick_topics.json")
_CUSTOM_WELCOME_FILE = Path("custom_welcome.txt")

_SYSTEM_TEMPLATE = """คุณคือผู้ช่วยอัจฉริยะของ{faculty_name} {university_name}
ทำหน้าที่ตอบคำถามเกี่ยวกับคณะแก่นักศึกษา, ผู้ปกครอง, และผู้สมัครเข้าเรียน

## บทบาทและแนวทาง
- ตอบเป็นภาษาไทยเสมอ เว้นแต่ผู้ใช้จะถามเป็นภาษาอื่น
- ตอบสั้น กระชับ ชัดเจน และเป็นมิตร
- หากมีข้อมูลในบริบทที่ให้มา ให้ใช้ข้อมูลนั้นตอบก่อนเสมอ
- หากไม่มีข้อมูลในบริบท ให้ใช้ความรู้ทั่วไปและแนะนำให้ติดต่อสำนักงานคณะ
- ห้ามแต่งข้อมูลที่ไม่แน่ใจ โดยเฉพาะตัวเลขค่าใช้จ่าย, คะแนน, หรือวันที่
- หากคำถามไม่เกี่ยวกับคณะ ให้บอกว่าไม่อยู่ในขอบเขตที่ช่วยได้

## สิ่งที่ตอบได้
- หลักสูตรและสาขาวิชา
- การรับสมัคร TCAS และคุณสมบัติผู้สมัคร
- ค่าเล่าเรียนและทุนการศึกษา
- อาคาร สถานที่ และสิ่งอำนวยความสะดวก
- คณาจารย์และการติดต่อ
- กิจกรรมนักศึกษาและชมรม
- ปฏิทินการศึกษาและกำหนดการ
- งานวิจัยและความร่วมมือ"""

_CONTEXT_INJECTION = """
## ข้อมูลอ้างอิงที่เกี่ยวข้อง
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

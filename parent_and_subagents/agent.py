import os
import logging
import google.cloud.logging
from datetime import datetime
from dotenv import load_dotenv

from google.adk import Agent
from google.adk.agents import SequentialAgent, LoopAgent, ParallelAgent
from google.adk.tools.tool_context import ToolContext
from google.adk.tools.langchain_tool import LangchainTool
from google.adk.models import Gemini
from google.genai import types
from google.adk.tools import exit_loop

from langchain_community.tools import WikipediaQueryRun
from langchain_community.utilities import WikipediaAPIWrapper


#  1) SYSTEM SETUP
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(message)s")

try:
    cloud_logging_client = google.cloud.logging.Client()
    cloud_logging_client.setup_logging()
except Exception:
    pass

load_dotenv()

model_name = os.getenv("MODEL", "gemini-1.5-pro-preview-0409")
RETRY_OPTIONS = types.HttpRetryOptions(initial_delay=1, attempts=6)

api_wrapper = WikipediaAPIWrapper(top_k_results=3, doc_content_chars_max=5000)
wiki_tool = LangchainTool(tool=WikipediaQueryRun(api_wrapper=api_wrapper))


# 2) TOOLS 

def normalize_topic_tool(tool_context: ToolContext, user_input: str) -> dict:
    """
    หา Official Wikipedia Title แบบ deterministic:
    - ใช้ api_wrapper.load() เพื่อได้ Document ที่มี metadata.title
    - เลือก title ตัวแรกเป็น official (ตามการจัดอันดับ top_k_results)
    """
    query = (user_input or "").strip()
    if not query:
        return {"status": "error", "official_title": ""}

    try:
        docs = api_wrapper.load(query)
    except Exception as e:
        logging.error(f"[ERROR] normalize_topic_tool load() failed: {str(e)}")
        return {"status": "error", "official_title": query}

    titles = []
    for d in docs or []:
        try:
            t = (d.metadata or {}).get("title", "") or ""
        except Exception:
            t = ""
        if t:
            titles.append(t)

    official = titles[0] if titles else query
    tool_context.state["official_title_candidates"] = titles
    logging.info(f"[TOPIC NORMALIZED] user_input='{query}' -> official='{official}'")

    return {"status": "success", "official_title": official}


def set_topic_tool(tool_context: ToolContext, official_topic_name: str) -> dict:
    """
    บันทึกหัวข้อ + ตั้งต้นคำค้นให้ 2 ฝั่ง
    """
    tool_context.state["topic"] = official_topic_name

    tool_context.state["pos_queries"] = [
        f"{official_topic_name} achievements",
        f"{official_topic_name} awards",
        f"{official_topic_name} legacy",
    ]
    tool_context.state["neg_queries"] = [
        f"{official_topic_name} controversy",
        f"{official_topic_name} criticism",
        f"{official_topic_name} scandals",
    ]

    logging.info(f"[CASE OPENED] Official Topic set to: {official_topic_name}")
    return {"status": "success"}


def append_to_state(tool_context: ToolContext, field: str, response: str) -> dict:
    """
    สะสมข้อความลง state เป็น list พร้อมเวลา
    """
    existing = tool_context.state.get(field, [])
    if isinstance(existing, str):
        existing = [existing]
    if not isinstance(existing, list):
        existing = []

    timestamp = datetime.now().strftime("%H:%M:%S")
    tool_context.state[field] = existing + [f"[{timestamp}] {response}"]
    return {"status": "success"}


def add_query_tool(tool_context: ToolContext, field: str, query: str) -> dict:
    """
    เพิ่มคำค้นลง pos_queries หรือ neg_queries เพื่อให้รอบถัดไปค้นเฉพาะเจาะจงขึ้นจริง
    """
    q = tool_context.state.get(field, [])
    if not isinstance(q, list):
        q = []
    q.append(query)
    tool_context.state[field] = q
    return {"status": "success"}


def get_latest_query_tool(tool_context: ToolContext, field: str) -> dict:
    """
    คืน query ตัวท้ายสุดจาก pos_queries/neg_queries แบบชัวร์
    """
    q = tool_context.state.get(field, [])
    if isinstance(q, list) and len(q) > 0:
        return {"status": "success", "query": q[-1]}
    return {"status": "success", "query": tool_context.state.get("topic", "")}


def write_verdict_file(tool_context: ToolContext, content: str = "") -> dict:
    """
    บันทึกไฟล์ .txt ลงโฟลเดอร์ final_verdicts_output
    """
    try:
        base_folder = "final_verdicts_output"
        current_dir = os.path.dirname(os.path.abspath(__file__))
        target_dir = os.path.join(current_dir, base_folder)
        os.makedirs(target_dir, mode=0o755, exist_ok=True)

        topic_prefix = tool_context.state.get("topic", "Report")
        safe_topic = "".join([c for c in topic_prefix if c.isalnum() or c in (" ", "-", "_")]).strip()

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        final_filename = f"{safe_topic}_{timestamp}.txt"
        target_path = os.path.join(target_dir, final_filename)

        with open(target_path, "w", encoding="utf-8") as f:
            f.write(content)

        return {"status": "success", "path": target_path}
    except Exception as e:
        return {"status": "error", "message": str(e)}


# 3) AGENTS 

admirer = Agent(
    name="admirer",
    model=Gemini(model=model_name, retry_options=RETRY_OPTIONS),
    description="ค้นหาข้อมูลด้านบวก",
    instruction="""
บทบาท: ทนายฝ่ายสนับสนุน
คดี: "{topic?}"

ขั้นตอน (ต้องทำตามลำดับ):
1) เรียก get_latest_query_tool(field="pos_queries")
2) เรียก wiki_tool ด้วย query ที่ได้เท่านั้น
3) สรุปจากผล Wikipedia เท่านั้น (ห้ามเดาจากความรู้เดิม)
4) บันทึกด้วย append_to_state(field="pos_data", response=...)

รูปแบบ:
- bullet 3–6 ข้อ
- เน้นความสำเร็จ/บทบาท/ผลงาน/อิทธิพล
""",
    tools=[get_latest_query_tool, wiki_tool, append_to_state],
)

critic = Agent(
    name="critic",
    model=Gemini(model=model_name, retry_options=RETRY_OPTIONS),
    description="ค้นหาข้อมูลด้านลบ",
    instruction="""
บทบาท: อัยการฝ่ายค้าน
คดี: "{topic?}"

ขั้นตอน (ต้องทำตามลำดับ):
1) เรียก get_latest_query_tool(field="neg_queries")
2) เรียก wiki_tool ด้วย query ที่ได้เท่านั้น
3) สรุปจากผล Wikipedia เท่านั้น (ห้ามเดาจากความรู้เดิม)
4) บันทึกด้วย append_to_state(field="neg_data", response=...)

รูปแบบ:
- bullet 3–6 ข้อ
- เน้นข้อโต้แย้ง/คำวิจารณ์/ประเด็นอื้อฉาว/ผลกระทบด้านลบ
""",
    tools=[get_latest_query_tool, wiki_tool, append_to_state],
)

judge = Agent(
    name="judge",
    model=Gemini(model=model_name, retry_options=RETRY_OPTIONS),
    description="ตรวจสอบหลักฐานและสั่งค้นเพิ่ม",
    instruction="""
บทบาท: ผู้พิพากษา
คดี: "{topic?}"

กติกา:
1) ตรวจ pos_data และ neg_data
   - เกณฑ์ขั้นต่ำ: ฝั่งละอย่างน้อย 2 entries
2) ถ้าฝั่งใดน้อยไป:
   - เรียก add_query_tool เพื่อเพิ่มคำค้นที่เจาะจงขึ้น
   - บันทึกเหตุผลลง judge_notes ด้วย append_to_state
   - ห้ามเรียก exit_loop
3) ถ้าสมดุลแล้ว:
   - บันทึกว่า "หลักฐานเพียงพอ" ลง judge_notes
   - ต้องเรียก exit_loop เพื่อจบ loop ทันที

ตัวอย่างคำค้น:
- บวก: "{topic?} reforms", "{topic?} contributions", "{topic?} policy"
- ลบ: "{topic?} allegations", "{topic?} controversy", "{topic?} criticism"
""",
    tools=[add_query_tool, append_to_state, exit_loop],
)

clerk = Agent(
    name="clerk",
    model=Gemini(model=model_name, retry_options=RETRY_OPTIONS),
    description="พนักงานศาลจัดทำรายงานและบันทึกไฟล์",
    instruction="""
บทบาท: รายงานคำพิพากษาของศาลจำลอง
คดี: "{topic?}"

หน้าที่:
1) รวบรวมจาก State: pos_data, neg_data, judge_notes
2) เขียนรายงานให้เป็นกลาง โดยมีหัวข้อ:
   - บทนำ
   - หลักฐานฝ่ายสนับสนุน
   - หลักฐานฝ่ายค้าน
   - บันทึกการพิจารณาของศาลจำลอง (สรุปจาก judge_notes และชั่งน้ำหนัก 2 ฝั่ง)
   - บทวิเคราะห์
   - คำตัดสิน
3) บันทึกไฟล์ด้วย write_verdict_file(content=รายงาน)
""",
    tools=[write_verdict_file],
)


#  4) WORKFLOW

investigation_team = ParallelAgent(
    name="investigation_team",
    sub_agents=[admirer, critic],
    description="ทีมสืบสวนทำงานขนานกัน",
)

trial_session = LoopAgent(
    name="trial_session",
    sub_agents=[investigation_team, judge],
    max_iterations=3,
    description="วงรอบการไต่สวน",
)

historical_court_system = SequentialAgent(
    name="historical_court_system",
    sub_agents=[trial_session, clerk],
)


# 5) ROOT AGENT

root_agent = Agent(
    name="receptionist",
    model=Gemini(model=model_name, retry_options=RETRY_OPTIONS),
    description="เจ้าหน้าที่รับเรื่อง ตรวจชื่อหัวข้อเป็น Official Wikipedia Title ก่อนเปิดคดี",
    instruction="""
คุณคือเจ้าหน้าที่รับเรื่อง

ขั้นตอน (ต้องทำตามลำดับ):
1) เรียก normalize_topic_tool(user_input=...) เพื่อหา Official Wikipedia Title แบบ deterministic
2) นำค่า official_title ไปเรียก set_topic_tool(official_topic_name=...)
3) ส่งต่องานให้ historical_court_system

หมายเหตุ: ใช้หัวข้อจาก State key: {topic?}
""",
    sub_agents=[historical_court_system],
    tools=[normalize_topic_tool, set_topic_tool],
)


# 6) MAIN

if __name__ == "__main__":
    print("System Ready. Waiting for input...")

    test_topic = "ธรรมนัส พรหมเผ่า"

    initial_state = {
        "topic": "",
        "pos_data": [],
        "neg_data": [],
        "pos_queries": [],
        "neg_queries": [],
        "judge_notes": [],
        "official_title_candidates": [],
    }

    result = root_agent.run(input=test_topic, state=initial_state)
    print("Court Session Adjourned.")
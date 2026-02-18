#  The Historical Court  
## Multi-Agent System with Google ADK

โครงงานนี้พัฒนาระบบ **Multi-Agent System** ด้วย Google Agent Development Kit (ADK)  
เพื่อวิเคราะห์บุคคลหรือเหตุการณ์ทางประวัติศาสตร์ในรูปแบบ **“ศาลจำลอง”**  
โดยสืบค้นข้อมูลจาก Wikipedia ทั้งด้านบวกและด้านลบ แล้วสรุปเป็นรายงานที่เป็นกลางที่สุด

---

# วัตถุประสงค์

1. ออกแบบสถาปัตยกรรม Multi-Agent ตามรูปแบบ Sequential + Parallel + Loop  
2. วิเคราะห์ข้อมูลจาก Wikipedia อย่างมีโครงสร้าง  
3. จัดการ Session State อย่างเป็นระบบ  
4. ใช้ `exit_loop` tool เพื่อควบคุมการจบ Loop ตามเงื่อนไข  
5. สร้างรายงานสรุปผลและบันทึกเป็นไฟล์ `.txt`

---

# สถาปัตยกรรมระบบ (System Architecture)
<img width="1312" height="897" alt="image" src="https://github.com/user-attachments/assets/0c806392-4704-4aaa-97d6-3a2ed93c32b7" />

ระบบแบ่งเป็น 4 ขั้นตอนหลัก

---

## Step 1: The Inquiry (Sequential)

**Agent: receptionist**

หน้าที่:
1. รับชื่อหัวข้อจากผู้ใช้
2. เรียก `normalize_topic_tool()` เพื่อหา Official Wikipedia Title แบบ deterministic
3. เรียก `set_topic_tool()` เพื่อเตรียม keyword สำหรับฝ่ายบวก/ลบ
4. ส่งงานต่อไปยังระบบศาล

---

## Step 2: The Investigation (Parallel)


###  Agent A – The Admirer
ค้นหาเฉพาะ:
- achievements  
- awards  
- legacy  
- contributions  

ขั้นตอน:
1. เรียก `get_latest_query_tool()`
2. เรียก `wiki_tool`
3. สรุปจาก Wikipedia เท่านั้น
4. บันทึกลง `pos_data`

---

###  Agent B – The Critic
ค้นหาเฉพาะ:
- controversy  
- criticism  
- scandals  
- allegations  

บันทึกลง `neg_data`

---

## Step 3: The Trial & Review (Loop)


### Agent: judge

เงื่อนไขขั้นต่ำ:
- pos_data ≥ 2 entries  
- neg_data ≥ 2 entries  

หากข้อมูลไม่สมดุล:
- เรียก `add_query_tool()` เพื่อเพิ่ม keyword ที่เจาะจงขึ้น
- บันทึกเหตุผลใน `judge_notes`
- ห้ามจบ loop

หากข้อมูลเพียงพอ:
- บันทึกว่า “หลักฐานเพียงพอ”
- เรียก `exit_loop()` เท่านั้น

> ห้ามใช้ prompt เพียงอย่างเดียวในการจบ loop  
> ต้องใช้ `exit_loop` tool ตามข้อกำหนด

---

## Step 4: The Verdict (Output)

**Agent: clerk**

หน้าที่:
1. รวบรวม `pos_data`, `neg_data`, `judge_notes`
2. เขียนรายงานแบบเป็นกลาง
3. บันทึกไฟล์ผ่าน `write_verdict_file()`

โครงสร้างรายงาน:
- บทนำ  
- หลักฐานฝ่ายสนับสนุน  
- หลักฐานฝ่ายค้าน  
- บันทึกการพิจารณาของศาลจำลอง  
- บทวิเคราะห์  
- คำตัดสิน  

---

# การจัดการ State

โครงสร้าง Session State:

```python
{
  "topic": "",
  "pos_data": [],
  "neg_data": [],
  "pos_queries": [],
  "neg_queries": [],
  "judge_notes": [],
  "official_title_candidates": []
}
---
---

#  Tools ที่ใช้

| Tool | หน้าที่ |
|------|---------|
| `normalize_topic_tool` | แปลงชื่อเป็น Official Wikipedia Title |
| `set_topic_tool` | ตั้งค่า keyword เริ่มต้น |
| `get_latest_query_tool` | ดึง keyword ล่าสุด |
| `add_query_tool` | เพิ่ม keyword เมื่อข้อมูลไม่พอ |
| `append_to_state` | บันทึกข้อมูลลง state |
| `write_verdict_file` | บันทึกไฟล์รายงาน |
| `exit_loop` | ควบคุมการจบ loop |
| `wiki_tool` | ดึงข้อมูลจาก Wikipedia |

---

#  Flow การทำงาน

```
User Input
    ↓
Receptionist (Sequential)
    ↓
Parallel Investigation
    ↓
Judge (Loop)
    ↓
Clerk
    ↓
Final Verdict File (.txt)
```

---

#  Output

```
final_verdicts_output/
<topic>_YYYYMMDD_HHMMSS.txt
```

---

#  Run

```bash
python agent.py
```

ตัวอย่างหัวข้อที่ใช้ทดสอบ:

```
Genghis Khan
Cold War
Ada Lovelace
ธรรมนัส พรหมเผ่า
```

---

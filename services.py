import json
import requests
import os
from openai import OpenAI
from typing import Dict, Any, List
from datetime import datetime, timedelta

# ========= הגדרות כלליות =========

DATA_FILE = "data.json"
CONVERSATION_FILE = "conversations.json"
ALLOWED_NUMBERS_FILE = "allowed_numbers.json"

# --- משתני סביבה (לגוגל קלאוד / סביבה מקומית) ---
OPENAI_KEY = os.getenv("OPENAI_KEY", "")
GREEN_INSTANCE = os.getenv("GREEN_INSTANCE", "")
GREEN_TOKEN = os.getenv("GREEN_TOKEN", "")
# -----------------------------------


# ========= פונקציות עזר לקבצים =========

def load_data() -> List[Dict[str, Any]]:
    """טוען את רשימת המשלוחים מ-data.json."""
    try:
        with open(DATA_FILE, "r", encoding="utf8") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return []


def save_data(data: List[Dict[str, Any]]):
    """שומר את רשימת המשלוחים ל-data.json."""
    try:
        with open(DATA_FILE, "w", encoding="utf8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print("❌ שגיאה בשמירת data.json:", e)


def load_conversations() -> Dict[str, List[Dict]]:
    """טוען את היסטוריית השיחות."""
    try:
        with open(CONVERSATION_FILE, "r", encoding="utf8") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def save_conversations(conversations: Dict[str, List[Dict]]):
    """שומר את היסטוריית השיחות."""
    try:
        with open(CONVERSATION_FILE, "w", encoding="utf8") as f:
            json.dump(conversations, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print("❌ שגיאה בשמירת conversations.json:", e)


def load_allowed_numbers() -> List[str]:
    """טוען את רשימת המספרים שמותר לשלוח אליהם הודעה."""
    try:
        with open(ALLOWED_NUMBERS_FILE, "r", encoding="utf8") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return []


def save_allowed_numbers(numbers: List[str]):
    """שומר את רשימת המספרים המורשים."""
    try:
        with open(ALLOWED_NUMBERS_FILE, "w", encoding="utf8") as f:
            json.dump(numbers, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print("❌ שגיאה בשמירת allowed_numbers.json:", e)


def normalize_phone(phone: str) -> str:
    """מנרמל מספר טלפון לפורמט 972xxxxxxxxx"""
    phone = str(phone).strip().replace("-", "").replace(" ", "").replace("+", "")
    phone = phone.lstrip("0")
    if not phone.startswith("972"):
        phone = "972" + phone
    return phone


# ========= חישוב זמן משוער להגעה =========

def calculate_time_range(position: int, start_time: datetime = None) -> str:
    """מחשב טווח זמן משוער לפי מיקום המשלוח ברשימה."""
    if start_time is None:
        start_time = datetime.now()
    
    if position <= 20:
        min_minutes = 20
        max_minutes = 150
    elif position <= 40:
        min_minutes = 120
        max_minutes = 270
    elif position <= 60:
        min_minutes = 270
        max_minutes = 390
    else:
        extra_batches = (position - 60) // 20
        min_minutes = 270 + (extra_batches * 120)
        max_minutes = 390 + (extra_batches * 120)
    
    arrival_min = start_time + timedelta(minutes=min_minutes)
    arrival_max = start_time + timedelta(minutes=max_minutes)
    
    time_format = "%H:%M"
    return f"{arrival_min.strftime(time_format)}-{arrival_max.strftime(time_format)}"


# ========= שליחת הודעות וואטסאפ (Green API) =========

def send_whatsapp_message(phone: str, message: str):
    """שולח הודעת וואטסאפ ללקוח דרך Green-API."""
    
    phone = normalize_phone(phone)
    
    allowed = load_allowed_numbers()
    phone_short = phone.lstrip("972")
    if phone_short not in allowed and phone not in allowed:
        print(f"❌ מספר {phone} לא ברשימת המורשים – לא שולחים הודעה.")
        return False
    
    url = f"https://api.green-api.com/waInstance{GREEN_INSTANCE}/sendMessage/{GREEN_TOKEN}"
    chat_id = phone + "@c.us"
    
    payload = {
        "chatId": chat_id,
        "message": message
    }
    
    try:
        resp = requests.post(url, json=payload, timeout=10)
        if resp.status_code == 200:
            print(f"✔ נשלחה הודעה ל-{phone}")
            return True
        else:
            print(f"❌ שגיאה בשליחה ל-{phone}: {resp.status_code} {resp.text}")
            return False
    except Exception as e:
        print("❌ שגיאה ב-requests לשליחת הודעה:", e)
        return False


# ========= סוכן AI חכם - שיחה טבעית =========

def chat_with_ai_agent(phone: str, user_message: str, delivery: dict) -> dict:
    """
    סוכן AI שמנהל שיחה טבעית עם הלקוח.
    מחזיר: {
        "reply": "תשובת הבוט ללקוח",
        "extracted_data": {...},  # מידע שהסוכן חילץ
        "is_complete": True/False  # האם יש את כל המידע?
    }
    """
    
    client = OpenAI(api_key=OPENAI_KEY)
    
    # טעינת היסטוריית שיחה
    conversations = load_conversations()
    phone_short = phone.lstrip("972")
    
    if phone_short not in conversations:
        conversations[phone_short] = []
    
    conversation_history = conversations[phone_short]
    
    # בניית ההקשר למערכת
    name = delivery.get("recipient_name", "")
    city = delivery.get("city", "")
    street = delivery.get("street", "")
    time_range = delivery.get("estimated_time_range", "")
    
    # מידע קיים
    someone_home = delivery.get("someone_home")
    drop_location = delivery.get("drop_location")
    apartment = delivery.get("apartment")
    floor = delivery.get("floor")
    entrance_code = delivery.get("entrance_code")
    
    system_prompt = f"""אתה סוכן שירות לקוחות של חברת Buzz - שירות משלוחים.
שמך הוא "רועי" ואתה מדבר בצורה מקצועית אך חמה בעברית.

🎯 **המשימה שלך:**
לנהל שיחה יעילה עם {name} ולאסוף את המידע הבא:
1. האם מישהו יהיה בבית? (כן/לא)
2. אם לא - איפה להשאיר את החבילה?
3. מספר דירה
4. קומה
5. קוד כניסה (או אין)

📦 **פרטי המשלוח:**
- לקוח: {name}
- כתובת: {street}, {city}
- זמן הגעה משוער: {time_range}

📊 **מידע שכבר יש לנו:**
- יש מישהו בבית: {someone_home if someone_home else "לא יודעים עדיין"}
- מיקום השארה: {drop_location if drop_location else "לא יודעים עדיין"}
- דירה: {apartment if apartment else "לא יודעים עדיין"}
- קומה: {floor if floor else "לא יודעים עדיין"}
- קוד כניסה: {entrance_code if entrance_code else "לא יודעים עדיין"}

🎭 **סגנון דיבור:**
- קצר ועניני - משפט אחד או שניים בלבד
- מקצועי אך לא קר
- ללא אימוג'י (או מקסימום 1 להודעה)
- לא חוזר על מידע שכבר יש
- לא משתמש במילים כמו "מעולה!", "סופר!", "יש!"
- פשוט ועניני: "תודה", "בסדר", "הבנתי"

💡 **חשוב:**
- שאלה אחת בלכד בכל הודעה
- אם הלקוח נותן מידע - פשוט תודה ושאלה הבאה
- אם משהו לא ברור - בקש הבהרה קצרה
- **בסיום - אל תאמר "מעולה" או "נהדר"**, פשוט אשר את הפרטים

🔧 **פורמט התשובה:**
אתה חייב להחזיר JSON בפורמט הבא:
{{
  "reply": "התשובה שלך ללקוח (טקסט חופשי)",
  "extracted_data": {{
    "someone_home": "yes" / "no" / null,
    "drop_location": "מיקום" / null,
    "apartment": "מספר" / null,
    "floor": "מספר" / null,
    "entrance_code": "קוד" / "אין קוד" / null
  }},
  "is_complete": true / false
}}

**is_complete = true רק אם:**
- someone_home = "yes" (ואז זה הכל)
- או someone_home = "no" ויש לנו: drop_location, apartment, floor, entrance_code

**דוגמאות תשובות טובות:**

לקוח: "כן"
{{
  "reply": "תודה. השליח יגיע ויתקשר בדלת.",
  "extracted_data": {{"someone_home": "yes", "drop_location": null, "apartment": null, "floor": null, "entrance_code": null}},
  "is_complete": true
}}

לקוח: "לא אהיה"
{{
  "reply": "בסדר. איפה נוח לך שנשאיר את החבילה?",
  "extracted_data": {{"someone_home": "no", "drop_location": null, "apartment": null, "floor": null, "entrance_code": null}},
  "is_complete": false
}}

לקוח: "מחוץ לדלת"
{{
  "reply": "הבנתי. מה מספר הדירה?",
  "extracted_data": {{"someone_home": null, "drop_location": "מחוץ לדלת", "apartment": null, "floor": null, "entrance_code": null}},
  "is_complete": false
}}

לקוח: "דירה 5"
{{
  "reply": "תודה. באיזו קומה?",
  "extracted_data": {{"someone_home": null, "drop_location": null, "apartment": "5", "floor": null, "entrance_code": null}},
  "is_complete": false
}}

לקוח: "קומה 3"
{{
  "reply": "בסדר. יש קוד כניסה לבניין?",
  "extracted_data": {{"someone_home": null, "drop_location": null, "apartment": null, "floor": "3", "entrance_code": null}},
  "is_complete": false
}}

לקוח: "אין"
{{
  "reply": "תודה רבה {name}.

📦 סיכום המשלוח:
📍 {street}, {city}
🏢 קומה {{floor}}, דירה {{apartment}}
📦 להשאיר: {{drop_location}}
🔑 קוד: אין

השליח יגיע בין השעות {time_range}.",
  "extracted_data": {{"someone_home": null, "drop_location": null, "apartment": null, "floor": null, "entrance_code": "אין קוד"}},
  "is_complete": true
}}

**חשוב: כשמסיימים (is_complete = true), תמיד תן סיכום מלא של כל הפרטים בפורמט הזה:**
```
תודה רבה {{name}}.

📦 סיכום המשלוח:
📍 {{street}}, {{city}}
🏢 קומה {{floor}}, דירה {{apartment}}
📦 להשאיר: {{drop_location}}
🔑 קוד: {{entrance_code}}

השליח יגיע בין השעות {{time_range}}.
```

אם someone_home = "yes", הסיכום יהיה פשוט יותר:
```
תודה רבה {{name}}.

השליח יגיע בין השעות {{time_range}} ויתקשר בדלת.
📍 {{street}}, {{city}}
```
"""

    # בניית ההיסטוריה
    messages = [{"role": "system", "content": system_prompt}]
    
    for msg in conversation_history[-10:]:  # רק 10 הודעות אחרונות
        messages.append({"role": msg["role"], "content": msg["content"]})
    
    messages.append({"role": "user", "content": user_message})
    
    try:
        resp = client.chat.completions.create(
            model="gpt-4o-mini",
            response_format={"type": "json_object"},
            messages=messages,
            temperature=0.3,  # הורדתי מ-0.7 ל-0.3 למענות יותר עקביות
        )
        
        content = resp.choices[0].message.content
        print("🤖 תשובת AI:", content)
        
        result = json.loads(content)
        
        # שמירת השיחה
        conversation_history.append({"role": "user", "content": user_message})
        conversation_history.append({"role": "assistant", "content": result.get("reply", "")})
        
        conversations[phone_short] = conversation_history
        save_conversations(conversations)
        
        return result
    
    except Exception as e:
        print("❌ שגיאה בקריאה ל-OpenAI:", e)
        return {
            "reply": "סליחה, הייתה בעיה טכנית. נסה שוב.",
            "extracted_data": {
                "someone_home": None,
                "drop_location": None,
                "apartment": None,
                "floor": None,
                "entrance_code": None
            },
            "is_complete": False
        }


def clear_conversation(phone: str):
    """מוחק את היסטוריית השיחה של לקוח."""
    conversations = load_conversations()
    phone_short = phone.lstrip("972")
    if phone_short in conversations:
        del conversations[phone_short]
        save_conversations(conversations)
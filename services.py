import json
import requests
from openai import OpenAI
from typing import Dict, Any, List
from datetime import datetime, timedelta
import os 

# ========= הגדרות כלליות =========

DATA_FILE = "data.json"

OPENAI_KEY = os.environ.get("OPENAI_KEY", "DEFAULT_OPENAI_KEY_IF_MISSING")
GREEN_INSTANCE = os.environ.get("GREEN_INSTANCE", "DEFAULT_GREEN_INSTANCE_IF_MISSING")
GREEN_TOKEN = os.environ.get("GREEN_TOKEN", "DEFAULT_GREEN_TOKEN_IF_MISSING")


# ========= פונקציות עזר =========

def load_data() -> Dict[str, Dict[str, Any]]:
    """
    טוען את הנתונים מהקובץ. מבטיח החזרה של מילון (dict).
    """
    try:
        with open(DATA_FILE, "r", encoding="utf8") as f:
            data = json.load(f)
            # בדיקה קריטית: אם הנתונים הם רשימה (מגרסה ישנה), נחזיר מילון ריק או נמיר
            if isinstance(data, list):
                return {} 
            return data if isinstance(data, dict) else {}
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def save_data(data: Dict[str, Dict[str, Any]]):
    try:
        with open(DATA_FILE, "w", encoding="utf8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print("❌ שגיאה בשמירת data.json:", e)


def normalize_phone(phone: str) -> str:
    phone = str(phone).strip().replace("-", "").replace(" ", "").replace("+", "")
    phone = phone.lstrip("0")
    if not phone.startswith("972"):
        phone = "972" + phone
    return phone


def calculate_time_range(position: int, start_time: datetime = None) -> str:
    if start_time is None:
        start_time = datetime.now()
    
    base_delay = 30
    per_delivery = 5
    
    start_delay = base_delay + (position * per_delivery)
    end_delay = start_delay + 120 
    
    arrival_min = start_time + timedelta(minutes=start_delay)
    arrival_max = start_time + timedelta(minutes=end_delay)
    
    time_format = "%H:%M"
    return f"{arrival_min.strftime(time_format)}-{arrival_max.strftime(time_format)}"


def send_whatsapp_message(phone: str, message: str):
    phone = normalize_phone(phone)
    url = f"https://api.green-api.com/waInstance{GREEN_INSTANCE}/sendMessage/{GREEN_TOKEN}"
    chat_id = phone + "@c.us"
    payload = {"chatId": chat_id, "message": message}
    
    try:
        resp = requests.post(url, json=payload, timeout=10)
        return resp.status_code == 200
    except Exception as e:
        print("❌ שגיאה בשליחה:", e)
        return False


# ========= AI – ניתוח ושיחה (טבעי וזורם) =========

def analyze_text_with_ai(text: str, current_state: dict) -> dict:
    """
    מנתח את הטקסט ומחזיר תשובה טבעית ואנושית.
    """
    client = OpenAI(api_key=OPENAI_KEY)
    
    state_desc = json.dumps(current_state, ensure_ascii=False)
    
    system_prompt = f"""
    אתה "בוט Buzz", שליח חכם, אדיב וקליל.
    המטרה שלך: לנהל שיחה נעימה עם הלקוח כדי להשיג את פרטי הגישה למשלוח.
    
    הנחיות לתגובה (reply_message):
    1. **סגנון דיבור:** דבר בעברית טבעית, יומיומית וקצרה. תהיה נחמד אבל ענייני. מותר להשתמש באימוג'יז 📦😊.
    2. **זרימת השיחה:** - אם חסר מידע, תשאל עליו בצורה שמתאימה להקשר. אל תהיה רובוטי ("חסר שדה X").
       - תשאל שאלה אחת בכל פעם כדי לא להעמיס.
       - סדר עדיפות: קודם כל תברר אם בבית. אם לא - איפה להשאיר. אחר כך פרטים טכניים (דירה/קומה/קוד).
    
    3. **חילוץ מידע:**
       - נסה להבין הקשר. אם הלקוח כותב "תשאיר בלובי", תבין מזה שצריך לעדכן את המיקום ל"לובי" ושלא צריך לשאול יותר שאלות.
       - אם הלקוח כותב "קומה 2 דירה 4", תחלץ את שניהם בבת אחת.
    
    מבנה פלט JSON:
    {{
      "extracted_data": {{
          "someone_home": "yes" | "no" | null,
          "drop_location": string | null,
          "apartment": string | null,
          "floor": string | null,
          "entrance_code": string | null
      }},
      "reply_message": "ההודעה שלך ללקוח"
    }}
    
    מצב נוכחי של הנתונים (מה שיש לנו כבר):
    {state_desc}
    """
    
    user_content = f"""הודעת הלקוח: "{text}"\nתגיב בצורה טבעית."""
    
    try:
        resp = client.chat.completions.create(
            model="gpt-4o-mini",
            response_format={"type": "json_object"},
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user",  "content": user_content},
            ],
            temperature=0.7, # יצירתיות מאוזנת לשיחה טבעית
        )
        return json.loads(resp.choices[0].message.content)
    except Exception as e:
        print("❌ AI Error:", e)
        return {
            "extracted_data": {},
            "reply_message": "סליחה, לא הבנתי. תוכל לחזור על זה?"
        }
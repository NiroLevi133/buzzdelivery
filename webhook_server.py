from fastapi import FastAPI, Request
import json
import uvicorn
from datetime import datetime, timedelta

from services import (
    load_data, 
    save_data, 
    chat_with_ai_agent,
    send_whatsapp_message,
    normalize_phone,
    clear_conversation
)

app = FastAPI()

# מנגנון למניעת הודעות כפולות
recent_messages = {}

def is_duplicate_message(phone: str, message: str) -> bool:
    """בודק אם זו הודעה כפולה תוך 30 שניות"""
    now = datetime.now()
    message_id = hash(message)
    
    if phone not in recent_messages:
        recent_messages[phone] = {}
    
    # ניקוי הודעות ישנות
    recent_messages[phone] = {
        mid: ts for mid, ts in recent_messages[phone].items()
        if (now - ts).total_seconds() < 60
    }
    
    # בדיקה אם ההודעה כבר התקבלה
    if message_id in recent_messages[phone]:
        last_time = recent_messages[phone][message_id]
        if (now - last_time).total_seconds() < 30:
            return True
    
    recent_messages[phone][message_id] = now
    return False


@app.post("/webhook")
async def whatsapp_webhook(request: Request):
    """
    Webhook חדש - עם סוכן AI שמנהל שיחה טבעית
    """
    
    # קריאת Payload
    try:
        payload = await request.json()
    except Exception as e:
        print(f"❌ שגיאה: {e}")
        return {"status": "error"}
    
    print("\n" + "="*70)
    print("📩 הודעה חדשה")
    
    # בדיקת סוג הודעה
    msg_data = payload.get("messageData", {})
    if msg_data.get("typeMessage") != "textMessage":
        print("⚠️ לא הודעת טקסט")
        return {"status": "ignored"}
    
    # חילוץ נתונים
    try:
        text = payload["messageData"]["textMessageData"]["textMessage"].strip()
        chat_id = payload["senderData"]["chatId"]
        phone = normalize_phone(chat_id.replace("@c.us", ""))
        
        print(f"📱 טלפון: {phone}")
        print(f"💬 הודעה: '{text}'")
    except Exception as e:
        print(f"❌ שגיאה בחילוץ: {e}")
        return {"status": "error"}
    
    # בדיקת הודעה כפולה
    if is_duplicate_message(phone, text):
        print("⚠️ הודעה כפולה - מתעלם")
        return {"status": "duplicate"}
    
    # חיפוש משלוח
    deliveries = load_data()
    delivery = None
    phone_short = phone.lstrip("972")
    
    for d in deliveries:
        d_phone = normalize_phone(str(d.get("recipient_phone", ""))).lstrip("972")
        if d_phone == phone_short:
            delivery = d
            break
    
    if not delivery:
        print(f"⚠️ מספר {phone} לא נמצא")
        return {"status": "not_found"}
    
    name = delivery.get("recipient_name", "")
    print(f"👤 לקוח: {name}")
    
    # בדיקה אם השיחה כבר הסתיימה
    if delivery.get("status") == "מלא":
        print("✅ המשלוח כבר הושלם - לא משיבים")
        return {"status": "already_complete"}
    
    # שמירת ההודעה האחרונה
    delivery["last_message"] = text
    delivery["last_interaction"] = datetime.now().isoformat()
    
    # הדפסת מצב נוכחי
    print(f"\n📊 מצב נוכחי:")
    print(f"   someone_home: {delivery.get('someone_home')}")
    print(f"   drop_location: {delivery.get('drop_location')}")
    print(f"   apartment: {delivery.get('apartment')}")
    print(f"   floor: {delivery.get('floor')}")
    print(f"   entrance_code: {delivery.get('entrance_code')}")
    
    # 🤖 קריאה לסוכן AI
    print("\n🤖 שולח לסוכן AI...")
    ai_response = chat_with_ai_agent(phone, text, delivery)
    
    print(f"\n💬 תשובת הסוכן: {ai_response.get('reply')}")
    print(f"📊 מידע שחולץ: {json.dumps(ai_response.get('extracted_data'), ensure_ascii=False)}")
    print(f"✅ הושלם: {ai_response.get('is_complete')}")
    
    # עדכון המידע שחולץ
    extracted = ai_response.get("extracted_data", {})
    
    if extracted.get("someone_home"):
        delivery["someone_home"] = extracted["someone_home"]
    
    if extracted.get("drop_location"):
        delivery["drop_location"] = extracted["drop_location"]
    
    if extracted.get("apartment"):
        delivery["apartment"] = extracted["apartment"]
    
    if extracted.get("floor"):
        delivery["floor"] = extracted["floor"]
    
    if extracted.get("entrance_code"):
        delivery["entrance_code"] = extracted["entrance_code"]
    
    # עדכון סטטוס
    if ai_response.get("is_complete"):
        delivery["status"] = "מלא"
        delivery["completed_at"] = datetime.now().isoformat()
        print("🎉 המשלוח הושלם!")
    else:
        delivery["status"] = "חלקי"
    
    # שמירה
    save_data(deliveries)
    
    # שליחת התשובה ללקוח
    reply = ai_response.get("reply", "")
    if reply:
        send_whatsapp_message(phone, reply)
    
    print("="*70)
    return {"status": "ok", "is_complete": ai_response.get("is_complete")}


@app.post("/reset-conversation/{phone}")
async def reset_conversation(phone: str):
    """
    מאפס את השיחה של לקוח ספציפי.
    שימושי אם רוצים להתחיל מחדש.
    """
    phone = normalize_phone(phone)
    clear_conversation(phone)
    return {"status": "ok", "message": f"השיחה של {phone} אופסה"}


@app.get("/health")
async def health_check():
    """בדיקת תקינות השרת"""
    return {"status": "ok", "timestamp": datetime.now().isoformat()}


if __name__ == "__main__":
    print("🚀 מפעיל Buzz AI Agent Server...")
    print("📡 Webhook: http://localhost:8000/webhook")
    print("🔄 Reset: POST http://localhost:8000/reset-conversation/{phone}")
    print("="*70)
    uvicorn.run(app, host="0.0.0.0", port=8000)
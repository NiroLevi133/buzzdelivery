from fastapi import FastAPI, Request
import json
import uvicorn
from datetime import datetime
from typing import Dict, Any
import os 

from services import (
    load_data, 
    save_data, 
    analyze_text_with_ai, 
    send_whatsapp_message,
    normalize_phone
)

app = FastAPI()
recent_messages = {}

def is_duplicate_message(phone: str, message: str) -> bool:
    now = datetime.now()
    message_id = hash(message)
    if phone not in recent_messages: recent_messages[phone] = {}
    recent_messages[phone] = {m: t for m, t in recent_messages[phone].items() if (now - t).total_seconds() < 120}
    if message_id in recent_messages[phone] and (now - recent_messages[phone][message_id]).total_seconds() < 60: return True
    recent_messages[phone][message_id] = now
    return False

def find_and_update_delivery(all_batches, phone):
    norm_phone = phone.lstrip("972")
    for bid, bdata in all_batches.items():
        for i, d in enumerate(bdata["deliveries"]):
            if normalize_phone(str(d.get("recipient_phone"))).lstrip("972") == norm_phone:
                return d, bid, str(i)
    return None, None, None

@app.post("/webhook")
async def whatsapp_webhook(request: Request):
    try:
        payload = await request.json()
        msg_data = payload.get("messageData", {})
        if msg_data.get("typeMessage") != "textMessage": return {"status": "ignored"}
        
        text = msg_data["textMessageData"]["textMessage"].strip()
        chat_id = payload["senderData"]["chatId"]
        phone = normalize_phone(chat_id.replace("@c.us", ""))
        
        if is_duplicate_message(phone, text): return {"status": "duplicate"}
        
        all_batches = load_data()
        delivery, batch_id, idx = find_and_update_delivery(all_batches, phone)
        
        if not delivery: return {"status": "not_found"}
        
        delivery["last_message"] = text
        
        # הכנת המצב הנוכחי לשליחה ל-AI
        current_state = {
            "someone_home": delivery.get("someone_home"),
            "drop_location": delivery.get("drop_location"),
            "apartment": delivery.get("apartment"),
            "floor": delivery.get("floor"),
            "entrance_code": delivery.get("entrance_code")
        }
        
        # === ה-AI מנהל את השיחה (בצורה טבעית) ===
        ai_response = analyze_text_with_ai(text, current_state)
        
        # 1. עדכון נתונים
        extracted = ai_response.get("extracted_data", {})
        data_changed = False
        for key, val in extracted.items():
            if val is not None and val != delivery.get(key):
                delivery[key] = val
                data_changed = True
        
        # בדיקה אם סיימנו (לצורך סטטוס ב-DB)
        is_finished = False
        if delivery.get("someone_home") == "yes":
            is_finished = True
        elif delivery.get("drop_location") and any(x in str(delivery.get("drop_location")) for x in ["שומר", "לובי", "קבלה"]):
            is_finished = True
            if not delivery.get("apartment"): delivery["apartment"] = "-"
            if not delivery.get("floor"): delivery["floor"] = "-"
            if not delivery.get("entrance_code"): delivery["entrance_code"] = "-"
        elif delivery.get("apartment") and delivery.get("floor") and delivery.get("entrance_code"):
            is_finished = True
            
        if is_finished:
            delivery["status"] = "מלא"
        elif data_changed: 
            delivery["status"] = "בתיאום"
            
        # 2. שליחת התגובה שה-AI ניסח
        reply_message = ai_response.get("reply_message")
        if reply_message:
            send_whatsapp_message(phone, reply_message)
            
        # 3. שמירה
        all_batches[batch_id]["deliveries"][int(idx)] = delivery
        save_data(all_batches)
        
        return {"status": "ok"}

    except Exception as e:
        print("Error:", e)
        return {"status": "error"}
        
    return {"status": "ok"}

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)
import streamlit as st
import pandas as pd
from datetime import datetime
from services import (
    send_whatsapp_message,
    load_data,
    save_data,
    calculate_time_range,
    normalize_phone
)
import uuid 
import os 

# עיצוב RTL והתאמות לטבלה
st.markdown("""
<style>
body, html, .stTextInput, .stButton, .stDataFrame, .stTextArea, div[data-testid="stTable"], .stNumberInput {
    direction: rtl;
    text-align: right;
}
/* עיצוב כותרות הטבלה */
th {
    text-align: right !important;
}
</style>
""", unsafe_allow_html=True)

# --- אתחול נתונים חכם (תיקון השגיאה) ---
if "all_batches" not in st.session_state:
    data = load_data()
    # בדיקה קריטית: אם הנתונים הם רשימה (גרסה ישנה), נאפס למילון
    if isinstance(data, list):
        st.session_state["all_batches"] = {}
    else:
        st.session_state["all_batches"] = data

# הגנה נוספת: ודא שזה מילון בכל מקרה
if not isinstance(st.session_state["all_batches"], dict):
    st.session_state["all_batches"] = {}

# אתחול רשימה זמנית לבניית המסלול (אם לא קיימת)
if "temp_route_list" not in st.session_state:
    st.session_state["temp_route_list"] = []

st.sidebar.title("🚛 Buzz Lite")
page = st.sidebar.selectbox("בחר פעולה:", ["בניית מסלול (הזנה)", "המסלול שלי (צפייה)"])

# ============================================================
# 1) בניית מסלול (הזנה דינמית)
# ============================================================
if page == "בניית מסלול (הזנה)":
    st.title("📝 בניית מסלול הפצה")
    st.info("הוסף את המשלוחים אחד-אחד. בסיום, לחץ על 'שלח הודעות לכולם'.")
    
    # זיהוי שליח (נשמר ב-Session כדי לא להקליד כל רגע)
    if "dispatcher_phone" not in st.session_state:
        st.session_state["dispatcher_phone"] = ""
        
    dispatcher_phone = st.text_input("מספר הטלפון שלך (השליח):", 
                                     value=st.session_state["dispatcher_phone"],
                                     placeholder="05X-XXXXXXX").strip()
    st.session_state["dispatcher_phone"] = dispatcher_phone # שמירה

    st.markdown("---")

    # --- חישוב המספר הסידורי הבא ---
    # ברירת המחדל: המספר הגבוה ביותר ברשימה + 1, או 1 אם הרשימה ריקה
    current_list = st.session_state["temp_route_list"]
    if current_list:
        next_seq = max([item['seq'] for item in current_list]) + 1
    else:
        next_seq = 1

    # --- טופס הוספת משלוח (שורה אחת) ---
    with st.form(key="add_delivery_form", clear_on_submit=True):
        c1, c2, c3 = st.columns([1, 2, 2])
        
        with c1:
            # השליח יכול לשנות את המספר ידנית אם יש כפילות
            seq_input = st.number_input("מס' סידורי", min_value=1, value=next_seq, step=1)
        with c2:
            name_input = st.text_input("שם הנמען (אופציונלי)")
        with c3:
            phone_input = st.text_input("טלפון (חובה)")
            
        add_btn = st.form_submit_button("➕ הוסף לרשימה")

    # --- לוגיקה בהוספה ---
    if add_btn:
        if not phone_input:
            st.error("❌ חובה להזין מספר טלפון.")
        else:
            # הוספה לרשימה הזמנית בזיכרון
            new_item = {
                "seq": seq_input,
                "name": name_input if name_input else "לקוח",
                "phone": normalize_phone(phone_input)
            }
            st.session_state["temp_route_list"].append(new_item)
            st.rerun() # ריענון כדי לעדכן את הטבלה ואת המספר הסידורי הבא

    # --- תצוגת הטבלה שנבנית ---
    if st.session_state["temp_route_list"]:
        st.write(f"### 📋 רשימת משלוחים ({len(st.session_state['temp_route_list'])})")
        
        # המרה ל-DataFrame לתצוגה יפה
        df = pd.DataFrame(st.session_state["temp_route_list"])
        
        # תצוגה בטבלה
        st.dataframe(
            df.rename(columns={"seq": "מס'", "name": "שם", "phone": "טלפון"}),
            use_container_width=True,
            hide_index=True
        )
        
        col_actions1, col_actions2 = st.columns(2)
        
        with col_actions1:
            if st.button("🗑️ נקה רשימה והתחל מחדש"):
                st.session_state["temp_route_list"] = []
                st.rerun()
                
        with col_actions2:
            # --- הכפתור הגדול: יצירת המסלול ושליחה ---
            if st.button("🚀 סיימתי - צור מסלול ושלח הודעות"):
                if not dispatcher_phone:
                    st.error("אנא הזן את מספר הטלפון שלך למעלה.")
                else:
                    # יצירת Batch
                    batch_id = f"ROUTE-{datetime.now().strftime('%Y%m%d-%H%M%S')}"
                    
                    new_batch = {
                        "dispatcher_phone": normalize_phone(dispatcher_phone),
                        "upload_time": datetime.now().strftime("%Y-%m-%d %H:%M"),
                        "deliveries": []
                    }
                    
                    progress = st.progress(0)
                    sent_count = 0
                    total = len(st.session_state["temp_route_list"])
                    
                    for i, item in enumerate(st.session_state["temp_route_list"]):
                        # חישוב זמן משוער
                        time_range = calculate_time_range(i + 1)
                        
                        delivery = {
                            "sequence_number": item["seq"],
                            "recipient_name": item["name"],
                            "recipient_phone": item["phone"],
                            "status": "נשלח",
                            "last_message": "",
                            "someone_home": None,
                            "drop_location": None,
                            "apartment": None,
                            "floor": None,
                            "entrance_code": None,
                            "estimated_time_range": time_range,
                            "batch_id": batch_id
                        }
                        
                        new_batch["deliveries"].append(delivery)
                        
                        # הודעת פתיחה מותאמת
                        msg_name = f" {item['name']}" if item['name'] != "לקוח" else ""
                        
                        msg = f"""היי{msg_name}! 👋 כאן השליח של Buzz.
יש לי משלוח עבורך שצפוי להגיע בין השעות {time_range}.

כדי שאוכל למסור אותו, אני צריך לדעת:
❓ האם יהיה מישהו בבית בשעות אלו? (כן / לא)"""

                        send_whatsapp_message(item["phone"], msg)
                        sent_count += 1
                        progress.progress((i + 1) / total)
                    
                    # שמירה ל-DB
                    st.session_state["all_batches"][batch_id] = new_batch
                    save_data(st.session_state["all_batches"])
                    
                    # איפוס
                    st.session_state["temp_route_list"] = []
                    st.success(f"✅ המסלול נוצר בהצלחה! נשלחו {sent_count} הודעות.")
                    st.balloons()

# ============================================================
# 2) המסלול שלי (צפייה וניהול)
# ============================================================
elif page == "המסלול שלי (צפייה)":
    st.title("📋 המסלול שלי")
    
    # שימוש בטלפון שנשמר בזיכרון אם קיים
    default_phone = st.session_state.get("dispatcher_phone", "")
    search = st.text_input("הכנס טלפון שליח:", value=default_phone, placeholder="05X-XXXXXXX").strip()
    
    if search:
        norm_search = normalize_phone(search)
        
        # שימוש ב-session_state כדי למנוע טעינה מחדש מיותרת
        all_data = st.session_state["all_batches"]
        my_deliveries = []
        
        # איסוף כל המשלוחים (עם הגנה מפני סוגי מידע שגויים)
        if isinstance(all_data, dict):
            for bid, bdata in all_data.items():
                if bdata.get("dispatcher_phone") == norm_search:
                    my_deliveries.extend(bdata["deliveries"])
        
        if not my_deliveries:
            st.warning("לא נמצאו משלוחים למספר זה.")
        else:
            # המרה ל-DF ומיון
            df = pd.DataFrame(my_deliveries)
            
            # מיון לפי ה-Batch ID (שהוא זמן) ואז לפי המספר הסידורי
            df = df.sort_values(by=["batch_id", "sequence_number"], ascending=[False, True])
            
            st.subheader(f"סה״כ משלוחים פעילים: {len(df)}")

            # תצוגה נקייה לשליח
            df_show = df[[
                "sequence_number", "recipient_name", "recipient_phone", "someone_home", 
                "drop_location", "floor", "apartment", "entrance_code", "status"
            ]].rename(columns={
                "sequence_number": "מס'",
                "recipient_name": "שם",
                "recipient_phone": "טלפון",
                "someone_home": "בבית?",
                "drop_location": "איפה להשאיר",
                "floor": "קומה",
                "apartment": "דירה",
                "entrance_code": "קוד",
                "status": "סטטוס"
            })
            
            # שימוש ב-dataframe אינטראקטיבי
            st.dataframe(df_show, hide_index=True)
            
            st.info("💡 הנתונים מתעדכנים בזמן אמת כשהלקוחות עונים בוואטסאפ.")
            
            if st.button("🔄 רענן נתונים"):
                st.session_state["all_batches"] = load_data()
                st.rerun()
import streamlit as st
import pandas as pd
from datetime import datetime
from services import (
    send_whatsapp_message,
    load_data,
    save_data,
    save_allowed_numbers,
    calculate_time_range,
    load_conversations,
    clear_conversation
)

# RTL CSS
st.markdown("""
<style>
body, html, .stTextInput, .stButton, .stDataFrame, .css-18e3th9, .css-1d391kg {
    direction: rtl;
    text-align: right;
}
.full-status { background-color: #d4edda; color: #155724; padding: 5px; border-radius: 5px; font-weight: bold; }
.partial-status { background-color: #fff3cd; color: #856404; padding: 5px; border-radius: 5px; font-weight: bold; }
.missing-status { background-color: #f8d7da; color: #721c24; padding: 5px; border-radius: 5px; font-weight: bold; }
.chat-message { padding: 10px; margin: 5px; border-radius: 10px; max-width: 80%; }
.user-message { background-color: #e3f2fd; margin-left: auto; text-align: right; }
.bot-message { background-color: #f5f5f5; margin-right: auto; text-align: left; }
</style>
""", unsafe_allow_html=True)


# מערכת נתונים בזיכרון
if "deliveries" not in st.session_state:
    st.session_state["deliveries"] = load_data()


st.sidebar.title("🚛 תפריט Buzz AI")
page = st.sidebar.selectbox("בחר מסך:", [
    "העלאת קובץ", 
    "שליחת הודעות פתיחה", 
    "דשבורד משלוחים",
    "צפייה בשיחות"
])


# ============================================================
# 1) העלאת קובץ
# ============================================================
if page == "העלאת קובץ":
    st.title("📦 העלאת קובץ משלוחים חדש")
    
    st.info("""
    **פורמט הקובץ הנדרש:**
    - עמודות חובה: `ID`, `recipient_name`, `recipient_phone`, `city`, `street`
    - עמודות אופציונליות: `apartment`, `floor`, `entrance_code`
    """)
    
    file = st.file_uploader("העלה קובץ Excel (פורמט XLSX)", type=["xlsx"])
    
    if file:
        df = pd.read_excel(file)
        st.subheader("נתוני קובץ:")
        st.dataframe(df)
        
        # מיפוי אפשרויות שמות עמודות
        col_mapping = {
            "ID": ["ID", "id", "מזהה"],
            "recipient_name": ["recipient_name", "name", "שם", "שם לקוח"],
            "recipient_phone": ["recipient_phone", "phone", "טלפון", "מספר טלפון"],
            "city": ["city", "עיר"],
            "street": ["street", "רחוב", "כתובת"]
        }
        
        normalized_df = df.copy()
        for standard_name, possible_names in col_mapping.items():
            for possible in possible_names:
                if possible in df.columns:
                    normalized_df.rename(columns={possible: standard_name}, inplace=True)
                    break
        
        required_cols = ["ID", "recipient_name", "recipient_phone", "city", "street"]
        missing_cols = [col for col in required_cols if col not in normalized_df.columns]
        
        if missing_cols:
            st.error(f"❌ חסרות עמודות חובה: {', '.join(missing_cols)}")
        else:
            if st.button("✅ שמור למערכת והכן לשליחה"):
                data = normalized_df.to_dict(orient="records")
                
                for i, d in enumerate(data, start=1):
                    d["recipient_phone"] = str(d["recipient_phone"]).replace("-", "").replace(" ", "").strip()
                    d["status"] = "חסר"
                    d["last_message"] = ""
                    d["someone_home"] = None
                    d["estimated_time_range"] = calculate_time_range(i)
                    d["position"] = i
                    d["apartment"] = d.get("apartment")
                    d["floor"] = d.get("floor")
                    d["entrance_code"] = d.get("entrance_code")
                
                st.session_state["deliveries"] = data
                save_data(data)
                
                allowed_numbers = [
                    str(p).replace("-", "").replace(" ", "").strip() 
                    for p in normalized_df["recipient_phone"].unique()
                ]
                save_allowed_numbers(allowed_numbers)
                
                st.success(f"✅ הקובץ נטען בהצלחה! ({len(data)} משלוחים)")


# ============================================================
# 2) שליחת הודעות פתיחה
# ============================================================
elif page == "שליחת הודעות פתיחה":
    st.title("📨 שליחת הודעות פתיחה ללקוחות")
    
    deliveries = load_data()
    
    if not deliveries:
        st.warning("⚠️ לא נטען עדיין קובץ משלוחים.")
    else:
        num_to_send = len(deliveries)
        st.info(f"מוכן לשליחת הודעה ל-**{num_to_send}** לקוחות.")
        
        with st.expander("👀 לחץ לראות דוגמה להודעה שתישלח"):
            example = deliveries[0] if deliveries else {}
            example_name = example.get("recipient_name", "ישראל ישראלי")
            example_time = example.get("estimated_time_range", "10:00-12:30")
            example_city = example.get("city", "תל אביב")
            example_street = example.get("street", "דיזנגוף 50")
            
            st.markdown(f"""
```
היי {example_name}! 👋

יש לך חבילה בדרך מ-Buzz!
השליח שלנו צפוי להגיע בין השעות {example_time}

📍 הכתובת שלך: {example_street}, {example_city}

האם יהיה מישהו בבית? 🏠
```
            """)
        
        if st.button(f"🚀 שלח הודעה לכל ה-{num_to_send} לקוחות"):
            progress_bar = st.progress(0)
            status_text = st.empty()
            
            success_count = 0
            fail_count = 0
            
            for i, d in enumerate(deliveries):
                phone = str(d["recipient_phone"])
                name = d["recipient_name"]
                time_range = d.get("estimated_time_range", "זמן מיוסך")
                city = d.get("city", "")
                street = d.get("street", "")
                
                message = f"""היי {name}! 👋

יש לך חבילה בדרך מ-Buzz!
השליח שלנו צפוי להגיע בין השעות {time_range}

📍 הכתובת שלך: {street}, {city}

האם יהיה מישהו בבית? 🏠"""
                
                status_text.text(f"שולח ל-{name} ({i+1}/{num_to_send})...")
                
                if send_whatsapp_message(phone, message):
                    success_count += 1
                else:
                    fail_count += 1
                
                progress_bar.progress((i + 1) / num_to_send)
            
            status_text.empty()
            st.success(f"""
            ✅ תהליך השליחה הסתיים!
            - נשלחו בהצלחה: {success_count}
            - נכשלו: {fail_count}
            
            🤖 הבוט מחכה כעת לתשובות הלקוחות בוואטסאפ
            """)


# ============================================================
# 3) דשבורד משלוחים
# ============================================================
elif page == "דשבורד משלוחים":
    st.title("🚚 דשבורד Buzz – סטטוס משלוחים")
    
    col1, col2 = st.columns([3, 1])
    with col1:
        st.info("הנתונים מתעדכנים אוטומטית כשהלקוח עונה.")
    with col2:
        if st.button("🔄 רענן"):
            st.rerun()
    
    deliveries = load_data()
    
    if not deliveries:
        st.warning("⚠️ אין נתוני משלוחים להצגה.")
    else:
        # סטטיסטיקות
        total = len(deliveries)
        completed = len([d for d in deliveries if d.get("status") == "מלא"])
        partial = len([d for d in deliveries if d.get("status") == "חלקי"])
        missing = len([d for d in deliveries if d.get("status") == "חסר"])
        
        st.subheader("📊 סטטיסטיקות")
        cols = st.columns(4)
        cols[0].metric("סה״כ משלוחים", total)
        cols[1].metric("✅ מלא", completed)
        cols[2].metric("⚠️ חלקי", partial)
        cols[3].metric("❌ חסר", missing)
        
        st.markdown("---")
        
        # פילטרים
        st.subheader("🔎 סינון")
        filter_col1, filter_col2 = st.columns(2)
        
        with filter_col1:
            status_filter = st.multiselect(
                "סנן לפי סטטוס:",
                options=["מלא", "חלקי", "חסר"],
                default=["מלא", "חלקי", "חסר"]
            )
        
        with filter_col2:
            search_name = st.text_input("חיפוש לפי שם לקוח:")
        
        # סינון הנתונים
        filtered = [d for d in deliveries if d.get("status") in status_filter]
        
        if search_name:
            filtered = [d for d in filtered if search_name.lower() in d.get("recipient_name", "").lower()]
        
        if not filtered:
            st.warning("אין משלוחים התואמים לסינון.")
        else:
            # הכנת DataFrame
            df = pd.DataFrame(filtered)
            
            def format_status(status):
                if status == "מלא":
                    return "<span class='full-status'>✅ מלא</span>"
                elif status == "חלקי":
                    return "<span class='partial-status'>⚠️ חלקי</span>"
                else:
                    return "<span class='missing-status'>❌ חסר</span>"
            
            df["סטטוס_HTML"] = df["status"].apply(format_status)
            
            display_df = df[[
                "position", "recipient_name", "recipient_phone", 
                "estimated_time_range", "סטטוס_HTML",
                "city", "street", "apartment", "floor", "entrance_code"
            ]].rename(columns={
                "position": "#",
                "recipient_name": "שם לקוח",
                "recipient_phone": "טלפון",
                "estimated_time_range": "זמן משוער",
                "סטטוס_HTML": "סטטוס",
                "city": "עיר",
                "street": "רחוב",
                "apartment": "דירה",
                "floor": "קומה",
                "entrance_code": "קוד כניסה"
            })
            
            display_df = display_df.sort_values("#")
            
            st.markdown(display_df.to_html(escape=False, index=False), unsafe_allow_html=True)
            
            st.download_button(
                label="📥 הורד כ-CSV",
                data=display_df.to_csv(index=False).encode('utf-8-sig'),
                file_name=f"buzz_deliveries_{datetime.now().strftime('%Y%m%d_%H%M')}.csv",
                mime="text/csv"
            )


# ============================================================
# 4) צפייה בשיחות
# ============================================================
elif page == "צפייה בשיחות":
    st.title("💬 צפייה בשיחות עם הלקוחות")
    
    deliveries = load_data()
    conversations = load_conversations()
    
    if not deliveries:
        st.warning("⚠️ אין נתוני משלוחים.")
    else:
        # בחירת לקוח
        customer_options = {
            f"{d['recipient_name']} ({d['recipient_phone']})": d['recipient_phone']
            for d in deliveries
        }
        
        selected_customer = st.selectbox(
            "בחר לקוח לצפייה בשיחה:",
            options=list(customer_options.keys())
        )
        
        if selected_customer:
            phone = customer_options[selected_customer]
            phone_short = phone.lstrip("972").lstrip("0")
            
            # מציאת המשלוח
            delivery = next((d for d in deliveries if phone_short in str(d.get("recipient_phone"))), None)
            
            if delivery:
                st.markdown("---")
                
                # מידע על הלקוח
                col1, col2 = st.columns(2)
                with col1:
                    st.subheader(f"👤 {delivery['recipient_name']}")
                    st.write(f"📍 {delivery.get('street', '')}, {delivery.get('city', '')}")
                    st.write(f"⏰ זמן משוער: {delivery.get('estimated_time_range', '')}")
                
                with col2:
                    status = delivery.get("status", "חסר")
                    if status == "מלא":
                        st.success("✅ הושלם")
                    elif status == "חלקי":
                        st.warning("⚠️ חלקי")
                    else:
                        st.error("❌ חסר")
                
                st.markdown("---")
                
                # הצגת השיחה
                if phone_short in conversations and conversations[phone_short]:
                    st.subheader("💬 השיחה:")
                    
                    for msg in conversations[phone_short]:
                        if msg["role"] == "user":
                            st.markdown(f"""
                            <div class="chat-message user-message">
                                <strong>👤 {delivery['recipient_name']}:</strong><br>
                                {msg['content']}
                            </div>
                            """, unsafe_allow_html=True)
                        elif msg["role"] == "assistant":
                            st.markdown(f"""
                            <div class="chat-message bot-message">
                                <strong>🤖 אלכס (Buzz):</strong><br>
                                {msg['content']}
                            </div>
                            """, unsafe_allow_html=True)
                    
                    # כפתור לאיפוס שיחה
                    if st.button("🔄 אפס שיחה"):
                        clear_conversation(phone)
                        st.success("השיחה אופסה!")
                        st.rerun()
                else:
                    st.info("💭 עדיין אין שיחה עם לקוח זה.")
            else:
                st.error("לא נמצא משלוח ללקוח זה.")
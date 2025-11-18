# שימוש בתמונת בסיס רשמית של פייתון
FROM python:3.11-slim

# הגדרת משתני סביבה כדי למנוע יצירת קבצי .pyc
ENV PYTHONDONTWRITEBYTECODE 1
ENV PYTHONUNBUFFERED 1

# הגדרת תיקיית העבודה
WORKDIR /app

# העתקת קובץ הדרישות והתקנת ספריות
COPY requirements.txt /app/
RUN pip install --no-cache-dir -r requirements.txt

# העתקת קבצי הפרויקט
COPY . /app

# ברירת מחדל: הפעלת השרת על הפורט הנדרש על ידי Cloud Run (משתמש ב-Gunicorn וב-Uvicorn כהמלצה ל-production)
# Cloud Run מגדיר את משתנה הסביבה PORT באופן אוטומטי
CMD exec gunicorn --bind :${PORT:-8080} --workers 1 --worker-class uvicorn.workers.UvicornWorker webhook_server:app

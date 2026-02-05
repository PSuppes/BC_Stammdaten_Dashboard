import os
from dotenv import load_dotenv
from supabase import create_client

load_dotenv()

url = os.getenv("SUPABASE_URL")
key = os.getenv("SUPABASE_KEY")

try:
    supabase = create_client(url, key)
    res = supabase.table("import_queue").select("*", count="exact").execute()
    print("✅ Verbindung zu Supabase erfolgreich!")
    print(f"📊 Aktuelle Anzahl Einträge: {len(res.data)}")
except Exception as e:
    print(f"❌ Fehler: {e}")
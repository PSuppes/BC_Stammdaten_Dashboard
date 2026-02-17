import time
import os
import requests
import re
import hashlib
import json
from datetime import datetime
from PIL import Image, ImageDraw
from dotenv import load_dotenv
from supabase import create_client, Client
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

# Selenium
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.options import Options
from webdriver_manager.chrome import ChromeDriverManager

# Lokale Logik & BC Connector
from connector import BusinessCentralConnector, VALUE_MAPPINGS, clean_string_global

# --- CONFIG & INITIALISIERUNG ---
load_dotenv()

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")
supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

START_URL = "https://flowzz.com/product?pagination%5Bpage%5D=124"
ANZAHL_CHECK = 2000
BILDER_ORDNER = "Produkt_Bilder"
MAX_ITEMS_PRO_SPALTE = 3

# --- HELPER FUNKTIONEN (ORIGINAL GITHUB LOGIK) ---
def make_session():
    retry = Retry(
        total=5, 
        backoff_factor=1.2,
        status_forcelist=[429, 500, 502, 503, 504],
        allowed_methods=["GET"]
    )
    adapter = HTTPAdapter(max_retries=retry, pool_connections=50, pool_maxsize=50)
    s = requests.Session()
    s.mount("https://", adapter)
    s.headers.update({"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"})
    return s

SESSION = make_session()

def get_driver():
    chrome_options = Options()
    chrome_options.add_argument("--headless=new") 
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-dev-shm-usage")
    chrome_options.add_argument("--disable-gpu")
    chrome_options.add_argument("--window-size=1920,1080")

    # PRÜFUNG: Sind wir in der Cloud?
    if os.path.exists("/usr/bin/chromium"):
        # CLOUD-MODUS: 
        # Wir nutzen die Binaries, die Streamlit via packages.txt installiert hat.
        chrome_options.binary_location = "/usr/bin/chromium"
        # Wir lassen Service() leer, damit Selenium den Treiber im System-Pfad sucht.
        return webdriver.Chrome(options=chrome_options)
    else:
        # LOKAL-MODUS (Dein PC):
        # Hier darf der ChromeDriverManager weiterarbeiten.
        from webdriver_manager.chrome import ChromeDriverManager
        service = Service(ChromeDriverManager().install())
        return webdriver.Chrome(service=service, options=chrome_options)

def clean_text(text):
    if not text: return ""
    t = text.strip()
    if len(t) > 50: return "" 
    if t in ["Wirkung", "Geschmack", "Terpene", "Effekte", "Medizinische Wirkung bei", "Alle anzeigen"]: return ""
    return t

def clean_number_int(text):
    if not text: return ""
    clean = re.sub(r'[^\d,.]', '', text).replace(',', '.')
    try:
        val = float(clean)
        return str(int(round(val)))
    except: return ""

def remove_watermark_rectangle(file_path):
    try:
        with Image.open(file_path) as img:
            img = img.convert("RGB")
            width, height = img.size
            draw = ImageDraw.Draw(img)
            coords = [width - 380, height - 160, width, height]
            draw.rectangle(coords, fill=(255, 255, 255), outline=None)
            img.save(file_path, quality=95)
    except: pass

def sanitize_filename(name):
    return re.sub(r'[\\/*?:"<>|]', "", name).strip()

def download_image(url, product_name):
    if not url: return None
    if not os.path.exists(BILDER_ORDNER): os.makedirs(BILDER_ORDNER, exist_ok=True)
    filename = f"{sanitize_filename(product_name)}.jpg"
    file_path = os.path.join(BILDER_ORDNER, filename)
    if os.path.exists(file_path): return file_path
    try:
        if url.startswith("/"): url = f"https://flowzz.com{url}"
        response = SESSION.get(url, timeout=(10, 45), stream=True)
        if response.status_code == 200:
            with open(file_path, 'wb') as f:
                for chunk in response.iter_content(1024): f.write(chunk)
            remove_watermark_rectangle(file_path) 
            return file_path
    except: pass
    return None

# --- SCRAPER LOGIK FUNKTIONEN (ORIGINAL GITHUB) ---

def hole_listen_safe(driver, keywords):
    ergebnis_liste = []
    if isinstance(keywords, str): keywords = [keywords]
    for kw in keywords:
        try:
            xpath_header = f"//*[self::h2 or self::h3 or self::h4 or self::h5 or self::p or self::div][contains(text(), '{kw}')]"
            headers = driver.find_elements(By.XPATH, xpath_header)
            for header in headers:
                try:
                    container = header.find_element(By.XPATH, "following-sibling::div[1]")
                    items = container.find_elements(By.XPATH, ".//*[contains(@class, 'MuiTypography-body1') or contains(@class, 'MuiChip-label')]")
                    for item in items:
                        t = clean_text(item.text)
                        if t and t not in ergebnis_liste and t not in keywords and len(t) < 40:
                            ergebnis_liste.append(t)
                    if ergebnis_liste: break 
                except: continue
        except: continue
    return list(dict.fromkeys(ergebnis_liste)) 

def hole_hersteller(driver):
    try:
        # Wir suchen das Label "Im Sortiment von"
        label = driver.find_element(By.XPATH, "//*[contains(text(), 'Im Sortiment von')]")
        
        # 'following::p[1]' ist die Lösung: Es findet das nächste <p> Element, 
        # egal ob es in einem <div>, einem <a> oder sonstwo verschachtelt ist.
        hersteller_text = label.find_element(By.XPATH, "following::p[1]").text.strip()
        
        return hersteller_text
    except Exception as e:
        # Falls gar nichts gefunden wird, geben wir einen leeren String zurück
        return ""

def hole_thc_cbd(driver, typ):
    try:
        label = driver.find_element(By.XPATH, f"//p[text()='{typ}']")
        val = label.find_element(By.XPATH, "following::p[1]").text.strip()
        return clean_number_int(val)
    except: return ""

def hole_herkunftsland(driver):
    try:
        img = driver.find_element(By.XPATH, "//img[contains(@src, 'flagcdn')]")
        return img.find_element(By.XPATH, "./..").text.strip()
    except: return ""

def hole_bestrahlung(driver):
    try:
        if driver.find_elements(By.XPATH, "//*[contains(@data-testid, 'NotIrradiated')]"): return "Unbestrahlt"
        if driver.find_elements(By.XPATH, "//*[contains(@data-testid, 'Irradiated')]"): return "Bestrahlt"
        return ""
    except: return ""

def hole_sorte_genetik(driver):
    try:
        chips = driver.find_elements(By.CLASS_NAME, "MuiChip-label")
        for chip in chips:
            t = chip.text.strip()
            if any(x in t for x in ["Hybrid", "Indica", "Sativa"]): return t
        return ""
    except: return ""

def hole_kultivar(driver):
    try:
        header = driver.find_element(By.XPATH, "//h3[contains(text(), 'Über diesen Strain')]")
        link = header.find_element(By.XPATH, "following::a[contains(@href, '/strain/')][1]")
        return link.text.strip()
    except: return ""

def hole_bild_url(driver):
    try:
        imgs = driver.find_elements(By.XPATH, "//div[contains(@class, 'MuiGrid-item')]//img")
        for img in imgs:
            src = img.get_attribute("src")
            if src and ("next/image" in src or "assets.flowzz" in src): return src
        return ""
    except: return ""

def scrape_full_details(driver, url):
    driver.get(url)
    time.sleep(3)
    daten = {'URL': url}
    try: daten['Produktname'] = driver.find_element(By.TAG_NAME, "h1").text.strip()
    except: daten['Produktname'] = "Unbekannt"
    
    try:
        breads = driver.find_elements(By.XPATH, "//li[contains(@class, 'MuiBreadcrumbs-li')]//p")
        daten['BC_DisplayName'] = breads[-1].text.strip() if breads else daten['Produktname']
    except: daten['BC_DisplayName'] = daten['Produktname']

    daten['Hersteller']  = hole_hersteller(driver)
    daten['Herkunft']    = hole_herkunftsland(driver)
    daten['Bestrahlung'] = hole_bestrahlung(driver)
    daten['THC']         = hole_thc_cbd(driver, "THC") 
    daten['CBD']         = hole_thc_cbd(driver, "CBD") 
    daten['Sorte']       = hole_sorte_genetik(driver)
    daten['Kultivar']    = hole_kultivar(driver)
    daten['Produktgruppe'] = "Blüten"
    
    img_url = hole_bild_url(driver)
    daten['Bild Datei'] = download_image(img_url, daten['Produktname'])
    daten['Bild Datei URL'] = img_url 
    
    # Listen Scrapen
    for key, keywords in [("Kategorie Effekt", ["Effekte", "Wirkung"]), 
                         ("Aroma", ["Aroma", "Geschmack"]), 
                         ("Terpen", "Terpene"), 
                         ("Med. Wirkung", ["Medizinische Wirkung", "Medizinische Wirkung bei"])]:
        items = hole_listen_safe(driver, keywords)
        for i in range(MAX_ITEMS_PRO_SPALTE):
            daten[f'{key} {i+1}'] = items[i] if i < len(items) else ""

    return daten

def hole_links_von_uebersicht(driver):
    print(f"🔎 JavaScript-Turbo-Scan wird gestartet...")
    
    # Kurz nach unten scrollen, um Lazy-Loading zu triggern
    driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
    time.sleep(10) 
    
    script = """
    return Array.from(
        document.querySelectorAll("div.MuiGrid2-grid-xs-6 div.MuiCard-root a")
    )
    .map(a => a.href)
    .filter(href => href);
    """
    found = driver.execute_script(script)
    
    # Duplikate entfernen (wichtig, falls Karten doppelt verlinkt sind)
    found = list(dict.fromkeys(found))
    
    print(f"✅ {len(found)} Links in Millisekunden extrahiert.")
    return found

def apply_pre_cleaning(details):
    def normalize_for_match(s): return re.sub(r'[\W_]+', '', s.lower())
    for key, mappings in VALUE_MAPPINGS.items():
        if key in details:
            raw_norm = normalize_for_match(details[key])
            for map_key, map_target in mappings.items():
                if normalize_for_match(map_key) == raw_norm:
                    details[key] = map_target 
                    break
    return details

# --- SUPABASE & FINGERPRINT LOGIK ---

def create_product_hash(hersteller, produktname, thc):
    identity = f"{str(hersteller).lower()}-{str(produktname).lower()}-{str(thc)}"
    clean_identity = re.sub(r'[\W_]+', '', identity)
    return hashlib.md5(clean_identity.encode()).hexdigest()

def sync_to_supabase(entry):
    try:
        sd = entry['ScrapedData']
        fingerprint = create_product_hash(sd.get('Hersteller'), entry['Produktname'], sd.get('THC'))
        
        # 1. Priorität auf die übergebene URL aus dem Loop
        target_url = entry.get("url") or sd.get('URL')

        # Check ob bereits verarbeitet (PROCESSED / IGNORED)
        existing = supabase.table("import_queue").select("status").eq("product_hash", fingerprint).execute()
        if existing.data:
            if existing.data[0]['status'] in ['PROCESSED', 'IGNORED']:
                return # Keine Änderung bei fertigen Produkten

        payload = {
            "product_hash": fingerprint,
            "produktname": entry['Produktname'],
            "status": entry['Status'],
            "match_info": entry['MatchInfo'],
            "scraped_data": sd,
            "url": target_url
        }
        # 2. Entscheidend: on_conflict="url" statt "product_hash"
        supabase.table("import_queue").upsert(payload, on_conflict="url").execute()
        print(f"✅ Synchronisiert: {entry['Produktname']}")
    except Exception as e:
        print(f"❌ Supabase Sync Fehler: {e}")

# --- MAIN RUNNER ---

def run_nightly_scraper():
    print("🚀 START: Flowzz Nightly Scraper -> SUPABASE CLOUD")
    try:
        bc = BusinessCentralConnector()
        bc.authenticate()
    except Exception as e:
        print(f"❌ ABBRUCH: BC nicht erreichbar: {e}"); return

    driver = get_driver()
    try:
        print(f"🌍 Öffne URL: {START_URL}")
        driver.get(START_URL)
        time.sleep(5)
        links = hole_links_von_uebersicht(driver)

        for link in links:
            # --- DER ENTSCHEIDENDE PERFORMANCE-CHECK ---
            # Wir prüfen anhand der URL, ob der Artikel schon in Supabase ist
            check = supabase.table("import_queue").select("status").eq("url", link).execute()
            
            if check.data:
                # Artikel ist bekannt (haben wir gerade im Quick-Import erledigt)
                # Wir überspringen ihn sofort, um Zeit zu sparen.
                continue 

            # Ab hier landen nur noch ECHTE NEUHEITEN
            print(f"\n✨ NEUHEIT ENTDECKT: {link}")
            details = scrape_full_details(driver, link)
            
            if not details.get('Produktname') or details['Produktname'] == "Unbekannt": 
                continue

            details = apply_pre_cleaning(details)

            # --- DEIN GENIALER NAMENS-CHECK ---
            p_name = details.get('Produktname', '').strip()
            p_kultivar = details.get('Kultivar', '').strip()
            bc_name_check = details.get('BC_DisplayName', p_name)
            
            if p_name and p_kultivar:
                clean_p_name = p_name
                if p_name.endswith(p_kultivar):
                     if not p_name.endswith(f"- {p_kultivar}") and not p_name.endswith(f"-{p_kultivar}"):
                         clean_p_name = p_name[:-len(p_kultivar)].strip()
                bc_name_check = f"{clean_p_name} - {p_kultivar}"

            print(f"   🔍 Prüfung für: '{bc_name_check}'")
            match_name, score, match_no = bc.get_match_info(bc_name_check)
            
            status = "READY"
            info_text = "Neu"
            if score > 0.98:
                status = "DUPLICATE"
                info_text = f"Gefunden: {match_name} ({match_no})"
            elif score > 0.85:
                status = "REVIEW"
                info_text = f"Ähnlich: {match_name} ({match_no}) | {int(score*100)}%"

            # Sync des neuen Artikels
            sync_to_supabase({
                "url": link,
                "Produktname": details['Produktname'],
                "Status": status,
                "MatchInfo": info_text,
                "ScrapedData": details
            })

    except Exception as e:
        print(f"❌ Fehler im Haupt-Loop: {e}")
    finally:
        driver.quit()
        print("😴 Scraper beendet.")

if __name__ == "__main__":
    run_nightly_scraper()
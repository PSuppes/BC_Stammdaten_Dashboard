import requests
import re
import os
import json
import time
from difflib import SequenceMatcher
from PIL import Image, ImageDraw
from dotenv import load_dotenv

# Lädt die Variablen aus der .env Datei in VS Code
load_dotenv()

# ==========================================
# KONFIGURATION (Dynamisch aus .env)
# ==========================================
TENANT_ID     = os.environ.get("TENANT_ID", "675e2df2-6e8f-4868-a9d7-2d3d1d093907")
ENVIRONMENT   = os.environ.get("ENVIRONMENT", "Production")
CLIENT_ID     = os.environ.get("BC_CLIENT_ID", "")
CLIENT_SECRET = os.environ.get("BC_CLIENT_SECRET", "")

# Falls du die IDs auch in die .env packen willst:
COMPANY_ID    = os.environ.get("BC_COMPANY_ID", "") 
ITEM_CATEGORY = ""  
UNIT_CODE     = "GR"
FILLING_CODE  = "100.XXX"

ODATA_ATTR_SERVICE  = "Artikelattribute_SD"        
ODATA_VAL_SERVICE   = "Artikelattributwerte_SD"    

API_PUBLISHER = "flowzz"       # Aus AL-Page: APIPublisher = 'flowzz'
API_GROUP     = "automation"   # Aus AL-Page: APIGroup = 'automation'
API_VERSION   = "v2.0"         # Aus AL-Page: APIVersion = 'v2.0'
# Für die Attribute:
API_ENTITY    = "itemAttributeMappings" # Aus EntitySetName

START_NUMMER  = 3000   
PREFIX        = "100." 

# ==========================================
# HELPER & CLEANING
# ==========================================

def clean_string_global(text):
    if not text: return ""
    text = str(text)
    text = re.sub(r'[^\w\s,.\-\(\)%/:]', '', text) 
    text = re.sub(r'\s+', ' ', text).strip()
    return text

def remove_watermark_rectangle(file_path):
    try:
        with Image.open(file_path) as img:
            img = img.convert("RGB")
            width, height = img.size
            draw = ImageDraw.Draw(img)
            # Koordinaten für das Rechteck unten rechts (Flowzz Logo)
            rect_width = 380
            rect_height = 160
            coords = [width - rect_width, height - rect_height, width, height]
            draw.rectangle(coords, fill=(255, 255, 255), outline=None)
            img.save(file_path, quality=95)
    except Exception as e:
        print(f"      ⚠️ Warnung: Konnte Wasserzeichen nicht entfernen: {e}")

# ==========================================
# MAPPINGS
# ==========================================
VALUE_MAPPINGS = {
    "Sorte": {
        "Hybrid Indica dominant":        "Indica dominant",
        "Hybrid Sativa dominant":        "Sativa dominant",
        "Sativa Sativa dominant":        "Sativa dominant",
        "Indica Indica dominant":        "Indica dominant",
        "Sativa dominant":               "Sativa dominant",
        "Indica dominant":               "Indica dominant",
        "Hybrid":                        "Hybrid", 
        "Sativa":                        "Sativa", 
        "Indica":                        "Indica"
    },
    "Bestrahlung": {
        "Bestrahlt": "Bestrahlt", 
        "Unbestrahlt": "Unbestrahlt", 
        "Nicht bestrahlt": "Unbestrahlt"
    }
}

MANUFACTURER_CODE_MAPPING = {
    "1A Pharma": "1APHARMA", "ACA Müller Pharma": "ACA-MUELLE", "ADREXpharma": "ADREX",
    "Adven": "ADVEN", "alephSana": "ALEPHSANA", "Amp": "AMP", "Apocan": "APOCAN",
    "Apurano": "APURANO", "Aurora": "AURORA", "Avaay Medical": "AVAAY", "Avaay": "AVAAY",  
    "Avextra Pharma": "AVEXTRA PH", "Balancial GmbH": "BALANCIAL", "Bathera": "BATHERA",
    "Bavamedical": "BAVAMED", "Bavaria Weed": "BAVA-WEED", "BC Green": "BC-GREEN",
    "Beacon Medical Germany": "BEACON", "Beacon Medical": "BEACON", "Becanex GmbH": "BECANEX",
    "Bedrocan": "BEDROCAN", "California’s Medical": "CALI-MED", "Can Bava Med": "CAN BAVA M",
    "Canify": "CANIFY", "Cannaflos": "CANNAFLOS", "Cannamedical": "CANNAMEDIC",
    "Cannovum": "CANNOVUM", "Cannymed": "CANNYMED", "canymed": "CANYMED", 
    "Canopy Growth": "CANOPY", "Canopy Medical": "CANOPY", "CanPharma": "CANPHARMA",
    "Cansativa": "CANSATIVA", "Cantourage": "CANTOURAGE", "Cannabistada": "CA-STADA",
    "Stada": "CA-STADA", "CNBS Medical": "CNBS", "Collini Apotheke": "COLLINI",
    "Day3 Pharma": "DAY3", "Demecan": "DEMECAN", "Dopiopharm": "DOPIOPHARM",
    "Drapalin": "DRAPALIN", "Enua": "ENUA", "ENUA Pharma": "ENUA", "Ethypharm": "ETHYPHARM",
    "Farmako": "FARMAKO", "Felder Green": "FELDERGREE", "Fette Pharma GmbH": "FETTE-PHAR",
    "Four 20 Pharma": "FOUR20PHAR", "Four20 Pharma": "FOUR20PHAR", "420 Pharma": "FOUR20PHAR",
    "German Medical": "GERMAN-MED", "Grow Pharma": "GROW-PHARM", "Grünhorn": "GRUENHORN",
    "HAPA pharm": "HAPA-PHARM", "HerbaMedica": "HERBAMED", "Herbery": "HERBERY",
    "Herbsana": "HERBSANA", "Hexacan": "HEXACAN", "Heyday": "HEYDAY", "Ilios Santé": "ILLIOS-SAN",
    "IMC": "IMC", "IUVO Therapeutics GmbH": "IUVO", "IUVO": "IUVO", "Khiron": "KHIRON",
    "Kineo Medical GmbH": "KINEO", "LINNEO Health S.L.": "LINNEO", "Little Green Pharma": "LITTLEGREE",
    "Madrecan": "MADRECAN", "Materia": "MATERIA", "MeCann": "MECANN", "MediCann": "MEDICANN",
    "Medipharm Labs": "MEDIPHARML", "Mediprocan": "MEDIPROCAN", "MGF Via Medical": "MGF",
    "Montu Group": "MONTU", "Naxiva": "NAXIVA", "NEDCANN": "NEDCANN", "Nimbus": "NIMBUS",
    "Noc Pharma GmbH": "NOC", "Novacana": "NOVACANA", "Oxygen": "OXYGEN", "Peace Naturals": "PEACENATUR",
    "Pharmaleaves": "PHARMALEA", "Pharmcann": "PHARMCANN", "phyto-hemp": "PHYTO-HEMP",
    "PureCan": "PURECAN", "Remexian": "REMEXIAN", "Remexian Pharma": "REMEXIAN",
    "Solidmind Group GmbH": "SOLIDMIND", "SOMAÍ Pharmaceuticals": "SOMAI", "Swiss Alpino Pharma": "SWISSALPIN",
    "Therismos": "THERISMOS", "Tikun Olam Europe": "TIKUNOLAM", "Tilray": "TILRAY",
    "Top Shelf Medical": "TOPSHELF", "Vayamed": "VAYAMED", "Vertanical": "VERTANICAL",
    "Weeco": "WEECO", "WMG Pharma": "WMG"
}

CREATE_NEW_VALUES = True 
MAX_ITEMS_PRO_SPALTE = 3

# ==========================================
# CLASS: BusinessCentralConnector
# ==========================================
class BusinessCentralConnector:
    def __init__(self):
        self.base_url = f"https://api.businesscentral.dynamics.com/v2.0/{TENANT_ID}/{ENVIRONMENT}/api/v2.0"
        self.odata_root = f"https://api.businesscentral.dynamics.com/v2.0/{TENANT_ID}/{ENVIRONMENT}/ODataV4"
        self.custom_api_root = f"https://api.businesscentral.dynamics.com/v2.0/{TENANT_ID}/{ENVIRONMENT}/api/{API_PUBLISHER}/{API_GROUP}/{API_VERSION}"
        
        self.token = None
        self.company_id = COMPANY_ID
        self.company_name = "" 
        self.existing_items_cache = [] 
        self.attributes_cache = {} 

    def authenticate(self):
        print("🔑 Verbinde mit Business Central...")
        url = f"https://login.microsoftonline.com/{TENANT_ID}/oauth2/v2.0/token"
        data = {
            "grant_type": "client_credentials",
            "client_id": CLIENT_ID,
            "client_secret": CLIENT_SECRET,
            "scope": "https://api.businesscentral.dynamics.com/.default"
        }
        r = requests.post(url, data=data)
        if r.status_code == 200:
            self.token = r.json().get("access_token")
            if not self.company_id:
                self._get_company_id()
            else:
                self._find_company_name()
            self._load_existing_items()
            self._load_odata_attributes() 
        else:
            raise Exception(f"Login fehlgeschlagen! ({r.text})")

    def _get_company_id(self):
        headers = {"Authorization": f"Bearer {self.token}"}
        r = requests.get(f"{self.base_url}/companies", headers=headers)
        if r.status_code == 200:
            val = r.json().get('value', [])
            if val: 
                target = next((c for c in val if "Masterstammdaten" in c['displayName']), val[0])
                self.company_id = target['id']
                self.company_name = target['name'] 
                print(f"🏢 Verbunden mit Firma: '{target['displayName']}'")
            else: 
                raise Exception("Keine Firma gefunden!")

    def _find_company_name(self):
        headers = {"Authorization": f"Bearer {self.token}"}
        r = requests.get(f"{self.base_url}/companies({self.company_id})", headers=headers)
        if r.status_code == 200:
            self.company_name = r.json().get('name')

    def _load_existing_items(self):
        print("⏳ Lade Artikelstamm...")
        headers = {"Authorization": f"Bearer {self.token}"}
        url = f"{self.base_url}/companies({self.company_id})/items?$select=id,number,displayName"
        r = requests.get(url, headers=headers)
        if r.status_code == 200:
            self.existing_items_cache = r.json().get('value', [])
            print(f"✅ {len(self.existing_items_cache)} Artikel im Cache.")

    def _load_odata_attributes(self):
        print("⏳ Lade Attribute und Werte über OData...")
        headers = {"Authorization": f"Bearer {self.token}"}
        comp_part = f"Company('{self.company_name}')"
        
        url_attr = f"{self.odata_root}/{comp_part}/{ODATA_ATTR_SERVICE}"
        r = requests.get(url_attr, headers=headers)
        if r.status_code == 200:
            for a in r.json().get('value', []):
                k_id = next((k for k in ['ID','id'] if k in a), 'ID')
                k_name = next((k for k in ['Name','name'] if k in a), 'Name')
                self.attributes_cache[a[k_name]] = {'id': a[k_id], 'values': {}}
        
        url_vals = f"{self.odata_root}/{comp_part}/{ODATA_VAL_SERVICE}"
        r_vals = requests.get(url_vals, headers=headers)
        if r_vals.status_code == 200:
            vals = r_vals.json().get('value', [])
            if vals:
                vf = vals[0]
                k_aid = next((k for k in ['Attribute_ID','AttributeID'] if k in vf), 'Attribute_ID')
                k_vid = next((k for k in ['ID','id'] if k in vf), 'ID')
                k_val = next((k for k in ['Value','value','Name'] if k in vf), 'Value')
                
                for v in vals:
                    try:
                        p_aid = v.get(k_aid)
                        p_val = str(v.get(k_val))
                        p_vid = v.get(k_vid)
                        for attr_data in self.attributes_cache.values():
                            if attr_data['id'] == p_aid:
                                attr_data['values'][p_val] = p_vid
                    except: pass
        print(f"✅ Attribute geladen.")

    def _ensure_value_exists(self, attr_name, attr_id, raw_val):
        clean_val = clean_string_global(raw_val)
        if not clean_val: return None

        def normalize_for_match(s):
            return re.sub(r'[\W_]+', '', s.lower())

        if attr_name in VALUE_MAPPINGS:
            val_norm = normalize_for_match(clean_val)
            for map_key, map_target in VALUE_MAPPINGS[attr_name].items():
                if normalize_for_match(map_key) == val_norm:
                    clean_val = map_target
                    break 
        
        cached_values = self.attributes_cache[attr_name]['values']
        search_key_strict = clean_val.lower().strip()

        if attr_name == "Hersteller":
            ignore_words = ["gmbh", "ag", "limited", "ltd", "pharma", "pharm", "medical", "cannabis", "deutschland", "germany", "europe", "healthcare", "therapeutics", "labs"]
            def normalize_brand(name):
                n = name.lower()
                for word in ignore_words: n = n.replace(word, "")
                return re.sub(r'[^a-z0-9]', '', n)

            input_core = normalize_brand(clean_val)
            for existing_name, existing_id in cached_values.items():
                bc_core = normalize_brand(existing_name)
                is_match = False
                if input_core == bc_core: is_match = True
                elif len(input_core) > 2 and len(bc_core) > 2:
                     if input_core in bc_core or bc_core in input_core: is_match = True
                if is_match: return existing_id
        else:
            for existing_name, existing_id in cached_values.items():
                if existing_name.lower().strip() == search_key_strict:
                    return existing_id

        ALLOWED_TO_CREATE = ["Produktname", "Kultivar", "URL", "Hersteller"] 
        if attr_name not in ALLOWED_TO_CREATE:
            print(f"      ⚠️ STRICT MODE: Wert '{clean_val}' existiert nicht für '{attr_name}' (Skip).")
            return None 

        if CREATE_NEW_VALUES:
            print(f"      🆕 Erstelle neuen Wert: '{clean_val}' für '{attr_name}'...")
            headers = {"Authorization": f"Bearer {self.token}", "Content-Type": "application/json"}
            comp_part = f"Company('{self.company_name}')"
            url = f"{self.odata_root}/{comp_part}/{ODATA_VAL_SERVICE}"
            payload = { "Attribute_ID": attr_id, "Value": clean_val }
            r = requests.post(url, headers=headers, json=payload)
            if r.status_code in [200, 201]:
                data = r.json()
                new_id = data.get('ID') or data.get('id')
                if new_id:
                    self.attributes_cache[attr_name]['values'][clean_val] = new_id
                    return new_id
        return None

    def find_next_number(self):
        max_val = START_NUMMER
        for item in self.existing_items_cache:
            nr = item.get('number', '')
            if nr.startswith(PREFIX):
                try:
                    val = int(nr.split(PREFIX)[1])
                    if val > max_val: max_val = val
                except: pass
        return f"{PREFIX}{max_val + 1}"

    def _calculate_token_sort_ratio(self, str1, str2):
        if not str1 or not str2: return 0.0
        def clean_token(s):
            # Erlaubt auch Buchstaben in Zahlen-Kontext
            s = re.sub(r'[^\w\s/]', '', str(s).lower())
            return s
        tokens1 = sorted(clean_token(str1).split())
        tokens2 = sorted(clean_token(str2).split())
        t1_str = " ".join(tokens1)
        t2_str = " ".join(tokens2)
        return SequenceMatcher(None, t1_str, t2_str).ratio()

    # =========================================================================
    # 🔥 VERBESSERTE MATCHING LOGIK (MIT STARTS-WITH & SUBSTRING BOOST) 🔥
    # =========================================================================
    def get_match_info(self, new_name):
        best_score = 0.0
        best_name = "Kein Vergleichswert"
        best_no = None
        if not self.existing_items_cache: return best_name, 0.0, None

        ignore_words = ["cannabis", "flos", "blüten", "extract", "gmbh", "kultivar", "strain"]
        
        # Stärkere Bereinigung für den Vergleich (Entfernt auch ' und - und .)
        def remove_fillers(text):
            t = text.lower()
            for w in ignore_words: t = t.replace(w, "")
            # Hier entfernen wir alles was KEIN Buchstabe/Zahl ist (also auch Apostrophe!)
            return re.sub(r'[^\w\s]', '', t).strip()

        clean_new_name = remove_fillers(new_name)
        
        for item in self.existing_items_cache:
            existing_name = item['displayName']
            clean_existing_name = remove_fillers(existing_name)
            
            # 1. Standard Mathe-Vergleich
            score_normal = SequenceMatcher(None, clean_new_name, clean_existing_name).ratio()
            score_token = self._calculate_token_sort_ratio(new_name, existing_name)
            current_score = max(score_normal, score_token)
            
            # 2. TURBO BOOST: Startswith Check
            # Da 'main_script' jetzt den Namen simuliert ("Name - Kultivar"), 
            # muss dieser fast identisch mit dem BC Namen sein.
            # Wir prüfen "Starts with" in beide Richtungen für maximale Sicherheit.
            
            # A) BC Name fängt mit Neuem Namen an (Klassiker)
            if existing_name.lower().startswith(new_name.lower()):
                if current_score < 0.95: current_score = 0.95
            
            # B) Neuer Name fängt mit BC Namen an (Falls BC kürzer ist)
            elif new_name.lower().startswith(existing_name.lower()):
                 if current_score < 0.95: current_score = 0.95

            # C) Wenn wir Sonderzeichen ignorieren (remove_fillers), sind sie identisch?
            # Das fängt "Casper's" vs "Casper’s" ab!
            if clean_new_name == clean_existing_name:
                 if current_score < 0.98: current_score = 0.99

            # 3. Nummern-Check (Strafpunkt, wenn Zahlen nicht stimmen, z.B. 20/1 vs 22/1)
            nums_new = re.findall(r'\d+/\d+', new_name)
            nums_old = re.findall(r'\d+/\d+', existing_name)
            if nums_new and nums_old:
                if nums_new[0] != nums_old[0]:
                    current_score = current_score - 0.5 
            
            # Besten Treffer speichern
            if current_score > best_score:
                best_score = current_score
                best_name = existing_name
                best_no = item['number']
                
        return best_name, best_score, best_no

    def create_item_now(self, display_name, bild_pfad, scraped_data):
        headers = { "Authorization": f"Bearer {self.token}", "Content-Type": "application/json" }
        next_no = self.find_next_number()
        base_api_root = self.base_url.rsplit("/v2.0", 1)[0]
        custom_url = f"{base_api_root}/{API_PUBLISHER}/{API_GROUP}/{API_VERSION}/companies({self.company_id})/items"

        # 1. HERSTELLER LOGIK
        raw_hersteller = scraped_data.get('Hersteller', '').strip()
        m_code = None
        m_code = MANUFACTURER_CODE_MAPPING.get(raw_hersteller)
        if not m_code:
            for k, v in MANUFACTURER_CODE_MAPPING.items():
                if k.lower() == raw_hersteller.lower(): m_code = v; break
        if not m_code:
             for k, v in MANUFACTURER_CODE_MAPPING.items():
                if k.lower() in raw_hersteller.lower(): m_code = v; break
        
        # 2. NAMENS-LOGIK
        p_name = scraped_data.get('Produktname', '').strip()
        p_kultivar = scraped_data.get('Kultivar', '').strip()
        final_display_name = display_name 
        if p_name and p_kultivar:
            if p_name.endswith(p_kultivar):
                if not p_name.endswith(f"- {p_kultivar}") and not p_name.endswith(f"-{p_kultivar}"):
                     p_name = p_name[:-len(p_kultivar)].strip()
            final_display_name = f"{p_name} - {p_kultivar}"

        print(f"      🏭 Hersteller: '{raw_hersteller}' -> Code: '{m_code if m_code else 'NICHT GEFUNDEN'}'")

        # 3. PAYLOAD
        payload = {
            "number": next_no,
            "displayName": display_name[:100], 
            "baseUnitOfMeasureCode": UNIT_CODE,
            "blocked": False,
            "fillingToleranceCode": FILLING_CODE,
            "genProdPostingGroup": "HANDEL",
            "inventoryPostingGroup": "BLÜTEN",
            "itemTrackingCode": "CHARGE",
            "vatProdPostingGroup": "MWST.19",
            "itemPackagingCode": "100.XXX",
            "priceIncludesVat": True
        }

        if m_code: payload["manufacturerCode"] = m_code
        if ITEM_CATEGORY: payload["itemCategoryCode"] = ITEM_CATEGORY

        # 4. API REQUEST
        # Wir bauen die URL sauber von Grund auf neu
        api_base = f"https://api.businesscentral.dynamics.com/v2.0/{TENANT_ID}/{ENVIRONMENT}/api"
        custom_url = f"{api_base}/{API_PUBLISHER}/{API_GROUP}/{API_VERSION}/companies({self.company_id})/items"

        print(f"🚀 Sende Request an BC: {payload['displayName']}")
        print(f"🔗 Pfad: {custom_url}") # Debug-Zeile zur Kontrolle
        
        try:
            r = requests.post(custom_url, headers=headers, json=payload, timeout=20)
            
            if r.status_code == 201:
                item = r.json()
                item_id = item.get('id') or item.get('systemId')
                self.existing_items_cache.append(item) 
                print(f"   ✅ Erstellt: {item.get('number', 'N/A')} - {item['displayName']}")
                
                # 5. BILD LOGIK
                final_img_path = bild_pfad
                temp_path = "temp_upload.jpg"
                
                if (not final_img_path or not os.path.exists(final_img_path)) and 'Bild Datei URL' in scraped_data:
                    try:
                        img_url = scraped_data['Bild Datei URL']
                        if img_url:
                            full_url = img_url if img_url.startswith("http") else f"https://flowzz.com{img_url}"
                            r_img = requests.get(full_url, stream=True, timeout=10)
                            if r_img.status_code == 200:
                                with open(temp_path, 'wb') as f:
                                    for chunk in r_img.iter_content(1024): f.write(chunk)
                                final_img_path = temp_path
                    except Exception as img_err:
                        print(f"   ⚠️ Bild-Download fehlgeschlagen: {img_err}")

                if final_img_path and os.path.exists(final_img_path):
                    try:
                        if 'remove_watermark_rectangle' in globals():
                            remove_watermark_rectangle(final_img_path)
                        
                        if item_id:
                            time.sleep(1) 
                            self._upload_image(item_id, final_img_path)
                    except Exception as upload_err:
                        print(f"   ⚠️ Bild-Upload Fehler: {upload_err}")
                
                if final_img_path == temp_path and os.path.exists(temp_path):
                    try: os.remove(temp_path)
                    except: pass
                
                # WICHTIG: Die Nummer für die Attribute nutzen
                self._process_and_link_attributes(item.get('number'), scraped_data)
                return True
                
            else:
                print(f"   ❌ FEHLER {r.status_code}: {payload['displayName']}")
                print(f"   📝 Rückmeldung von BC: {r.text}")
                return False

        except Exception as e:
            print(f"   🔥 Schwerer Fehler bei API-Request: {e}")
            return False

    def _upload_image(self, item_id, file_path):
        url = f"{self.base_url}/companies({self.company_id})/items({item_id})/picture/pictureContent"
        headers = { "Authorization": f"Bearer {self.token}", "Content-Type": "application/octet-stream", "If-Match": "*" }
        try:
            with open(file_path, "rb") as f: requests.put(url, headers=headers, data=f.read())
            print("      📸 Bild hochgeladen.")
        except: pass

    def _link_attribute_to_item(self, item_no, attr_id, val_id):
        url = f"{self.custom_api_root}/companies({self.company_id})/itemAttributeMappings"
        headers = { "Authorization": f"Bearer {self.token}", "Content-Type": "application/json" }
        payload = { "itemNo": item_no, "attributeId": attr_id, "valueId": val_id }
        r = requests.post(url, headers=headers, json=payload)
        if r.status_code in [200, 201] or "already exists" in r.text:
            return True
        return False

    def _process_and_link_attributes(self, item_no, data):
        static_mapping = {
            'THC': 'THC in Prozent', 'CBD': 'CBD in Prozent', 'Hersteller': 'Hersteller',
            'Herkunft': 'Herkunftsland', 'Sorte': 'Sorte', 'Bestrahlung': 'Bestrahlung',
            'Kultivar': 'Kultivar', 'Produktgruppe': 'Produktgruppen', 'URL': 'URL', 'Produktname': 'Produktname'
        }
        list_mapping = {
            'Aroma': 'Aroma', 'Terpen': 'Terpen', 
            'Med. Wirkung': 'Medizinische Wirkung', 'Kategorie Effekt': 'Kategorie Effekt' 
        }
        
        print(f"      🔗 Verknüpfe Attribute...")
        for scraper_key, bc_name in static_mapping.items():
            raw_val = data.get(scraper_key, "").strip()
            if not raw_val: continue
            
            if bc_name in self.attributes_cache:
                attr_id = self.attributes_cache[bc_name]['id']
                val_id = self._ensure_value_exists(bc_name, attr_id, raw_val)
                if val_id: self._link_attribute_to_item(item_no, attr_id, val_id)

        for scraper_base, bc_name in list_mapping.items():
            if bc_name not in self.attributes_cache: continue 
            attr_id = self.attributes_cache[bc_name]['id']
            for i in range(1, MAX_ITEMS_PRO_SPALTE + 1):
                key = f"{scraper_base} {i}" 
                raw_val = data.get(key, "").strip()
                if raw_val:
                    val_id = self._ensure_value_exists(bc_name, attr_id, raw_val)
                    if val_id: self._link_attribute_to_item(item_no, attr_id, val_id)

    def get_existing_attribute_values(self, item_no):
        """Holt alle bereits verknüpften Attribut-IDs für einen Artikel."""
        url = f"{self.custom_api_root}/companies({self.company_id})/itemAttributeMappings?$filter=itemNo eq '{item_no}'"
        headers = {"Authorization": f"Bearer {self.token}"}
        try:
            r = requests.get(url, headers=headers)
            if r.status_code == 200:
                return {item['attributeId'] for item in r.json().get('value', [])}
        except Exception as e:
            print(f"Fehler beim Laden existierender Attribute: {e}")
        return set()

    def has_image(self, item_id):
        """Prüft, ob der Artikel bereits ein Bild hat."""
        url = f"{self.base_url}/companies({self.company_id})/items({item_id})/picture"
        headers = {"Authorization": f"Bearer {self.token}"}
        r = requests.get(url, headers=headers)
        if r.status_code == 200:
            val = r.json().get('value', [])
            if val and val[0].get('width', 0) > 0:
                return True
        return False                

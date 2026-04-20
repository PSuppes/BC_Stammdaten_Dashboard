import streamlit as st
import pandas as pd
import os
import time
from supabase import create_client
from dotenv import load_dotenv
from connector import BusinessCentralConnector

# Lade lokale .env (falls vorhanden), sonst nutzt Streamlit Secrets
load_dotenv()

# --- 1. LOGIN LOGIK ---
def check_password():
    """Gibt True zurück, wenn das Passwort korrekt ist."""
    if "password_correct" not in st.session_state:
        st.session_state.password_correct = False

    if st.session_state.password_correct:
        return True

    # Login-Formular anzeigen
    st.title("🔐 BC Stammdaten Login")
    password = st.text_input("Bitte Passwort eingeben", type="password")
    if st.button("Anmelden"):
        # Das Passwort hinterlegst du in den Streamlit Cloud Secrets!
        if password == st.secrets.get("APP_PASSWORD"):
            st.session_state.password_correct = True
            st.rerun()
        else:
            st.error("❌ Passwort falsch")
    return False

# Stoppt das Skript hier, wenn nicht eingeloggt
if not check_password():
    st.stop()

# --- CONFIG ---
st.set_page_config(layout="wide", page_title="Flowzz Engine", page_icon="🌿")

# --- CONNECTION ---
S_URL = os.getenv("SUPABASE_URL") or st.secrets.get("SUPABASE_URL")
S_KEY = os.getenv("SUPABASE_KEY") or st.secrets.get("SUPABASE_KEY")
supabase = create_client(S_URL, S_KEY)

# --- CSS ---
st.markdown("""
<style>
    .stApp { background-color: #f8f9fa; }
    .card { background: white; padding: 20px; border-radius: 12px; border: 1px solid #eee; margin-bottom: 10px; }
    .status-badge { padding: 4px 10px; border-radius: 20px; font-size: 10px; font-weight: 700; text-transform: uppercase; }
    .READY { background: #e3f2fd; color: #1976d2; }
    .PROCESSED { background: #e8f5e9; color: #2e7d32; }
    .DUPLICATE { background: #fff3e0; color: #ef6c00; }
</style>
""", unsafe_allow_html=True)

# --- DATA HELPERS ---
def fetch_data():
    res = supabase.table("import_queue").select("*").order("id", desc=True).execute()
    return pd.DataFrame(res.data)

def update_status(db_id, new_status):
    supabase.table("import_queue").update({"status": new_status}).eq("id", db_id).execute()

# --- SIDEBAR ---
df = fetch_data()

with st.sidebar:
    st.title("🌿 Admin Panel")
    if not df.empty:
        st.metric("Offen", len(df[df['status'].isin(['READY', 'REVIEW', 'DUPLICATE'])]))
    
    st.divider()
    show_ignored = st.checkbox("🗑️ Papierkorb zeigen")
    
    status_options = ['READY', 'REVIEW', 'DUPLICATE', 'PROCESSED']
    if show_ignored: status_options = ['IGNORED']
    
    filter_sel = st.multiselect("Filter:", status_options, default=status_options[:3])

    st.divider()
    if st.button("✅ Alle Sichtbaren anwählen"):
        if 'visible_ids' in st.session_state:
            for i in st.session_state.visible_ids: st.session_state[f"sel_{i}"] = True
        st.rerun()

    # --- NEU: MANUELLER UPDATE BEREICH ---
    st.divider()
    st.subheader("🔄 Manueller Artikel-Update")
    with st.expander("Bestehende Artikel nachpflegen"):
        target_item_no = st.text_input("BC Artikelnr", placeholder="z.B. 100.3001")
        flowzz_url = st.text_input("Flowzz URL", placeholder="https://flowzz.com/product/...")
        
        if st.button("Update jetzt starten", use_container_width=True):
            if not target_item_no or not flowzz_url:
                st.error("Bitte Artikelnr und URL angeben!")
            else:
                # Import innerhalb der Funktion um Zirkelbezüge zu vermeiden
                from scraper import get_driver, scrape_full_details, apply_pre_cleaning
                
                with st.spinner("🔍 Scrape Daten von Flowzz..."):
                    driver = get_driver()
                    try:
                        # 1. Flowzz Daten holen
                        scraped_data = scrape_full_details(driver, flowzz_url)
                        scraped_data = apply_pre_cleaning(scraped_data)
                        
                        # 2. BC Verbindung herstellen
                        bc = BusinessCentralConnector()
                        bc.authenticate()
                        
                        # 3. Artikel in BC suchen
                        item_data = next((i for i in bc.existing_items_cache if i['number'] == target_item_no), None)
                        
                        if not item_data:
                            st.error(f"Fehler: Artikel {target_item_no} nicht in BC gefunden!")
                        else:
                            st.info(f"Bearbeite: {item_data['displayName']}")
                            
                            # 4. Fehlende Attribute ergänzen
                            # Hinweis: Die Connector-Methode überspringt Duplikate automatisch
                            bc._process_and_link_attributes(target_item_no, scraped_data)
                            
                            # 5. Bild prüfen & ggf. ohne Watermark hochladen
                            if not bc.has_image(item_data['id']):
                                st.warning("Kein Bild in BC gefunden. Lade hoch...")
                                img_path = scraped_data.get('Bild Datei')
                                if img_path and os.path.exists(img_path):
                                    bc._upload_image(item_data['id'], img_path)
                                    st.success("✅ Bild wurde erfolgreich nachgepflegt!")
                                else:
                                    st.error("❌ Kein lokaler Bild-Pfad verfügbar.")
                            else:
                                st.success("✅ Artikel hat bereits ein Bild.")

                            st.balloons()
                            st.success(f"Update für {target_item_no} abgeschlossen!")

                    except Exception as e:
                        st.error(f"🔥 Fehler beim manuellen Update: {e}")
                    finally:
                        driver.quit()

# --- MAIN ---
st.title("Flowzz Live Import")

if df.empty:
    st.info("Datenbank ist leer. Starte den Scraper.")
else:
    df_view = df[df['status'].isin(filter_sel)].copy()
    st.session_state.visible_ids = df_view.index.tolist()

    selected_indices = []

    for index, row in df_view.iterrows():
        sd = row['scraped_data']
        item_id = row['id']
        st.markdown(f'<div class="card">', unsafe_allow_html=True)
        c1, c2, c3, c4 = st.columns([0.4, 1.2, 4, 2])
        
        with c1:
            key = f"sel_{index}"
            if key not in st.session_state: st.session_state[key] = (row['status'] == 'READY')
            if st.checkbox("", key=key, label_visibility="collapsed"):
                selected_indices.append(index)
        
        with c2:
            # --- CLOUD FIX: Bild-URL statt lokaler Pfad ---
            bild_url = sd.get('Bild Datei URL')
            if bild_url:
                full_url = bild_url if bild_url.startswith("http") else f"https://flowzz.com{bild_url}"
                st.image(full_url, width=80)
            elif sd.get('Bild Datei') and os.path.exists(str(sd.get('Bild Datei'))):
                # Fallback für lokales Testen
                st.image(sd.get('Bild Datei'), width=80)
            else:
                st.caption("Kein Bild")

            # --- NEU: Checkbox für Default-Bild ---
            st.checkbox("Standard-Bild?", key=f"default_img_{item_id}")    
        
        with c3:
            st.markdown(f"<span class='status-badge {row['status']}'>{row['status']}</span>", unsafe_allow_html=True)
            st.markdown(f"**{row['produktname']}**")
            st.caption(f"🏗️ {sd.get('Hersteller')} | 🧬 {sd.get('Kultivar')}")
            
            if row['status'] in ['DUPLICATE', 'REVIEW'] and row.get('match_info'):
                color = "#ef6c00" if row['status'] == 'DUPLICATE' else "#1976d2"
                st.markdown(f"""
                    <div style="font-size: 0.85rem; color: {color}; background-color: {color}15; padding: 5px 10px; border-radius: 5px; border: 1px solid {color}30; margin-top: 5px;">
                        🔍 {row['match_info']}
                    </div>
                """, unsafe_allow_html=True)
        
        with c4:
            with st.expander("Details"):
                st.json(sd)
        st.markdown('</div>', unsafe_allow_html=True)

    # --- AKTIONEN ---
    st.divider()
    col_a, col_b = st.columns(2)
    
    if col_a.button("🚀 IMPORT STARTEN", type="primary", use_container_width=True):
        if not selected_indices:
            st.warning("Bitte wähle zuerst Produkte aus!")
        else:
            bc = BusinessCentralConnector()
            try:
                with st.spinner("🔑 Authentifiziere bei Business Central..."):
                    bc.authenticate()
                st.toast("Verbindung zu BC erfolgreich!")
            except Exception as e:
                st.error(f"❌ BC-Login fehlgeschlagen: {e}")
                st.stop()

            p = st.progress(0)
            status_text = st.empty()
            
            for i, idx in enumerate(selected_indices):
                item = df_view.loc[idx]
                sd = item['scraped_data']
                
                clean_p_name = sd.get('Produktname', '').strip()
                p_kultivar = sd.get('Kultivar', '').strip()
                final_name = f"{clean_p_name} - {p_kultivar}" if p_kultivar else clean_p_name
                
                status_text.info(f"⏳ Übertrage ({i+1}/{len(selected_indices)}): {final_name}")
                
                try:
                    use_default = st.session_state.get(f"default_img_{item['id']}", False)
                    success = bc.create_item_now(final_name, sd.get('Bild Datei'), sd, use_default_image=use_default)
                    
                    if success:
                        update_status(item['id'], 'PROCESSED')
                        st.toast(f"✅ {final_name} erfolgreich!")
                    else:
                        st.error(f"⚠️ BC hat {final_name} abgelehnt.")
                
                except Exception as e:
                    st.error(f"🔥 Fehler bei {final_name}: {e}")
                
                p.progress((i + 1) / len(selected_indices))
            
            status_text.success("🏁 Alle ausgewählten Importe abgeschlossen!")
            time.sleep(2)
            st.rerun()

    if col_b.button("🗑️ ALS IGNORIERT MARKIEREN", use_container_width=True):
        if not selected_indices:
            st.warning("Bitte wähle zuerst Produkte aus!")
        else:
            for idx in selected_indices:
                item = df_view.loc[idx]
                update_status(item['id'], 'IGNORED')
            st.rerun()

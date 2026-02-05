import streamlit as st
import pandas as pd
import os
import time
from supabase import create_client
from dotenv import load_dotenv
from connector import BusinessCentralConnector

# Lade lokale .env (falls vorhanden), sonst nutzt Streamlit Secrets
load_dotenv()

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
        st.markdown(f'<div class="card">', unsafe_allow_html=True)
        c1, c2, c3, c4 = st.columns([0.4, 1.2, 4, 2])
        
        with c1:
            key = f"sel_{index}"
            if key not in st.session_state: st.session_state[key] = (row['status'] == 'READY')
            if st.checkbox("", key=key, label_visibility="collapsed"):
                selected_indices.append(index)
        
        with c2:
            if sd.get('Bild Datei'): st.image(sd.get('Bild Datei'), width=80)
        
        with c3:
            # Badge für den Status (Farbe basierend auf Status)
            st.markdown(f"<span class='status-badge {row['status']}'>{row['status']}</span>", unsafe_allow_html=True)
            
            # Hauptname des Produkts
            st.markdown(f"**{row['produktname']}**")
            
            # Hersteller und Kultivar als kleine Info
            st.caption(f"🏗️ {sd.get('Hersteller')} | 🧬 {sd.get('Kultivar')}")
            
            # --- NEU: Hinweis bei DUPLICATE oder REVIEW ---
            if row['status'] in ['DUPLICATE', 'REVIEW'] and row.get('match_info'):
                # Wir färben den Hinweis dezent ein, um Aufmerksamkeit zu erregen
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
            status_text = st.empty() # Platzhalter für Live-Meldungen
            
            for i, idx in enumerate(selected_indices):
                item = df_view.loc[idx]
                sd = item['scraped_data']
                
                # Name-Kultivar Logik
                clean_p_name = sd.get('Produktname', '').strip()
                p_kultivar = sd.get('Kultivar', '').strip()
                final_name = f"{clean_p_name} - {p_kultivar}" if p_kultivar else clean_p_name
                
                status_text.info(f"⏳ Übertrage ({i+1}/{len(selected_indices)}): {final_name}")
                
                try:
                    # Der eigentliche Import-Aufruf
                    # Wir prüfen hier den Rückgabewert der create_item_now Funktion
                    success = bc.create_item_now(final_name, sd.get('Bild Datei'), sd)
                    
                    if success:
                        update_status(item['id'], 'PROCESSED')
                        st.toast(f"✅ {final_name} erfolgreich!")
                    else:
                        st.error(f"⚠️ BC hat {final_name} abgelehnt. Prüfe das Terminal für Details.")
                
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
            
            st.info(f"✅ {len(selected_indices)} Produkte als IGNORED markiert.")
            time.sleep(1)
            st.rerun()
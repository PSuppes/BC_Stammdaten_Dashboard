import os
import time

import pandas as pd
import streamlit as st
from dotenv import load_dotenv
from supabase import create_client

from connector import BusinessCentralConnector

st.set_page_config(layout="wide", page_title="Flowzz Engine", page_icon="GB")
load_dotenv()


def check_password():
    """Return True when the password is correct."""
    if "password_correct" not in st.session_state:
        st.session_state.password_correct = False

    if st.session_state.password_correct:
        return True

    st.title("BC Stammdaten Login")
    password = st.text_input("Bitte Passwort eingeben", type="password")
    if st.button("Anmelden"):
        if password == st.secrets.get("APP_PASSWORD"):
            st.session_state.password_correct = True
            st.rerun()
        else:
            st.error("Passwort falsch")
    return False


if not check_password():
    st.stop()


S_URL = os.getenv("SUPABASE_URL") or st.secrets.get("SUPABASE_URL")
S_KEY = os.getenv("SUPABASE_KEY") or st.secrets.get("SUPABASE_KEY")
supabase = create_client(S_URL, S_KEY)

st.markdown(
    """
<style>
    .stApp { background-color: #f8f9fa; }
    .card { background: white; padding: 20px; border-radius: 12px; border: 1px solid #eee; margin-bottom: 10px; }
    .status-badge { padding: 4px 10px; border-radius: 20px; font-size: 10px; font-weight: 700; text-transform: uppercase; }
    .READY { background: #e3f2fd; color: #1976d2; }
    .REVIEW { background: #e8f1ff; color: #1565c0; }
    .PROCESSED { background: #e8f5e9; color: #2e7d32; }
    .DUPLICATE { background: #fff3e0; color: #ef6c00; }
    .IGNORED { background: #f5f5f5; color: #616161; }
</style>
""",
    unsafe_allow_html=True,
)


def fetch_data():
    response = supabase.table("import_queue").select("*").order("id", desc=True).execute()
    return pd.DataFrame(response.data)


def update_status(db_id, new_status):
    supabase.table("import_queue").update({"status": new_status}).eq("id", db_id).execute()


def run_manual_update(target_item_no, flowzz_url):
    from scraper import apply_pre_cleaning, cleanup_driver, get_driver, scrape_full_details

    driver = None
    try:
        with st.spinner("Scrape Daten von Flowzz..."):
            driver = get_driver()
            scraped_data = apply_pre_cleaning(scrape_full_details(driver, flowzz_url))

        bc = BusinessCentralConnector()
        with st.spinner("Verbinde mit Business Central..."):
            bc.authenticate()

        item_data = next((item for item in bc.existing_items_cache if item["number"] == target_item_no), None)
        if not item_data:
            st.error(f"Artikel {target_item_no} nicht in BC gefunden.")
            return

        st.info(f"Bearbeite: {item_data['displayName']}")
        bc._process_and_link_attributes(target_item_no, scraped_data)

        if not bc.has_image(item_data["id"]):
            st.warning("Kein Bild in BC gefunden. Lade hoch...")
            img_path = scraped_data.get("Bild Datei")
            if img_path and os.path.exists(img_path):
                bc._upload_image(item_data["id"], img_path)
                st.success("Bild wurde erfolgreich nachgepflegt.")
            else:
                st.error("Kein lokaler Bild-Pfad verfuegbar.")
        else:
            st.success("Artikel hat bereits ein Bild.")

        st.balloons()
        st.success(f"Update fuer {target_item_no} abgeschlossen.")
    except Exception as e:
        st.error(f"Fehler beim manuellen Update: {e}")
    finally:
        if driver is not None:
            cleanup_driver(driver)


df = fetch_data()

with st.sidebar:
    st.title("Admin Panel")
    if not df.empty:
        st.metric("Offen", len(df[df["status"].isin(["READY", "REVIEW", "DUPLICATE"])]))
        st.caption(
            "READY: "
            f"{len(df[df['status'] == 'READY'])} | "
            "REVIEW: "
            f"{len(df[df['status'] == 'REVIEW'])} | "
            "DUPLICATE: "
            f"{len(df[df['status'] == 'DUPLICATE'])} | "
            "PROCESSED: "
            f"{len(df[df['status'] == 'PROCESSED'])}"
        )

    st.divider()
    show_ignored = st.checkbox("Papierkorb zeigen")

    status_options = ["READY", "REVIEW", "DUPLICATE", "PROCESSED"]
    if show_ignored:
        status_options = ["IGNORED"]

    filter_sel = st.multiselect("Filter:", status_options, default=status_options)

    st.divider()
    if st.button("Alle Sichtbaren anwaehlen"):
        if "visible_ids" in st.session_state:
            for visible_id in st.session_state.visible_ids:
                st.session_state[f"sel_{visible_id}"] = True
        st.rerun()

    st.divider()
    st.subheader("Manueller Artikel-Update")
    with st.expander("Bestehende Artikel nachpflegen"):
        target_item_no = st.text_input("BC Artikelnr", placeholder="z.B. 100.3001")
        flowzz_url = st.text_input("Flowzz URL", placeholder="https://flowzz.com/product/...")

        if st.button("Update jetzt starten", use_container_width=True):
            if not target_item_no or not flowzz_url:
                st.error("Bitte Artikelnr und URL angeben.")
            else:
                run_manual_update(target_item_no, flowzz_url)


st.title("Flowzz Live Import")

if df.empty:
    st.info("Datenbank ist leer. Starte den Scraper.")
else:
    df_view = df[df["status"].isin(filter_sel)].copy()
    st.session_state.visible_ids = df_view.index.tolist()

    selected_indices = []

    for index, row in df_view.iterrows():
        sd = row["scraped_data"]
        item_id = row["id"]
        st.markdown("<div class='card'>", unsafe_allow_html=True)
        c1, c2, c3, c4 = st.columns([0.4, 1.2, 4, 2])

        with c1:
            key = f"sel_{index}"
            if key not in st.session_state:
                st.session_state[key] = row["status"] == "READY"
            if st.checkbox("", key=key, label_visibility="collapsed"):
                selected_indices.append(index)

        with c2:
            bild_url = sd.get("Bild Datei URL")
            if bild_url:
                full_url = bild_url if bild_url.startswith("http") else f"https://flowzz.com{bild_url}"
                st.image(full_url, width=80)
            elif sd.get("Bild Datei") and os.path.exists(str(sd.get("Bild Datei"))):
                st.image(sd.get("Bild Datei"), width=80)
            else:
                st.caption("Kein Bild")

            st.checkbox("Standard-Bild?", key=f"default_img_{item_id}")

        with c3:
            st.markdown(
                f"<span class='status-badge {row['status']}'>{row['status']}</span>",
                unsafe_allow_html=True,
            )
            st.markdown(f"**{row['produktname']}**")
            st.caption(f"Hersteller: {sd.get('Hersteller')} | Kultivar: {sd.get('Kultivar')}")

            if row["status"] in ["DUPLICATE", "REVIEW"] and row.get("match_info"):
                color = "#ef6c00" if row["status"] == "DUPLICATE" else "#1976d2"
                st.markdown(
                    f"""
                    <div style="font-size: 0.85rem; color: {color}; background-color: {color}15; padding: 5px 10px; border-radius: 5px; border: 1px solid {color}30; margin-top: 5px;">
                        Match: {row['match_info']}
                    </div>
                    """,
                    unsafe_allow_html=True,
                )

        with c4:
            with st.expander("Details"):
                st.json(sd)
        st.markdown("</div>", unsafe_allow_html=True)

    st.divider()
    col_a, col_b = st.columns(2)

    if col_a.button("IMPORT STARTEN", type="primary", use_container_width=True):
        if not selected_indices:
            st.warning("Bitte waehle zuerst Produkte aus.")
        else:
            bc = BusinessCentralConnector()
            try:
                with st.spinner("Authentifiziere bei Business Central..."):
                    bc.authenticate()
                st.toast("Verbindung zu BC erfolgreich.")
            except Exception as e:
                st.error(f"BC-Login fehlgeschlagen: {e}")
                st.stop()

            progress = st.progress(0)
            status_text = st.empty()

            for i, idx in enumerate(selected_indices):
                item = df_view.loc[idx]
                sd = item["scraped_data"]

                clean_p_name = sd.get("Produktname", "").strip()
                p_kultivar = sd.get("Kultivar", "").strip()
                final_name = f"{clean_p_name} - {p_kultivar}" if p_kultivar else clean_p_name

                status_text.info(f"Uebertrage ({i + 1}/{len(selected_indices)}): {final_name}")

                try:
                    use_default = st.session_state.get(f"default_img_{item['id']}", False)
                    success = bc.create_item_now(
                        final_name,
                        sd.get("Bild Datei"),
                        sd,
                        use_default_image=use_default,
                    )

                    if success:
                        update_status(item["id"], "PROCESSED")
                        st.toast(f"{final_name} erfolgreich.")
                    else:
                        st.error(f"BC hat {final_name} abgelehnt.")
                except Exception as e:
                    st.error(f"Fehler bei {final_name}: {e}")

                progress.progress((i + 1) / len(selected_indices))

            status_text.success("Alle ausgewaehlten Importe abgeschlossen.")
            time.sleep(2)
            st.rerun()

    if col_b.button("ALS IGNORIERT MARKIEREN", use_container_width=True):
        if not selected_indices:
            st.warning("Bitte waehle zuerst Produkte aus.")
        else:
            for idx in selected_indices:
                item = df_view.loc[idx]
                update_status(item["id"], "IGNORED")
            st.rerun()

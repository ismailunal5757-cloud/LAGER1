app.py
import os
import streamlit as st
import pandas as pd
from datetime import date
from dateutil.parser import parse as dtparse

from src.auth import require_login
from src.db import (
    init_db, get_items, add_item, get_locations, add_location,
    get_lots, add_lot, get_inventory, upsert_inventory_delta,
    add_movement, get_movements, get_documents_for_movement,
    add_document, get_document_blob
)
from src.storage import save_upload

st.set_page_config(page_title="Lager & Versand", layout="wide")

DATA_DIR = st.secrets.get("DATA_DIR", "data")
os.makedirs(DATA_DIR, exist_ok=True)

init_db(DATA_DIR)

require_login()

st.title("📦 Lager & Versand")

tabs = st.tabs([
    "Dashboard",
    "Stammdaten",
    "Wareneingang (IN)",
    "Versand (OUT)",
    "Bewegungen & Dokumente",
    "Reports"
])

def _num(x):
    try:
        return int(x)
    except Exception:
        return 0

def _as_date(s):
    if s is None or s == "":
        return None
    if isinstance(s, date):
        return s
    return dtparse(str(s)).date()

# ---------------- Dashboard ----------------
with tabs[0]:
    st.subheader("Aktueller Bestand (nach Charge & Lagerplatz)")
    inv = get_inventory(DATA_DIR)
    if inv.empty:
        st.info("Noch kein Bestand vorhanden. Lege Stammdaten an und buche Wareneingang.")
    else:
        # kleine Kennzahlen
        c1, c2, c3 = st.columns(3)
        c1.metric("Positionen (Zeilen)", int(len(inv)))
        c2.metric("Summe Paletten", int(inv["paletten"].sum()))
        c3.metric("Summe Koli", int(inv["koli"].sum()))

        st.dataframe(inv, use_container_width=True, hide_index=True)

# ---------------- Stammdaten ----------------
with tabs[1]:
    st.subheader("Stammdaten")
    colA, colB, colC = st.columns(3)

    with colA:
        st.markdown("### Artikel")
        items = get_items(DATA_DIR)
        st.dataframe(items, use_container_width=True, hide_index=True)
        with st.form("add_item", clear_on_submit=True):
            sku = st.text_input("SKU / Artikelnummer")
            name = st.text_input("Bezeichnung")
            submitted = st.form_submit_button("Artikel anlegen")
            if submitted:
                if not sku or not name:
                    st.error("Bitte SKU und Bezeichnung ausfüllen.")
                else:
                    add_item(DATA_DIR, sku.strip(), name.strip())
                    st.success("Artikel angelegt.")
                    st.rerun()

    with colB:
        st.markdown("### Lagerplätze")
        locs = get_locations(DATA_DIR)
        st.dataframe(locs, use_container_width=True, hide_index=True)
        with st.form("add_location", clear_on_submit=True):
            code = st.text_input("Lagerplatz (Code)", placeholder="z.B. A-01-03")
            desc = st.text_input("Beschreibung (optional)")
            submitted = st.form_submit_button("Lagerplatz anlegen")
            if submitted:
                if not code:
                    st.error("Bitte Lagerplatz-Code ausfüllen.")
                else:
                    add_location(DATA_DIR, code.strip(), (desc or "").strip())
                    st.success("Lagerplatz angelegt.")
                    st.rerun()

    with colC:
        st.markdown("### Chargen (mit MHD)")
        lots = get_lots(DATA_DIR)
        st.dataframe(lots, use_container_width=True, hide_index=True)
        with st.form("add_lot", clear_on_submit=True):
            items = get_items(DATA_DIR)
            if items.empty:
                st.warning("Bitte zuerst mindestens einen Artikel anlegen.")
                st.stop()
            item_id = st.selectbox("Artikel", items["id"], format_func=lambda i: f'{items.loc[items["id"]==i,"sku"].values[0]} – {items.loc[items["id"]==i,"name"].values[0]}')
            batch = st.text_input("Charge", placeholder="z.B. CH-2026-02-001")
            mhd = st.date_input("MHD", value=None)
            submitted = st.form_submit_button("Charge anlegen")
            if submitted:
                if not batch:
                    st.error("Bitte Charge ausfüllen.")
                else:
                    add_lot(DATA_DIR, int(item_id), batch.strip(), mhd)
                    st.success("Charge angelegt.")
                    st.rerun()

# ---------------- Wareneingang ----------------
with tabs[2]:
    st.subheader("Wareneingang (IN)")
    items = get_items(DATA_DIR)
    locs = get_locations(DATA_DIR)
    lots = get_lots(DATA_DIR)

    if items.empty or locs.empty or lots.empty:
        st.warning("Bitte zuerst Stammdaten anlegen: Artikel, Lagerplätze und Chargen.")
    else:
        with st.form("in_form", clear_on_submit=True):
            lot_id = st.selectbox("Charge wählen", lots["id"], format_func=lambda i: f'{lots.loc[lots["id"]==i,"sku"].values[0]} | Charge {lots.loc[lots["id"]==i,"batch"].values[0]} | MHD {lots.loc[lots["id"]==i,"mhd"].values[0]}')
            location_id = st.selectbox("Lagerplatz", locs["id"], format_func=lambda i: f'{locs.loc[locs["id"]==i,"code"].values[0]}')
            pal = st.number_input("Paletten", min_value=0, step=1, value=0)
            koli = st.number_input("Koli", min_value=0, step=1, value=0)
            partner = st.text_input("Lieferant/Quelle (optional)")
            reference = st.text_input("Referenz (optional)", placeholder="z.B. Wareneingangsnr, PO, Lieferschein")
            notes = st.text_area("Notizen (optional)")
            move_date = st.date_input("Buchungsdatum", value=date.today())
            submitted = st.form_submit_button("Wareneingang buchen")
            if submitted:
                if pal == 0 and koli == 0:
                    st.error("Bitte mindestens Paletten oder Koli > 0 eingeben.")
                else:
                    mv_id = add_movement(DATA_DIR, "IN", int(lot_id), int(location_id), int(pal), int(koli),
                                        partner.strip(), reference.strip(), notes.strip(), move_date)
                    upsert_inventory_delta(DATA_DIR, int(lot_id), int(location_id), int(pal), int(koli))
                    st.success(f"Wareneingang gebucht (ID {mv_id}).")
                    st.rerun()

# ---------------- Versand (OUT) ----------------
with tabs[3]:
    st.subheader("Versand (OUT)")
    inv = get_inventory(DATA_DIR)
    locs = get_locations(DATA_DIR)
    lots = get_lots(DATA_DIR)

    if inv.empty:
        st.info("Kein Bestand vorhanden.")
    else:
        st.dataframe(inv, use_container_width=True, hide_index=True)

        st.markdown("### Versand buchen + Dokumente anhängen")
        with st.form("out_form", clear_on_submit=True):
            # Auswahl anhand Inventory-Zeilen, damit nur vorhandene Kombinationen versendbar sind
            inv_rows = inv.copy()
            inv_rows["label"] = (
                inv_rows["sku"] + " | " +
                "Charge " + inv_rows["batch"].astype(str) + " | " +
                "MHD " + inv_rows["mhd"].astype(str) + " | " +
                "Platz " + inv_rows["lagerplatz"].astype(str) + " | " +
                "Bestand: " + inv_rows["paletten"].astype(str) + " Pal / " + inv_rows["koli"].astype(str) + " Koli"
            )
            chosen = st.selectbox("Aus Bestand auswählen", inv_rows.index, format_func=lambda i: inv_rows.loc[i,"label"])
            row = inv_rows.loc[chosen]

            pal = st.number_input("Paletten zu senden", min_value=0, step=1, value=0)
            koli = st.number_input("Koli zu senden", min_value=0, step=1, value=0)

            receiver = st.text_input("Empfänger / an wen gesendet")
            reference = st.text_input("Referenz (optional)", placeholder="z.B. Auftrag, Lieferschein, CMR-Nr.")
            notes = st.text_area("Notizen (optional)")
            move_date = st.date_input("Versanddatum", value=date.today())

            uploads = st.file_uploader("Dokumente (PDF/JPG/PNG) – mehrere möglich", accept_multiple_files=True)

            submitted = st.form_submit_button("Versand buchen")
            if submitted:
                if (pal == 0 and koli == 0) or not receiver.strip():
                    st.error("Bitte Paletten/Koli > 0 und Empfänger angeben.")
                else:
                    # Bestand prüfen
                    if pal > int(row["paletten"]) or koli > int(row["koli"]):
                        st.error("Nicht genug Bestand für diese Charge/Lagerplatz.")
                    else:
                        mv_id = add_movement(
                            DATA_DIR, "OUT", int(row["lot_id"]), int(row["location_id"]),
                            int(pal), int(koli), receiver.strip(), reference.strip(), notes.strip(), move_date
                        )
                        upsert_inventory_delta(DATA_DIR, int(row["lot_id"]), int(row["location_id"]), -int(pal), -int(koli))

                        # Dokumente speichern
                        saved = 0
                        if uploads:
                            for uf in uploads:
                                stored_path, mime, size = save_upload(DATA_DIR, uf)
                                add_document(DATA_DIR, mv_id, uf.name, stored_path, mime, size)
                                saved += 1

                        st.success(f"Versand gebucht (ID {mv_id}). Dokumente gespeichert: {saved}.")
                        st.rerun()

# ---------------- Bewegungen & Dokumente ----------------
with tabs[4]:
    st.subheader("Bewegungen")
    moves = get_movements(DATA_DIR)
    if moves.empty:
        st.info("Noch keine Bewegungen vorhanden.")
    else:
        # Filter
        c1, c2, c3, c4 = st.columns(4)
        with c1:
            t = st.selectbox("Typ", ["ALLE", "IN", "OUT"])
        with c2:
            partner = st.text_input("Partner/Empfänger enthält", value="")
        with c3:
            from_d = st.date_input("Von", value=None)
        with c4:
            to_d = st.date_input("Bis", value=None)

        df = moves.copy()
        if t != "ALLE":
            df = df[df["typ"] == t]
        if partner.strip():
            df = df[df["partner"].fillna("").str.contains(partner.strip(), case=False)]
        if from_d:
            df = df[pd.to_datetime(df["datum"]).dt.date >= from_d]
        if to_d:
            df = df[pd.to_datetime(df["datum"]).dt.date <= to_d]

        st.dataframe(df, use_container_width=True, hide_index=True)

        st.markdown("### Dokumente zu einer Bewegung")
        move_ids = df["id"].tolist()
        if move_ids:
            mv_id = st.selectbox("Bewegung auswählen", move_ids)
            docs = get_documents_for_movement(DATA_DIR, int(mv_id))
            if docs.empty:
                st.info("Keine Dokumente für diese Bewegung.")
            else:
                st.dataframe(docs[["id","filename","mime","size_bytes","uploaded_at"]], use_container_width=True, hide_index=True)
                for _, r in docs.iterrows():
                    blob = get_document_blob(DATA_DIR, int(r["id"]))
                    st.download_button(
                        label=f"⬇️ Download: {r['filename']}",
                        data=blob,
                        file_name=r["filename"],
                        mime=r["mime"] or "application/octet-stream"
                    )

# ---------------- Reports ----------------
with tabs[5]:
    st.subheader("Reports")
    moves = get_movements(DATA_DIR)

    if moves.empty:
        st.info("Keine Daten.")
    else:
        out = moves[moves["typ"]=="OUT"].copy()
        c1, c2, c3 = st.columns(3)
        with c1:
            from_d = st.date_input("Von", value=None, key="r_from")
        with c2:
            to_d = st.date_input("Bis", value=None, key="r_to")
        with c3:
            grp = st.selectbox("Gruppieren nach", ["Empfänger", "Artikel (SKU)"], index=0)

        if from_d:
            out = out[pd.to_datetime(out["datum"]).dt.date >= from_d]
        if to_d:
            out = out[pd.to_datetime(out["datum"]).dt.date <= to_d]

        if out.empty:
            st.warning("Keine OUT-Daten im gewählten Zeitraum.")
        else:
            if grp == "Empfänger":
                rep = out.groupby("partner", dropna=False)[["paletten","koli"]].sum().reset_index().rename(columns={"partner":"empfaenger"})
            else:
                rep = out.groupby("sku", dropna=False)[["paletten","koli"]].sum().reset_index()
            st.dataframe(rep, use_container_width=True, hide_index=True)

            st.download_button(
                "⬇️ Report als CSV",
                data=rep.to_csv(index=False).encode("utf-8"),
                file_name="report.csv",
                mime="text/csv"
            )

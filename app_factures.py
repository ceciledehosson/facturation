import io
from datetime import datetime, date
from decimal import Decimal, ROUND_HALF_UP

import requests
import streamlit as st
from reportlab.lib.pagesizes import A4
from reportlab.lib import colors
from reportlab.lib.units import mm
from reportlab.lib.utils import ImageReader
from reportlab.platypus import (
    SimpleDocTemplate,
    Table,
    TableStyle,
    Paragraph,
    Spacer,
)
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle


# =========================
# CONFIG
# =========================
st.set_page_config(page_title="Facturation L'Atelier Kez'ya", layout="wide")

DEFAULT_SELLER_NAME = "L'Atelier Kez'ya"
DEFAULT_SELLER_ADDRESS = ""
DEFAULT_SELLER_SIRET = ""
DEFAULT_TVA_RATE = 20.0  # en %

APPS_SCRIPT_URL = "https://script.google.com/macros/s/AKfycbx8FiyF-eVCtd3PA246BIhSTj5oAdUREYVupZcUeorCdseSkhs6-5QKuaaWuB4liMTLUg/exec"


# =========================
# OUTILS
# =========================
def q2(value):
    """Arrondi à 2 décimales façon comptable."""
    return float(Decimal(str(value)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))


def euro(value):
    return f"{q2(value):.2f} €"


def safe_filename(invoice_number):
    cleaned = invoice_number.replace("/", "-").replace(" ", "_")
    return f"facture_LK_{cleaned}.pdf"


def compute_line_totals(qty, unit_ttc, tva_rate):
    qty_d = Decimal(str(qty))
    unit_ttc_d = Decimal(str(unit_ttc))
    tva_rate_d = Decimal(str(tva_rate))

    divisor = Decimal("1") + (tva_rate_d / Decimal("100"))
    unit_ht = (unit_ttc_d / divisor).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    total_ttc = (qty_d * unit_ttc_d).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    total_ht = (qty_d * unit_ht).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    total_tva = (total_ttc - total_ht).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

    return {
        "unit_ht": float(unit_ht),
        "total_ht": float(total_ht),
        "total_tva": float(total_tva),
        "total_ttc": float(total_ttc),
    }


def get_invoice_number_and_save(data, line_items, totals, filename):
    payload = {
        "invoice_date": data["invoice_date"],
        "client_name": data["client_name"],
        "total_ht": totals["total_ht"],
        "total_tva": totals["total_tva"],
        "total_ttc": totals["total_ttc"],
        "payment_terms": data["payment_terms"],
        "notes": data["notes"],
        "pdf_filename": filename,
        "line_items": " | ".join(
            [
                f"{item['description']} x{item['qty']} @ {item['unit_ttc']:.2f} TTC"
                for item in line_items
            ]
        ),
    }

    response = requests.post(APPS_SCRIPT_URL, json=payload, timeout=30)
    response.raise_for_status()
    result = response.json()

    return result["invoice_number"]


def build_pdf(data, line_items, logo_bytes=None):
    buffer = io.BytesIO()

    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        rightMargin=18 * mm,
        leftMargin=18 * mm,
        topMargin=18 * mm,
        bottomMargin=18 * mm,
    )

    styles = getSampleStyleSheet()
    styles.add(
        ParagraphStyle(
            name="Small",
            parent=styles["Normal"],
            fontSize=9,
            leading=11,
        )
    )
    styles.add(
        ParagraphStyle(
            name="TitleCustom",
            parent=styles["Title"],
            fontSize=20,
            leading=24,
            textColor=colors.HexColor("#222222"),
            spaceAfter=8,
        )
    )

    story = []

    # Logo
    if logo_bytes:
        try:
            img = ImageReader(io.BytesIO(logo_bytes))
            iw, ih = img.getSize()
            max_w = 45 * mm
            scale = max_w / iw
            story.append(
                __import__("reportlab.platypus", fromlist=["Image"]).Image(
                    io.BytesIO(logo_bytes),
                    width=iw * scale,
                    height=ih * scale,
                )
            )
            story.append(Spacer(1, 6))
        except Exception:
            pass

    # Titre
    story.append(Paragraph("FACTURE", styles["TitleCustom"]))
    story.append(Spacer(1, 4))

    seller_address_html = data["seller_address"].replace("\n", "<br/>") if data["seller_address"] else ""
    client_address_html = data["client_address"].replace("\n", "<br/>") if data["client_address"] else ""

    left_block = f"""
    <b>{data['seller_name']}</b><br/>
    {seller_address_html}<br/>
    SIRET : {data['seller_siret']}<br/>
    """

    client_block = f"""
    <b>Client</b><br/>
    {data['client_name']}<br/>
    {client_address_html}
    """

    meta_block = f"""
    <b>Facture n° :</b> {data['invoice_number']}<br/>
    <b>Date :</b> {data['invoice_date']}<br/>
    <b>Échéance :</b> {data['due_date']}<br/>
    """

    header_table = Table(
        [
            [
                Paragraph(left_block, styles["Small"]),
                Paragraph(client_block, styles["Small"]),
                Paragraph(meta_block, styles["Small"]),
            ]
        ],
        colWidths=[65 * mm, 65 * mm, 42 * mm],
    )
    header_table.setStyle(
        TableStyle(
            [
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("BOX", (0, 0), (-1, -1), 0.5, colors.white),
                ("LEFTPADDING", (0, 0), (-1, -1), 4),
                ("RIGHTPADDING", (0, 0), (-1, -1), 4),
                ("TOPPADDING", (0, 0), (-1, -1), 2),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
            ]
        )
    )
    story.append(header_table)
    story.append(Spacer(1, 10))

    # Tableau des lignes
    table_data = [
        ["Désignation", "Qté", "PU TTC", "TVA", "PU HT", "Total HT", "Total TTC"]
    ]

    total_ht = 0
    total_tva = 0
    total_ttc = 0

    for item in line_items:
        calc = compute_line_totals(item["qty"], item["unit_ttc"], item["tva_rate"])
        total_ht += calc["total_ht"]
        total_tva += calc["total_tva"]
        total_ttc += calc["total_ttc"]

        table_data.append(
            [
                item["description"],
                str(item["qty"]),
                euro(item["unit_ttc"]),
                f"{q2(item['tva_rate']):.2f} %",
                euro(calc["unit_ht"]),
                euro(calc["total_ht"]),
                euro(calc["total_ttc"]),
            ]
        )

    items_table = Table(
        table_data,
        colWidths=[58 * mm, 16 * mm, 24 * mm, 18 * mm, 24 * mm, 24 * mm, 24 * mm],
        repeatRows=1,
    )
    items_table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#EAEAEA")),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.black),
                ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#BBBBBB")),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("ALIGN", (1, 1), (-1, -1), "CENTER"),
                ("LEFTPADDING", (0, 0), (-1, -1), 5),
                ("RIGHTPADDING", (0, 0), (-1, -1), 5),
                ("TOPPADDING", (0, 0), (-1, -1), 6),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
            ]
        )
    )
    story.append(items_table)
    story.append(Spacer(1, 10))

    # Totaux
    totals_data = [
        ["Total HT", euro(total_ht)],
        ["TVA", euro(total_tva)],
        ["Total TTC", euro(total_ttc)],
    ]

    totals_table = Table(totals_data, colWidths=[40 * mm, 30 * mm], hAlign="RIGHT")
    totals_table.setStyle(
        TableStyle(
            [
                ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#BBBBBB")),
                ("BACKGROUND", (0, 0), (-1, -1), colors.whitesmoke),
                ("FONTNAME", (0, 0), (-1, -1), "Helvetica-Bold"),
                ("ALIGN", (0, 0), (-1, -1), "CENTER"),
                ("LEFTPADDING", (0, 0), (-1, -1), 5),
                ("RIGHTPADDING", (0, 0), (-1, -1), 5),
                ("TOPPADDING", (0, 0), (-1, -1), 6),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
            ]
        )
    )
    story.append(totals_table)
    story.append(Spacer(1, 12))

    # Notes
    if data["payment_terms"]:
        story.append(
            Paragraph(
                f"<b>Conditions de paiement :</b> {data['payment_terms']}",
                styles["Small"],
            )
        )
        story.append(Spacer(1, 4))

    if data["notes"]:
        notes_html = data["notes"].replace("\n", "<br/>")
        story.append(
            Paragraph(
                f"<b>Notes :</b><br/>{notes_html}",
                styles["Small"],
            )
        )

    doc.build(story)
    pdf = buffer.getvalue()
    buffer.close()
    return pdf


# =========================
# SESSION STATE
# =========================
if "line_count" not in st.session_state:
    st.session_state.line_count = 3


# =========================
# INTERFACE
# =========================
st.title("Facturation - L'Atelier Kez'ya")

col_a, col_b = st.columns([2, 1])

with col_a:
    st.subheader("Informations facture")

    st.text_input("Numéro de facture", value="Attribué automatiquement", disabled=True)
    invoice_date = st.date_input("Date de facture", value=date.today())
    due_date = st.date_input("Date d'échéance", value=date.today())

    seller_name = st.text_input("Nom émetteur", value=DEFAULT_SELLER_NAME)
    seller_address = st.text_area("Adresse émetteur", value=DEFAULT_SELLER_ADDRESS, height=80)
    seller_siret = st.text_input("SIRET", value=DEFAULT_SELLER_SIRET)

    client_name = st.text_input("Nom du client")
    client_address = st.text_area("Adresse du client", height=80)

with col_b:
    st.subheader("PDF")
    logo_file = st.file_uploader("Logo (PNG/JPG)", type=["png", "jpg", "jpeg"])
    payment_terms = st.text_input("Conditions de paiement", value="Paiement à réception")
    notes = st.text_area("Notes", height=120)

st.markdown("---")
st.subheader("Lignes de facture")

btn1, btn2, _ = st.columns([1, 1, 4])
with btn1:
    if st.button("Ajouter une ligne"):
        st.session_state.line_count += 1
with btn2:
    if st.button("Supprimer une ligne") and st.session_state.line_count > 1:
        st.session_state.line_count -= 1

line_items = []
global_total_ht = 0
global_total_tva = 0
global_total_ttc = 0

for i in range(st.session_state.line_count):
    st.markdown(f"**Ligne {i + 1}**")
    c1, c2, c3, c4 = st.columns([4, 1, 2, 1])

    with c1:
        description = st.text_input(
            f"Désignation_{i}",
            value="",
            key=f"description_{i}",
            label_visibility="collapsed",
            placeholder="Désignation du produit ou service",
        )
    with c2:
        qty = st.number_input(
            f"Qté_{i}",
            min_value=1,
            value=1,
            step=1,
            key=f"qty_{i}",
            label_visibility="collapsed",
        )
    with c3:
        unit_ttc = st.number_input(
            f"PU TTC_{i}",
            min_value=0.0,
            value=0.0,
            step=1.0,
            format="%.2f",
            key=f"unit_ttc_{i}",
            label_visibility="collapsed",
        )
    with c4:
        tva_rate = st.number_input(
            f"TVA_{i}",
            min_value=0.0,
            value=float(DEFAULT_TVA_RATE),
            step=0.1,
            format="%.2f",
            key=f"tva_{i}",
            label_visibility="collapsed",
        )

    calc = compute_line_totals(qty, unit_ttc, tva_rate)

    c5, c6, c7 = st.columns(3)
    c5.caption(f"PU HT : {euro(calc['unit_ht'])}")
    c6.caption(f"Total HT : {euro(calc['total_ht'])}")
    c7.caption(f"Total TTC : {euro(calc['total_ttc'])}")

    if description.strip():
        line_items.append(
            {
                "description": description.strip(),
                "qty": qty,
                "unit_ttc": unit_ttc,
                "tva_rate": tva_rate,
            }
        )
        global_total_ht += calc["total_ht"]
        global_total_tva += calc["total_tva"]
        global_total_ttc += calc["total_ttc"]

st.markdown("---")
st.subheader("Récapitulatif")

r1, r2, r3 = st.columns(3)
r1.metric("Total HT", euro(global_total_ht))
r2.metric("TVA", euro(global_total_tva))
r3.metric("Total TTC", euro(global_total_ttc))

generate = st.button("Générer la facture PDF", type="primary")

if generate:
    if not client_name.strip():
        st.error("Merci de renseigner le nom du client.")
    elif not line_items:
        st.error("Merci de renseigner au moins une ligne avec une désignation.")
    else:
        data = {
            "invoice_number": "",
            "invoice_date": invoice_date.strftime("%d/%m/%Y"),
            "due_date": due_date.strftime("%d/%m/%Y"),
            "seller_name": seller_name.strip(),
            "seller_address": seller_address.strip(),
            "seller_siret": seller_siret.strip(),
            "client_name": client_name.strip(),
            "client_address": client_address.strip(),
            "payment_terms": payment_terms.strip(),
            "notes": notes.strip(),
        }

        totals = {
            "total_ht": global_total_ht,
            "total_tva": global_total_tva,
            "total_ttc": global_total_ttc,
        }

        try:
            temp_filename = "facture_LK_temp.pdf"
            invoice_number = get_invoice_number_and_save(data, line_items, totals, temp_filename)
            data["invoice_number"] = invoice_number

            filename = safe_filename(invoice_number)

            logo_bytes = logo_file.getvalue() if logo_file else None
            pdf_bytes = build_pdf(data, line_items, logo_bytes=logo_bytes)

            with open(filename, "wb") as f:
                f.write(pdf_bytes)

            st.success(f"Facture générée : {filename}")

            st.download_button(
                label="Télécharger le PDF",
                data=pdf_bytes,
                file_name=filename,
                mime="application/pdf",
            )

        except Exception as e:
            st.error(f"Erreur lors de l'enregistrement de la facture : {e}")

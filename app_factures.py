import os
import io
import json
import requests
from datetime import datetime

import streamlit as st
import pandas as pd
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.pdfgen import canvas
from reportlab.lib.utils import ImageReader

# ============================================================
# CONFIGURATION GÉNÉRALE
# ============================================================

st.set_page_config(page_title="Facturation L'Atelier Kez'ya", layout="wide")

# --- Informations fixes émetteur ---
EMETTEUR_NOM = "L'Atelier Kez'ya"
EMETTEUR_ADRESSE = "7 rue Pasteur, 89700 Tonnerre, France"
EMETTEUR_SIRET = "92538207900018"

# --- TVA ---
TAUX_TVA = 0.20  # 20%

# --- Logo ---
LOGO_PATH = "logo.png"

# --- Apps Script ---
# Mets l'URL de ta web app Apps Script dans les secrets Streamlit
# Exemple dans secrets.toml :
# APPS_SCRIPT_URL = "https://script.google.com/macros/s/XXXXXXXX/exec"

# ============================================================
# OUTILS
# ============================================================

def arrondi(valeur):
    return round(float(valeur), 2)

def ttc_to_ht(prix_ttc, taux_tva=TAUX_TVA):
    return arrondi(prix_ttc / (1 + taux_tva))

def ht_to_tva(prix_ht, taux_tva=TAUX_TVA):
    return arrondi(prix_ht * taux_tva)

def ht_to_ttc(prix_ht, taux_tva=TAUX_TVA):
    return arrondi(prix_ht * (1 + taux_tva))

def format_euro(x):
    return f"{x:,.2f} €".replace(",", " ").replace(".", ",")

def generer_numero_facture_local():
    if "compteur_facture" not in st.session_state:
        st.session_state.compteur_facture = 1
    numero = f"LK-{datetime.now().strftime('%Y%m%d')}-{st.session_state.compteur_facture:03d}"
    return numero

def incrementer_numero_facture():
    if "compteur_facture" not in st.session_state:
        st.session_state.compteur_facture = 1
    st.session_state.compteur_facture += 1

# ============================================================
# APPS SCRIPT
# ============================================================

def enregistrer_facture_apps_script(data_facture, lignes, pdf_filename):
    try:
        if "APPS_SCRIPT_URL" not in st.secrets:
            return False, "La clé APPS_SCRIPT_URL est absente de st.secrets.", None

        payload = {
            "invoice_date": data_facture["date_facture"],
            "client_name": data_facture["client_nom"],
            "client_address": data_facture["client_adresse"],
            "total_ht": data_facture["total_ht"],
            "total_tva": data_facture["total_tva"],
            "total_ttc": data_facture["total_ttc"],
            "payment_terms": data_facture["mode_paiement"],
            "notes": "",
            "pdf_filename": pdf_filename,
            "line_items": " | ".join([ligne["description"] for ligne in lignes])
        }

        response = requests.post(
            st.secrets["APPS_SCRIPT_URL"],
            json=payload,
            timeout=30
        )

        if response.status_code != 200:
            return False, f"Erreur Apps Script ({response.status_code}) : {response.text}", None

        result = response.json()

        if not result.get("success", True):
            return False, f"Erreur Apps Script : {result.get('error', 'erreur inconnue')}", None

        invoice_number = result.get("invoice_number")
        return True, "Facture enregistrée dans Google Sheets via Apps Script.", invoice_number

    except Exception as e:
        return False, f"Erreur Apps Script : {e}", None

# ============================================================
# PDF
# ============================================================

def dessiner_texte_multiligne(c, texte, x, y, largeur_max, leading=12, font_name="Helvetica", font_size=10):
    c.setFont(font_name, font_size)
    mots = str(texte).split()
    lignes = []
    ligne_courante = ""

    for mot in mots:
        test = ligne_courante + (" " if ligne_courante else "") + mot
        if c.stringWidth(test, font_name, font_size) <= largeur_max:
            ligne_courante = test
        else:
            if ligne_courante:
                lignes.append(ligne_courante)
            ligne_courante = mot

    if ligne_courante:
        lignes.append(ligne_courante)

    for i, ligne in enumerate(lignes):
        c.drawString(x, y - i * leading, ligne)

    return y - len(lignes) * leading

def generer_pdf_facture(data_facture, lignes):
    buffer = io.BytesIO()
    c = canvas.Canvas(buffer, pagesize=A4)
    width, height = A4

    marge_gauche = 20 * mm
    marge_droite = 20 * mm
    y = height - 20 * mm

    # --- Logo automatique agrandi ---
    if os.path.exists(LOGO_PATH):
        try:
            logo = ImageReader(LOGO_PATH)
            c.drawImage(
                logo,
                marge_gauche,
                y - 30 * mm,
                width=55 * mm,
                height=30 * mm,
                preserveAspectRatio=True,
                mask='auto',
                anchor='sw'
            )
        except Exception:
            pass

    # --- En-tête émetteur ---
    c.setFont("Helvetica-Bold", 16)
    c.drawRightString(width - marge_droite, y, EMETTEUR_NOM)

    c.setFont("Helvetica", 10)
    c.drawRightString(width - marge_droite, y - 6 * mm, EMETTEUR_ADRESSE)
    c.drawRightString(width - marge_droite, y - 11 * mm, f"SIRET : {EMETTEUR_SIRET}")

    # --- Titre facture ---
    y -= 40 * mm
    c.setFont("Helvetica-Bold", 18)
    c.drawString(marge_gauche, y, "FACTURE")

    c.setFont("Helvetica", 11)
    c.drawString(marge_gauche, y - 8 * mm, f"Numéro : {data_facture['numero_facture']}")
    c.drawString(marge_gauche, y - 14 * mm, f"Date : {data_facture['date_facture']}")

    # --- Client ---
    y -= 30 * mm
    c.setFont("Helvetica-Bold", 12)
    c.drawString(marge_gauche, y, "Facturé à :")

    c.setFont("Helvetica", 11)
    y_client = y - 7 * mm
    y_client = dessiner_texte_multiligne(
        c, data_facture["client_nom"], marge_gauche, y_client, 80 * mm,
        leading=12, font_name="Helvetica-Bold", font_size=11
    )
    y_client = dessiner_texte_multiligne(
        c, data_facture["client_adresse"], marge_gauche, y_client, 80 * mm,
        leading=12, font_name="Helvetica", font_size=10
    )

    # --- Tableau lignes ---
    y_table = y - 25 * mm
    x_positions = {
        "description": marge_gauche,
        "quantite": 100 * mm,
        "pu_ht": 120 * mm,
        "total_ht": 155 * mm
    }

    c.setFont("Helvetica-Bold", 10)
    c.drawString(x_positions["description"], y_table, "Description")
    c.drawString(x_positions["quantite"], y_table, "Qté")
    c.drawString(x_positions["pu_ht"], y_table, "PU HT")
    c.drawString(x_positions["total_ht"], y_table, "Total HT")

    c.line(marge_gauche, y_table - 2 * mm, width - marge_droite, y_table - 2 * mm)

    y_ligne = y_table - 8 * mm
    c.setFont("Helvetica", 10)

    for ligne in lignes:
        c.drawString(x_positions["description"], y_ligne, str(ligne["description"])[:40])
        c.drawRightString(x_positions["quantite"] + 10 * mm, y_ligne, str(ligne["quantite"]))
        c.drawRightString(x_positions["pu_ht"] + 25 * mm, y_ligne, format_euro(ligne["prix_unitaire_ht"]))
        c.drawRightString(width - marge_droite, y_ligne, format_euro(ligne["montant_ht"]))
        y_ligne -= 7 * mm

        if y_ligne < 50 * mm:
            c.showPage()
            y_ligne = height - 30 * mm

    # --- Totaux ---
    y_totaux = y_ligne - 10 * mm
    c.line(120 * mm, y_totaux + 8 * mm, width - marge_droite, y_totaux + 8 * mm)

    c.setFont("Helvetica", 11)
    c.drawString(120 * mm, y_totaux, "Total HT")
    c.drawRightString(width - marge_droite, y_totaux, format_euro(data_facture["total_ht"]))

    c.drawString(120 * mm, y_totaux - 7 * mm, f"TVA ({int(TAUX_TVA * 100)}%)")
    c.drawRightString(width - marge_droite, y_totaux - 7 * mm, format_euro(data_facture["total_tva"]))

    c.setFont("Helvetica-Bold", 12)
    c.drawString(120 * mm, y_totaux - 16 * mm, "Total TTC")
    c.drawRightString(width - marge_droite, y_totaux - 16 * mm, format_euro(data_facture["total_ttc"]))

    # --- Paiement ---
    c.setFont("Helvetica", 10)
    c.drawString(marge_gauche, 30 * mm, f"Mode de paiement : {data_facture['mode_paiement']}")

    c.save()
    buffer.seek(0)
    return buffer

# ============================================================
# INTERFACE STREAMLIT
# ============================================================

st.title("Facturation – L'Atelier Kez'ya")

st.markdown(
    "Remplis les informations client et les lignes de facture. "
    "Le logo, l’adresse émetteur et le SIRET sont intégrés automatiquement."
)

with st.form("form_facture"):
    col1, col2 = st.columns(2)

    with col1:
        numero_facture = st.text_input("Numéro de facture", value=generer_numero_facture_local())
        date_facture = st.date_input("Date de facture", value=datetime.today())
        client_nom = st.text_input("Nom / raison sociale du client")
        client_adresse = st.text_area("Adresse du client", height=100)

    with col2:
        st.text_input("Émetteur", value=EMETTEUR_NOM, disabled=True)
        st.text_input("Adresse émetteur", value=EMETTEUR_ADRESSE, disabled=True)
        st.text_input("SIRET", value=EMETTEUR_SIRET, disabled=True)
        mode_paiement = st.selectbox("Mode de paiement", ["Virement", "Espèces", "Carte bancaire", "Autre"])

    st.subheader("Lignes de facture")

    nb_lignes = st.number_input("Nombre de lignes", min_value=1, max_value=20, value=1, step=1)

    lignes = []
    for i in range(int(nb_lignes)):
        st.markdown(f"**Produit / prestation {i+1}**")
        c1, c2, c3 = st.columns([5, 2, 2])

        with c1:
            description = st.text_input(f"Description {i+1}", key=f"description_{i}")
        with c2:
            quantite = st.number_input(f"Quantité {i+1}", min_value=1, value=1, step=1, key=f"quantite_{i}")
        with c3:
            prix_unitaire_ttc = st.number_input(
                f"Prix unitaire TTC {i+1}",
                min_value=0.0,
                value=0.0,
                step=1.0,
                format="%.2f",
                key=f"puttc_{i}"
            )

        lignes.append({
            "description": description,
            "quantite": quantite,
            "prix_unitaire_ttc": prix_unitaire_ttc
        })

    submitted = st.form_submit_button("Générer la facture")

# ============================================================
# TRAITEMENT
# ============================================================

if submitted:
    erreurs = []

    if not client_nom.strip():
        erreurs.append("Le nom du client est obligatoire.")
    if not client_adresse.strip():
        erreurs.append("L'adresse du client est obligatoire.")

    lignes_calculees = []
    total_ht = 0
    total_tva = 0
    total_ttc = 0

    for ligne in lignes:
        description = ligne["description"].strip()
        quantite = int(ligne["quantite"])
        prix_unitaire_ttc = float(ligne["prix_unitaire_ttc"])

        if not description:
            erreurs.append("Chaque ligne doit comporter une description.")

        prix_unitaire_ht = ttc_to_ht(prix_unitaire_ttc)
        montant_ht = arrondi(prix_unitaire_ht * quantite)
        montant_tva = ht_to_tva(montant_ht)
        montant_ttc = arrondi(prix_unitaire_ttc * quantite)

        lignes_calculees.append({
            "description": description,
            "quantite": quantite,
            "prix_unitaire_ttc": arrondi(prix_unitaire_ttc),
            "prix_unitaire_ht": prix_unitaire_ht,
            "montant_ht": montant_ht,
            "montant_tva": montant_tva,
            "montant_ttc": montant_ttc
        })

        total_ht += montant_ht
        total_tva += montant_tva
        total_ttc += montant_ttc

    total_ht = arrondi(total_ht)
    total_tva = arrondi(total_tva)
    total_ttc = arrondi(total_ttc)

    if erreurs:
        for err in erreurs:
            st.error(err)
    else:
        data_facture = {
            "numero_facture": numero_facture,
            "date_facture": date_facture.strftime("%d/%m/%Y"),
            "client_nom": client_nom,
            "client_adresse": client_adresse,
            "mode_paiement": mode_paiement,
            "total_ht": total_ht,
            "total_tva": total_tva,
            "total_ttc": total_ttc
        }

        st.success("Facture calculée avec succès.")

        recap_df = pd.DataFrame(lignes_calculees)
        st.subheader("Récapitulatif")
        st.dataframe(recap_df, use_container_width=True)

        colA, colB, colC = st.columns(3)
        colA.metric("Total HT", format_euro(total_ht))
        colB.metric("TVA", format_euro(total_tva))
        colC.metric("Total TTC", format_euro(total_ttc))

        # Enregistrement dans Apps Script pour récupérer le vrai numéro LK-AAAA-XXX
        nom_fichier_temp = f"facture_{numero_facture}.pdf"
        ok, message, invoice_number_from_sheet = enregistrer_facture_apps_script(
            data_facture,
            lignes_calculees,
            nom_fichier_temp
        )

        if ok and invoice_number_from_sheet:
            data_facture["numero_facture"] = invoice_number_from_sheet

        pdf_buffer = generer_pdf_facture(data_facture, lignes_calculees)
        nom_fichier = f"facture_{data_facture['numero_facture']}.pdf"

        st.download_button(
            label="Télécharger le PDF",
            data=pdf_buffer,
            file_name=nom_fichier,
            mime="application/pdf"
        )

        if ok:
            st.success(message)
            incrementer_numero_facture()
        else:
            st.warning(message)

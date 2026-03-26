import streamlit as st
from datetime import datetime
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas
from reportlab.lib.utils import ImageReader
import os
import pandas as pd

st.title("Facturation - L'Atelier Kez'ya")

# =========================
# CONFIG
# =========================
EMETTEUR_NOM = "L'Atelier Kez'ya"
EMETTEUR_ADRESSE = "7 rue Pasteur, 89700 Tonnerre"
EMETTEUR_SIRET = "92538207900018"
LOGO_PATH = "logo_kezya.png"

DOSSIER_FACTURES = "factures"
os.makedirs(DOSSIER_FACTURES, exist_ok=True)

# =========================
# NUMÉROTATION AUTOMATIQUE
# =========================
def get_next_invoice_number():
    fichiers = os.listdir(DOSSIER_FACTURES)
    numeros = []

    for f in fichiers:
        if f.startswith("facture_LK_") and f.endswith(".pdf"):
            try:
                num = int(f.split("_")[-1].replace(".pdf", ""))
                numeros.append(num)
            except:
                pass

    return max(numeros, default=0) + 1

# =========================
# CLIENT
# =========================
st.header("Client")
nom_client = st.text_input("Nom du client")
adresse_client = st.text_area("Adresse du client")

# =========================
# INFOS FACTURE
# =========================
st.header("Facture")
date_facture = st.date_input("Date", datetime.today())

# =========================
# LIGNES DE FACTURE
# =========================
st.subheader("Lignes de facture")

df_initial = pd.DataFrame(
    [
        {
            "Description": "",
            "Quantité": 1,
            "PU TTC": 0.0,
            "TVA (%)": 0.0
        }
    ]
)

lignes = st.data_editor(
    df_initial,
    num_rows="dynamic",
    use_container_width=True,
    key="table_facture"
)

# Nettoyage et calculs
lignes_calculees = []
total_ht_general = 0.0
total_tva_general = 0.0
total_ttc_general = 0.0

for _, row in lignes.iterrows():
    description = str(row["Description"]).strip()
    quantite = row["Quantité"]
    pu_ttc = row["PU TTC"]
    tva = row["TVA (%)"]

    if description == "" and pu_ttc == 0 and quantite == 1 and tva == 0:
        continue

    try:
        quantite = float(quantite)
        pu_ttc = float(pu_ttc)
        tva = float(tva)
    except:
        continue

    if tva == 0:
        pu_ht = pu_ttc
    else:
        pu_ht = pu_ttc / (1 + tva / 100)

    total_ht_ligne = quantite * pu_ht
    total_ttc_ligne = quantite * pu_ttc
    montant_tva_ligne = total_ttc_ligne - total_ht_ligne

    lignes_calculees.append(
        {
            "Description": description,
            "Quantité": quantite,
            "PU TTC": pu_ttc,
            "TVA (%)": tva,
            "PU HT": pu_ht,
            "Total HT": total_ht_ligne,
            "Montant TVA": montant_tva_ligne,
            "Total TTC": total_ttc_ligne,
        }
    )

    total_ht_general += total_ht_ligne
    total_tva_general += montant_tva_ligne
    total_ttc_general += total_ttc_ligne

st.subheader("Résumé")
st.write(f"Total HT : {total_ht_general:.2f} €")
st.write(f"TVA : {total_tva_general:.2f} €")
st.write(f"Total TTC : {total_ttc_general:.2f} €")

if lignes_calculees:
    df_resume = pd.DataFrame(lignes_calculees)[
        ["Description", "Quantité", "PU TTC", "TVA (%)", "PU HT", "Total HT", "Montant TVA", "Total TTC"]
    ]
    st.dataframe(df_resume, use_container_width=True)

# =========================
# PDF
# =========================
def generer_pdf(nom_fichier, numero, nom_client, adresse_client, date_facture, lignes_calculees,
                total_ht_general, total_tva_general, total_ttc_general):

    c = canvas.Canvas(nom_fichier, pagesize=A4)
    largeur, hauteur = A4

    # Logo
    if os.path.exists(LOGO_PATH):
        logo = ImageReader(LOGO_PATH)
        c.drawImage(logo, 40, hauteur - 100, width=120, height=60, mask='auto')

    # Émetteur
    c.setFont("Helvetica-Bold", 14)
    c.drawString(40, hauteur - 130, EMETTEUR_NOM)

    c.setFont("Helvetica", 10)
    c.drawString(40, hauteur - 145, EMETTEUR_ADRESSE)
    c.drawString(40, hauteur - 160, f"SIRET : {EMETTEUR_SIRET}")

    # Titre
    c.setFont("Helvetica-Bold", 18)
    c.drawString(400, hauteur - 130, "FACTURE")

    # Numéro
    c.setFont("Helvetica", 10)
    c.drawString(400, hauteur - 150, f"N° : LK-{numero:03d}")

    # Client
    c.setFont("Helvetica-Bold", 12)
    c.drawString(40, hauteur - 220, "Client :")

    c.setFont("Helvetica", 10)
    c.drawString(40, hauteur - 235, nom_client)

    text = c.beginText(40, hauteur - 250)
    for line in adresse_client.split("\n"):
        text.textLine(line)
    c.drawText(text)

    # Date
    c.drawString(400, hauteur - 220, f"Date : {date_facture}")

    # Tableau
    y = hauteur - 330
    c.setFont("Helvetica-Bold", 9)
    c.drawString(40, y, "Description")
    c.drawString(250, y, "Qté")
    c.drawString(290, y, "PU HT")
    c.drawString(350, y, "TVA")
    c.drawString(400, y, "Total HT")
    c.drawString(470, y, "TTC")

    y -= 15
    c.line(40, y, 550, y)
    y -= 15

    c.setFont("Helvetica", 9)

    for ligne in lignes_calculees:
        if y < 120:
            c.showPage()
            y = hauteur - 60
            c.setFont("Helvetica-Bold", 9)
            c.drawString(40, y, "Description")
            c.drawString(250, y, "Qté")
            c.drawString(290, y, "PU HT")
            c.drawString(350, y, "TVA")
            c.drawString(400, y, "Total HT")
            c.drawString(470, y, "TTC")
            y -= 15
            c.line(40, y, 550, y)
            y -= 15
            c.setFont("Helvetica", 9)

        description = str(ligne["Description"])[:38]
        c.drawString(40, y, description)
        c.drawString(250, y, f'{ligne["Quantité"]:.0f}')
        c.drawString(290, y, f'{ligne["PU HT"]:.2f} €')
        c.drawString(350, y, f'{ligne["TVA (%)"]:.1f}%')
        c.drawString(400, y, f'{ligne["Total HT"]:.2f} €')
        c.drawString(470, y, f'{ligne["Total TTC"]:.2f} €')
        y -= 18

    # Totaux
    y -= 20
    c.setFont("Helvetica-Bold", 10)
    c.drawString(330, y, "Total HT :")
    c.drawString(430, y, f"{total_ht_general:.2f} €")

    y -= 18
    c.drawString(330, y, "TVA :")
    c.drawString(430, y, f"{total_tva_general:.2f} €")

    y -= 18
    c.drawString(330, y, "Total TTC :")
    c.drawString(430, y, f"{total_ttc_general:.2f} €")

    c.save()

# =========================
# BOUTON
# =========================
if st.button("Générer le PDF"):
    if nom_client.strip() == "":
        st.error("Veuillez renseigner le client.")
    elif len(lignes_calculees) == 0:
        st.error("Veuillez renseigner au moins une ligne de facture.")
    else:
        numero = get_next_invoice_number()
        nom_fichier = os.path.join(
            DOSSIER_FACTURES,
            f"facture_LK_{numero:03d}.pdf"
        )

        generer_pdf(
            nom_fichier,
            numero,
            nom_client,
            adresse_client,
            str(date_facture),
            lignes_calculees,
            total_ht_general,
            total_tva_general,
            total_ttc_general
        )

        st.success(f"Facture créée : LK-{numero:03d}")

        with open(nom_fichier, "rb") as f:
            st.download_button(
                "Télécharger la facture",
                f,
                file_name=f"facture_LK_{numero:03d}.pdf",
                mime="application/pdf"
            )
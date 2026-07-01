"""
Script de consolidation et détection d'anomalies - Réseau vétérinaire
------------------------------------------------------------------
Ce script :
1. Lit tous les CSV du dossier exports_cliniques/
2. Les consolide en un seul registre réseau
3. Calcule le panier moyen (CA / nb rendez-vous)
4. Détecte les journées d'activité anormale (nb_rdv), en comparant
   chaque jour à la moyenne de SON site ET de SON type de jour
   (semaine vs weekend), pour éviter les faux positifs du dimanche.
5. Écrit une synthèse lisible dans rapport_anomalies.txt

Conçu pour tourner sans supervision (ex : GitHub Actions planifié).
"""

import glob
import pandas as pd
from datetime import datetime

# --- Paramètres ---
DOSSIER_EXPORTS = "exports_cliniques_mai2026"
FICHIER_RAPPORT = "rapport_anomalies.txt"
SEUIL_ECART_TYPE = 2  # nombre d'écarts-types au-delà duquel un jour est jugé anormal


def charger_et_consolider(dossier):
    """Lit tous les CSV du dossier et les empile en un seul DataFrame."""
    fichiers = glob.glob(f"{dossier}/*.csv")
    if not fichiers:
        raise FileNotFoundError(f"Aucun CSV trouvé dans '{dossier}'")

    tables = []
    for f in fichiers:
        tables.append(pd.read_csv(f))

    reseau = pd.concat(tables, ignore_index=True)
    return reseau


def calculer_kpi(reseau):
    """Ajoute le panier moyen et les infos de calendrier (type de jour)."""
    reseau["panier_moyen"] = reseau["ca_ht"] / reseau["nb_rdv"]

    reseau["date"] = pd.to_datetime(reseau["date"])
    reseau["jour_semaine"] = reseau["date"].dt.dayofweek
    reseau["type_jour"] = reseau["jour_semaine"].apply(
        lambda x: "weekend" if x >= 5 else "semaine"
    )
    return reseau


def detecter_anomalies_activite(reseau, seuil=SEUIL_ECART_TYPE):
    """Détecte les jours où nb_rdv s'écarte anormalement de la moyenne
    du site, calibrée séparément pour la semaine et le weekend."""
    stats = (
        reseau.groupby(["clinique", "type_jour"])["nb_rdv"]
        .agg(mean_rdv="mean", std_rdv="std")
        .reset_index()
    )
    reseau = reseau.merge(stats, on=["clinique", "type_jour"], how="left")

    ecart = (reseau["nb_rdv"] - reseau["mean_rdv"]).abs()
    seuil_absolu = seuil * reseau["std_rdv"]
    reseau["anomalie_activite"] = ecart > seuil_absolu

    return reseau


def generer_rapport(reseau, fichier_sortie):
    """Écrit une synthèse lisible des anomalies détectées."""
    anomalies = reseau[reseau["anomalie_activite"]].copy()
    anomalies = anomalies.sort_values("date")

    lignes = []
    lignes.append("=" * 60)
    lignes.append("RAPPORT DE DÉTECTION D'ANOMALIES - RÉSEAU VÉTÉRINAIRE")
    lignes.append(f"Généré le : {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    lignes.append("=" * 60)
    lignes.append("")

    if anomalies.empty:
        lignes.append("Aucune anomalie détectée sur la période analysée.")
    else:
        lignes.append(f"{len(anomalies)} anomalie(s) détectée(s) :\n")
        for _, row in anomalies.iterrows():
            date_str = row["date"].strftime("%d/%m/%Y")
            sens = "chute" if row["nb_rdv"] < row["mean_rdv"] else "pic"
            lignes.append(
                f"- {row['clinique']} : {sens} d'activité le {date_str} "
                f"({int(row['nb_rdv'])} rdv, moyenne habituelle "
                f"{row['mean_rdv']:.0f} rdv en {row['type_jour']})"
            )

    lignes.append("")
    lignes.append("-" * 60)
    lignes.append(f"Total lignes analysées : {len(reseau)}")
    lignes.append(f"Sites couverts : {reseau['clinique'].nunique()}")

    contenu = "\n".join(lignes)

    with open(fichier_sortie, "w", encoding="utf-8") as f:
        f.write(contenu)

    return contenu


def main():
    reseau = charger_et_consolider(DOSSIER_EXPORTS)
    reseau = calculer_kpi(reseau)
    reseau = detecter_anomalies_activite(reseau)
    rapport = generer_rapport(reseau, FICHIER_RAPPORT)
    print(rapport)


if __name__ == "__main__":
    main()

from pathlib import Path



import pandas as pd

import plotly.express as px

import streamlit as st



# La librairie 'unidecode' est essentielle pour le nettoyage des noms de gare.

# Assurez-vous qu'elle est installée dans votre environnement: pip install unidecode

import unidecode



def clean_name(name):

    """Nettoie un nom de gare pour la jointure."""

    if not isinstance(name, str):

        return ""

    name = name.lower().strip()

    name = unidecode.unidecode(name)  # enlève accents

    name = name.replace("(", "").replace(")", "")

    name = name.replace("-", " ")

    name = " ".join(name.split())  # supprime espaces multiples

    return name





# ================== CONFIG DE PAGE ==================

st.set_page_config(

    page_title="Portfolio & Dashboard Transport — Aziz Djerbi",

    page_icon="👨‍💻",

    layout="wide",

)



# ================== COULEURS UNIFIÉES ==================



# Palette de couleurs cohérente basée sur les modes de transport IDF

MODE_COLOR_MAP = {

    "Métro": "#0099DD",  # Bleu vif pour Métro

    "RER": "#009854",    # Vert pour RER

    "Train": "#8A4B8F",  # Violet pour Train (Transilien)

    "Tram": "#FF7900",   # Orange pour Tramway

    "VAL": "#F7E300",    # Jaune pour VAL

    "Autre": "#A9A9A9",  # Gris

}





# ================== LOCALISATION FICHIERS (Garde la logique initiale) ==================

BASE_DIR = Path(__file__).resolve().parent



# (Le reste des fonctions locate_case_insensitive et first_existing reste inchangé)

def locate_case_insensitive(name: str) -> Path:

    """Retourne un Path dans BASE_DIR en ignorant la casse."""

    p = BASE_DIR / name

    if p.exists():

        return p

    lname = name.lower()

    for child in BASE_DIR.iterdir():

        if child.name.lower() == lname:

            return child

    return p





def first_existing(candidates: list[str]) -> Path:

    """Retourne le premier fichier existant parmi une liste de noms possibles."""

    for n in candidates:

        p = locate_case_insensitive(n)

        if p.exists():

            return p

    return BASE_DIR / candidates[0]





PHOTO_PATH = first_existing(["photo.jpg", "photo.jpeg", "photo.png"])

PDF_PATH = locate_case_insensitive("CV_Aziz_Djerbi.pdf")



VALIDATIONS_PATH = locate_case_insensitive(

    "validations-reseau-ferre-profils-horaires-par-jour-type-1er-trimestre.csv"

)

GARES_PATH = locate_case_insensitive(

    "emplacement-des-gares-idf-data-generalisee.csv"

)



# ================== FONCTIONS : DONNÉES TRANSPORT ==================





@st.cache_data

def load_validations_data(path: Path) -> pd.DataFrame:

    """Charge et prépare les données de profils horaires de validations (réseau ferré)."""

    df = pd.read_csv(path, sep=";")



    # Renommage pour plus de clarté

    df = df.rename(

        columns={

            "libelle_arret": "gare",

            "cat_jour": "type_jour",

            "trnc_horr_60": "tranche_horaire",

            "pourcentage_validations": "pct_validations",

        }

    )



    # Types

    df["pct_validations"] = pd.to_numeric(df["pct_validations"], errors="coerce")



    # Extraire l'heure de début à partir de la tranche horaire "6H-7H" -> 6

    def parse_heure(tranche: str | float) -> int | None:

        if not isinstance(tranche, str):

            return None

        part = tranche.split("-")[0]  # "6H"

        part = part.replace("H", "")

        try:

            return int(part)

        except ValueError:

            return None



    df["heure"] = df["tranche_horaire"].apply(parse_heure)



    # Nettoyage

    df = df.dropna(

        subset=["gare", "type_jour", "tranche_horaire", "pct_validations", "heure"]

    )

    df["heure"] = df["heure"].astype(int)



    # Nettoyage du nom de gare

    df["gare"] = df["gare"].apply(clean_name)



    return df





@st.cache_data

def load_gares_data(path: Path) -> pd.DataFrame:

    """Charge et prépare les données de localisation des gares."""

    df = pd.read_csv(path, sep=";")



    # Renommage : le nom de la gare est dans 'nom_long'

    if "nom_long" in df.columns:

        df = df.rename(columns={"nom_long": "gare"})



    # Extraction lat / lon depuis geo_point_2d ("lat, lon")

    if "geo_point_2d" in df.columns:

        def split_geo(s):

            if isinstance(s, str):

                parts = s.split(",")

                if len(parts) == 2:

                    return parts[0].strip(), parts[1].strip()

            return None, None



        df[["lat_str", "lon_str"]] = df["geo_point_2d"].apply(

            lambda x: pd.Series(split_geo(x))

        )

        df["lat"] = pd.to_numeric(df["lat_str"], errors="coerce")

        df["lon"] = pd.to_numeric(df["lon_str"], errors="coerce")



    # Si la colonne 'mode' existe déjà dans le fichier, on la garde,

    # sinon on l'infère à partir des colonnes binaires.

    for col in ["termetro", "terrer", "tertrain", "tertram", "terval"]:

        if col not in df.columns:

            df[col] = 0



    if "mode" not in df.columns:

        def infer_mode(row):

            if row.get("termetro", 0) == 1:

                return "Métro"

            if row.get("terrer", 0) == 1:

                return "RER"

            if row.get("tertrain", 0) == 1:

                return "Train"

            if row.get("tertram", 0) == 1:

                return "Tram"

            if row.get("terval", 0) == 1:

                return "VAL"

            return "Autre"



        df["mode"] = df.apply(infer_mode, axis=1)



    keep_cols = [

        "gare",

        "lat",

        "lon",

        "mode",

        "exploitant",

        "termetro",

        "terrer",

        "tertrain",

        "tertram",

        "terval",

    ]

    keep_cols = [c for c in keep_cols if c in df.columns]

    df = df[keep_cols]



    # On supprime les lignes sans nom de gare

    df = df.dropna(subset=["gare"])



    # Nettoyage du nom de gare

    df["gare"] = df["gare"].apply(clean_name)



    return df





@st.cache_data

def merge_validations_gares(df_val: pd.DataFrame, df_gares: pd.DataFrame) -> pd.DataFrame:

    """Jointure entre profils horaires et géolocalisation des gares."""

    merged = df_val.merge(df_gares, on="gare", how="left")

    return merged





def plot_profil_horaire(df: pd.DataFrame) -> None:

    """Courbe : profil horaire des validations."""

    if df.empty:

        st.info("Aucune donnée pour ce filtre.")

        return



    # Utilisation d'un thème Plotly clean pour une meilleure esthétique

    fig = px.line(

        df.sort_values(["gare", "heure"]),

        x="heure",

        y="pct_validations",

        color="gare",

        markers=True,

        labels={

            "heure": "Heure de la journée",

            "pct_validations": "% des validations journalières",

            "gare": "Gare / station",

        },

        title="Profil horaire des validations par gare",

        template="plotly_white", # Thème clair

    )

    fig.update_xaxes(dtick=1)

    st.plotly_chart(fig, use_container_width=True)





def plot_boxplot(df: pd.DataFrame) -> None:

    """Boxplot : distribution des validations par mode de transport."""

    df_plot = df.dropna(subset=["mode"]).copy()

    if df_plot.empty:

        st.info("Aucune donnée avec mode de transport pour ce filtre.")

        return



    # Utilisation de la carte de couleurs MODE_COLOR_MAP

    fig = px.box(

        df_plot,

        x="mode",

        y="pct_validations",

        color="mode",

        points="all", # Afficher tous les points de données

        color_discrete_map=MODE_COLOR_MAP,

        labels={

            "mode": "Mode de Transport",

            "pct_validations": "% des validations journalières",

        },

        title="Distribution du % de validations par mode de transport",

        template="plotly_white",

    )

    # Tri des modes par médiane des validations (optionnel mais recommandé)

    order = df_plot.groupby('mode')['pct_validations'].median().sort_values(ascending=False).index

    fig.update_layout(xaxis={'categoryorder':'array', 'categoryarray': order})

    st.plotly_chart(fig, use_container_width=True)





def plot_heatmap(df: pd.DataFrame) -> None:

    """Heatmap : heure × type de jour."""

    if df.empty:

        return



    pivot = (

        df.groupby(["type_jour", "heure"])["pct_validations"]

        .mean()

        .reset_index()

        .pivot(index="type_jour", columns="heure", values="pct_validations")

    )



    fig = px.imshow(

        pivot,

        aspect="auto",

        labels=dict(x="Heure", y="Type de jour", color="% validations"),

        title="Répartition moyenne des validations par heure et type de jour",

        template="plotly_white",

    )

    st.plotly_chart(fig, use_container_width=True)





def show_map(df_merged: pd.DataFrame) -> None:

    """Carte interactive des gares avec taille proportionnelle aux validations et couleur par mode."""

    df_map = df_merged.dropna(subset=["lat", "lon"]).copy()

    if df_map.empty:

        st.info("Pas de données géolocalisées pour ce filtre.")

        return



    # Agrégation par gare pour obtenir les validations totales (somme) et les métadonnées (mode)

    df_map = (

        df_map.groupby(["gare", "lat", "lon", "mode", "exploitant"], as_index=False)["pct_validations"]

        .sum()

        .rename(columns={"pct_validations": "total_pct_validations"})

    )

   

    # Configuration du style pour le Mapbox

    # REMARQUE : Pour une carte Mapbox complète et de haute qualité, une clé Mapbox est nécessaire

    # (px.set_mapbox_access_token("VOTRE_TOKEN_ICI")).

    # Ici, nous utilisons l'un des styles de base disponibles sans token, comme 'carto-positron'.



    fig = px.scatter_mapbox(

        df_map,

        lat="lat",

        lon="lon",

        color="mode", # Couleur par mode de transport (utilise MODE_COLOR_MAP si spécifié)

        size="total_pct_validations", # Taille du point proportionnelle aux validations

        hover_name="gare",

        hover_data={

            "mode": True,

            "total_pct_validations": ":.2f",

            "lat": False,

            "lon": False,

        },

        color_discrete_map=MODE_COLOR_MAP,

        zoom=9,  # Zoom centré sur l'Île-de-France

        center={"lat": df_map["lat"].mean(), "lon": df_map["lon"].mean()},

        mapbox_style="carto-positron", # Style de carte simple et efficace (alternative à 'open-street-map' si vous avez un token)

        title="Localisation des gares (Taille = % total de validations)",

    )



    fig.update_layout(margin={"r": 0, "t": 30, "l": 0, "b": 0})

    st.plotly_chart(fig, use_container_width=True)





# ================== UI : DASHBOARD TRANSPORT (avec les nouveaux graphiques) ==================





def show_transport_dashboard() -> None:

    st.title("Dashboard Transport — Profils horaires du réseau ferré")

    st.subheader(

        "Analyse des profils horaires de validations et localisation des gares en Île-de-France"

    )



    st.write(

        """

Ce dashboard exploite les **profils horaires de validations** sur le réseau ferré (métro / RER / train)

et les **coordonnées géographiques des gares** pour analyser :



- les **heures de pointe** (courbes et heatmap),

- la **distribution** des validations par **mode de transport** (boxplot),

- la **répartition spatiale** des gares à fort trafic (carte interactive).

        """

    )




    if not VALIDATIONS_PATH.exists() or not GARES_PATH.exists():

        if not VALIDATIONS_PATH.exists():

            st.error(

                "Fichier des profils horaires introuvable. "

                "Place `validations-reseau-ferre-profils-horaires-par-jour-type-1er-trimestre.csv` "

                "à côté de `app.py`."

            )

        if not GARES_PATH.exists():

            st.error(

                "Fichier des gares introuvable. "

                "Place `emplacement-des-gares-idf-data-generalisee.csv` à côté de `app.py`."

            )

        return



    df_val = load_validations_data(VALIDATIONS_PATH)

    df_gares = load_gares_data(GARES_PATH)

    df_merged = merge_validations_gares(df_val, df_gares)




    with st.expander("Aperçu des données et préparation", expanded=False):

        col1, col2 = st.columns(2)

        with col1:

            st.markdown("**Profils horaires (réseau ferré)**")

            st.dataframe(df_val.head(), use_container_width=True)

        with col2:

            st.markdown("**Localisation des gares**")

            st.dataframe(df_gares.head(), use_container_width=True)



        st.markdown(

            """

- Données horaires : `gare`, `type_jour`, `tranche_horaire`, `pct_validations`, `heure` dérivée.  

- Données géographiques : `gare`, `lat`, `lon`, `mode`.  

- Jointure réalisée sur le nom de gare (`gare`).

            """

        )




    st.markdown("### Filtres")



    type_jour_options = ["Tous"] + sorted(df_val["type_jour"].unique())

    selected_type_jour = st.selectbox("Type de jour", type_jour_options, index=0)




    gares_dispo = sorted(df_merged.dropna(subset=['mode'])["gare"].unique())

    selected_gares = st.multiselect(

        "Gares / stations à afficher",

        gares_dispo,

        default=gares_dispo[:5],  
    )



    min_h = int(df_val["heure"].min())

    max_h = int(df_val["heure"].max())

    plage_horaire = st.slider(

        "Plage horaire (heures)",

        min_value=min_h,

        max_value=max_h,

        value=(min_h, max_h),

    )




    df_filtered = df_val.copy()

    if selected_type_jour != "Tous":

        df_filtered = df_filtered[df_filtered["type_jour"] == selected_type_jour]

    if selected_gares:

        df_filtered = df_filtered[df_filtered["gare"].isin(selected_gares)]

    df_filtered = df_filtered[

        (df_filtered["heure"] >= plage_horaire[0])

        & (df_filtered["heure"] <= plage_horaire[1])

    ]



    df_merged_filtered = df_merged.merge(

        df_filtered[["gare", "type_jour", "heure", "pct_validations"]],

        on=["gare", "type_jour", "heure", "pct_validations"],

        how="inner",

    )

   


    colk1, colk2, colk3 = st.columns(3)

    with colk1:

        st.metric("Gares sélectionnées", len(selected_gares) if selected_gares else len(gares_dispo))

    with colk2:

        st.metric("Combinaisons heure × gare", len(df_filtered))

    with colk3:

        st.metric("Types de jour présents", df_filtered["type_jour"].nunique())

       

    st.divider()




   

    col_viz_1, col_viz_2 = st.columns(2)

   

    with col_viz_1:


        st.markdown("### 1. Profil horaire des validations (Courbes)")

        plot_profil_horaire(df_filtered)

       

    with col_viz_2:


        st.markdown("### 2. Distribution par mode (Boxplot)")

        plot_boxplot(df_merged_filtered) # Utilise le df filtré fusionné pour inclure le mode



    st.divider()




    st.markdown("### 3. Heatmap validations par heure et type de jour")

    if selected_type_jour == "Tous":

        plot_heatmap(df_filtered)

    else:

        st.info(

            "Pour afficher la heatmap complète, sélectionne **Tous** dans le filtre 'Type de jour'."

        )


        plot_heatmap(df_val[df_val["gare"].isin(selected_gares)])



    st.divider()

   


    st.markdown("### 4. Carte des gares (Réseau ferré - Mapbox)")

    show_map(df_merged_filtered)



    st.divider()




    st.markdown("### Tableau des données filtrées")

    st.dataframe(df_filtered.sort_values(["gare", "heure"]), use_container_width=True)




    st.markdown("### Synthèse des enseignements")

    st.write(

        """

- Le **profil horaire** met en évidence les **heures de pointe** (pics du % de validations).  

- Le **Boxplot** permet de comparer la **dispersion** et les **pics de trafic** selon le **mode de transport** (Métro, RER, etc.).  

- La **heatmap** permet de comparer les dynamiques selon les **types de jour** (semaine, week-end, etc.).  

- La **carte des gares** (Mapbox) offre une vision géographique du trafic, avec des points **colorés par mode** et **dimensionnés par le total des validations**.

        """

    )










def show_cv() -> None:


    left, right = st.columns([1, 3], vertical_alignment="center")



    with left:

        if PHOTO_PATH.exists():

            st.image(

                PHOTO_PATH,

                caption="Aziz DJERBI",

                use_container_width=True,

            )

        else:

            st.warning(

                "Photo introuvable. Place **photo.jpg** (ou .jpeg/.png) à côté de `app.py`."

            )



    with right:

        st.title("AZIZ DJERBI")

        st.write("En recherche d’un **contrat d’alternance** dans la Data")

        st.write("📍 Pierrefitte-sur-Seine • 🚗 Permis B")

        st.write("📞 07 78 16 05 47")



        if PDF_PATH.exists():

            st.download_button(

                "📄 Télécharger le CV (PDF)",

                PDF_PATH.read_bytes(),

                file_name=PDF_PATH.name,

                mime="application/pdf",

            )

        else:

            st.info(

                "Place **CV_Aziz_Djerbi.pdf** à côté de `app.py` pour activer le bouton de téléchargement."

            )



    st.divider()




    tab_profil, tab_exp, tab_form, tab_proj, tab_comp, tab_lang = st.tabs(

        ["Profil", "Expériences", "Formations", "Projets", "Compétences", "Langues & Intérêts"]

    )




    with tab_profil:

        st.subheader("Profil")

        st.write(

            "Passionné par l’analyse de données et la programmation, je recherche une alternance d’un an "

            "pour approfondir mes compétences et les mettre en pratique dans un contexte professionnel."

        )



        c1, c2, c3 = st.columns(3)

        with c1:

            st.metric("Domaines", "Data / BI")

            st.caption("SQL • Python • Power BI • Excel")

        with c2:

            st.metric("Dév & Outils", "Tech polyvalente")

            st.caption("HTML/CSS • VBA • Access • SAS • R")

        with c3:

            st.metric("Langues", "Anglais B2, Allemand B1")




    with tab_exp:

        st.subheader("Expériences professionnelles")

        with st.container(border=True):

            st.markdown(

                "**Stagiaire Data Analyst — Laevitas (Tunis)** \n"

                "*Fin juin – Août 2025 (2 mois et 9 jours)*"

            )

            st.markdown(

                """

- Monitoring des **coûts cloud** *(AWS, OVH, Azure)* - **Pipeline data** : collecte → nettoyage → stockage **SQLite** → dashboards  

- Définition de **KPI** & réalisation de **dashboards** interactifs *(Dash/Plotly)*

                """

            )




    with tab_form:

        st.subheader("Formations")

        with st.container(border=True):

            st.markdown(

                "**BUT Science des Données (2e année)** — IUT de Paris – Rives de Seine *(2023–2026)*"

            )

        with st.container(border=True):

            st.markdown(

                "**Baccalauréat Général** — Lycée La Salle – Saint-Rosaire *(2020–2023)*"

            )




    with tab_proj:

        st.subheader("Projets")

        c1, c2 = st.columns(2)

        with c1:

            with st.container(border=True):

                st.markdown("**Enquête IA** *(Nov. 2023 – Janv. 2024)*")

                st.caption(

                    "Excel, PowerPoint — Analyse des réponses et **présentation orale**."

                )

            with st.container(border=True):

                st.markdown("**Étude de cas** *(Oct. 2023 – Nov. 2023)*")

                st.caption(

                    "Excel, Word — **Synthèse** et **graphiques** pour résoudre une problématique."

                )

        with c2:

            with st.container(border=True):

                st.markdown("**Reporting** *(Janv. 2024)*")

                st.caption(

                    "Excel, **SQL** — Extraction d’une base **ventes DVD** + **reco business**."

                )

            with st.container(border=True):

                st.markdown("**Fichiers de données** *(Déc. 2023)*")

                st.caption(

                    "Excel, **Python** — **Nettoyage** et conversion vers **CSV**."

                )




    with tab_comp:

        st.subheader("Compétences — niveaux (0–100)")



        core = pd.DataFrame(

            {

                "Compétence": ["SQL", "Python", "Excel", "Power BI", "R"],

                "Niveau": [80, 75, 85, 70, 60],

            }

        )

        tools = pd.DataFrame(

            {

                "Compétence": ["HTML/CSS", "VBA", "Access", "SAS"],

                "Niveau": [65, 70, 60, 50],

            }

        )



        colA, colB = st.columns(2)

        with colA:

            st.markdown("**Data / BI**")

            st.dataframe(

                core,

                hide_index=True,

                use_container_width=True,

                column_config={

                    "Compétence": st.column_config.TextColumn("Compétence"),

                    "Niveau": st.column_config.ProgressColumn(

                        "Niveau",

                        help="Auto-évaluation",

                        min_value=0,

                        max_value=100,

                        format="%d%%",

                    ),

                },

            )

        with colB:

            st.markdown("**Dev / Outils**")

            st.dataframe(

                tools,

                hide_index=True,

                use_container_width=True,

                column_config={

                    "Compétence": st.column_config.TextColumn("Compétence"),

                    "Niveau": st.column_config.ProgressColumn(

                        "Niveau",

                        help="Auto-évaluation",

                        min_value=0,

                        max_value=100,

                        format="%d%%",

                    ),

                },

            )

        st.caption("Modifie les valeurs 0–100 dans les DataFrames pour ajuster les jauges.")




    with tab_lang:

        st.subheader("Langues & Intérêts")

        c1, c2 = st.columns(2)

        with c1:

            st.markdown("**Langues**")

            st.write("- Anglais **B2**")

            st.write("- Allemand **B1**")

        with c2:

            st.markdown("**Centres d’intérêt**")

            st.write("- Football")

            st.write("- Jeux vidéo")

            st.write("- Automobile")



    st.divider()

    st.caption("© Aziz DJERBI — CV interactif Streamlit")










def main() -> None:

    st.sidebar.title("Navigation")

    page = st.sidebar.radio(

        "Aller à",

        ["Dashboard transport", "CV / Portfolio"],

        index=0,

    )



    if page == "Dashboard transport":

        show_transport_dashboard()

    else:

        show_cv()





if __name__ == "__main__":

    main()


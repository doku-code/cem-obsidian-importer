# Changelog

## 0.2.6

- remplace l'arborescence de rapports par un seul `reports/detail-summary.md` lisible;
- conserve `reports/summary.json` comme compagnon machine-readable, désormais enrichi avec les détails de chaque problème;
- écrit les rapports par cours dans un dossier temporaire puis les fusionne et les supprime automatiquement;
- recrée `reports/` à chaque lancement pour éliminer les anciens sous-dossiers et rapports obsolètes;
- organise le rapport détaillé par cours avec vue d'ensemble, liens non résolus, avertissements, composants inconnus et statistiques de conversion.

## 0.2.5

- convertit les composants Docusaurus `Image` utilisant `img={require(...)}` en images locales Obsidian tout en conservant leur largeur;
- prend en charge les fragments MDX statiques réutilisables sous `docs/_components` en les incorporant dans la note générée;
- simplifie les wrappers de coloration Python `C`, `S`, `N`, `K`, `F` et `B` de 420-SN1 en code Markdown portable;
- résout les liens Docusaurus contenant des paramètres de sélection d’onglet (`?onglet=...`) vers la bonne note locale;
- ignore désormais les faux liens Markdown affichés littéralement dans du code inline;
- ajoute le nombre de types de composants inconnus dans `report.json`;
- conserve les rapports centralisés sous `reports/`, hors du vault.

## 0.2.4

- déplace tous les rapports de conversion hors du vault Obsidian;
- centralise les rapports sous `reports/<code>/report.md` et `report.json`;
- ajoute `reports/summary.md` et `reports/summary.json` pour le dernier lancement;
- affiche les chemins des rapports centralisés dans le résumé terminal;
- ignore `reports/` dans Git afin de garder le dépôt propre;
- conserve l’URL du dépôt source dans les rapports au lieu du chemin temporaire de clonage.

## 0.2.3

- accepte les chemins collés avec guillemets/apostrophes depuis le terminal;
- accepte aussi les espaces échappés (par ex. `My\ Vault`);
- corrige la détection du vault Obsidian lorsque la destination est collée au format shell.

Toutes les modifications notables du projet seront documentées ici.

## 0.2.2

- group generated course folders by academic session;
- use explicit session metadata instead of inferring the session from repository names or course codes;
- reflect DEC-BAC placement for courses whose code does not match their actual session (for example 3M5, 4D5 and 5N6);
- group the interactive course selection menu by session;
- place courses without a fixed session in `Autres cours`.

## 0.2.1

- use human course names for generated folders instead of GitHub repository slugs or abbreviations;
- rename the generated course content folder from `Notes de cours` to `Cours`;
- keep repository URLs internal to the predefined course catalogue.

## 0.2.0

- nouveau workflow interactif unique avec `python cem_importer.py run`;
- catalogue intégré des dépôts de cours CEM connus;
- sélection de plusieurs cours par numéros, plages ou `all`;
- destination demandée à chaque lancement avec mémorisation de la dernière valeur;
- résumé final des erreurs d'import et problèmes de conversion regroupés par dépôt;
- ajout d’un `report.json` machine-readable par cours pour l’agrégation automatique des résultats;
- simplification de la configuration locale : plus de liste de dépôts à maintenir manuellement;
- documentation mise à jour autour du nouveau workflow.

## 0.1.0

Première base du projet :

- import de dépôts Docusaurus / Markdown / MDX vers Obsidian;
- navigation basée sur les sidebars Docusaurus;
- assets locaux;
- callouts, layouts multi-colonnes et highlights;
- onglets Codeblock Customizer;
- previews multi-fichiers Code Playground avec fallback Markdown;
- DataFlow vers Mermaid lorsque possible;
- vidéos intégrées;
- rapport de conversion conservateur;
- CSS CEM avec largeur de page à 1400 px.

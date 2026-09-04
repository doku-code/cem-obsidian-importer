# Changelog

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
- ajout de `_assets/_conversion/report.json` pour l'agrégation automatique des résultats;
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

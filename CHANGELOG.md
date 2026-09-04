# Changelog

## 0.2.14

- renomme le conteneur généré de chaque cours de `Cours` vers `Classe`, afin de distinguer clairement la classe de la section pédagogique `Cours`;
- produit désormais une structure `Cours du programme / Classe / {Cours, TP, Laboratoire, Recettes, ...}` sans modifier les noms canoniques des sections pédagogiques;
- met à jour toutes les regex Iconize documentées pour cibler `Classe` puis ses sous-dossiers;
- conserve intégralement la normalisation prudente et les protections de collision introduites en 0.2.13;
- ajoute un test de régression sur le nom du conteneur généré.

## 0.2.13

- normalise les dossiers pédagogiques de premier niveau vers des noms canoniques communs aux 13 dépôts CEM supportés;
- convertit notamment `01-notes`/`01-cours` en `Cours`, `tp`/`tps` en `TP`, toutes les variantes `labo`/`labos`/`laboratoire(s)` en `Laboratoire`, et `aidememoire` en `Aide-mémoire`;
- couvre aussi les sections observées `Recettes`, `Solution`, `Extra`, `Défis`, `Informations`, `Exercices`, `Archives`, `Angular`, `Python`, `Colab`, `NumPy & Keras`, `Google Cloud`, `Projet Web` et `Dans l'autobus`;
- conserve la numérotation des notes de cours et ne normalise que le premier niveau de dossiers sous le contenu généré;
- garde les noms inconnus avec leur préfixe numérique au lieu de deviner leur signification;
- ajoute une protection contre les collisions : deux dossiers source qui aboutiraient au même nom canonique conservent leurs noms préfixés et génèrent un avertissement;
- documente dans le README des règles Iconize `Folders only`, avec une variante recommandée limitée aux chemins CEM;
- ajoute `assets/iconize/cem-symbol-iconize.svg` comme icône CEM optionnelle pour les custom icon packs Iconize;
- ajoute des tests de régression pour la matrice d'alias, la conservation des numéros de notes, les dossiers inconnus et les collisions.

## 0.2.12

- Prevent Dataview inline-query parsing from hijacking legitimate inline code that starts with `=` or `$=`.
- Preserve fenced code verbatim while rendering only conflicting inline spans as HTML `<code>`.
- Add regression coverage for the 1P6 assignment/comparison operator lesson.
- Move the shared department Git guide out of its one-file `Ressources` folder and place it directly at the Cégep import root.


## 0.2.11

- normalise les corps de `TabItem` avant toute conversion de composant afin d'empêcher les remplacements précoces (images, Feedback, fragments MDX) de casser l'indentation globale de 420-SN1;
- prend en charge les admonitions Docusaurus imbriquées avec fences de 4+ deux-points (`::::note`) ainsi que les variantes CEM `info-nt`, `tip-nt`, `warning-nt` et `danger-nt`;
- conserve correctement les blocs de code à l'intérieur des callouts imbriqués au lieu de laisser des marqueurs `::::` ou de produire de gros blocs de code accidentels;
- supprime silencieusement les widgets `Feedback` du site, qui ne sont pas du contenu pédagogique et ajoutaient du bruit dans les notes locales;
- évite de revalider comme liens source les assets déjà générés sous `_assets`, éliminant les faux liens non résolus observés dans 420-SN1;
- résout les assets Docusaurus dont l'URL contient déjà le `baseUrl` du cours, par exemple `/420-SN1/img/logo.svg`;
- ajoute des tests de régression directement inspirés des blocs `Variables`, `On commence!` et des diagnostics du rapport 420-SN1.

## 0.2.10

- empêche le vrai composant Angular de la page Git départementale d'être interprété comme un bloc de code indenté dans Obsidian en normalisant son HTML à la colonne zéro;
- corrige l'ordre des transformations des fences de code et des `Tabs`, afin que les onglets mixtes de 420-SN1 soient déduits comme un bloc cohérent avant de normaliser les fences;
- ajoute des tests de régression reproduisant les deux rendus cassés observés dans Obsidian.

## 0.2.9

- remplace la mauvaise source legacy `git.md` par le vrai composant Angular utilisé par `https://info.cegepmontpetit.ca/git`;
- reproduit la page Git départementale en grille responsive de cartes avec badges et alertes via le CSS Obsidian;
- supprime l’erreur Mermaid provoquée par les fences Mermaid complètement vides;
- conserve l’indentation des fragments MDX importés à l’intérieur des `TabItem`, afin d’éviter que de longues portions de cours soient rendues comme du code dans Obsidian;
- convertit aussi les images JSX minuscules `img` avec `src={require(...).default}`, notamment les icônes inline de 420-SN1;
- ajoute des styles dédiés pour garder les petites icônes inline au lieu de les centrer comme des figures;
- ajoute des tests de régression ciblant les problèmes visuels observés sur la page Git départementale et 420-SN1.

## 0.2.8

- synchronise automatiquement la page officielle `https://info.cegepmontpetit.ca/git`;
- range cette ressource commune dans `Ressources/Git - Consignes du département.md`;
- conserve le contenu Markdown officiel et ajoute seulement les métadonnées Obsidian nécessaires;
- affiche l'état de cette ressource dans `doctor`.


## 0.2.7

- prend en charge les quiz CEM qui référencent directement un fichier JSON sous `web/static/quiz`;
- tolère les espaces insécables présents autour de certains attributs JSX dans les sources de cours;
- ignore les liens Markdown placés dans des commentaires HTML, afin que du contenu volontairement désactivé ne génère plus de faux avertissements;
- ignore les fichiers de documentation dont le nom commence par `_`, conformément à la convention CEM pour les brouillons/helpers non publiés;
- répare prudemment certains liens de rencontres manifestement erronés lorsque le numéro affiché dans le libellé permet d'identifier une route locale existante;
- ajoute des tests de régression couvrant les 8 derniers problèmes observés dans le rapport global des 13 cours.

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

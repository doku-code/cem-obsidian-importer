# CEM Obsidian Importer

Convertit les dépôts de cours Docusaurus / Markdown / MDX du département d'informatique du CÉM en notes locales prêtes pour Obsidian.

Le projet vise un résultat **lisible, local et pratique pour l'étude** : navigation entre les pages, assets copiés localement, callouts Obsidian, onglets de code, diagrammes Mermaid et previews interactifs lorsque les plugins requis sont disponibles.

> **Projet communautaire non officiel.** Ce dépôt n'est pas un produit officiel du Cégep Édouard-Montpetit et n'implique aucune approbation de l'établissement ou du département. Le contenu importé conserve les conditions de licence et de diffusion de son dépôt source.

## En bref

Pour un usage normal, il n'y a qu'une commande à retenir :

```bash
python3 cem_importer.py run
```

Le programme :

1. demande dans quel dossier du vault placer les cours;
2. affiche la liste des dépôts CEM connus;
3. permet d'en sélectionner un ou plusieurs;
4. synchronise aussi la page Git commune du département à la racine du dossier Cégep;
5. importe les cours choisis;
6. affiche un résumé avec les erreurs d'import et les problèmes de conversion, regroupés par dépôt.

La dernière destination utilisée est mémorisée localement et proposée comme valeur par défaut au prochain lancement.

---

# Fonctionnalités

- clone automatiquement les dépôts GitHub officiels connus;
- détecte le dossier Docusaurus `docs`;
- convertit les pages `.md` et `.mdx` vers du Markdown compatible Obsidian;
- copie images, vidéos locales et autres ressources sous `_assets`;
- conserve l'ordre et les titres du `sidebars.js` lorsqu'il est disponible;
- normalise prudemment les dossiers pédagogiques de premier niveau (`01-notes` → `Cours`, `03-labos` → `Laboratoire`, etc.) sans toucher à la numérotation des notes;
- génère `Navigation.md` avec Iconize, ou `00 - Navigation.md` en fallback autonome, plus une navigation précédent / suivant;
- convertit les admonitions Docusaurus en callouts Obsidian;
- convertit les layouts `Row` / `Column` en colonnes via le CSS fourni;
- transforme certains `DataFlowPlayer` en Mermaid;
- transforme les `ReactPreview` multi-fichiers en playgrounds interactifs avec **Code Playground**;
- utilise **Codeblock Customizer** pour les comparaisons de snippets;
- produit des rapports Markdown/JSON centralisés dans le dossier `reports/` du projet, sans polluer les notes;
- synchronise **et active** automatiquement le CSS Obsidian fourni lorsque le vault est détecté;
- synchronise automatiquement la vraie page Angular des consignes Git du département dans `Git - Consignes du département.md` à la racine du dossier Cégep, avec sa grille de cartes et ses badges adaptés à Obsidian.

La conversion est volontairement conservatrice : un composant MDX inconnu n'est jamais supprimé silencieusement. Il est signalé dans le rapport d'import.

---

# Installation

## Prérequis

Il faut :

- **Python 3.11 ou plus récent**;
- **Git**;
- **Obsidian**.

Aucune bibliothèque Python externe n'est requise.

Vérification rapide :

```bash
python3 --version
git --version
```

Sous Windows, `python3` peut être remplacé par `py` ou `python` selon l'installation.

## Récupérer le projet

Avec Git :

```bash
git clone <URL_DU_REPO_CEM_OBSIDIAN_IMPORTER>
cd cem-obsidian-importer
```

Ou utilisez **Code → Download ZIP** sur GitHub, puis ouvrez un terminal dans le dossier extrait.

## Plugins Obsidian recommandés

| Plugin | Utilité |
|---|---|
| **Codeblock Customizer** | Onglets pour comparer plusieurs snippets de code |
| **Code Playground** | Previews React / TypeScript interactifs multi-fichiers |
| **Execute Code** | Exécuter les snippets de code directement dans les notes |
| **Hide Folders** | Masquer `_assets` et `_playgrounds` dans l'explorateur |
| **Iconize** | Ajouter des icônes cohérentes aux dossiers normalisés |

Les plugins restent optionnels. Lorsque c'est possible, l'importeur produit un fallback Markdown lisible.

Pour **Execute Code**, les runtimes du langage doivent être disponibles sur la machine. Par exemple, les snippets JavaScript/TypeScript nécessitent généralement `node` et `ts-node`.

---

# Utilisation

Lancez :

```bash
python3 cem_importer.py run
```

## 1. Choisir la destination

Le programme demande d'abord où créer les dossiers de cours.

Exemple macOS / Linux :

```text
/Users/alex/Documents/Obsidian/MonVault/School/Cégep Édouard-Montpetit
```

Exemple Windows :

```text
C:\Users\Alex\Documents\Obsidian\MonVault\School\Cégep Édouard-Montpetit
```

Au prochain lancement, cette destination sera proposée entre crochets. Appuyez simplement sur **Entrée** pour la réutiliser ou tapez un nouveau chemin pour la changer. Vous pouvez coller le chemin tel quel, avec des guillemets/apostrophes ou des espaces échappés; le lanceur les normalise automatiquement.

La préférence est stockée dans `.cem-importer.json`, fichier local ignoré par Git.

## 2. Sélectionner les cours

Le programme affiche ensuite les cours regroupés par session :

```text
Cours disponibles

Session 1
  [ ]  1. 1P6 - Introduction à la programmation

Session 2
  [ ]  2. 2P6 - Programmation orientée objet

Session 3
  [ ]  3. 3W6 - Programmation Web transactionnelle
  ...

Session 4
  [ ]  7. 3M5 - Introduction à la programmation mobile
  [ ]  8. 4W6 - Programmation Web orientée services
  ...
```

Plusieurs formats sont acceptés :

```text
3 8 10
```

```text
3-6
```

```text
1,3,5-8
```

ou simplement :

```text
all
```

Le programme réaffiche la sélection avant de commencer l'import.

## 3. Lire le résumé

À la fin, un résumé global est affiché :

```text
RÉSUMÉ DE L'IMPORT
========================================================================
Destination            : ...
Cours demandés         : 3
Imports réussis        : 3
Erreurs d'import       : 0
Problèmes de conversion: 2

Problèmes de conversion par repo :
  ⚠ Z03: 2 — 2 composant(s) MDX inconnu(s)

📄 Rapport détaillé : .../cem-obsidian-importer/reports/detail-summary.md
```

Deux catégories sont distinguées :

- **Erreur d'import** : le dépôt n'a pas pu être cloné ou le convertisseur a échoué.
- **Problème de conversion** : l'import s'est terminé, mais certains éléments demandent une vérification, par exemple un composant MDX inconnu ou un lien local non résolu.

---

# Structure générée

Les cours sont automatiquement rangés par session. Une destination comme
`School/Cégep Édouard-Montpetit` peut donc produire :

```text
Cégep Édouard-Montpetit/
├── Git - Consignes du département.md
├── Session 1/
│   └── 1P6 - Introduction à la programmation/
│       └── Classe/
├── Session 3/
│   └── 3W6 - Programmation Web transactionnelle/
│       └── Classe/
├── Session 4/
│   ├── 3M5 - Introduction à la programmation mobile/
│   │   └── Classe/
│   └── 4W6 - Programmation Web orientée services/
│       └── Classe/
└── Session 6/
    └── 5N6 - Applications mobiles avancées/
        └── Classe/
```

La page Git du département est placée directement à la racine du dossier Cégep et mise à jour automatiquement à chaque `run` depuis sa source officielle.

Le dossier `Classe` est le conteneur généré pour un cours. À l'intérieur, la section pédagogique `Cours` reste distincte des sections `TP`, `Laboratoire`, `Recettes`, etc.

À l'intérieur de chaque dossier `Classe`, l'importeur conserve le contenu pédagogique et les liens du site, mais **normalise seulement les dossiers de section connus** afin que les mêmes concepts aient le même nom d'un cours à l'autre. Les cours sans session fixe sont rangés dans `Autres cours`.

Par exemple :

```text
4W6 - Programmation Web orientée services/
└── Classe/
    ├── Navigation.md        # avec Iconize; sinon 00 - Navigation.md
    ├── Accueil.md
    ├── Cours/          # source : 01-notes
    ├── TP/             # source : 02-tp
    ├── Laboratoire/    # source : 03-labos
    └── Angular/        # source : 04-angular

420-SN1 - Programmation en sciences/
└── Classe/
    ├── Navigation.md        # si Iconize + frontmatter sont actifs
    ├── Accueil.md
    ├── Cours/
    ├── TP/
    ├── Recettes/
    ├── Aide-mémoire/
    └── Archives/
```

La normalisation est volontairement conservatrice :

- seuls les alias observés dans les dépôts CEM supportés sont renommés;
- un dossier inconnu conserve son nom humanisé **et son préfixe numérique** plutôt que d'être deviné;
- si deux dossiers source différents risquent de se retrouver sous le même nom canonique, l'importeur annule cette normalisation pour ces dossiers et le signale dans le rapport;
- la numérotation des **notes** (`1.1 - Introduction`, `2.1 - ...`, etc.) n'est pas supprimée.

Les principaux alias actuellement reconnus sont :

| Nom canonique | Variantes source reconnues |
|---|---|
| `Cours` | `cours`, `notes` |
| `TP` | `tp`, `tps` |
| `Laboratoire` | `laboratoire`, `laboratoires`, `labo`, `labos` |
| `Recettes` | `recette`, `recettes` |
| `Aide-mémoire` | `aidememoire`, `aide-memoire` |
| `Solution` | `solution`, `solutions` |
| `Extra` | `extra`, `extras` |
| `Défis` | `defi`, `defis` |
| `Informations` | `info`, `infos`, `information`, `informations` |
| `Exercices` | `exercice`, `exercices` |
| `Archives` | `ancien`, `anciens`, `archive`, `archives`, `tp_archives_idees` |
| `Autres` | `autre`, `autres` |
| noms spécialisés | `angular`, `python`, `colab`, `numpykeras`, `googlecloud`, `projet-web`, `dans-autobus` |

Avec Code Playground, `_playgrounds` peut aussi être créé à la racine du vault pour stocker les projets interactifs multi-fichiers.

> **Important :** le dossier `Classe` est généré et peut être reconstruit lors d'un nouvel import. Gardez vos annotations personnelles dans un dossier séparé, par exemple `Mes notes`.

---

# Iconize — configuration recommandée

Iconize est **optionnel**. L'importeur continue de produire des notes autonomes s'il n'est
pas installé. Lorsqu'il est installé, activé et configuré avec **Use icon in frontmatter**,
l'importeur utilise cependant Iconize pour séparer clairement :

- les **dossiers de navigation** : icônes Lucide/SVG via les règles Iconize;
- les **notes de cours** : emoji via la propriété `icon`;
- `Accueil` : `LiHouse` (Lucide);
- `Navigation` : `LiCompass` (Lucide);
- `Git - Consignes du département` : `LiGitBranch`.

Les emojis déjà utilisés par les professeurs dans le titre d'une note sont déplacés dans
la propriété Iconize et retirés du nom/titre généré. Si une note de la section `Cours` n'a
aucun emoji, l'importeur utilise `📘` comme icône générique. **Si Iconize ou le frontmatter
Iconize ne sont pas actifs, rien n'est retiré des titres.**

Avec Iconize actif, la navigation générée s'appelle :

```text
Navigation.md
```

Sans Iconize, l'importeur conserve le fallback autonome :

```text
00 - Navigation.md
```

## Installer les règles sans tout saisir à la main

Le projet fournit les règles dans :

```text
config/iconize-rules.json
```

Le plus simple est de **fermer Obsidian**, puis de lancer :

```bash
python3 cem_importer.py iconize
```

> Depuis la 0.2.16, `python3 cem_importer.py run` exécute automatiquement cette synchronisation lorsque Iconize est installé et activé. La commande `iconize` reste disponible pour réparer/configurer Iconize sans réimporter les cours. Si Obsidian était ouvert pendant une première synchronisation, rechargez-le une fois pour que le plugin relise ses règles.

Le launcher retrouve le dernier vault utilisé, sauvegarde le `data.json` d'Iconize, puis :

- ajoute les règles CEM manquantes;
- corrige les règles existantes pour utiliser **Folders only**;
- active le matching sur le **chemin complet** (`useFilePath: true`);
- conserve l'icône que vous aviez déjà choisie pour une règle existante.

Une sauvegarde du genre suivant est créée avant toute modification :

```text
.obsidian/plugins/obsidian-icon-folder/data.json.cem-backup-YYYYMMDD-HHMMSS
```

Vous pouvez vérifier sans écrire avec :

```bash
python3 cem_importer.py iconize --dry-run
```

Puis relancez Obsidian, ou désactivez/réactivez Iconize.

> **Pourquoi les regex peuvent sembler ne rien faire ?**  Les règles ci-dessous portent sur
> le chemin complet (`.../Session 4/4W6.../Classe/Cours`). Dans l'éditeur d'une règle Iconize,
> l'option **Include folders and files that are part of the path** doit donc être activée.
> Sinon Iconize essaie la regex uniquement sur le dernier nom (`Cours`, `TP`, etc.) et elle ne
> peut pas matcher. Le command `iconize` configure ce point automatiquement.

## Regex utilisées par le projet

Toutes ces règles sont **Folders only** et **Use file path = ON**. Elles correspondent à la
structure réellement générée par l'importeur :

```text
Session
(?:^|/)Session [1-6]$

Autres cours
(?:^|/)Autres cours$

Classe
(?:^|/)(?:Session [1-6]|Autres cours)/[^/]+/Classe$

Cours
(?:^|/)(?:Session [1-6]|Autres cours)/[^/]+/Classe/Cours$

TP
(?:^|/)(?:Session [1-6]|Autres cours)/[^/]+/Classe/TP$

Laboratoire
(?:^|/)(?:Session [1-6]|Autres cours)/[^/]+/Classe/Laboratoire$

Recettes
(?:^|/)(?:Session [1-6]|Autres cours)/[^/]+/Classe/Recettes$

Aide-mémoire
(?:^|/)(?:Session [1-6]|Autres cours)/[^/]+/Classe/Aide-mémoire$

Solution
(?:^|/)(?:Session [1-6]|Autres cours)/[^/]+/Classe/Solution$

Extra
(?:^|/)(?:Session [1-6]|Autres cours)/[^/]+/Classe/Extra$

Défis
(?:^|/)(?:Session [1-6]|Autres cours)/[^/]+/Classe/Défis$

Informations
(?:^|/)(?:Session [1-6]|Autres cours)/[^/]+/Classe/Informations$

Exercices
(?:^|/)(?:Session [1-6]|Autres cours)/[^/]+/Classe/Exercices$

Archives
(?:^|/)(?:Session [1-6]|Autres cours)/[^/]+/Classe/Archives$

Autres
(?:^|/)(?:Session [1-6]|Autres cours)/[^/]+/Classe/Autres$

Angular
(?:^|/)(?:Session [1-6]|Autres cours)/[^/]+/Classe/Angular$

Python
(?:^|/)(?:Session [1-6]|Autres cours)/[^/]+/Classe/Python$

Colab
(?:^|/)(?:Session [1-6]|Autres cours)/[^/]+/Classe/Colab$

NumPy & Keras
(?:^|/)(?:Session [1-6]|Autres cours)/[^/]+/Classe/NumPy & Keras$

Google Cloud
(?:^|/)(?:Session [1-6]|Autres cours)/[^/]+/Classe/Google Cloud$

Projet Web
(?:^|/)(?:Session [1-6]|Autres cours)/[^/]+/Classe/Projet Web$

Dans l'autobus
(?:^|/)(?:Session [1-6]|Autres cours)/[^/]+/Classe/Dans l'autobus$
```

Parce que les règles sont `Folders only`, une note Markdown nommée `Cours`, `TP`, `Solution`,
etc. **n'est jamais affectée** par ces regex.

## Icône du Cégep optionnelle

Le symbole simplifié utilisé pour le dossier du Cégep est fourni dans :

```text
assets/iconize/cem-symbol-iconize.svg
```

Il s'agit d'une recréation vectorielle simplifiée destinée à un vault personnel, et non d'un
SVG officiel distribué par le Cégep. Créez un custom icon pack dans Iconize puis glissez ce SVG
sur la ligne du pack. Le fichier utilise `currentColor`, donc il suit la couleur du thème/Iconize.

Iconize ne gère pas l'ordre des dossiers. L'importeur ne rajoute donc ni caractères invisibles,
ni faux numéros pour forcer un tri visuel.

---

# CSS Obsidian

Lorsque la destination se trouve dans un vault Obsidian, `run` copie automatiquement :

```text
obsidian-wide-notes.css
```

vers :

```text
.obsidian/snippets/obsidian-wide-notes.css
```

Il suffit ensuite de l'activer une fois :

```text
Settings
→ Appearance
→ CSS snippets
→ Reload snippets
→ obsidian-wide-notes
```

La largeur des pages de cours est configurée à **1400 px**.

---

# Autres commandes

La commande principale reste `run`, mais quelques utilitaires sont disponibles :

```bash
python3 cem_importer.py courses
```

Affiche les dépôts inclus dans le catalogue.

```bash
python3 cem_importer.py doctor
```

Vérifie rapidement Python, Git, le dernier vault utilisé, le CSS et Code Playground.

```bash
python3 cem_importer.py sync-css
```

Resynchronise seulement le CSS dans le dernier vault utilisé.

Le moteur de conversion peut également être appelé directement par les développeurs :

```bash
python3 cem_to_obsidian.py --help
```

---

# Rapports de conversion

Les diagnostics sont volontairement gardés **hors du vault** afin que les notes importées restent propres. Le dernier lancement produit seulement deux fichiers plats :

```text
cem-obsidian-importer/
└── reports/
    ├── detail-summary.md
    └── summary.json
```

`detail-summary.md` est le rapport à lire : il commence par une vue globale, puis sépare clairement les erreurs et avertissements **par cours**, avec le chemin de la note et la cible problématique lorsque cette information est disponible. Les cours sans problème sont regroupés dans une section compacte à la fin.

`summary.json` contient les mêmes données sous forme structurée pour le débogage et une éventuelle automatisation. Les rapports temporaires de chaque cours sont fusionnés pendant l'import puis supprimés automatiquement : il n'y a donc plus de sous-dossiers `reports/3M5/`, `reports/4W6/`, etc.

Le dossier `reports/` est ignoré par Git par défaut et est recréé proprement à chaque `run`.

---

# Documentation supplémentaire

- [`docs/COURSES.md`](docs/COURSES.md) — catalogue des dépôts CEM intégrés;
- [`docs/SUPPORTED_COMPONENTS.md`](docs/SUPPORTED_COMPONENTS.md) — composants Docusaurus / MDX actuellement pris en charge;
- [`docs/TROUBLESHOOTING.md`](docs/TROUBLESHOOTING.md) — problèmes fréquents et solutions;
- [`docs/DEVELOPMENT.md`](docs/DEVELOPMENT.md) — architecture interne et développement;
- [`CONTRIBUTING.md`](CONTRIBUTING.md) — conventions pour contribuer au projet.

---

# Limites

Les dépôts de cours évoluent et peuvent introduire de nouveaux composants React / MDX. L'importeur préfère alors conserver le contenu statique disponible et signaler le composant plutôt que d'inventer un résultat ou de supprimer silencieusement de l'information.

Les previews **Code Playground** utilisent Sandpack. Selon la configuration du plugin, leur compilation peut utiliser un service de bundling externe. Consultez la documentation du plugin si le code doit rester entièrement local.

# CEM Obsidian Importer

Convertit des dépôts de cours Docusaurus / Markdown / MDX du département d'informatique du CÉM en notes locales prêtes pour Obsidian.

Le projet vise un résultat **lisible, local et pratique pour l'étude** : navigation entre les pages, images et assets copiés localement, callouts Obsidian, onglets de code, diagrammes Mermaid et previews interactifs lorsque les plugins requis sont disponibles.

> **Projet communautaire non officiel.** Ce dépôt n'est pas un produit officiel du Cégep Édouard-Montpetit et n'implique aucune approbation de l'établissement ou du département. Le contenu importé conserve les conditions de licence et de diffusion du dépôt source.

## Ce que l'importeur fait

- importe un dépôt GitHub directement ou un dépôt déjà cloné sur la machine;
- détecte automatiquement le dossier Docusaurus `docs`;
- convertit les pages `.md` et `.mdx` vers du Markdown compatible Obsidian;
- copie les images, vidéos locales et autres ressources sous `_assets`;
- conserve l'ordre et les titres du `sidebars.js` lorsqu'il est disponible;
- génère une page `00 - Navigation.md` et une navigation précédent / suivant;
- convertit les admonitions Docusaurus en callouts Obsidian;
- convertit les layouts `Row` / `Column` en colonnes via le CSS fourni;
- transforme certains `DataFlowPlayer` en Mermaid;
- transforme les exemples multi-fichiers en playground interactif avec **Code Playground**;
- utilise **Codeblock Customizer** pour les comparaisons de snippets;
- produit un rapport de conversion pour signaler les composants inconnus ou les liens non résolus.

La conversion est volontairement conservatrice : un composant MDX inconnu n'est pas supprimé silencieusement. Il est signalé dans le rapport d'import.

---

# Installation rapide

## 1. Prérequis

Il faut :

- **Python 3.11 ou plus récent**;
- **Git**;
- **Obsidian**.

Aucune bibliothèque Python externe n'est requise.

Pour vérifier Python :

```bash
python3 --version
```

Sous Windows, la commande peut plutôt être :

```powershell
py --version
```

Pour vérifier Git :

```bash
git --version
```

## 2. Télécharger le projet

Deux options simples :

### Option A — Git

```bash
git clone <URL_DU_REPO_CEM_OBSIDIAN_IMPORTER>
cd cem-obsidian-importer
```

### Option B — ZIP

Sur GitHub : **Code → Download ZIP**, puis décompressez l’archive. Ouvrez ensuite un terminal dans le dossier extrait.

## 3. Plugins Obsidian recommandés

Les plugins ne sont pas tous obligatoires. Sans eux, l'importeur tente de garder un résultat lisible en Markdown standard.

| Plugin | Utilité |
|---|---|
| **Codeblock Customizer** | Onglets pour comparer plusieurs snippets de code |
| **Code Playground** | Previews React / TypeScript interactifs multi-fichiers |
| **Hide Folders** | Masquer `_assets` et `_playgrounds` dans l'explorateur Obsidian |

Le CSS fourni est également recommandé pour reproduire certains éléments visuels des cours : largeur des pages, images centrées, colonnes, badges et navigation.

---

# Premier démarrage

> **Important :** `import-all` reconstruit le dossier généré `Notes de cours`. Placez vos annotations personnelles dans un dossier séparé, par exemple `Mes notes`, afin qu’elles ne soient jamais écrasées.

Le moyen le plus simple est d'utiliser `cem_importer.py`.

## 1. Configurer la destination

Depuis le dossier du projet :

```bash
python3 cem_importer.py configure
```

Le script demande où placer les cours dans le vault Obsidian.

Exemple :

```text
/Users/alex/Documents/Obsidian/Vault/School
```

Sous Windows :

```text
C:\Users\Alex\Documents\Obsidian\Vault\School
```

La destination est enregistrée dans `.cem-importer.json`, un fichier local ignoré par Git.

Pour changer la destination plus tard :

```bash
python3 cem_importer.py configure "/nouvelle/destination"
```

## 2. Ajouter un cours

```bash
python3 cem_importer.py add-course \
  https://github.com/departement-info-cem/3M5-Intro-Mobile.git \
  "3M5 - Programmation Mobile"
```

Il est possible d'en ajouter autant que nécessaire.

## 3. Vérifier la configuration

```bash
python3 cem_importer.py show-config
```

Pour un diagnostic plus complet :

```bash
python3 cem_importer.py doctor
```

## 4. Importer tous les cours configurés

```bash
python3 cem_importer.py import-all
```

L'importeur reconstruit les copies locales et synchronise automatiquement le CSS dans le vault lorsqu'une racine `.obsidian` est détectée.

---

# Activer le CSS dans Obsidian

Le fichier `obsidian-wide-notes.css` est copié automatiquement vers :

```text
.obsidian/snippets/obsidian-wide-notes.css
```

Il suffit ensuite de l'activer une fois dans Obsidian :

```text
Settings
→ Appearance
→ CSS snippets
→ Reload snippets
→ obsidian-wide-notes
```

La largeur des pages de cours est configurée à **1400 px**.

Pour synchroniser seulement le CSS :

```bash
python3 cem_importer.py sync-css
```

---

# Commandes utiles

```text
python3 cem_importer.py configure
python3 cem_importer.py show-config
python3 cem_importer.py add-course <repo> "Nom du dossier"
python3 cem_importer.py remove-course <numéro-ou-nom>
python3 cem_importer.py import-all
python3 cem_importer.py sync-css
python3 cem_importer.py doctor
```

Sous Windows, `python3` peut être remplacé par `py` ou `python` selon l'installation.

---

# Importer un seul dépôt sans configuration

Le moteur de conversion peut aussi être utilisé directement :

```bash
python3 cem_to_obsidian.py \
  https://github.com/departement-info-cem/4W6-WebServices.git \
  -o "/chemin/vers/la/sortie" \
  --course-name "Notes de cours" \
  --copy-all-static \
  --force
```

Aide complète :

```bash
python3 cem_to_obsidian.py --help
```

---

# Structure générée

Un cours ressemble généralement à ceci :

```text
3M5 - Programmation Mobile/
└── Notes de cours/
    ├── 00 - Navigation.md
    ├── 01 - Cours/
    ├── 02 - Recettes/
    ├── 03 - TP/
    └── _assets/
        └── _conversion/
            └── report.md
```

Avec Code Playground, un dossier `_playgrounds` peut aussi être créé à la racine du vault pour stocker les projets interactifs multi-fichiers.

Les dossiers techniques peuvent être masqués avec un plugin tel que Hide Folders sans empêcher les notes d'accéder à leur contenu.

---

# Rapport de conversion

Après chaque import, consultez :

```text
_assets/_conversion/report.md
```

Un import réussi peut afficher :

```text
Aucun problème de conversion détecté. ✅
```

Si un composant MDX n'est pas encore supporté, il sera listé dans ce rapport. Cela permet d'ajouter un nouveau handler sans perdre silencieusement du contenu pédagogique.

---

# Limites importantes

L'objectif est une copie locale utile pour l'étude, pas une reproduction pixel-perfect de Docusaurus.

Quelques éléments peuvent toujours dépendre d'Internet :

- vidéos YouTube / Vimeo;
- liens vers des ressources externes;
- previews Code Playground lorsque le bundler Sandpack configuré est distant; selon la configuration du plugin, le code du playground peut être transmis au service de bundling;
- téléchargement initial des dépôts Git.

Les fichiers du cours, images et snippets présents dans les dépôts peuvent toutefois être copiés localement.

Consultez [docs/SUPPORTED_COMPONENTS.md](docs/SUPPORTED_COMPONENTS.md) pour le détail des conversions prises en charge.

---

# Dépannage

Commencez par :

```bash
python3 cem_importer.py doctor
```

Puis consultez [docs/TROUBLESHOOTING.md](docs/TROUBLESHOOTING.md).

---

# Développement

Les détails d'architecture et les commandes de test sont dans [docs/DEVELOPMENT.md](docs/DEVELOPMENT.md).

Pour exécuter tous les tests :

```bash
python3 -m unittest discover -s tests -v
```

Les contributions sont bienvenues; voir [CONTRIBUTING.md](CONTRIBUTING.md).

# CEM → Obsidian Importer v13

Importeur déterministe pour transformer les cours Docusaurus/Markdown/MDX du département d'informatique du CÉM en copie locale agréable à utiliser dans Obsidian.



- Les marqueurs MDX invisibles `&#8203;` / zero-width space sont retirés du texte converti.


## Changements v13 — ReactPreview interactif dans Obsidian

- Les fichiers d'un même `<ReactPreview>` sont maintenant regroupés **par appartenance au preview**, pas par nom de fichier. Ainsi `/page.tsx` et `/_types/item.ts` deviennent bien les onglets du même exemple.
- Si le plugin **Code Playground** est installé dans le vault, les `<ReactPreview>` deviennent de vrais playgrounds **Sandpack** avec éditeur, onglets de fichiers et aperçu React directement dans la note.
- L'importeur détecte automatiquement `.obsidian/plugins/code-playground/manifest.json`; aucun flag supplémentaire n'est nécessaire.
- Les sources du playground restent locales dans le vault, dans `_playgrounds/<id>.json`. Les identifiants sont déterministes, donc un nouvel import met à jour le même playground au lieu d'en créer un autre.
- Si Code Playground n'est pas installé, l'importeur retombe proprement sur des onglets **Codeblock Customizer** statiques.
- Le runtime reproduit le composant CEM avec le template `react-ts`, un `/App.tsx` caché, les fichiers auxiliaires et les styles CEM.

La v13 passe **31 tests de régression**.

## Changements v12 — surlignements fidèles au site

- `<Highlight color="tip">` conserve maintenant le vert du site au lieu de devenir jaune;
- `caution`, `info`, `danger` et `note` conservent également leurs couleurs CEM;
- les highlights deviennent de petits badges plus épais (padding, arrondi, poids de police);
- les `==highlights==` Markdown déjà présents reçoivent aussi une forme plus épaisse dans les notes `cem-course`;
- une couleur inconnue retombe sur `==...==` afin de ne jamais perdre le contenu.

La v12 passe **28 tests de régression**.

## Changements v10 — navigation compacte

La v10 affine le pied de page de navigation après validation visuelle dans Obsidian :

- seulement **Précédent** et **Suivant** sont affichés comme cartes compactes;
- **Sommaire** redevient un petit lien discret centré au-dessus des cartes;
- une page sans précédent/suivant ne crée plus de grosse carte vide;
- les cartes utilisent uniquement du Markdown + des callouts custom, donc les liens restent de vrais liens Obsidian;
- les images sont centrées via leur wrapper `.image-embed`, ce qui corrige le cas où centrer uniquement le `<img>` ne suffisait pas;
- le centrage est ciblé en Reading View et Live Preview;
- la navigation devient verticale automatiquement sur petite largeur/mobile.

La v10 passe **26 tests de régression**.

## Changements v8 — fidélité visuelle / moins de bruit

La v8 se concentre sur les différences qui restaient visibles entre le site du CÉM et Obsidian :

- suppression des callouts ajoutés uniquement par l'importeur (`Exemple exécutable local`, `Code GitHub copié localement`, `Vidéo du cours`, etc.);
- `<NonVoyant>` conservé, mais **replié par défaut** comme description secondaire;
- `JavaScriptConsole files={{...}}` devient maintenant un vrai groupe d'onglets Codeblock Customizer;
- `GHCode` devient directement un bloc de code local, sans commentaire parasite, et respecte les plages `ignore="x-y"` courantes;
- YouTube/Vimeo/vidéos locales sont intégrés directement, sans callout intermédiaire;
- `<Row>/<Column>` est conservé sous forme de **vraies colonnes responsives** grâce au snippet CSS fourni;
- toutes les notes importées reçoivent `cssclasses: cem-course` afin que le style reste limité aux cours importés;
- les images des notes importées sont centrées automatiquement;
- les conversions réussies `DataFlow → Mermaid` n'ajoutent plus de texte explicatif généré.

## Plugins Obsidian recommandés

### Code Playground — recommandé pour les `ReactPreview`

Installe :

```text
Settings → Community plugins → Browse → Code Playground
```

Les exemples React du cours deviennent alors de vrais mini-projets exécutables dans la note :

```text
/page.tsx | /_types/item.ts
---------------------------
éditeur de code
---------------------------
aperçu React interactif
```

Le plugin utilise Sandpack, comme le composant `ReactPreview` du site du CEM. Les fichiers éditables sont stockés localement dans le dossier `_playgrounds` du vault. Par défaut, la compilation utilise le bundler hébergé de CodeSandbox et demande donc Internet. Code Playground permet aussi de configurer une URL de bundler Sandpack auto-hébergée si tu veux plus tard garder cette partie dans ton homelab.

Si Code Playground n'est pas installé, le même ReactPreview reste lisible sous forme d'onglets Codeblock Customizer sans perte de code.

### Codeblock Customizer — recommandé

Installe :

```text
Settings → Community plugins → Browse → Codeblock Customizer
```

Les comparaisons de code deviennent des blocs du type :

````md
```kotlin group:cem-tabs-1 tab:"AndroidView"
AndroidView(...)
```

```kotlin group:cem-tabs-1 tab:"factory"
factory = { ... }
```
````

Sans le plugin, le code reste du Markdown normal et lisible. Avec le plugin, les blocs du même groupe deviennent des onglets cliquables. Cette approche reste compatible avec Execute Code.

Les `JavaScriptConsole` multi-fichiers du CEM (par exemple JavaScript vs TypeScript) utilisent maintenant le même principe automatiquement.

### Hide Folders — recommandé

Masque `_assets` pour garder l'arbre propre.

## Snippet CSS à installer / remplacer

Copie :

```text
obsidian-wide-notes.css
```

dans :

```text
TonVault/.obsidian/snippets/
```

Puis :

```text
Settings → Appearance → CSS snippets → Reload snippets
```

et active `obsidian-wide-notes`.

Le snippet fournit maintenant :

- largeur de lecture de `1100px`;
- images centrées pour les notes `cem-course`;
- vidéos intégrées propres;
- rendu responsive des `<Row>/<Column>` en 2 colonnes lorsque l'espace le permet, puis en une colonne sur petit écran.

## Vidéos intégrées

Aucun plugin vidéo n'est nécessaire pour YouTube.

La v8 convertit :

- YouTube / youtu.be / Shorts / embed → lecteur directement dans la note;
- Vimeo → iframe intégrée;
- vidéo locale (`.mp4`, `.mov`, `.mkv`, `.webm`, `.ogv`) → copie sous `_assets` + lecteur local;
- autre URL → lien normal.

## Cours utilisés pour solidifier l'importeur

Première famille réellement importée/testée :

- `departement-info-cem/4W6-WebServices`
- `departement-info-cem/3M5-Intro-Mobile`
- `departement-info-cem/3W6-Web-Transactionelle`

Compatibilité ajoutée après inspection des composants des repos suivants :

- `departement-info-cem/1P6`
- `departement-info-cem/5W5-Web-Avancee`
- `departement-info-cem/5N6-mobile-2`
- `departement-info-cem/3s4-cybersec`
- `departement-info-cem/z03`
- `departement-info-cem/420-SN1`
- `departement-info-cem/420-4A4`
- `departement-info-cem/2P6`
- `departement-info-cem/4D5-Base-De-Donnees-Et-Prog-Web`
- `departement-info-cem/3U4-cybersec`

## Conversions prises en charge

- `.mdx` → `.md`;
- images et assets locaux → `_assets/`;
- routes Docusaurus → liens locaux;
- labels/ordre de `sidebars.js` quand disponibles;
- navigation précédent / sommaire / suivant;
- admonitions Docusaurus → callouts Obsidian, y compris `:::info[Titre]`;
- `Row` / `Column` → grille responsive Obsidian;
- `<center>` + images → images locales centrées par CSS;
- `Highlight` → surlignage Obsidian `==...==`;
- `Video` → lecteur intégré quand possible;
- `Tabs` / `TabItem` de comparaison → onglets Codeblock Customizer;
- `raw-loader`, `JavaScriptConsole` → snippets locaux;
- `ReactPreview` → Code Playground interactif si installé, sinon onglets Codeblock Customizer;
- `DataFlowPlayer` → Mermaid lorsque possible;
- `GHCode` → code téléchargé, filtré et conservé localement;
- `Quiz` → quiz statique local avec réponses repliables;
- `DocsViewer` → sommaire local;
- `NonVoyant` → description locale repliée par défaut;
- `ConsoleWindow` → bloc de code/console normal;
- `GithubDownload` → ressource locale si possible, sinon lien sûr;
- `SlideImage` → image Markdown;
- `SlidePage` / sections Reveal → contenu Markdown aplati;
- `ExampleFrame` / `ExamplePeek` → exemple HTML local + sources disponibles;
- `TopicBadges` / `KeyPoint` → repères/callouts Obsidian;
- `ProjectStepHero` / `ProjectJourney` → représentation statique locale;
- `StyleSwitcher` → supprimé (cosmétique uniquement);
- `Feedback` → marqueur local non interactif;
- `PlanDeCoursMenu` → liste locale des PDF trouvés;
- composants inconnus → avertissement visible + rapport, jamais supprimés silencieusement.

## Importer tes trois cours actuels

```bash
./import_my_courses.sh "/chemin/vers/ton/Vault/School/Cégep Édouard-Montpetit"
```

Le helper remplace uniquement `Notes de cours` de :

- 3M5 - Programmation Mobile
- 3W6 - Programmation Web Transactionnelle
- 4W6 - Programmation Web Orienté Services

## Import individuel

```bash
python3 cem_to_obsidian.py \
  https://github.com/departement-info-cem/4W6-WebServices.git \
  -o "/chemin/vers/un/dossier" \
  --course-name "Notes de cours" \
  --copy-all-static \
  --force
```

## Rapport

```text
Notes de cours/_assets/_conversion/report.md
```

L'objectif reste : **aucune perte silencieuse**.

## Tests

La v13 passe **31 tests de régression**, incluant les anciens comportements ainsi que les ReactPreview multi-fichiers et la génération automatique des sidecars Code Playground.

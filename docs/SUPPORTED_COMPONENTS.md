# Composants pris en charge

Cette page décrit les principaux éléments reconnus par l'importeur et leur équivalent dans Obsidian.

| Source Docusaurus / MDX | Sortie Obsidian |
|---|---|
| Markdown standard | Markdown standard |
| Titres, listes, tableaux | Conservés |
| Images locales | Copiées sous `_assets` et centrées via CSS |
| `Image` avec `img={require(...)}` | Image locale copiée sous `_assets`, largeur conservée |
| `:::note`, `:::tip`, `:::warning`, etc. | Callouts Obsidian |
| `Row` / `Column` | Mise en page multi-colonnes via CSS |
| `Tabs` / `TabItem` avec code | Groupe Codeblock Customizer |
| `Tabs` complexes | Contenu aplati sans perte volontaire |
| `GHCode` | Code distant récupéré puis copié localement |
| `JavaScriptConsole` | Bloc exécutable / comparaison de fichiers |
| `ReactPreview` | Code Playground si disponible; fallback en onglets de code |
| `DataFlowPlayer` | Mermaid lorsque la structure est convertible |
| `Video` YouTube | Lecteur intégré Obsidian |
| Vimeo | iframe intégrée |
| Vidéo locale | Copie locale + embed |
| `NonVoyant` | Callout replié par défaut |
| `Highlight` | Badge coloré compatible CSS CEM |
| `Quiz` | Version statique locale avec réponses repliables (`file={...}` ou JSON statique) |
| `DocsViewer` | Index/navigation locale |
| `SlidePage` / `SlideImage` | Contenu aplati + image locale |
| `ConsoleWindow` | Bloc de code / console |
| `PlanDeCoursMenu` | Liens vers les PDF locaux lorsque disponibles |
| Fragments statiques `docs/_components/*.mdx` | Contenu incorporé dans la note lorsqu’il est importé comme composant |
| `C`, `S`, `N`, `K`, `F`, `B` (PyCode 420-SN1) | Code inline portable, sans dépendance au CSS du site |
| Composant inconnu | Signalé dans le rapport de conversion |

## ReactPreview et Code Playground

Les previews React sont d'abord transformées en représentation interne de projet :

```text
InteractiveProject
├── template: react-ts
├── entry: /page.tsx
├── /page.tsx
├── /_types/item.ts
└── /globals.css
```

Si Code Playground est détecté dans le vault, l'importeur produit un playground multi-fichiers. Sinon, tous les fichiers restent disponibles sous forme de blocs de code regroupés.

## Principe de compatibilité

L'importeur préfère une sortie moins interactive mais lisible plutôt qu'une conversion silencieusement incomplète. Un nouveau composant MDX doit être ajouté explicitement au pipeline lorsqu'il nécessite un traitement spécialisé.

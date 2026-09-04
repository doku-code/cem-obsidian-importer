# Développement

## Architecture

Le projet sépare autant que possible :

1. la découverte du dépôt et des pages;
2. la compréhension des composants Docusaurus / MDX;
3. leur rendu vers des primitives adaptées à Obsidian.

Pipeline simplifié :

```text
Repo de cours
   ↓
Découverte docs / static / sidebars
   ↓
Markdown / MDX
   ↓
Pipeline de transformations
   ├── callouts
   ├── layouts
   ├── code comparisons
   ├── InteractiveProject
   ├── Mermaid
   ├── vidéos
   └── assets
   ↓
Markdown Obsidian + assets + sidecars
```

`ReactPreview` est d'abord parsé comme un `InteractiveProject` indépendant du plugin Obsidian. Cela évite de coupler le parser de cours à Code Playground.

## Fichiers principaux

- `cem_to_obsidian.py` : moteur de conversion;
- `cem_importer.py` : workflow interactif, catalogue des cours et résumé multi-repos;
- `obsidian-wide-notes.css` : rendu des notes CEM;
- `tests/` : tests de régression.

## Catalogue de cours

Le launcher ne demande pas aux utilisateurs de maintenir des URLs. Les dépôts connus sont déclarés dans `COURSES` dans `cem_importer.py`.

Lorsqu'un nouveau dépôt officiel est ajouté :

1. ajouter son entrée au catalogue;
2. lancer ses imports représentatifs;
3. traiter les composants MDX manquants dans le moteur;
4. ajouter les tests de régression correspondants.

## Rapports machine-readable

Le moteur écrit `report.md` pour l'humain et `report.json` pour la CLI. Le JSON sert uniquement à agréger proprement les problèmes de plusieurs repos sans parser du Markdown.

Les composants inconnus, liens non résolus et avertissements indépendants contribuent au compteur de problèmes de conversion.

## Tests

```bash
python3 -m unittest discover -s tests -v
```

Avant une modification de handler, ajoutez idéalement un test minimal qui reproduit le MDX réel responsable du cas.

## Ajouter un composant MDX

Approche recommandée :

1. trouver une page réelle utilisant le composant;
2. vérifier son implémentation dans `web/src/components`;
3. définir ce qui doit être conservé dans Obsidian;
4. ajouter un handler déterministe;
5. ajouter un test de régression;
6. vérifier le rapport de conversion.

Évitez de simplement ajouter le composant à une liste d'exclusions : cela peut masquer une perte de contenu.

## Version

Le projet utilise une version sémantique publique. La version courante est stockée dans `VERSION` et dans la constante `VERSION` de `cem_to_obsidian.py`.

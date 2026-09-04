# Contribuer

Merci de vouloir améliorer CEM Obsidian Importer.

## Signaler un problème de conversion

Une bonne issue contient idéalement :

- le dépôt source;
- le chemin de la page `.md` / `.mdx`;
- le contenu pertinent du fichier `_assets/_conversion/report.md`;
- une capture du rendu attendu et du rendu Obsidian, si le problème est visuel.

## Proposer un changement

Avant d'envoyer un changement :

```bash
python3 -m unittest discover -s tests -v
```

Tous les tests existants doivent continuer à passer.

Pour un nouveau composant MDX, ajoutez un test reproduisant un exemple réel du dépôt de cours concerné.

## Principes du projet

- ne pas supprimer silencieusement du contenu inconnu;
- garder les sorties aussi portables que possible;
- préférer le Markdown natif lorsqu'un plugin n'est pas nécessaire;
- conserver un fallback lisible lorsque les plugins optionnels sont absents;
- ne pas modifier silencieusement le contenu pédagogique du dépôt source.

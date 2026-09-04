# Dépannage

La plupart des problèmes peuvent être identifiés avec :

```bash
python3 cem_importer.py doctor
```

## `python3` n'existe pas

Selon la plateforme, essayez :

```bash
python --version
```

ou sous Windows :

```powershell
py --version
```

Python 3.11 ou plus récent est requis.

## Git est introuvable

Vérifiez :

```bash
git --version
```

Git est nécessaire pour cloner les dépôts de cours sélectionnés par `run`.

## Je veux changer la destination

Relancez simplement :

```bash
python3 cem_importer.py run
```

La dernière destination apparaît comme valeur par défaut. Tapez un nouveau chemin au lieu d'appuyer sur Entrée.

## Aucun vault Obsidian n'est détecté

La destination doit normalement se trouver sous un dossier contenant :

```text
.obsidian/
```

Par exemple :

```text
MonVault/
├── .obsidian/
└── School/
    └── Cégep Édouard-Montpetit/
```

L'import peut tout de même fonctionner sans détection du vault, mais le CSS et Code Playground ne pourront pas être configurés automatiquement.

## Le CSS n'apparaît pas dans Obsidian

Vérifiez :

```text
Settings → Appearance → CSS snippets
```

Puis utilisez **Reload snippets** et activez `obsidian-wide-notes`.

Vous pouvez aussi resynchroniser le fichier :

```bash
python3 cem_importer.py sync-css
```

## Les previews React ne sont pas interactifs

Vérifiez que **Code Playground** est installé et activé dans le vault importé.

L'importeur détecte :

```text
.obsidian/plugins/code-playground/manifest.json
```

Sans le plugin, les exemples restent disponibles sous forme de blocs de code / onglets lorsque possible.

## Un cours affiche des problèmes de conversion

À la fin de `run`, la CLI indique le dépôt concerné et le nombre de problèmes détectés.

Ouvrez ensuite :

```text
<dossier du cours>/Cours/_assets/_conversion/report.md
```

Le rapport détaille notamment :

- les composants MDX inconnus;
- les liens locaux non résolus;
- les avertissements rencontrés pendant la conversion.

## Un dépôt échoue complètement

Le résumé classe alors le cours sous **Erreurs d'import par repo**.

Les causes les plus courantes sont :

- connexion Internet indisponible;
- Git non installé;
- dépôt renommé ou momentanément inaccessible;
- changement majeur dans la structure du dépôt.

Le dépôt fautif est affiché avec son URL afin de faciliter le diagnostic.

## Mes notes personnelles ont disparu

Le dossier :

```text
Cours/
```

est généré et peut être reconstruit avec `--force` lors d'un nouvel import. Ne placez pas vos notes personnelles directement dedans.

Utilisez plutôt un dossier voisin, par exemple :

```text
3M5 - Introduction à la programmation mobile/
├── Cours/            ← généré
└── Mes notes/        ← personnel
```

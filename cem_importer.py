#!/usr/bin/env python3
"""Interactive launcher for CEM Obsidian Importer.

The common workflow is intentionally small::

    python cem_importer.py run

`run` asks where the generated course folders should be written, lets the user
select one or more known CEM course repositories, imports them, then prints a
summary grouped by repository.

Python 3.11+; standard library only.
"""

from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parent
CONFIG_PATH = PROJECT_ROOT / ".cem-importer.json"
ENGINE_PATH = PROJECT_ROOT / "cem_to_obsidian.py"
CSS_SOURCE = PROJECT_ROOT / "obsidian-wide-notes.css"
DEFAULT_NOTES_FOLDER = "Notes de cours"
VERSION = (PROJECT_ROOT / "VERSION").read_text(encoding="utf-8").strip()


@dataclass(frozen=True)
class Course:
    """One course repository supported by the interactive launcher."""

    code: str
    folder: str
    repo: str


# The launcher is intentionally scoped to the repositories maintained by the
# CEM department. Add new official course repositories here as they are adopted.
COURSES: tuple[Course, ...] = (
    Course("1P6", "1P6", "https://github.com/departement-info-cem/1P6.git"),
    Course("2P6", "2P6", "https://github.com/departement-info-cem/2P6.git"),
    Course("3M5", "3M5 - Programmation Mobile", "https://github.com/departement-info-cem/3M5-Intro-Mobile.git"),
    Course("3S4", "3S4 - Cybersec", "https://github.com/departement-info-cem/3s4-cybersec.git"),
    Course("3U4", "3U4 - Cybersec", "https://github.com/departement-info-cem/3U4-cybersec.git"),
    Course("3W6", "3W6 - Programmation Web Transactionnelle", "https://github.com/departement-info-cem/3W6-Web-Transactionelle.git"),
    Course("4D5", "4D5 - Base de Données et Prog Web", "https://github.com/departement-info-cem/4D5-Base-De-Donnees-Et-Prog-Web.git"),
    Course("4W6", "4W6 - Programmation Web Orienté Services", "https://github.com/departement-info-cem/4W6-WebServices.git"),
    Course("5N6", "5N6 - Mobile 2", "https://github.com/departement-info-cem/5N6-mobile-2.git"),
    Course("5W5", "5W5 - Web Avancée", "https://github.com/departement-info-cem/5W5-Web-Avancee.git"),
    Course("420-4A4", "420-4A4", "https://github.com/departement-info-cem/420-4A4.git"),
    Course("420-SN1", "420-SN1", "https://github.com/departement-info-cem/420-SN1.git"),
    Course("Z03", "Z03", "https://github.com/departement-info-cem/z03.git"),
)


@dataclass
class ImportResult:
    course: Course
    succeeded: bool
    issue_count: int = 0
    unknown_components: int = 0
    unresolved_links: int = 0
    warnings: int = 0
    report_path: Path | None = None
    error: str = ""


def load_config() -> dict[str, Any]:
    """Load machine-local preferences.

    Only convenience values belong here. The repository list is part of the
    application itself so users never need to maintain URLs manually.
    """

    if not CONFIG_PATH.is_file():
        return {"destination": ""}
    try:
        data = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"Configuration invalide dans {CONFIG_PATH.name}: {exc}") from exc
    if not isinstance(data, dict):
        raise RuntimeError(f"Configuration invalide dans {CONFIG_PATH.name}: objet JSON attendu.")
    return {"destination": str(data.get("destination") or "")}


def save_config(config: dict[str, Any]) -> None:
    CONFIG_PATH.write_text(
        json.dumps(config, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def normalize_destination(value: str) -> Path:
    path = Path(value).expanduser().resolve()
    path.mkdir(parents=True, exist_ok=True)
    return path


def find_vault_root(start: Path) -> Path | None:
    current = start.resolve()
    for candidate in (current, *current.parents):
        if (candidate / ".obsidian").is_dir():
            return candidate
    return None


def sync_css(destination: Path, *, quiet: bool = False) -> Path | None:
    vault = find_vault_root(destination)
    if vault is None:
        if not quiet:
            print(
                "⚠ Aucun vault Obsidian détecté au-dessus de la destination.\n"
                "  Le CSS ne sera pas synchronisé, mais l'import peut continuer."
            )
        return None

    snippets = vault / ".obsidian" / "snippets"
    snippets.mkdir(parents=True, exist_ok=True)
    target = snippets / CSS_SOURCE.name
    shutil.copy2(CSS_SOURCE, target)
    if not quiet:
        print(f"✓ CSS synchronisé : {target}")
    return target


def prompt_destination(config: dict[str, Any]) -> Path:
    """Ask for the destination every run, while remembering the previous value."""

    current = str(config.get("destination") or "").strip()
    prompt = "Destination des cours dans ton vault Obsidian"
    if current:
        prompt += f"\n[{current}]"
    prompt += "\n> "

    entered = input(prompt).strip()
    value = entered or current
    if not value:
        raise RuntimeError("Aucune destination fournie.")

    destination = normalize_destination(value)
    config["destination"] = str(destination)
    save_config(config)
    return destination


def _parse_selection(raw: str, total: int) -> list[int]:
    """Parse `1,3,5`, `1-4`, or combinations thereof into zero-based indices."""

    selected: set[int] = set()
    for token in re.split(r"[\s,;]+", raw.strip()):
        if not token:
            continue
        if "-" in token:
            parts = token.split("-", 1)
            if not all(part.isdigit() for part in parts):
                raise ValueError(token)
            start, end = map(int, parts)
            if start > end:
                start, end = end, start
            values = range(start, end + 1)
        else:
            if not token.isdigit():
                raise ValueError(token)
            values = (int(token),)

        for value in values:
            if value < 1 or value > total:
                raise ValueError(str(value))
            selected.add(value - 1)
    return sorted(selected)


def prompt_courses() -> list[Course]:
    """Show a dependency-free checkbox-like multi-select menu."""

    print("\nCours disponibles\n")
    for index, course in enumerate(COURSES, start=1):
        print(f"  [ ] {index:>2}. {course.folder}")

    print("\nChoisis un ou plusieurs cours.")
    print("Exemples : 3 8 10   |   3-6   |   all")

    while True:
        raw = input("> ").strip()
        if raw.lower() in {"all", "a", "tout", "tous"}:
            selected = list(COURSES)
        else:
            try:
                indices = _parse_selection(raw, len(COURSES))
            except ValueError as exc:
                print(f"Choix invalide : {exc}. Réessaie.")
                continue
            selected = [COURSES[index] for index in indices]

        if not selected:
            print("Sélectionne au moins un cours.")
            continue

        print("\nSélection :")
        for course in selected:
            print(f"  [x] {course.folder}")
        answer = input("\nLancer l'import ? [O/n] ").strip().lower()
        if answer in {"", "o", "oui", "y", "yes"}:
            return selected
        print("\nD'accord, choisis à nouveau.")


def report_path_for(course: Course, destination: Path) -> Path:
    return destination / course.folder / DEFAULT_NOTES_FOLDER / "_assets" / "_conversion" / "report.json"


def read_conversion_summary(path: Path) -> dict[str, int]:
    if not path.is_file():
        return {
            "issue_count": 0,
            "unknown_components": 0,
            "unresolved_links": 0,
            "warnings": 0,
        }
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {
            "issue_count": 0,
            "unknown_components": 0,
            "unresolved_links": 0,
            "warnings": 0,
        }
    issues = data.get("issues", {}) if isinstance(data, dict) else {}
    return {
        "issue_count": int(issues.get("count", 0) or 0),
        "unknown_components": int(issues.get("unknown_component_occurrences", 0) or 0),
        "unresolved_links": int(issues.get("unresolved_local_links", 0) or 0),
        "warnings": int(issues.get("warnings", 0) or 0),
    }


def run_course_import(course: Course, destination: Path) -> ImportResult:
    output_parent = destination / course.folder
    cmd = [
        sys.executable,
        str(ENGINE_PATH),
        course.repo,
        "-o",
        str(output_parent),
        "--course-name",
        DEFAULT_NOTES_FOLDER,
        "--copy-all-static",
        "--force",
    ]

    print(f"\n{'─' * 72}")
    print(f"Import : {course.folder}")
    print(f"Repo   : {course.repo}")
    print(f"{'─' * 72}")

    completed = subprocess.run(cmd, text=True)
    report_path = report_path_for(course, destination)
    if completed.returncode != 0:
        return ImportResult(
            course=course,
            succeeded=False,
            report_path=report_path if report_path.exists() else None,
            error=f"Le convertisseur a quitté avec le code {completed.returncode}.",
        )

    summary = read_conversion_summary(report_path)
    return ImportResult(
        course=course,
        succeeded=True,
        report_path=report_path if report_path.exists() else None,
        **summary,
    )


def print_final_summary(results: list[ImportResult], destination: Path) -> int:
    hard_failures = [result for result in results if not result.succeeded]
    issue_results = [result for result in results if result.succeeded and result.issue_count > 0]
    total_issues = sum(result.issue_count for result in issue_results)

    print(f"\n{'=' * 72}")
    print("RÉSUMÉ DE L'IMPORT")
    print(f"{'=' * 72}")
    print(f"Destination            : {destination}")
    print(f"Cours demandés         : {len(results)}")
    print(f"Imports réussis        : {len(results) - len(hard_failures)}")
    print(f"Erreurs d'import       : {len(hard_failures)}")
    print(f"Problèmes de conversion: {total_issues}")

    if not hard_failures and not issue_results:
        print("\n✓ Aucun problème détecté dans les cours importés.")
        return 0

    if hard_failures:
        print("\nErreurs d'import par repo :")
        for result in hard_failures:
            print(f"  ✗ {result.course.code} — {result.course.repo}")
            if result.error:
                print(f"      {result.error}")

    if issue_results:
        print("\nProblèmes de conversion par repo :")
        for result in issue_results:
            details: list[str] = []
            if result.unknown_components:
                details.append(f"{result.unknown_components} composant(s) MDX inconnu(s)")
            if result.unresolved_links:
                details.append(f"{result.unresolved_links} lien(s) non résolu(s)")
            if result.warnings:
                details.append(f"{result.warnings} avertissement(s)")
            detail_text = ", ".join(details) or "voir le rapport"
            print(f"  ⚠ {result.course.code}: {result.issue_count} — {detail_text}")
            if result.report_path:
                print(f"      {result.report_path.with_suffix('.md')}")

    # A conversion warning does not make the launcher itself fail. A hard import
    # failure does, which is useful for CI or scripted runs later on.
    return 1 if hard_failures else 0


def cmd_run(args: argparse.Namespace) -> int:
    config = load_config()
    destination = prompt_destination(config)
    vault = find_vault_root(destination)
    if vault:
        print(f"✓ Vault détecté : {vault}")
    else:
        print("⚠ Aucun dossier .obsidian détecté au-dessus de la destination.")
    sync_css(destination)

    selected = prompt_courses()
    results = [run_course_import(course, destination) for course in selected]
    return print_final_summary(results, destination)


def cmd_list_courses(args: argparse.Namespace) -> int:
    for course in COURSES:
        print(f"{course.code:<8} {course.folder}\n         {course.repo}")
    return 0


def cmd_sync_css(args: argparse.Namespace) -> int:
    config = load_config()
    destination_raw = args.destination or str(config.get("destination") or "").strip()
    if not destination_raw:
        raise RuntimeError("Aucune destination connue. Lance d'abord `python cem_importer.py run`.")
    destination = normalize_destination(destination_raw)
    return 0 if sync_css(destination) else 1


def cmd_doctor(args: argparse.Namespace) -> int:
    config = load_config()
    print("Diagnostic CEM Obsidian Importer\n")

    print(f"Python : {sys.version.split()[0]}")
    print("  [OK]" if sys.version_info >= (3, 11) else "  [ERREUR] Python 3.11+ est requis.")

    git = shutil.which("git")
    print(f"Git : {git or '(introuvable)'}")
    print("  [OK]" if git else "  [ERREUR] Git est requis pour cloner les cours.")

    destination_raw = str(config.get("destination") or "").strip()
    print(f"Dernière destination : {destination_raw or '(aucune)'}")
    if destination_raw:
        destination = Path(destination_raw).expanduser()
        vault = find_vault_root(destination)
        if vault:
            print(f"Vault : {vault}")
            code_playground = vault / ".obsidian" / "plugins" / "code-playground" / "manifest.json"
            print(f"Code Playground : {'installé' if code_playground.is_file() else 'non détecté (optionnel)'}")
            snippet = vault / ".obsidian" / "snippets" / CSS_SOURCE.name
            print(f"CSS CEM : {'installé' if snippet.is_file() else 'non installé'}")
        else:
            print("  [ATTENTION] Aucun .obsidian trouvé au-dessus de la destination.")

    print(f"Cours connus : {len(COURSES)}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Importer interactivement les cours CEM connus vers un vault Obsidian."
    )
    parser.add_argument("--version", action="version", version=f"cem-obsidian-importer {VERSION}")
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("run", help="Choisir une destination, sélectionner les cours et les importer.")
    p.set_defaults(func=cmd_run)

    p = sub.add_parser("courses", help="Afficher la liste des dépôts de cours connus.")
    p.set_defaults(func=cmd_list_courses)

    p = sub.add_parser("sync-css", help="Resynchroniser le snippet CSS dans le dernier vault utilisé.")
    p.add_argument("--destination", help="Utiliser temporairement une autre destination.")
    p.set_defaults(func=cmd_sync_css)

    p = sub.add_parser("doctor", help="Vérifier Python, Git, Obsidian et Code Playground.")
    p.set_defaults(func=cmd_doctor)

    return parser


def main(argv: list[str] | None = None) -> int:
    try:
        args = build_parser().parse_args(argv)
        return int(args.func(args))
    except (RuntimeError, OSError, KeyboardInterrupt) as exc:
        if isinstance(exc, KeyboardInterrupt):
            print("\nImport annulé.", file=sys.stderr)
            return 130
        print(f"Erreur : {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())

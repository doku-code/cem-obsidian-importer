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
import shlex
import shutil
import subprocess
import sys
import tempfile
from urllib.request import Request, urlopen
from dataclasses import dataclass
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parent
CONFIG_PATH = PROJECT_ROOT / ".cem-importer.json"
ENGINE_PATH = PROJECT_ROOT / "cem_to_obsidian.py"
CSS_SOURCE = PROJECT_ROOT / "obsidian-wide-notes.css"
REPORTS_ROOT = PROJECT_ROOT / "reports"
DEFAULT_NOTES_FOLDER = "Classe"
GIT_GUIDE_FILENAME = "Git - Consignes du département.md"
GIT_GUIDE_SOURCE_PAGE = "https://info.cegepmontpetit.ca/git"
GIT_GUIDE_RAW_URL = (
    "https://raw.githubusercontent.com/departement-info-cem/"
    "departement-info-cem.github.io/main/angular/src/app/page/git/git.component.html"
)
ICONIZE_PLUGIN_ID = "obsidian-icon-folder"
ICONIZE_RULES_FILE = PROJECT_ROOT / "config" / "iconize-rules.json"
ICONIZE_GIT_ICON = "LiGitBranch"
VERSION = (PROJECT_ROOT / "VERSION").read_text(encoding="utf-8").strip()


@dataclass(frozen=True)
class Course:
    """One course repository supported by the interactive launcher."""

    code: str
    folder: str
    repo: str
    session: int | None

    @property
    def session_folder(self) -> str:
        """Human folder used to group courses by academic session."""

        return f"Session {self.session}" if self.session is not None else "Autres cours"


# The launcher is intentionally scoped to the repositories maintained by the
# CEM department. Add new official course repositories here as they are adopted.
COURSES: tuple[Course, ...] = (
    Course("1P6", "1P6 - Introduction à la programmation", "https://github.com/departement-info-cem/1P6.git", 1),
    Course("2P6", "2P6 - Programmation orientée objet", "https://github.com/departement-info-cem/2P6.git", 2),
    Course("3W6", "3W6 - Programmation Web transactionnelle", "https://github.com/departement-info-cem/3W6-Web-Transactionelle.git", 3),
    Course("3S4", "3S4 - Introduction à la cybersécurité", "https://github.com/departement-info-cem/3s4-cybersec.git", 3),
    Course("3U4", "3U4 - Introduction à la cybersécurité", "https://github.com/departement-info-cem/3U4-cybersec.git", 3),
    Course("420-SN1", "420-SN1 - Programmation en sciences", "https://github.com/departement-info-cem/420-SN1.git", 3),
    Course("3M5", "3M5 - Introduction à la programmation mobile", "https://github.com/departement-info-cem/3M5-Intro-Mobile.git", 4),
    Course("4W6", "4W6 - Programmation Web orientée services", "https://github.com/departement-info-cem/4W6-WebServices.git", 4),
    Course("420-4A4", "420-4A4 - Réseaux de neurones et sciences", "https://github.com/departement-info-cem/420-4A4.git", 4),
    Course("4D5", "4D5 - Base de données et programmation Web", "https://github.com/departement-info-cem/4D5-Base-De-Donnees-Et-Prog-Web.git", 5),
    Course("5W5", "5W5 - Programmation Web avancée", "https://github.com/departement-info-cem/5W5-Web-Avancee.git", 5),
    Course("5N6", "5N6 - Applications mobiles avancées", "https://github.com/departement-info-cem/5N6-mobile-2.git", 6),
    Course("Z03", "Z03 - Introduction à la programmation web", "https://github.com/departement-info-cem/z03.git", None),
)


@dataclass
class ImportResult:
    course: Course
    succeeded: bool
    issue_count: int = 0
    unknown_components: int = 0
    unresolved_links: int = 0
    warnings: int = 0
    report_data: dict[str, Any] | None = None
    error: str = ""


@dataclass(frozen=True)
class IconizeState:
    installed: bool
    enabled: bool
    frontmatter_enabled: bool
    frontmatter_field: str
    data_path: Path | None


def iconize_state(vault: Path | None) -> IconizeState:
    if vault is None:
        return IconizeState(False, False, False, "icon", None)
    obsidian = vault / ".obsidian"
    plugin_dir = obsidian / "plugins" / ICONIZE_PLUGIN_ID
    data_path = plugin_dir / "data.json"
    installed = (plugin_dir / "manifest.json").is_file()
    enabled = False
    try:
        plugins = json.loads((obsidian / "community-plugins.json").read_text(encoding="utf-8"))
        enabled = isinstance(plugins, list) and ICONIZE_PLUGIN_ID in plugins
    except (OSError, json.JSONDecodeError):
        pass

    frontmatter_enabled = False
    frontmatter_field = "icon"
    if installed and enabled:
        try:
            payload = json.loads(data_path.read_text(encoding="utf-8"))
            settings = payload.get("settings", {}) if isinstance(payload, dict) else {}
            if isinstance(settings, dict):
                frontmatter_enabled = bool(settings.get("iconInFrontmatterEnabled", False))
                frontmatter_field = str(settings.get("iconInFrontmatterFieldName") or "icon").strip() or "icon"
        except (OSError, json.JSONDecodeError):
            pass
    return IconizeState(installed, enabled, frontmatter_enabled, frontmatter_field, data_path if installed else None)


def set_frontmatter_scalar(text: str, key: str, value: str) -> str:
    line = f"{key}: {value}"
    if not text.startswith("---"):
        return f"---\n{line}\n---\n\n{text.lstrip()}"
    end = text.find("\n---", 3)
    if end < 0:
        return text
    fm = text[3:end]
    pattern = re.compile(rf"(?m)^{re.escape(key)}\s*:\s*.*$")
    if pattern.search(fm):
        fm = pattern.sub(line, fm, count=1)
    else:
        fm = fm.rstrip() + "\n" + line + "\n"
    return "---" + fm + text[end:]


def load_recommended_iconize_rules() -> list[dict[str, Any]]:
    try:
        payload = json.loads(ICONIZE_RULES_FILE.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise RuntimeError(f"Configuration Iconize invalide: {exc}") from exc
    rules = payload.get("rules", []) if isinstance(payload, dict) else []
    if not isinstance(rules, list):
        raise RuntimeError("Configuration Iconize invalide: tableau `rules` attendu.")
    return [dict(rule) for rule in rules if isinstance(rule, dict)]


def iconize_rule_status(vault: Path | None) -> tuple[int, int]:
    state = iconize_state(vault)
    desired = load_recommended_iconize_rules()
    if not state.data_path or not state.data_path.is_file():
        return 0, len(desired)
    try:
        payload = json.loads(state.data_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return 0, len(desired)
    settings = payload.get("settings", {}) if isinstance(payload, dict) else {}
    existing = settings.get("rules", []) if isinstance(settings, dict) else []
    by_rule = {r.get("rule"): r for r in existing if isinstance(r, dict)}
    valid = 0
    for wanted in desired:
        current = by_rule.get(wanted.get("rule"))
        if current and current.get("for") == "folders" and current.get("useFilePath") is True:
            valid += 1
    return valid, len(desired)


def sync_iconize_rules(destination: Path, *, dry_run: bool = False) -> tuple[int, int, Path | None]:
    """Merge the CEM folder rules into Iconize without replacing user settings/icons.

    Existing CEM rules keep the icon the user selected; only the important matching
    semantics are repaired (full path + folders only). Missing rules get the project
    defaults. A timestamped backup is written before changes.
    """
    vault = find_vault_root(destination)
    state = iconize_state(vault)
    if not state.installed:
        raise RuntimeError("Iconize n'est pas installé dans ce vault.")
    if not state.enabled:
        raise RuntimeError("Iconize est installé mais n'est pas activé dans ce vault.")
    if not state.data_path or not state.data_path.is_file():
        raise RuntimeError("Le fichier data.json d'Iconize est introuvable.")

    try:
        payload = json.loads(state.data_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"data.json d'Iconize invalide: {exc}") from exc
    if not isinstance(payload, dict):
        raise RuntimeError("data.json d'Iconize invalide: objet JSON attendu.")
    settings = payload.setdefault("settings", {})
    if not isinstance(settings, dict):
        raise RuntimeError("data.json d'Iconize invalide: `settings` doit être un objet.")
    existing = settings.setdefault("rules", [])
    if not isinstance(existing, list):
        raise RuntimeError("data.json d'Iconize invalide: `settings.rules` doit être un tableau.")

    desired = load_recommended_iconize_rules()
    existing_by_rule = {r.get("rule"): r for r in existing if isinstance(r, dict)}
    changed = 0
    max_order = max((int(r.get("order", -1)) for r in existing if isinstance(r, dict)), default=-1)
    for wanted in desired:
        pattern = wanted["rule"]
        current = existing_by_rule.get(pattern)
        if current is not None:
            before = dict(current)
            current["for"] = "folders"
            current["useFilePath"] = True
            if not current.get("icon"):
                current["icon"] = wanted["icon"]
            if "order" not in current:
                max_order += 1
                current["order"] = max_order
            if current != before:
                changed += 1
            continue

        max_order += 1
        rule = {
            "rule": pattern,
            "icon": wanted["icon"],
            "for": "folders",
            "useFilePath": True,
            "order": max_order,
        }
        existing.append(rule)
        existing_by_rule[pattern] = rule
        changed += 1

    backup: Path | None = None
    if changed and not dry_run:
        from datetime import datetime
        stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        backup = state.data_path.with_name(f"data.json.cem-backup-{stamp}")
        shutil.copy2(state.data_path, backup)
        state.data_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return changed, len(desired), backup


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


def clean_path_input(value: str) -> str:
    """Normalize a path pasted from a shell or Finder drag-and-drop.

    Python's ``input()`` does not ask the shell to interpret quotes or escaped
    spaces. This helper accepts common pasted forms such as ``'/Users/.../My Vault'``
    and ``/Users/.../My\\ Vault`` while leaving ordinary paths untouched.
    """

    raw = value.strip()
    if not raw:
        return raw

    try:
        parts = shlex.split(raw)
    except ValueError:
        parts = []

    if len(parts) == 1:
        return parts[0]

    return raw


def normalize_destination(value: str) -> Path:
    path = Path(clean_path_input(value)).expanduser().resolve()
    path.mkdir(parents=True, exist_ok=True)
    return path


def find_vault_root(start: Path) -> Path | None:
    current = start.resolve()
    for candidate in (current, *current.parents):
        if (candidate / ".obsidian").is_dir():
            return candidate
    return None


def build_department_git_note(
    source_html: str, *, icon_field: str | None = None
) -> str:
    """Render the actual department Git page inside Obsidian.

    ``/git`` is an Angular page. The old top-level ``git.md`` file in the
    repository is legacy content and does not match the page students see.
    The current content lives in
    ``angular/src/app/page/git/git.component.html``.

    The component is static HTML (cards, lists, ``pre`` blocks and badges), so
    preserving that markup is more faithful than flattening it into plain
    Markdown. ``obsidian-wide-notes.css`` recreates the responsive card grid.
    """

    body = source_html.lstrip("\ufeff").strip()
    # Obsidian's Markdown parser can reinterpret nested HTML lines indented by
    # four spaces as an indented code block once a blank line terminates a raw
    # HTML block. The Angular template is heavily indented, so normalize every
    # non-empty line to column zero. HTML collapses these newlines to spaces in
    # text nodes, while the Bootstrap-like classes remain available to our CSS.
    body = "\n".join(line.strip() for line in body.splitlines() if line.strip())
    # The URL is fixed to the official CEM repository, but do not persist
    # executable tags if upstream ever introduces them unexpectedly.
    body = re.sub(r"<script\b.*?</script>", "", body, flags=re.IGNORECASE | re.DOTALL)
    frontmatter = (
        "---\n"
        "title: Git - Consignes du département\n"
        f"source: {GIT_GUIDE_SOURCE_PAGE}\n"
        "cssclasses:\n"
        "  - cem-course\n"
        "---\n\n"
    )
    rendered = frontmatter + '<div class="cem-dept-git">\n' + body + "\n</div>\n"
    if icon_field:
        rendered = set_frontmatter_scalar(rendered, icon_field, ICONIZE_GIT_ICON)
    return rendered


def sync_department_git_guide(
    destination: Path,
    *,
    quiet: bool = False,
    fetcher=None,
) -> Path:
    """Download the department-wide Git guide directly into the Cégep import root.

    This resource applies to every course, so it is intentionally synchronized
    on every launcher run instead of appearing in the course selection menu.
    The source is the Angular component used by the real ``/git`` page, not the
    repository's legacy top-level ``git.md`` file. ``fetcher`` exists to keep
    the network behavior easy to unit test.
    """

    if fetcher is None:
        def fetcher(url: str) -> str:
            request = Request(url, headers={"User-Agent": "cem-obsidian-importer"})
            with urlopen(request, timeout=20) as response:
                return response.read().decode("utf-8")

    source = fetcher(GIT_GUIDE_RAW_URL)
    if not isinstance(source, str) or not source.strip():
        raise RuntimeError("La page Git départementale téléchargée est vide.")

    destination.mkdir(parents=True, exist_ok=True)
    state = iconize_state(find_vault_root(destination))
    icon_field = state.frontmatter_field if state.frontmatter_enabled else None
    target = destination / GIT_GUIDE_FILENAME
    target.write_text(
        build_department_git_note(source, icon_field=icon_field), encoding="utf-8"
    )

    # Migration from 0.2.8-0.2.11: the shared Git page used to live alone
    # under Ressources/. Remove only that generated file, never arbitrary user content.
    legacy_dir = destination / "Ressources"
    legacy_note = legacy_dir / GIT_GUIDE_FILENAME
    if legacy_note.is_file():
        legacy_note.unlink()
    if legacy_dir.is_dir():
        try:
            legacy_dir.rmdir()
        except OSError:
            pass

    if not quiet:
        print(f"✓ Guide Git départemental synchronisé : {target}")
    return target


def sync_css(destination: Path, *, quiet: bool = False) -> Path | None:
    """Install the bundled snippet and enable it without disturbing user appearance settings."""
    vault = find_vault_root(destination)
    if vault is None:
        if not quiet:
            print(
                "⚠ Aucun vault Obsidian détecté au-dessus de la destination.\n"
                "  Le CSS ne sera pas synchronisé, mais l'import peut continuer."
            )
        return None

    obsidian = vault / ".obsidian"
    snippets = obsidian / "snippets"
    snippets.mkdir(parents=True, exist_ok=True)
    target = snippets / CSS_SOURCE.name
    shutil.copy2(CSS_SOURCE, target)

    # Obsidian stores enabled snippets without the .css suffix. Preserve every
    # unrelated appearance setting and only append ours if needed.
    appearance_path = obsidian / "appearance.json"
    try:
        appearance = json.loads(appearance_path.read_text(encoding="utf-8")) if appearance_path.is_file() else {}
    except json.JSONDecodeError:
        appearance = {}
    if not isinstance(appearance, dict):
        appearance = {}
    enabled = appearance.get("enabledCssSnippets", [])
    if not isinstance(enabled, list):
        enabled = []
    snippet_name = CSS_SOURCE.stem
    if snippet_name not in enabled:
        enabled.append(snippet_name)
        appearance["enabledCssSnippets"] = enabled
        appearance_path.write_text(json.dumps(appearance, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    if not quiet:
        print(f"✓ CSS synchronisé et activé : {target}")
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
    """Show a dependency-free checkbox-like multi-select menu grouped by session."""

    print("\nCours disponibles\n")
    current_group: str | None = None
    for index, course in enumerate(COURSES, start=1):
        if course.session_folder != current_group:
            current_group = course.session_folder
            print(f"{current_group}")
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
            print(f"  [x] {course.session_folder} / {course.folder}")
        answer = input("\nLancer l'import ? [O/n] ").strip().lower()
        if answer in {"", "o", "oui", "y", "yes"}:
            return selected
        print("\nD'accord, choisis à nouveau.")


def read_conversion_report(path: Path) -> dict[str, Any]:
    """Read one engine report produced in the temporary run workspace."""

    if not path.is_file():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}
    return data if isinstance(data, dict) else {}


def summarize_conversion_report(data: dict[str, Any]) -> dict[str, int]:
    issues = data.get("issues", {}) if isinstance(data, dict) else {}
    return {
        "issue_count": int(issues.get("count", 0) or 0),
        "unknown_components": int(issues.get("unknown_component_occurrences", 0) or 0),
        "unresolved_links": int(issues.get("unresolved_local_links", 0) or 0),
        "warnings": int(issues.get("warnings", 0) or 0),
    }


def run_course_import(course: Course, destination: Path, temporary_report_root: Path) -> ImportResult:
    """Import one course and keep its raw diagnostics only for this run.

    Per-course reports are intentionally written to a temporary workspace. The
    launcher later merges them into a single detailed report under ``reports/``.
    """

    output_parent = destination / course.session_folder / course.folder
    report_dir = temporary_report_root / course.code
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
        "--report-dir",
        str(report_dir),
        "--report-source",
        course.repo,
    ]

    print(f"\n{'─' * 72}")
    print(f"Import : {course.session_folder} / {course.folder}")
    print(f"Repo   : {course.repo}")
    print(f"{'─' * 72}")

    completed = subprocess.run(cmd, text=True)
    report_path = report_dir / "report.json"
    report_data = read_conversion_report(report_path)

    if completed.returncode != 0:
        return ImportResult(
            course=course,
            succeeded=False,
            report_data=report_data or None,
            error=f"Le convertisseur a quitté avec le code {completed.returncode}.",
        )

    summary = summarize_conversion_report(report_data)
    return ImportResult(
        course=course,
        succeeded=True,
        report_data=report_data or None,
        **summary,
    )


def _course_payload(result: ImportResult) -> dict[str, Any]:
    report_data = result.report_data or {}
    return {
        "code": result.course.code,
        "name": result.course.folder,
        "session": result.course.session,
        "repo": result.course.repo,
        "succeeded": result.succeeded,
        "issues": result.issue_count,
        "unknown_components": result.unknown_components,
        "unresolved_links": result.unresolved_links,
        "warnings": result.warnings,
        "stats": report_data.get("stats", {}),
        "details": report_data.get("details", {}),
        "error": result.error or None,
    }


def reset_reports_root() -> None:
    """Start each launcher run with one clean, flat reports directory."""

    if REPORTS_ROOT.exists():
        shutil.rmtree(REPORTS_ROOT)
    REPORTS_ROOT.mkdir(parents=True, exist_ok=True)


def write_aggregate_report(results: list[ImportResult], destination: Path) -> tuple[Path, Path]:
    """Write one human report plus one machine-readable companion.

    There are deliberately no per-course report folders. Course sections are
    separated inside the Markdown report so diagnostics stay easy to browse.
    """

    reset_reports_root()
    hard_failures = [result for result in results if not result.succeeded]
    issue_results = [result for result in results if result.succeeded and result.issue_count > 0]
    clean_results = [result for result in results if result.succeeded and result.issue_count == 0]
    total_issues = sum(result.issue_count for result in issue_results)

    payload = {
        "destination": str(destination),
        "courses_requested": len(results),
        "imports_succeeded": len(results) - len(hard_failures),
        "import_errors": len(hard_failures),
        "conversion_issues": total_issues,
        "courses": [_course_payload(result) for result in results],
    }
    json_path = REPORTS_ROOT / "summary.json"
    json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    lines = [
        "# Rapport détaillé — CEM → Obsidian",
        "",
        "Ce fichier regroupe le résultat complet du dernier lancement. "
        "Aucun rapport de diagnostic n'est écrit dans le vault Obsidian.",
        "",
        "## Vue d'ensemble",
        "",
        f"- Destination : `{destination}`",
        f"- Cours demandés : **{len(results)}**",
        f"- Imports réussis : **{len(results) - len(hard_failures)}**",
        f"- Erreurs d'import : **{len(hard_failures)}**",
        f"- Problèmes de conversion : **{total_issues}**",
        "",
        "| État | Cours | Problèmes | MDX inconnus | Liens | Avertissements |",
        "|---|---|---:|---:|---:|---:|",
    ]

    for result in results:
        status = "✅" if result.succeeded and result.issue_count == 0 else ("⚠️" if result.succeeded else "❌")
        display_name = result.course.folder.removeprefix(result.course.code + " - ")
        lines.append(
            f"| {status} | {result.course.code} — {display_name} "
            f"| {result.issue_count if result.succeeded else '—'} "
            f"| {result.unknown_components if result.succeeded else '—'} "
            f"| {result.unresolved_links if result.succeeded else '—'} "
            f"| {result.warnings if result.succeeded else '—'} |"
        )

    if hard_failures:
        lines += ["", "## ❌ Erreurs d'import", ""]
        for result in hard_failures:
            lines += [
                f"### {result.course.code} — {result.course.folder}",
                "",
                f"- Repo : `{result.course.repo}`",
                f"- Erreur : {result.error or 'Erreur non détaillée.'}",
                "",
            ]

    if issue_results:
        lines += ["", "## ⚠️ Détails des problèmes de conversion", ""]
        for result in issue_results:
            data = result.report_data or {}
            details = data.get("details", {}) if isinstance(data, dict) else {}
            unknown = details.get("unknown_components", {})
            unresolved = details.get("unresolved_local_links", [])
            warnings = details.get("warnings", [])

            lines += [
                f"### {result.course.code} — {result.course.folder}",
                "",
                f"**{result.issue_count} problème(s)** "
                f"({result.unknown_components} MDX inconnu(s), "
                f"{result.unresolved_links} lien(s), {result.warnings} avertissement(s))",
                "",
            ]

            if unknown:
                lines += ["#### Composants MDX inconnus", ""]
                for name, count in sorted(unknown.items(), key=lambda item: (-int(item[1]), item[0])):
                    lines.append(f"- `{name}` : {count} occurrence(s)")
                lines.append("")

            if unresolved:
                lines += ["#### Liens locaux non résolus", ""]
                for item in unresolved:
                    if isinstance(item, dict):
                        note = item.get("note", "?")
                        target = item.get("target", "?")
                    elif isinstance(item, (list, tuple)) and len(item) >= 2:
                        note, target = item[0], item[1]
                    else:
                        note, target = "?", str(item)
                    lines.append(f"- `{note}` → `{target}`")
                lines.append("")

            if warnings:
                lines += ["#### Avertissements", ""]
                for item in warnings:
                    if isinstance(item, dict):
                        note = item.get("note", "?")
                        message = item.get("message", "?")
                    elif isinstance(item, (list, tuple)) and len(item) >= 2:
                        note, message = item[0], item[1]
                    else:
                        note, message = "?", str(item)
                    lines.append(f"- `{note}` : {message}")
                lines.append("")

            if not unknown and not unresolved and not warnings:
                lines += [
                    "> Les compteurs signalent un problème, mais aucun détail structuré "
                    "n'était disponible dans le rapport du moteur.",
                    "",
                ]

    if clean_results:
        lines += ["", "## ✅ Cours sans problème détecté", ""]
        for result in clean_results:
            lines.append(f"- **{result.course.code}** — {result.course.folder}")
        lines.append("")

    lines += [
        "",
        "## Statistiques de conversion",
        "",
        "| Cours | Notes | Assets | Snippets | Vidéos | Callouts | Layouts | Playgrounds |",
        "|---|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for result in results:
        stats = (result.report_data or {}).get("stats", {})
        lines.append(
            f"| {result.course.code} "
            f"| {stats.get('notes', '—')} "
            f"| {stats.get('assets', '—')} "
            f"| {stats.get('snippets_inlined', '—')} "
            f"| {stats.get('videos', '—')} "
            f"| {stats.get('admonitions', '—')} "
            f"| {stats.get('layout_rows', '—')} "
            f"| {stats.get('react_playgrounds', '—')} |"
        )

    lines += [
        "",
        "---",
        "",
        "`summary.json` contient les mêmes données sous forme structurée pour le débogage et l'automatisation.",
        "",
    ]

    md_path = REPORTS_ROOT / "detail-summary.md"
    md_path.write_text("\n".join(lines), encoding="utf-8")
    return md_path, json_path


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
    summary_md, _ = write_aggregate_report(results, destination)
    print(f"Rapport détaillé      : {summary_md}")

    if not hard_failures and not issue_results:
        print("\n✓ Aucun problème détecté dans les cours importés.")
        print(f"📄 Rapport : {summary_md}")
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

    print(f"\n📄 Rapport détaillé : {summary_md}")

    # A conversion warning does not make the launcher itself fail. A hard import
    # failure does, which is useful for CI or scripted runs later on.
    return 1 if hard_failures else 0


def cmd_run(args: argparse.Namespace) -> int:
    config = load_config()
    destination = prompt_destination(config)
    vault = find_vault_root(destination)
    if vault:
        print(f"✓ Vault détecté : {vault}")
        state = iconize_state(vault)
        if state.enabled:
            # `run` owns the normal setup path: repair/install the CEM folder
            # rules before conversion. Existing user-selected icons are preserved.
            try:
                changed, total, backup = sync_iconize_rules(destination)
                if changed:
                    print(f"✓ Règles de dossiers Iconize synchronisées : {total}/{total}")
                    if backup:
                        print(f"  Backup Iconize : {backup}")
                    print("  ℹ Si Obsidian était ouvert, recharge-le une fois pour rafraîchir les règles.")
                else:
                    print(f"✓ Règles de dossiers Iconize : {total}/{total}")
            except RuntimeError as exc:
                print(f"⚠ Configuration Iconize non synchronisée : {exc}")

            # Re-read after synchronization so the following status reflects the
            # actual file on disk. Frontmatter remains opt-in because disabling
            # it is an explicit user preference.
            state = iconize_state(vault)
            if state.frontmatter_enabled:
                print(f"✓ Iconize actif : icônes de notes via `{state.frontmatter_field}`")
            else:
                print(
                    "⚠ Iconize est actif, mais `Use icon in frontmatter` est désactivé.\n"
                    "  Les emojis resteront dans les titres pour éviter de perdre l'information visuelle."
                )
    else:
        print("⚠ Aucun dossier .obsidian détecté au-dessus de la destination.")
    sync_css(destination)
    try:
        sync_department_git_guide(destination)
    except Exception as exc:
        print(
            "⚠ Impossible de synchroniser la page Git départementale.\n"
            f"  {exc}\n"
            "  L'import des cours peut tout de même continuer."
        )

    selected = prompt_courses()
    with tempfile.TemporaryDirectory(prefix="cem-obsidian-reports-") as td:
        temporary_report_root = Path(td)
        results = [
            run_course_import(course, destination, temporary_report_root)
            for course in selected
        ]
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


def cmd_iconize(args: argparse.Namespace) -> int:
    config = load_config()
    destination_raw = args.destination or str(config.get("destination") or "").strip()
    if not destination_raw:
        raise RuntimeError("Aucune destination connue. Lance d'abord `python3 cem_importer.py run`.")
    destination = normalize_destination(destination_raw)
    changed, total, backup = sync_iconize_rules(destination, dry_run=args.dry_run)
    if args.dry_run:
        print(f"Iconize : {changed} règle(s) à ajouter/corriger sur {total}.")
        return 0
    if changed == 0:
        print(f"✓ Iconize : les {total} règles CEM sont déjà correctement configurées.")
    else:
        print(f"✓ Iconize : {changed} règle(s) ajoutée(s)/corrigée(s) sur {total}.")
        if backup:
            print(f"✓ Sauvegarde : {backup}")
        print("Relance Obsidian (ou désactive/réactive Iconize) pour recharger data.json.")
    return 0


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
            state = iconize_state(vault)
            print(
                "Iconize : "
                + (
                    f"activé, frontmatter {'activé' if state.frontmatter_enabled else 'désactivé'}"
                    if state.enabled
                    else ("installé mais désactivé" if state.installed else "non détecté (optionnel)")
                )
            )
            if state.enabled:
                valid, total = iconize_rule_status(vault)
                print(f"Règles Iconize CEM : {valid}/{total} valides")
            snippet = vault / ".obsidian" / "snippets" / CSS_SOURCE.name
            print(f"CSS CEM : {'installé' if snippet.is_file() else 'non installé'}")
            git_guide = Path(destination_raw).expanduser() / GIT_GUIDE_FILENAME
            print(f"Guide Git départemental : {'installé' if git_guide.is_file() else 'non installé'}")
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

    p = sub.add_parser("iconize", help="Installer/réparer les règles de dossiers Iconize recommandées.")
    p.add_argument("--destination", help="Utiliser temporairement une autre destination.")
    p.add_argument("--dry-run", action="store_true", help="Afficher les changements sans modifier data.json.")
    p.set_defaults(func=cmd_iconize)

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

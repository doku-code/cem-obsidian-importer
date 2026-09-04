#!/usr/bin/env python3
"""CEM Docusaurus -> Obsidian importer.

Conservative, deterministic converter aimed at the course repositories published by
`departement-info-cem`. It accepts either a local repository path or a Git URL,
finds the Docusaurus docs tree, converts Markdown/MDX into Obsidian-friendly
Markdown, and copies referenced local assets under `_assets`.

Python 3.11+, standard library only.

The conversion pipeline is explicit and interactive previews are represented independently
from the Obsidian renderer so rendering plugins can be replaced without rewriting the parser.
"""

from __future__ import annotations

import argparse
import hashlib
import html
import json
import os
import posixpath
import re
import shutil
import subprocess
import sys
import tempfile
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import unquote, urlparse
from urllib.request import Request, urlopen


VERSION = (Path(__file__).resolve().parent / "VERSION").read_text(encoding="utf-8").strip()

MARKDOWN_EXTS = {".md", ".mdx"}
CODE_LANG = {
    ".js": "javascript",
    ".jsx": "jsx",
    ".ts": "typescript",
    ".tsx": "tsx",
    ".kt": "kotlin",
    ".kts": "kotlin",
    ".cs": "csharp",
    ".java": "java",
    ".py": "python",
    ".cpp": "cpp",
    ".cc": "cpp",
    ".cxx": "cpp",
    ".c": "c",
    ".h": "cpp",
    ".hpp": "cpp",
    ".css": "css",
    ".html": "html",
    ".sql": "sql",
    ".json": "json",
    ".xml": "xml",
    ".sh": "bash",
    ".ps1": "powershell",
}

RAW_IMPORT_RE = re.compile(
    r"^\s*import\s+(?P<var>[A-Za-z_$][\w$]*)\s+from\s+['\"]!!raw-loader!(?P<path>[^'\"]+)['\"]\s*;?\s*$",
    re.MULTILINE,
)
DEFAULT_LOCAL_IMPORT_RE = re.compile(
    r"^\s*import\s+(?P<var>[A-Za-z_$][\w$]*)\s+from\s+['\"](?P<path>\.{1,2}/[^'\"]+)['\"]\s*;?\s*$",
    re.MULTILINE,
)
MDX_COMPONENT_IMPORT_RE = re.compile(
    r"^\s*import\s+(?P<var>[A-Za-z_$][\w$]*)\s+from\s+['\"](?P<path>(?:@site/|\.{1,2}/)[^'\"]+\.mdx?)['\"]\s*;?\s*$",
    re.MULTILINE,
)


@dataclass
class Report:
    notes: int = 0
    assets: int = 0
    snippets_inlined: int = 0
    dataflows: int = 0
    videos: int = 0
    admonitions: int = 0
    tabs: int = 0
    layout_rows: int = 0
    react_playgrounds: int = 0
    unknown_components: Counter[str] = field(default_factory=Counter)
    unresolved_local_links: list[tuple[str, str]] = field(default_factory=list)
    warnings: list[tuple[str, str]] = field(default_factory=list)

    def warn(self, note: Path | str, message: str) -> None:
        self.warnings.append((str(note), message))


@dataclass
class NoteContext:
    source_note: Path
    rel_note: Path
    output_note: Path
    asset_dir: Path
    raw_imports: dict[str, Path]
    local_imports: dict[str, Path]
    mdx_imports: dict[str, Path]


@dataclass
class SidebarEntry:
    section: str
    label: str
    doc_id: str
    source_note: Path | None = None


@dataclass(frozen=True)
class TransformStep:
    """One deterministic step in the MDX -> Obsidian pipeline.

    `needs_context` documents whether the handler needs file/import state from the
    current note. Keeping the order in one registry makes the transformation graph
    inspectable and prevents the convert_note method from becoming another wall of
    ad-hoc calls.
    """

    name: str
    method: str
    needs_context: bool = False


@dataclass
class InteractiveProject:
    """Plugin-neutral representation of an interactive code example.

    ReactPreview projects render to Code Playground when available and to
    Codeblock Customizer tabs otherwise. The parser does not need to know which
    Obsidian plugin ultimately renders the project.
    """

    template: str
    entry_file: str
    files: dict[str, str]
    source_files: dict[str, Path]
    hidden_files: set[str] = field(default_factory=set)
    preview_height: int | None = None


class CEMImporter:
    def __init__(
        self,
        source: Path,
        output_parent: Path,
        course_name: str | None = None,
        force: bool = False,
        copy_all_static: bool = False,
        report_dir: Path | None = None,
        report_source: str | None = None,
    ) -> None:
        self.source = source.resolve()
        self.docs_root = self.discover_docs_root(self.source)
        self.course_name = course_name or self.source.name.removesuffix(".git")
        self.output_root = (output_parent / self.course_name).resolve()
        self.report_dir = (report_dir or (Path.cwd() / "reports" / self.course_name)).expanduser().resolve()
        self.report_source = report_source or str(self.source)
        self.force = force
        self.copy_all_static = copy_all_static
        self.vault_root = self.discover_vault_root(output_parent.resolve())
        self.code_playground_available = bool(
            self.vault_root
            and (self.vault_root / ".obsidian" / "plugins" / "code-playground" / "manifest.json").is_file()
        )
        self._react_preview_counter: Counter[str] = Counter()
        self.report = Report()
        self._asset_sources: dict[Path, Path] = {}
        self.content_notes = self.discover_content_notes()
        self.route_index = self.build_route_index()
        self.sidebar_entries = self.parse_sidebars()
        self.sidebar_labels = self.build_sidebar_labels()
        self.output_map = self.build_output_map()
        self.navigation_sequence = self.build_navigation_sequence()


    @staticmethod
    def discover_vault_root(start: Path) -> Path | None:
        """Return the nearest ancestor that looks like an Obsidian vault.

        Code Playground stores its per-block sidecars in a vault-relative `_playgrounds`
        directory.  When the converter is writing directly into a vault, detecting the
        `.obsidian` directory lets us generate those sidecars automatically.
        """
        current = start.resolve()
        for candidate in (current, *current.parents):
            if (candidate / ".obsidian").is_dir():
                return candidate
        return None

    def discover_content_notes(self) -> list[Path]:
        """Return actual course pages, excluding helper/source folders such as `_03-rencontre2.1`.

        CEM repos keep quiz prompts, code fragments and other supporting Markdown inside underscore
        directories next to the real course page. Docusaurus does not expose those as sidebar pages,
        so they should become assets, not notes in Obsidian's file tree.
        """
        notes: list[Path] = []
        for p in self.docs_root.rglob("*"):
            if not p.is_file() or p.suffix.lower() not in MARKDOWN_EXTS:
                continue
            rel = p.relative_to(self.docs_root)
            # CEM uses leading-underscore folders *and files* for helper/draft content that
            # Docusaurus does not expose as normal student-facing pages. Keep those available
            # as importable source material, but do not create visible Obsidian notes for them.
            if any(part.startswith("_") for part in rel.parts):
                continue
            notes.append(p.resolve())
        return sorted(notes)

    @staticmethod
    def _quoted_js_value(body: str, key: str) -> str | None:
        m = re.search(rf"\b{re.escape(key)}\s*:\s*([\"'])(.*?)\1", body, re.DOTALL)
        return m.group(2) if m else None

    def parse_sidebars(self) -> list[SidebarEntry]:
        """Read the simple Docusaurus sidebars.js structure used by the CEM repos.

        This is intentionally not a JavaScript interpreter. It extracts `doc` labels/ids and expands
        `autogenerated` directories. If a future repo uses a very different sidebar implementation,
        the importer falls back to document titles and filesystem order.
        """
        candidates = [self.source / "web" / "sidebars.js", self.source / "sidebars.js"]
        sidebar_file = next((p for p in candidates if p.is_file()), None)
        if sidebar_file is None:
            return []
        raw = sidebar_file.read_text(encoding="utf-8")
        lines = raw.splitlines()
        sections: list[tuple[str, str]] = []
        i = 0
        while i < len(lines):
            m = re.match(r"^\s{2}([A-Za-z0-9_-]+)\s*:\s*\[", lines[i])
            if not m:
                i += 1
                continue
            key = m.group(1)
            block = [lines[i]]
            depth = lines[i].count("[") - lines[i].count("]")
            i += 1
            while i < len(lines) and depth > 0:
                block.append(lines[i])
                depth += lines[i].count("[") - lines[i].count("]")
                i += 1
            sections.append((key, "\n".join(block)))

        entries: list[SidebarEntry] = []
        for section, block in sections:
            # Split on outer item markers. `type:` also appears nowhere in the nested CEM customProps.
            item_starts = list(re.finditer(r"\btype\s*:\s*([\"'])(doc|autogenerated)\1", block))
            for idx, start in enumerate(item_starts):
                end = item_starts[idx + 1].start() if idx + 1 < len(item_starts) else len(block)
                item = block[start.start():end]
                typ = start.group(2)
                if typ == "doc":
                    label = self._quoted_js_value(item, "label")
                    doc_id = self._quoted_js_value(item, "id")
                    if label and doc_id:
                        source_note = self.route_index.get(doc_id.strip("/"))
                        entries.append(SidebarEntry(section, label, doc_id.strip("/"), source_note))
                else:
                    dir_name = self._quoted_js_value(item, "dirName")
                    if not dir_name:
                        continue
                    prefix = Path(dir_name)
                    auto_notes = [
                        n for n in self.content_notes
                        if n.relative_to(self.docs_root).parts[:len(prefix.parts)] == prefix.parts
                    ]
                    for note in sorted(auto_notes):
                        label = self.extract_document_title(note, prefer_sidebar=False)
                        entries.append(SidebarEntry(section, label, self.route_for_note(note), note))
        return entries

    def build_sidebar_labels(self) -> dict[Path, list[str]]:
        result: dict[Path, list[str]] = {}
        for entry in self.sidebar_entries:
            if entry.source_note is not None:
                result.setdefault(entry.source_note.resolve(), []).append(entry.label)
        return result

    def build_navigation_sequence(self) -> list[Path]:
        seen: set[Path] = set()
        sequence: list[Path] = []
        for entry in self.sidebar_entries:
            if entry.source_note is None:
                continue
            note = entry.source_note.resolve()
            if note in self.output_map and note not in seen:
                seen.add(note)
                sequence.append(note)
        return sequence

    @staticmethod
    def sanitize_filename(value: str) -> str:
        value = re.sub(r"[\\/:*?\"<>|]", " - ", value)
        value = re.sub(r"\s+", " ", value).strip().rstrip(".")
        return value or "Note"

    @staticmethod
    def humanize_segment(segment: str) -> str:
        prefix_m = re.match(r"^(\d+)[-_](.+)$", segment)
        prefix = prefix_m.group(1) if prefix_m else None
        base = prefix_m.group(2) if prefix_m else segment
        key = base.lower().replace("_", "-")
        common = {
            "notes": "Notes de cours",
            "cours": "Cours",
            "tp": "TP",
            "recettes": "Recettes",
            "labos": "Laboratoires",
            "labo": "Laboratoires",
            "autres": "Autres",
            "angular": "Angular",
        }
        label = common.get(key)
        if label is None:
            label = re.sub(r"[-_]+", " ", base).strip()
            label = label[:1].upper() + label[1:] if label else base
        return f"{prefix} - {label}" if prefix else label

    @staticmethod
    def read_frontmatter_title(note: Path) -> str | None:
        try:
            text = note.read_text(encoding="utf-8")
        except Exception:
            return None
        if not text.startswith("---"):
            return None
        end = text.find("\n---", 3)
        if end < 0:
            return None
        fm = text[3:end]
        m = re.search(r"^\s*title\s*:\s*(.*?)\s*$", fm, re.MULTILINE)
        if not m:
            return None
        value = m.group(1).strip().strip("'\"")
        return value or None

    @staticmethod
    def first_h1(note: Path) -> str | None:
        try:
            text = note.read_text(encoding="utf-8")
        except Exception:
            return None
        # Ignore fenced code while looking for the document heading.
        chunks = re.split(r"```.*?```", text, flags=re.DOTALL)
        for chunk in chunks:
            m = re.search(r"^#\s+(.+?)\s*$", chunk, re.MULTILINE)
            if m:
                return re.sub(r"<[^>]+>", "", m.group(1)).strip()
        return None

    def extract_document_title(self, note: Path, prefer_sidebar: bool = True) -> str:
        if prefer_sidebar:
            labels = self.sidebar_labels.get(note.resolve(), []) if hasattr(self, "sidebar_labels") else []
            if labels:
                return labels[0]
        title = self.read_frontmatter_title(note) or self.first_h1(note)
        if title:
            return title
        stem = self.strip_number_prefix(note.stem)
        return re.sub(r"[-_]+", " ", stem).strip().capitalize() or note.stem

    @staticmethod
    def source_order_prefix(stem: str) -> str | None:
        m = re.match(r"^(\d+(?:\.\d+)?)[-_]", stem)
        return m.group(1) if m else None

    def friendly_note_name(self, note: Path) -> str:
        title = self.extract_document_title(note)
        order = self.source_order_prefix(note.stem)
        has_sidebar_label = bool(self.sidebar_labels.get(note.resolve(), []))
        if order and not has_sidebar_label:
            normalized = order
            if order.isdigit():
                normalized = str(int(order))
            starts_with_order = bool(re.match(rf"^0*{re.escape(normalized)}(?:[.\s-])", title))
            if not starts_with_order:
                # In autogenerated sidebars, source filenames often carry the only explicit sort key
                # (`04-rencontre4.md` with H1 `Rencontre 4`). Keep it in the visible filename.
                title = f"{order} - {title}"
        return self.sanitize_filename(title) + ".md"

    def build_output_map(self) -> dict[Path, Path]:
        mapping: dict[Path, Path] = {}
        used: dict[Path, Path] = {}
        for note in self.content_notes:
            rel = note.relative_to(self.docs_root)
            parent_parts = [self.humanize_segment(p) for p in rel.parts[:-1]]
            candidate = Path(*parent_parts, self.friendly_note_name(note)) if parent_parts else Path(self.friendly_note_name(note))
            if candidate in used and used[candidate] != note:
                fallback = self.sanitize_filename(f"{Path(candidate).stem} [{note.stem}]") + ".md"
                candidate = candidate.with_name(fallback)
            used[candidate] = note
            mapping[note.resolve()] = candidate
        return mapping

    def output_rel_for(self, note: Path) -> Path:
        return self.output_map[note.resolve()]

    @staticmethod
    def discover_docs_root(source: Path) -> Path:
        preferred = [source / "web" / "docs", source / "docs", source / "website" / "docs"]
        for candidate in preferred:
            if candidate.is_dir():
                return candidate.resolve()

        ignored = {"node_modules", ".git", "build", "dist", ".docusaurus", ".next"}
        best: tuple[int, Path] | None = None
        for root, dirs, files in os.walk(source):
            dirs[:] = [d for d in dirs if d not in ignored]
            count = sum(Path(f).suffix.lower() in MARKDOWN_EXTS for f in files)
            if count:
                p = Path(root)
                score = count * 10 + (5 if p.name.lower() == "docs" else 0)
                if best is None or score > best[0]:
                    best = (score, p)
        if best:
            return best[1].resolve()
        raise FileNotFoundError("Aucun dossier de documentation Markdown/MDX trouvé dans le repo.")

    @staticmethod
    def strip_number_prefix(segment: str) -> str:
        """Replicate Docusaurus' common numeric ordering prefix for CEM docs.

        `01-notes` -> `notes`, `03-tp` -> `tp`, while `1.1-accueil` stays intact.
        """
        return re.sub(r"^\d+[-_]", "", segment)

    def route_for_note(self, note: Path) -> str:
        rel = note.relative_to(self.docs_root).with_suffix("")
        parts = [self.strip_number_prefix(p) for p in rel.parts]
        return "/".join(parts).strip("/")

    @staticmethod
    def frontmatter_slug(note: Path) -> str | None:
        try:
            text = note.read_text(encoding="utf-8")
        except Exception:
            return None
        if not text.startswith("---"):
            return None
        end = text.find("\n---", 3)
        if end < 0:
            return None
        fm = text[3:end]
        m = re.search(r"^\s*slug\s*:\s*['\"]?([^'\"\n]+)['\"]?\s*$", fm, re.MULTILINE)
        return m.group(1).strip().strip("/") if m else None

    def build_route_index(self) -> dict[str, Path]:
        index: dict[str, Path] = {}
        for note in self.content_notes:
            rel_no_ext = note.relative_to(self.docs_root).with_suffix("")
            aliases = {
                str(rel_no_ext).replace(os.sep, "/").strip("/"),
                self.route_for_note(note),
            }
            slug = self.frontmatter_slug(note)
            if slug is not None:
                aliases.add(slug)
            # A unique basename fallback resolves a few hand-written Docusaurus links.
            aliases.add(rel_no_ext.name)
            aliases.add(self.strip_number_prefix(rel_no_ext.name))
            for alias in aliases:
                if alias and alias not in index:
                    index[alias] = note.resolve()
        return index

    TRANSFORM_PIPELINE: tuple[TransformStep, ...] = (
        TransformStep("imported-mdx-components", "convert_imported_mdx_components", True),
        TransformStep("pycode-components", "convert_pycode_components"),
        TransformStep("docusaurus-image", "convert_docusaurus_image", True),
        TransformStep("nonvoyant", "convert_nonvoyant"),
        TransformStep("javascript-console", "convert_javascript_console", True),
        TransformStep("react-preview", "convert_react_preview", True),
        TransformStep("dataflow", "convert_dataflow", True),
        TransformStep("ghcode", "convert_ghcode", True),
        TransformStep("quiz", "convert_quiz", True),
        TransformStep("docs-viewer", "convert_docs_viewer", True),
        TransformStep("console-window", "convert_console_window"),
        TransformStep("github-download", "convert_github_download", True),
        TransformStep("slides", "convert_slide_components"),
        TransformStep("examples", "convert_example_components", True),
        TransformStep("learning-cues", "convert_learning_cues"),
        TransformStep("project-visuals", "convert_project_visuals"),
        TransformStep("plan-de-cours", "convert_plan_de_cours_menu"),
        TransformStep("feedback", "convert_feedback"),
        TransformStep("video", "convert_video", True),
        TransformStep("tabs", "convert_tabs"),
        TransformStep("highlight", "convert_highlight"),
        TransformStep("admonitions", "convert_admonitions"),
        TransformStep("layout", "convert_layout_rows"),
        TransformStep("layout-cleanup", "strip_layout_wrappers"),
    )

    def apply_transform_pipeline(self, text: str, ctx: NoteContext) -> str:
        """Apply the ordered component conversion pipeline.

        Handlers remain small deterministic functions, but their ordering now lives in
        one declarative registry. This makes adding support for new CEM components far
        less likely to accidentally reorder unrelated transforms.
        """
        for step in self.TRANSFORM_PIPELINE:
            handler = getattr(self, step.method)
            text = handler(text, ctx) if step.needs_context else handler(text)
        return text

    def run(self) -> Path:
        if self.output_root.exists():
            if not self.force:
                raise FileExistsError(
                    f"La destination existe déjà: {self.output_root}\n"
                    "Relancez avec --force pour la remplacer."
                )
            shutil.rmtree(self.output_root)
        self.output_root.mkdir(parents=True, exist_ok=True)

        for note in self.content_notes:
            self.convert_note(note)

        if self.copy_all_static:
            self.copy_static_trees()

        self.write_navigation()
        self.write_report()
        return self.output_root

    def convert_note(self, source_note: Path) -> None:
        rel = source_note.relative_to(self.docs_root)
        output_rel = self.output_rel_for(source_note)
        output_note = self.output_root / output_rel
        output_note.parent.mkdir(parents=True, exist_ok=True)
        asset_dir = self.output_root / "_assets" / output_rel.with_suffix("")

        source_text = source_note.read_text(encoding="utf-8")
        raw_imports = {
            m.group("var"): self.resolve_import(source_note, m.group("path"))
            for m in RAW_IMPORT_RE.finditer(source_text)
        }
        local_imports = {
            m.group("var"): self.resolve_import(source_note, m.group("path"))
            for m in DEFAULT_LOCAL_IMPORT_RE.finditer(source_text)
        }
        mdx_imports = {
            m.group("var"): self.resolve_import(source_note, m.group("path"))
            for m in MDX_COMPONENT_IMPORT_RE.finditer(source_text)
        }
        ctx = NoteContext(source_note, rel, output_note, asset_dir, raw_imports, local_imports, mdx_imports)

        text = source_text
        text = self.remove_import_lines(text)
        text = self.strip_zero_width_markers(text)
        text = self.sanitize_code_fences(text)
        text = self.apply_transform_pipeline(text, ctx)
        # Detect leftover MDX *before* generating Obsidian links. Markdown destinations are
        # deliberately wrapped in angle brackets when they contain spaces, e.g.
        # `[Voir](<Librairie Standard.md>)`; scanning after link rewriting would mistake
        # `<Librairie` for a React/MDX component.
        text = self.handle_unknown_components(text, ctx)
        text = self.rewrite_markdown_links(text, ctx)
        text = self.rewrite_html_sources(text, ctx)
        text = self.add_navigation_footer(text, ctx)
        text = self.cleanup_whitespace(text)
        text = self.ensure_course_cssclass(text)

        output_note.write_text(text, encoding="utf-8")
        self.report.notes += 1

    def resolve_import(self, note: Path, raw_path: str) -> Path:
        raw_path = raw_path.strip()
        if raw_path.startswith("@site/"):
            candidate = (self.source / "web" / raw_path[len("@site/"):]).resolve()
            if not candidate.exists():
                candidate = (self.source / raw_path[len("@site/"):]).resolve()
        else:
            candidate = (note.parent / raw_path).resolve()
        if candidate.exists():
            return candidate
        if not candidate.suffix:
            for ext in (".ts", ".tsx", ".js", ".jsx", ".json", ".md", ".mdx"):
                c = Path(str(candidate) + ext)
                if c.exists():
                    return c
        return candidate

    @staticmethod
    def remove_import_lines(text: str) -> str:
        # Course MDX imports are top-level statements. Preserve imports inside fenced code.
        chunks = re.split(r"(```.*?```)", text, flags=re.DOTALL)
        for i in range(0, len(chunks), 2):
            chunks[i] = re.sub(r"^\s*import\s+[^\n;]+;?\s*$", "", chunks[i], flags=re.MULTILINE)
        return "".join(chunks)

    @staticmethod
    def strip_zero_width_markers(text: str) -> str:
        """Remove invisible spacing markers used by the Docusaurus source for JSX layout.

        Some CEM notes prefix inline React components with ``&#8203;`` (U+200B ZERO WIDTH
        SPACE) to influence MDX parsing/layout. Obsidian does not need this hack and can render
        the HTML entity literally, so strip it from prose while preserving fenced code verbatim.
        """
        chunks = re.split(r"(```.*?```)", text, flags=re.DOTALL)
        for i in range(0, len(chunks), 2):
            chunks[i] = re.sub(
                r"(?:&#8203;|&#x200[bB];|&ZeroWidthSpace;|\u200b)",
                "",
                chunks[i],
                flags=re.IGNORECASE,
            )
        return "".join(chunks)

    @staticmethod
    def sanitize_code_fences(text: str) -> str:
        """Normalize Docusaurus fence metadata and dedent fences nested in JSX/Tabs.

        MDX authors commonly indent fenced blocks inside `<TabItem>` by 4+ spaces. In Obsidian
        that indentation turns the *backticks themselves* into an indented code block, which is
        exactly the literal ```js showLineNumbers rendering seen in the first visual test.
        """
        out: list[str] = []
        in_fence = False
        base_indent = ""
        fence_len = 3
        for line in text.splitlines():
            if not in_fence:
                m = re.match(r"^(?P<indent>[ \t]*)(?P<fence>`{3,})(?P<lang>[^\s`]*)\s*(?P<meta>.*)$", line)
                if not m:
                    out.append(line)
                    continue
                base_indent = m.group("indent")
                fence_len = len(m.group("fence"))
                lang = m.group("lang").strip()
                metadata = m.group("meta").strip()
                title_match = re.search(r'title=["\']([^"\']+)["\']', metadata)
                if title_match:
                    out.append(f"**`{title_match.group(1)}`**")
                    out.append("")
                out.append("`" * fence_len + lang)
                in_fence = True
                continue

            # A closing fence may be indented by the surrounding JSX/TabItem.
            if re.match(r"^[ \t]*`{%d,}[ \t]*$" % fence_len, line):
                out.append("`" * fence_len)
                in_fence = False
                base_indent = ""
                continue

            # Remove only the indentation introduced by the MDX container, preserving the code's
            # own indentation. Tabs are handled conservatively as one prefix character here.
            if base_indent and line.startswith(base_indent):
                line = line[len(base_indent):]
            out.append(line)
        return "\n".join(out)

    def _load_imported_mdx_fragment(self, path: Path, seen: set[Path] | None = None) -> str:
        """Load a static MDX helper fragment used as a reusable course component.

        Several CEM repos keep aide-mémoire and reminder blocks under ``docs/_components``
        and import them as JSX (``<AideMemoireListe />``).  They are course content, not
        dynamic widgets, so inlining them is both more faithful and less noisy than
        replacing every occurrence with a warning callout.
        """
        resolved = path.resolve()
        seen = set() if seen is None else set(seen)
        if resolved in seen or not resolved.is_file():
            return ""
        seen.add(resolved)

        text = resolved.read_text(encoding="utf-8")
        imports = {
            m.group("var"): self.resolve_import(resolved, m.group("path"))
            for m in MDX_COMPONENT_IMPORT_RE.finditer(text)
        }
        for name, imported in imports.items():
            if not imported.is_file():
                continue
            fragment = self._load_imported_mdx_fragment(imported, seen)
            if not fragment:
                continue
            text = re.sub(
                rf"<{re.escape(name)}\b[^>]*/>",
                lambda _m, body=fragment: "\n" + body.strip() + "\n",
                text,
                flags=re.DOTALL,
            )

        text = self.remove_import_lines(text)
        text = self.strip_zero_width_markers(text)
        return text.strip()

    def convert_imported_mdx_components(self, text: str, ctx: NoteContext) -> str:
        """Inline static default-imported ``.md/.mdx`` helper components.

        This intentionally targets content fragments, not arbitrary React components.
        Dynamic JS/TS components still go through their dedicated handlers and remain
        reportable when unsupported.

        A subtle but important detail: when a helper is used inside an indented
        ``<TabItem>``, preserve the component line's indentation on every inlined line.
        Otherwise the helper introduces a zero-indented line, the tab body can no longer
        be dedented as a unit, and Obsidian interprets the remaining 4+ space-indented
        prose as one giant code block.
        """
        for name, source in ctx.mdx_imports.items():
            if not source.is_file():
                continue
            # Reusable course-content fragments live under underscore component folders.
            # Avoid accidentally inlining full document pages imported for some other use.
            if not any(part.startswith("_") and "component" in part.lower() for part in source.parts):
                continue
            fragment = self._load_imported_mdx_fragment(source, {ctx.source_note.resolve()})
            if not fragment:
                continue

            standalone = re.compile(
                rf"(?m)^(?P<indent>[ \t]*)<{re.escape(name)}\b[^>]*/>[ \t]*$"
            )

            def standalone_repl(match: re.Match[str], body: str = fragment) -> str:
                indent = match.group("indent")
                return "\n".join(
                    indent + line if line else "" for line in body.strip().splitlines()
                )

            text = standalone.sub(standalone_repl, text)
            # Rare inline usage: keep the old safe behavior rather than dropping content.
            text = re.sub(
                rf"<{re.escape(name)}\b[^>]*/>",
                lambda _m, body=fragment: "\n" + body.strip() + "\n",
                text,
                flags=re.DOTALL,
            )
        return text

    @staticmethod
    def convert_pycode_components(text: str) -> str:
        """Flatten the 420-SN1 PyCode colour wrappers into portable Markdown code.

        ``S/N/K/F/B`` only colour tokens on the Docusaurus site.  Their text content is
        retained, while ``C`` becomes an inline-code span so the examples still read as
        code in Obsidian without depending on site-specific CSS variables.
        """
        chunks = re.split(r"(```.*?```|`[^`\n]*`)", text, flags=re.DOTALL)
        for i in range(0, len(chunks), 2):
            chunk = chunks[i]
            for tag in ("S", "N", "K", "F", "B"):
                chunk = re.sub(rf"</?{tag}\b[^>]*>", "", chunk)

            def code_repl(match: re.Match[str]) -> str:
                body = match.group("body").strip()
                if "\n" in body:
                    return body
                ticks = "``" if "`" in body else "`"
                return f"{ticks}{body}{ticks}"

            chunk = re.sub(
                r"<C\b[^>]*>(?P<body>.*?)</C>",
                code_repl,
                chunk,
                flags=re.DOTALL,
            )
            chunks[i] = chunk
        return "".join(chunks)

    def convert_docusaurus_image(self, text: str, ctx: NoteContext) -> str:
        """Convert CEM/Docusaurus image JSX into local Obsidian images.

        Two forms occur in the course repos:

        - ``<Image img={require('./x.png')} width="300" />``
        - ``<img src={require('/img/x.png').default} ... />``

        The lowercase form is especially common in 420-SN1. Small images carrying
        React's ``verticalAlign`` style are inline UI icons; mark them explicitly so
        the course CSS does not center them like ordinary figures.
        """
        pattern = re.compile(r"<(?P<tag>Image|img)\b(?P<attrs>.*?)/?>", re.DOTALL | re.IGNORECASE)

        def repl(match: re.Match[str]) -> str:
            attrs = match.group("attrs")
            alt = self.parse_jsx_string_attr(attrs, "alt") or ""
            width = self.parse_jsx_string_attr(attrs, "width")
            required = re.search(
                r"\b(?:img|src)\s*=\s*\{\s*require\(\s*['\"]([^'\"]+)['\"]\s*\)\s*(?:\.default)?\s*\}",
                attrs,
                flags=re.DOTALL,
            )
            src = required.group(1) if required else self.parse_jsx_string_attr(attrs, "src")
            if not src or self.is_external_target(src):
                return match.group(0)

            resolved = self.resolve_local_reference(ctx.source_note, src)
            if not resolved or not resolved.is_file():
                self.report.warn(ctx.rel_note, f"Image Docusaurus introuvable: {src}")
                return match.group(0)

            copied = self.copy_asset(resolved, ctx)
            rel_link = os.path.relpath(copied, ctx.output_note.parent).replace(os.sep, "/")
            escaped_src = html.escape(rel_link, quote=True)
            escaped_alt = html.escape(alt, quote=True)

            # React inline icons (copy button, console icon, etc.) must stay on the
            # surrounding text line. Ordinary figures keep the existing centered style.
            is_inline_icon = bool(re.search(r"verticalAlign\s*:", attrs, re.IGNORECASE))
            if is_inline_icon:
                width_attr = f' width="{html.escape(width, quote=True)}"' if width else ""
                return (
                    f'<img class="cem-inline-image" src="{escaped_src}" '
                    f'alt="{escaped_alt}"{width_attr}>'
                )

            if width and re.fullmatch(r"\d+(?:\.\d+)?(?:px|%|em|rem|vw|vh)?", width):
                return (
                    f'<img src="{escaped_src}" alt="{escaped_alt}" '
                    f'width="{html.escape(width, quote=True)}">'
                )
            return f"![{alt}](<{rel_link}>)"

        return pattern.sub(repl, text)

    def convert_nonvoyant(self, text: str) -> str:
        pattern = re.compile(r"<NonVoyant\b[^>]*>(.*?)</NonVoyant>", re.DOTALL | re.IGNORECASE)

        def repl(m: re.Match[str]) -> str:
            body = self.normalize_indentation(m.group(1)).strip()
            if not body:
                return ""
            return self.callout("info", "Description de la démonstration", body, collapsible=True)

        return pattern.sub(repl, text)

    def convert_javascript_console(self, text: str, ctx: NoteContext) -> str:
        """Inline JavaScriptConsole sources without adding converter commentary.

        A console with multiple files is a code-comparison UI on the original site. In Obsidian,
        render those files as a Codeblock Customizer group so they remain clickable tabs while
        still being ordinary fenced code blocks when the plugin is disabled.
        """
        pattern = re.compile(r"<JavaScriptConsole\b(?P<attrs>.*?)/>", re.DOTALL)
        group_index = 0

        def repl(m: re.Match[str]) -> str:
            nonlocal group_index
            attrs = m.group("attrs")
            vars_to_show: list[tuple[str, str | None]] = []
            code = re.search(r"\bcode=\{([A-Za-z_$][\w$]*)\}", attrs)
            if code:
                vars_to_show.append((code.group(1), None))
            files = re.search(r"\bfiles=\{\{(.*?)\}\}", attrs, re.DOTALL)
            if files:
                for filename, var in re.findall(
                    r'["\']([^"\']+)["\']\s*:\s*([A-Za-z_$][\w$]*)', files.group(1)
                ):
                    vars_to_show.append((var, filename))
            if not vars_to_show:
                self.report.warn(ctx.rel_note, "JavaScriptConsole trouvé mais attributs non reconnus.")
                return self.callout("warning", "Console interactive non convertie", m.group(0), collapsible=True)

            resolved: list[tuple[str, Path, str]] = []
            for var, display_name in vars_to_show:
                source = ctx.raw_imports.get(var)
                if not source or not source.is_file():
                    self.report.warn(ctx.rel_note, f"Source du snippet introuvable pour {var}.")
                    continue
                self.copy_source_asset(source, ctx)
                code_text = source.read_text(encoding="utf-8")
                resolved.append((display_name or source.name, source, code_text))
                self.report.snippets_inlined += 1

            if not resolved:
                return self.callout("warning", "Source du code introuvable", "Voir le rapport de conversion.", collapsible=True)

            if len(resolved) == 1:
                _, source, code_text = resolved[0]
                return self.code_block(source, code_text)

            group_index += 1
            group = f"cem-console-{group_index}"
            blocks: list[str] = []
            for label, source, code_text in resolved:
                lang = CODE_LANG.get(source.suffix.lower(), source.suffix.lstrip(".")) or "text"
                fence = "````" if "```" in code_text else "```"
                safe_label = label.replace('"', "'")
                blocks.append(
                    f'{fence}{lang} group:{group} tab:"{safe_label}"\n{code_text.rstrip()}\n{fence}'
                )
            return "\n\n".join(blocks)

        return pattern.sub(repl, text)

    REACT_PREVIEW_GLOBAL_STYLES = """body {
  background: #ffffff;
  color: #171717;
  font-family: Arial, Helvetica, sans-serif;
  margin: 0;
}

.btn {
  color: white;
  font-weight: bold;
  padding: 0.5rem 1rem;
  border: none;
  border-radius: 0.125rem;
  cursor: pointer;
}

.textInput {
  display: block;
  margin-bottom: 0.5rem;
}

.textInput:not([type="checkbox"]) {
  border: 1px solid #c4c4cc;
  border-radius: 0.125rem;
  padding: 0.25rem 0.5rem;
}

.btn-blue   { background-color: royalblue; }
.btn-red    { background-color: crimson; }
.btn-yellow { background-color: goldenrod; }

.cyan  { background-color: rgb(229, 255, 255); }
.red   { background-color: rgb(255, 229, 229); }
.amber { background-color: rgb(255, 248, 229); }
.light { background-color: rgb(244, 245, 246); }
.dark  { background-color: rgb(87, 87, 87); }
"""

    def _react_preview_project(self, attrs: str, ctx: NoteContext) -> InteractiveProject | None:
        """Parse one CEM ReactPreview into a plugin-neutral InteractiveProject."""
        file_name_match = re.search(r'\bfileName=["\']([^"\']+)["\']', attrs)
        entry_file = file_name_match.group(1) if file_name_match else "/page.tsx"
        if not entry_file.startswith("/"):
            entry_file = "/" + entry_file

        requested: list[tuple[str, str]] = []
        code = re.search(r"\bcode=\{([A-Za-z_$][\w$]*)\}", attrs)
        if code:
            requested.append((entry_file, code.group(1)))

        files_match = re.search(r"\bfiles=\{\{(.*?)\}\}", attrs, re.DOTALL)
        if files_match:
            for filename, var in re.findall(
                r'["\']([^"\']+)["\']\s*:\s*([A-Za-z_$][\w$]*)', files_match.group(1)
            ):
                display = filename if filename.startswith("/") else "/" + filename
                requested.append((display, var))

        css = re.search(r"\bcss=\{([A-Za-z_$][\w$]*)\}", attrs)
        if css:
            requested.append(("/globals.css", css.group(1)))

        project_files: dict[str, str] = {}
        source_files: dict[str, Path] = {}
        for display_name, var in requested:
            source = ctx.raw_imports.get(var)
            if not source or not source.is_file():
                self.report.warn(ctx.rel_note, f"Source ReactPreview introuvable pour {var}.")
                continue
            self.copy_source_asset(source, ctx)
            project_files[display_name] = source.read_text(encoding="utf-8")
            source_files[display_name] = source
            self.report.snippets_inlined += 1

        if not project_files:
            return None

        preview_height_match = re.search(r"\bpreviewHeight=\{?([0-9]+)\}?", attrs)
        preview_height = int(preview_height_match.group(1)) if preview_height_match else None
        return InteractiveProject(
            template="react-ts",
            entry_file=entry_file,
            files=project_files,
            source_files=source_files,
            preview_height=preview_height,
        )

    def _render_interactive_project_static(
        self, ctx: NoteContext, project: InteractiveProject
    ) -> str:
        """Portable fallback: one Codeblock Customizer group per interactive project."""
        key = ctx.rel_note.as_posix()
        self._react_preview_counter[key] += 1
        group = f"cem-react-{self._react_preview_counter[key]}"
        blocks: list[str] = []
        for display_name, code_text in project.files.items():
            source = project.source_files.get(display_name)
            suffix = source.suffix.lower() if source else Path(display_name).suffix.lower()
            lang = CODE_LANG.get(suffix, suffix.lstrip(".")) or "text"
            fence = "````" if "```" in code_text else "```"
            safe_label = display_name.lstrip("/").replace('"', "'")
            blocks.append(
                f'{fence}{lang} group:{group} tab:"{safe_label}"\n{code_text.rstrip()}\n{fence}'
            )
        return "\n\n".join(blocks)

    def _render_interactive_project_playground(
        self, ctx: NoteContext, project: InteractiveProject
    ) -> str | None:
        """Render an InteractiveProject through Code Playground when available."""
        if not self.code_playground_available or self.vault_root is None:
            return None

        if project.entry_file not in project.files:
            return None

        note_key = ctx.rel_note.as_posix()
        self._react_preview_counter[note_key] += 1
        ordinal = self._react_preview_counter[note_key]
        digest = hashlib.sha1(
            f"{self.course_name}|{note_key}|interactive-project|{ordinal}".encode("utf-8")
        ).hexdigest()[:20]
        block_id = f"cem-{digest}"

        files = dict(project.files)
        has_globals = "/globals.css" in files
        entry_import = "." + re.sub(r"\.[jt]sx?$", "", project.entry_file)
        imports = [f'import Page from "{entry_import}";', 'import "./styles.css";']
        if has_globals:
            imports.insert(1, 'import "./globals.css";')

        app_code = "\n".join(imports) + """
import { useEffect } from "react";

export default function App() {
  useEffect(() => {
    const id = "cem-tailwind-browser";
    if (!document.getElementById(id)) {
      const script = document.createElement("script");
      script.id = id;
      script.src = "https://cdn.jsdelivr.net/npm/@tailwindcss/browser@4";
      document.head.appendChild(script);
    }
  }, []);
  return <Page />;
}
"""
        files["/App.tsx"] = app_code
        files["/styles.css"] = self.REACT_PREVIEW_GLOBAL_STYLES

        hidden_files = sorted(project.hidden_files | {"/App.tsx", "/styles.css"})
        playground_dir = self.vault_root / "_playgrounds"
        playground_dir.mkdir(parents=True, exist_ok=True)
        sidecar = {
            "version": 1,
            "files": files,
            "activeFile": project.entry_file,
            "hiddenFiles": hidden_files,
        }
        (playground_dir / f"{block_id}.json").write_text(
            json.dumps(sidecar, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )

        min_editor = 180
        max_editor = 650
        if project.preview_height is not None:
            max_editor = max(420, min(800, project.preview_height * 3))

        config = {
            "id": block_id,
            "template": project.template,
            "theme": "auto",
            "showEditor": True,
            "showPreview": True,
            "showConsole": False,
            "showFileTabs": True,
            "minEditorHeight": min_editor,
            "maxEditorHeight": max_editor,
            "showOpenInCodeSandbox": False,
        }
        self.report.react_playgrounds += 1
        return "```code-playground\n" + json.dumps(config, ensure_ascii=False, indent=2) + "\n```"

    def render_interactive_project(self, ctx: NoteContext, project: InteractiveProject) -> str:
        """Render through the preferred Obsidian integration with a portable fallback."""
        playground = self._render_interactive_project_playground(ctx, project)
        if playground is not None:
            return playground
        return self._render_interactive_project_static(ctx, project)

    def convert_react_preview(self, text: str, ctx: NoteContext) -> str:
        """Convert CEM ReactPreview into a plugin-neutral interactive project first."""
        pattern = re.compile(r"<ReactPreview\b(?P<attrs>.*?)/>", re.DOTALL)

        def repl(m: re.Match[str]) -> str:
            project = self._react_preview_project(m.group("attrs"), ctx)
            if project is None:
                self.report.warn(
                    ctx.rel_note,
                    "ReactPreview trouvé, mais aucune source locale n'a pu être extraite.",
                )
                return self.callout(
                    "warning", "Aperçu non converti", "Voir le rapport de conversion.", collapsible=True
                )
            return self.render_interactive_project(ctx, project)

        return pattern.sub(repl, text)

    def convert_dataflow(self, text: str, ctx: NoteContext) -> str:
        pattern = re.compile(r"<DataFlowPlayer\b(?P<attrs>.*?)/>", re.DOTALL)

        def repl(m: re.Match[str]) -> str:
            attrs = m.group("attrs")
            spec_match = re.search(r"\bspec=\{([A-Za-z_$][\w$]*)\}", attrs)
            if not spec_match:
                self.report.warn(ctx.rel_note, "DataFlowPlayer sans spec reconnue.")
                return self.callout("warning", "Animation non convertie", "Spec inconnue.")
            var = spec_match.group(1)
            source = ctx.local_imports.get(var)
            if not source or not source.is_file():
                self.report.warn(ctx.rel_note, f"Spec DataFlow introuvable pour {var}.")
                return self.callout("warning", "Animation non convertie", f"Spec `{var}` introuvable.")
            self.copy_source_asset(source, ctx)
            try:
                raw = source.read_text(encoding="utf-8").strip()
                raw = re.sub(r"^\s*export\s+default\s+", "", raw)
                raw = raw.rstrip().rstrip(";")
                spec = json.loads(raw)
                mermaid = self.dataflow_to_mermaid(spec)
                if mermaid:
                    self.report.dataflows += 1
                    return "```mermaid\n" + mermaid + "\n```"
            except Exception as exc:  # conservative fallback
                self.report.warn(ctx.rel_note, f"Échec DataFlow {source.name}: {exc}")
            return (
                self.callout(
                    "warning",
                    "Animation conservée comme source",
                    "La conversion Mermaid n'a pas été possible automatiquement. La spec originale reste locale.",
                )
                + "\n\n"
                + self.code_block(source, source.read_text(encoding="utf-8"))
            )

        return pattern.sub(repl, text)

    @staticmethod
    def dataflow_to_mermaid(spec: dict) -> str | None:
        nodes = {str(n.get("id")): str(n.get("text") or n.get("id")) for n in spec.get("nodes", [])}
        if not nodes:
            return None
        packets = {str(p.get("id")): p for p in spec.get("packets", [])}

        def safe_id(value: str) -> str:
            value = re.sub(r"\W+", "_", value)
            if value and value[0].isdigit():
                value = "n_" + value
            return value or "node"

        alias = {node_id: safe_id(node_id) for node_id in nodes}

        def packet_label(object_id: str) -> str:
            p = packets.get(str(object_id), {})
            kind = p.get("kind")
            if kind == "http_packet":
                content = p.get("packet_content", {})
                header = str(content.get("header", object_id))
                return header.splitlines()[0]
            if kind == "sql_request":
                return str(p.get("request_content", object_id)).replace("\n", " ")
            if kind == "sql_response":
                response = p.get("response_content", {})
                return str(response.get("header", object_id))
            return str(object_id)

        lines = ["sequenceDiagram"]
        for node_id, label in nodes.items():
            lines.append(f"    participant {alias[node_id]} as {label}")

        def walk(actions) -> None:
            for action in actions or []:
                typ = action.get("type")
                if typ == "parallel":
                    walk(action.get("actions", []))
                elif typ == "move":
                    src = str(action.get("from"))
                    dst = str(action.get("to"))
                    if src in alias and dst in alias:
                        label = packet_label(str(action.get("object", "message")))
                        label = label.replace(":", " -").replace("\n", " ")
                        lines.append(f"    {alias[src]}->>{alias[dst]}: {label}")
                elif typ == "comment":
                    obj = str(action.get("object"))
                    if obj in alias:
                        label = str(action.get("text", "")).replace(":", " -").replace("\n", " ")
                        lines.append(f"    Note over {alias[obj]}: {label}")
                elif typ == "set_content":
                    obj = str(action.get("object"))
                    if obj in alias:
                        content = action.get("content", {})
                        value = content.get("value") or content.get("url") or "Affichage mis à jour"
                        value = str(value).replace("\n", " ").replace(":", " -")
                        if len(value) > 100:
                            value = value[:97] + "..."
                        lines.append(f"    Note over {alias[obj]}: {value}")

        walk(spec.get("timeline", []))
        return "\n".join(lines)

    def convert_quiz(self, text: str, ctx: NoteContext) -> str:
        """Convert the two Quiz forms currently used by CEM course sites.

        Older repos import a JavaScript quiz definition and pass it as ``file={quizVar}``.
        Newer/simple repos point directly at JSON under Docusaurus ``static`` using
        ``file="/quiz/foo.json"``. Both become static, foldable Obsidian quiz content.
        """
        pattern = re.compile(r"<Quiz\b(?P<attrs>.*?)/>", re.DOTALL)

        def render_json_quiz(source: Path) -> str | None:
            try:
                payload = json.loads(source.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                return None
            if not isinstance(payload, dict) or not isinstance(payload.get("questions"), list):
                return None

            title = str(payload.get("titre") or "Quiz du cours")
            blocks = [f"### 🧠 {title}"]
            valid_questions = 0
            for idx, question in enumerate(payload["questions"], 1):
                if not isinstance(question, dict):
                    continue
                question_text = str(question.get("texte") or f"Question {idx}")
                choices = question.get("choix")
                answer = question.get("reponse")
                if not isinstance(choices, list):
                    continue
                valid_questions += 1
                body = [question_text]
                code = question.get("code")
                if isinstance(code, str) and code.strip():
                    body.extend(["", "```", code.rstrip(), "```"] )
                body.append("")
                for cidx, choice in enumerate(choices, 1):
                    body.append(f"{cidx}. {choice}")
                blocks.append(self.callout("question", f"Question {idx}", "\n".join(body)))
                if isinstance(answer, int) and 0 <= answer < len(choices):
                    blocks.append(f"> [!success]- Réponse\n> **{answer + 1}. {choices[answer]}**")
            return "\n\n".join(blocks) if valid_questions else None

        def repl(m: re.Match[str]) -> str:
            attrs = m.group("attrs")

            # JavaScript/MDX form: <Quiz file={quizDefinition} />
            file_var = re.search(r"\bfile\s*=\s*\{([A-Za-z_$][\w$]*)\}", attrs)
            source: Path | None = None
            source_label = ""
            if file_var:
                source_label = file_var.group(1)
                source = ctx.local_imports.get(source_label)
            else:
                # Static JSON form. ``\s`` intentionally accepts non-breaking spaces copied
                # into a few course documents around JSX attributes.
                file_path = re.search(r"\bfile\s*=\s*([\"'])(.*?)\1", attrs, re.DOTALL)
                if file_path:
                    source_label = file_path.group(2).strip()
                    source = self.resolve_local_reference(ctx.source_note, source_label)

            if not source_label:
                self.report.warn(ctx.rel_note, "Quiz trouvé mais attribut file non reconnu.")
                return self.callout("warning", "Quiz non converti", "La définition du quiz n'a pas pu être localisée.")
            if not source or not source.is_file():
                self.report.warn(ctx.rel_note, f"Définition Quiz introuvable pour {source_label}.")
                return self.callout("warning", "Quiz non converti", "La définition du quiz est introuvable.")

            self.copy_source_asset(source, ctx)
            if source.suffix.lower() == ".json":
                rendered = render_json_quiz(source)
                if rendered is not None:
                    return rendered
                self.report.warn(ctx.rel_note, f"Quiz {source.name}: JSON non reconnu; source conservée localement.")
                return self.callout(
                    "warning", "Quiz interactif non reconstruit",
                    f"La définition originale `{source.name}` est conservée dans `_assets`; aucun contenu n'a été supprimé."
                )

            raw = source.read_text(encoding="utf-8")
            raw_questions: dict[str, Path] = {}
            for rm in RAW_IMPORT_RE.finditer(raw):
                raw_questions[rm.group("var")] = self.resolve_import(source, rm.group("path"))

            title_m = re.search(r"\btitre\s*:\s*[\"']([^\"']+)[\"']", raw)
            title = title_m.group(1) if title_m else "Quiz du cours"
            question_pattern = re.compile(
                r"\{\s*texte\s*:\s*(?P<text>[A-Za-z_$][\w$]*)\s*,\s*"
                r"choix\s*:\s*\[(?P<choices>.*?)\]\s*,\s*"
                r"reponse\s*:\s*(?P<answer>\d+)",
                re.DOTALL,
            )
            questions = list(question_pattern.finditer(raw))
            if not questions:
                self.report.warn(ctx.rel_note, f"Quiz {source.name}: format non reconnu; source conservée localement.")
                return self.callout(
                    "warning", "Quiz interactif non reconstruit",
                    f"La définition originale `{source.name}` est conservée dans `_assets`; aucun contenu n'a été supprimé."
                )

            blocks = [f"### 🧠 {title}"]
            for idx, qm in enumerate(questions, 1):
                qvar = qm.group("text")
                qsource = raw_questions.get(qvar)
                if qsource and qsource.is_file():
                    self.copy_source_asset(qsource, ctx)
                    question_text = qsource.read_text(encoding="utf-8").strip()
                else:
                    question_text = f"Question `{qvar}` (source introuvable)"
                    self.report.warn(ctx.rel_note, f"Texte de question Quiz introuvable: {qvar}")

                choices = re.findall(r"[\"']((?:\\.|[^\"'])*)[\"']", qm.group("choices"))
                answer_index = int(qm.group("answer"))
                body = [question_text, ""]
                for cidx, choice in enumerate(choices, 1):
                    body.append(f"{cidx}. {choice}")
                blocks.append(self.callout("question", f"Question {idx}", "\n".join(body)))
                if 0 <= answer_index < len(choices):
                    blocks.append(f"> [!success]- Réponse\n> **{answer_index + 1}. {choices[answer_index]}**")
            return "\n\n".join(blocks)

        return pattern.sub(repl, text)

    def convert_docs_viewer(self, text: str, ctx: NoteContext) -> str:
        # CEM homepages use DocsViewer as a dashboard/calendar shell. The actual course
        # documents are already converted individually, so replace the dashboard with a
        # deterministic local index rather than trying to emulate its React UI.
        if "<DocsViewer" not in text:
            return text
        pattern = re.compile(r"<DocsViewer\b.*?/>(?=\s*$)", re.DOTALL)
        folders: list[str] = []
        for child in sorted(self.docs_root.iterdir()):
            if child.is_dir() and not child.name.startswith("_"):
                folders.append(self.strip_number_prefix(child.name))
        body = "Le tableau de bord React du site est remplacé par le sommaire local [[00 - Navigation]]."
        if folders:
            body += "\n\nSections détectées : " + ", ".join(f"`{f}`" for f in folders) + "."
        replacement = self.callout("info", "Tableau de bord du site simplifié", body)
        converted, n = pattern.subn(replacement, text)
        if n == 0:
            self.report.warn(ctx.rel_note, "DocsViewer trouvé mais sa structure n'a pas pu être simplifiée proprement.")
        return converted

    @staticmethod
    def parse_jsx_string_attr(attrs: str, name: str) -> str | None:
        m = re.search(rf"\b{re.escape(name)}\s*=\s*[\"']([^\"']+)[\"']", attrs)
        return m.group(1) if m else None

    def convert_ghcode(self, text: str, ctx: NoteContext) -> str:
        """Convert GHCode directly to a local fenced block, without importer prose."""
        pattern = re.compile(r"<GHCode\b(?P<attrs>.*?)/>", re.DOTALL)

        def repl(m: re.Match[str]) -> str:
            attrs = m.group("attrs")
            user = self.parse_jsx_string_attr(attrs, "user") or "departement-info-cem"
            repo = self.parse_jsx_string_attr(attrs, "repo")
            file_path = self.parse_jsx_string_attr(attrs, "filePath")
            branch = self.parse_jsx_string_attr(attrs, "branch") or "main"
            language = self.parse_jsx_string_attr(attrs, "language")
            start_raw = self.parse_jsx_string_attr(attrs, "startLine")
            end_raw = self.parse_jsx_string_attr(attrs, "endLine")
            ignore_raw = self.parse_jsx_string_attr(attrs, "ignore")

            if not repo or not file_path:
                self.report.warn(ctx.rel_note, "GHCode trouvé mais repo/filePath est absent ou dynamique.")
                return self.callout("warning", "Code GitHub non converti", "Attributs GHCode non reconnus.", collapsible=True)

            url = f"https://raw.githubusercontent.com/{user}/{repo}/{branch}/{file_path}"
            try:
                req = Request(url, headers={"User-Agent": f"cem-obsidian-importer/{VERSION}"})
                with urlopen(req, timeout=20) as response:
                    code = response.read().decode("utf-8")
            except Exception as exc:
                self.report.warn(ctx.rel_note, f"GHCode impossible à télécharger: {url} ({exc})")
                return self.callout(
                    "warning", "Code externe non téléchargé",
                    f"[Ouvrir la source]({url})",
                    collapsible=True,
                )

            remote_dest = ctx.asset_dir / "sources" / "remote" / repo / file_path
            remote_dest.parent.mkdir(parents=True, exist_ok=True)
            if not remote_dest.exists():
                remote_dest.write_text(code, encoding="utf-8")
                self.report.assets += 1

            numbered = [(idx + 1, line) for idx, line in enumerate(code.splitlines())]
            if ignore_raw:
                hidden: set[int] = set()
                for group in ignore_raw.split(","):
                    group = group.strip()
                    rm = re.fullmatch(r"(\d+)-(\d+)", group)
                    if rm:
                        a, b = int(rm.group(1)), int(rm.group(2))
                        hidden.update(range(min(a, b), max(a, b) + 1))
                if hidden:
                    numbered = [(n, line) for n, line in numbered if n not in hidden]

            try:
                start_line = int(start_raw) if start_raw is not None else 0
            except ValueError:
                start_line = 0
            try:
                end_line = int(end_raw) if end_raw is not None else (numbered[-1][0] if numbered else 0)
            except ValueError:
                end_line = numbered[-1][0] if numbered else 0

            if start_line:
                shown_lines = [line for n, line in numbered if start_line <= n <= end_line]
            else:
                shown_lines = [line for n, line in numbered if n <= end_line]
            shown = "\n".join(shown_lines)
            suffix = Path(file_path).suffix.lower()
            lang = language or CODE_LANG.get(suffix, suffix.lstrip(".")) or "text"
            fence = "````" if "```" in shown else "```"
            self.report.snippets_inlined += 1
            return f"{fence}{lang}\n{shown.rstrip()}\n{fence}"

        return pattern.sub(repl, text)

    def convert_console_window(self, text: str) -> str:
        """Convert the CEM ConsoleWindow visual component to a normal fenced block."""
        pair = re.compile(r"<ConsoleWindow\b(?P<attrs>[^>]*)>(?P<body>.*?)</ConsoleWindow>", re.DOTALL)
        self_closing = re.compile(r"<ConsoleWindow\b(?P<attrs>.*?)/>", re.DOTALL)

        def render(attrs: str, body: str = "") -> str:
            title = self.parse_jsx_string_attr(attrs, "title")
            language = self.parse_jsx_string_attr(attrs, "language") or "text"
            literal = self.parse_jsx_string_attr(attrs, "text")
            content = literal if literal is not None else body
            content = re.sub(r"<br\s*/?>", "\n", content, flags=re.IGNORECASE)
            content = re.sub(r"</?(?:p|div|span|section)\b[^>]*>", "", content, flags=re.IGNORECASE)
            content = self.normalize_indentation(content).strip()
            if not content:
                return ""
            fence = "````" if "```" in content else "```"
            heading = f"**{title}**\n\n" if title else ""
            return f"{heading}{fence}{language}\n{content}\n{fence}"

        text = pair.sub(lambda m: render(m.group("attrs"), m.group("body")), text)
        text = self_closing.sub(lambda m: render(m.group("attrs")), text)
        return text

    def convert_github_download(self, text: str, ctx: NoteContext) -> str:
        """Preserve GithubDownload resources, localizing folders when they live in this repo."""
        pattern = re.compile(r"<GithubDownload\b(?P<attrs>.*?)/>", re.DOTALL)

        def repl(m: re.Match[str]) -> str:
            attrs = m.group("attrs")
            repo = self.parse_jsx_string_attr(attrs, "repo") or self.source.name
            folder = self.parse_jsx_string_attr(attrs, "folder")
            branch = self.parse_jsx_string_attr(attrs, "branch") or "main"
            label = self.parse_jsx_string_attr(attrs, "label") or "Télécharger les fichiers"
            if not folder:
                return self.callout("warning", "Ressource GitHub", "Dossier GitHub non reconnu.")

            if repo.lower() == self.source.name.lower():
                candidate = (self.source / folder).resolve()
                try:
                    candidate.relative_to(self.source)
                except ValueError:
                    candidate = Path("/__invalid__")
                if candidate.is_dir():
                    dest = ctx.asset_dir / "downloads" / candidate.name
                    shutil.copytree(candidate, dest, dirs_exist_ok=True)
                    self.report.assets += sum(1 for p in candidate.rglob("*") if p.is_file())
                    rel = os.path.relpath(dest, ctx.output_note.parent).replace(os.sep, "/")
                    return self.callout(
                        "info", label,
                        f"Le dossier de support a été copié localement dans `{rel}`."
                    )

            url = f"https://github.com/departement-info-cem/{repo}/tree/{branch}/{folder}"
            return self.callout("info", label, f"[↗ Ouvrir le dossier source sur GitHub]({url})")

        return pattern.sub(repl, text)

    def convert_slide_components(self, text: str) -> str:
        """Flatten Reveal/Slide wrappers while preserving slide images and content."""
        image_re = re.compile(r"<SlideImage\b(?P<attrs>.*?)/>", re.DOTALL)

        def image_repl(m: re.Match[str]) -> str:
            attrs = m.group("attrs")
            src = self.parse_jsx_string_attr(attrs, "src")
            alt = self.parse_jsx_string_attr(attrs, "alt") or ""
            return f"![{alt}]({src})" if src else self.callout("warning", "Image de diapositive", "Source non reconnue.")

        text = image_re.sub(image_repl, text)
        text = re.sub(r"</?SlidePage\b[^>]*>", "", text)
        # Reveal slides commonly use bare <section> containers. Removing the containers lets
        # Markdown inside render normally in Obsidian instead of becoming raw HTML content.
        text = re.sub(r"</?section\b[^>]*>", "", text, flags=re.IGNORECASE)
        return text

    def convert_example_components(self, text: str, ctx: NoteContext) -> str:
        """Convert z03 browser previews to local source links/code without dropping examples."""
        def frame_repl(m: re.Match[str]) -> str:
            attrs = m.group("attrs")
            title = self.parse_jsx_string_attr(attrs, "title") or "Exemple web"
            src = self.parse_jsx_string_attr(attrs, "src")
            blocks: list[str] = []
            if src:
                resolved = self.resolve_local_reference(ctx.source_note, src)
                if resolved and resolved.is_file():
                    copied = self.copy_asset(resolved, ctx)
                    rel = os.path.relpath(copied, ctx.output_note.parent).replace(os.sep, "/")
                    blocks.append(self.callout("example", title, f"[↗ Ouvrir l'exemple HTML local](<{rel}>)"))
                else:
                    blocks.append(self.callout("example", title, f"Source : `{src}`"))
            for attr_name, label, fallback_ext in (("html", "index.html", ".html"), ("css", "styles.css", ".css")):
                vm = re.search(rf"\b{attr_name}=\{{([A-Za-z_$][\w$]*)\}}", attrs)
                if vm:
                    source = ctx.raw_imports.get(vm.group(1)) or ctx.local_imports.get(vm.group(1))
                    if source and source.is_file():
                        self.copy_source_asset(source, ctx)
                        blocks.append(f"##### `{label}`\n\n{self.code_block(source, source.read_text(encoding='utf-8'))}")
                        self.report.snippets_inlined += 1
            return "\n\n".join(blocks) if blocks else self.callout("example", title, "Aperçu web simplifié.")

        frame = re.compile(r"<ExampleFrame\b(?P<attrs>.*?)/>", re.DOTALL)
        peek = re.compile(r"<ExamplePeek\b(?P<attrs>.*?)/>", re.DOTALL)
        text = frame.sub(frame_repl, text)
        text = peek.sub(frame_repl, text)
        return text

    def convert_learning_cues(self, text: str) -> str:
        topic_labels = {
            "html": "HTML", "css": "CSS", "structure": "Structure", "content": "Contenu",
            "paths": "Chemins", "selectors": "Sélecteurs", "box": "Modèle en boîte",
            "flexbox": "Flexbox", "test": "À tester", "validation": "Validation", "optional": "Optionnel",
        }
        topic_re = re.compile(r"<TopicBadges\b(?P<attrs>.*?)/>", re.DOTALL)

        def topics(m: re.Match[str]) -> str:
            attrs = m.group("attrs")
            arr = re.search(r"\btopics=\{\[([^\]]*)\]\}", attrs, re.DOTALL)
            if not arr:
                return ""
            keys = re.findall(r"[\"']([^\"']+)[\"']", arr.group(1))
            shown = " · ".join(topic_labels.get(k, k) for k in keys)
            return f"**Repères :** {shown}" if shown else ""

        text = topic_re.sub(topics, text)
        key_re = re.compile(r"<KeyPoint\b(?P<attrs>[^>]*)>(?P<body>.*?)</KeyPoint>", re.DOTALL)

        def keypoint(m: re.Match[str]) -> str:
            attrs = m.group("attrs")
            typ = self.parse_jsx_string_attr(attrs, "type") or "remember"
            title = self.parse_jsx_string_attr(attrs, "title")
            defaults = {"remember": ("tip", "À retenir"), "method": ("info", "Méthode"), "test": ("success", "À tester"), "debug": ("warning", "Réflexe")}
            kind, default_title = defaults.get(typ, ("note", "Point clé"))
            body = self.normalize_indentation(m.group("body")).strip()
            return self.callout(kind, title or default_title, body)

        return key_re.sub(keypoint, text)

    def convert_project_visuals(self, text: str) -> str:
        hero = re.compile(r"<ProjectStepHero\b(?P<attrs>.*?)/>", re.DOTALL)

        def hero_repl(m: re.Match[str]) -> str:
            sm = re.search(r"\bstep=\{?(\d+)\}?", m.group("attrs"))
            step = sm.group(1) if sm else "?"
            return self.callout("info", f"Projet Web — étape {step}", "Le bandeau visuel du site a été simplifié; le contenu pédagogique de l'étape est conservé dans cette note.")

        text = hero.sub(hero_repl, text)
        text = re.sub(
            r"<ProjectJourney\b.*?/>",
            self.callout("info", "Parcours du projet", "Voir [[00 - Navigation]] pour les étapes importées du cours."),
            text,
            flags=re.DOTALL,
        )
        text = re.sub(r"<StyleSwitcher\b.*?/>", "", text, flags=re.DOTALL)
        return text

    def convert_plan_de_cours_menu(self, text: str) -> str:
        if "<PlanDeCoursMenu" not in text:
            return text
        pattern = re.compile(r"<PlanDeCoursMenu\b.*?/>", re.DOTALL)
        pdf_dir = self.source / "web" / "static" / "pdf"
        pdfs = sorted(pdf_dir.glob("*.pdf")) if pdf_dir.is_dir() else []
        body = "\n".join(f"- [{p.stem}](/pdf/{p.name})" for p in pdfs)
        if not body:
            body = "Les PDF du plan de cours n'ont pas été trouvés dans `web/static/pdf`."
        return pattern.sub(self.callout("info", "Plan de cours", body), text)

    def convert_feedback(self, text: str) -> str:
        # This component submits course-site feedback to a server. It is not course content and
        # cannot usefully operate in an offline vault, so preserve an explicit harmless marker.
        return re.sub(
            r"<Feedback\b.*?/>",
            self.callout("note", "Rétroaction du site", "Widget de rétroaction en ligne omis dans la copie locale."),
            text,
            flags=re.DOTALL,
        )

    def convert_highlight(self, text: str) -> str:
        """Preserve the CEM Highlight component's semantic colour in Obsidian.

        Known CEM colours become small inline HTML badges styled by the bundled CSS.
        Unknown/custom colours fall back to portable Obsidian ==highlight== syntax so
        content is never lost just because a new colour name appears upstream.
        """
        pattern = re.compile(r"<Highlight\b(?P<attrs>[^>]*)>(?P<body>.*?)</Highlight>", re.DOTALL)
        known = {"note", "tip", "info", "caution", "danger"}

        def repl(match: re.Match[str]) -> str:
            attrs = match.group("attrs") or ""
            body = self.normalize_indentation(match.group("body")).strip()
            color_match = re.search(r"\bcolor\s*=\s*[\"']([^\"']+)[\"']", attrs, re.IGNORECASE)
            color = color_match.group(1).strip().lower() if color_match else "default"
            if color == "default":
                return f'<span class="cem-highlight cem-highlight-default">{body}</span>'
            if color in known:
                return f'<span class="cem-highlight cem-highlight-{color}">{body}</span>'
            return f"=={body}=="

        return pattern.sub(repl, text)

    @staticmethod
    def _youtube_watch_url(value: str) -> str | None:
        """Return a canonical YouTube watch URL when *value* is a recognized YouTube URL."""
        try:
            parsed = urlparse(value)
        except Exception:
            return None
        host = parsed.netloc.lower().split(":", 1)[0]
        if host.startswith("www."):
            host = host[4:]
        video_id = None
        if host == "youtu.be":
            video_id = parsed.path.strip("/").split("/", 1)[0]
        elif host in {"youtube.com", "m.youtube.com", "music.youtube.com"}:
            if parsed.path == "/watch":
                from urllib.parse import parse_qs
                video_id = parse_qs(parsed.query).get("v", [None])[0]
            else:
                parts = [p for p in parsed.path.split("/") if p]
                if len(parts) >= 2 and parts[0] in {"embed", "shorts", "live"}:
                    video_id = parts[1]
        if not video_id:
            return None
        # Keep only the normal YouTube id characters. If the URL is malformed, fall back to a link.
        if not re.fullmatch(r"[A-Za-z0-9_-]{6,}", video_id):
            return None
        return f"https://www.youtube.com/watch?v={video_id}"

    @staticmethod
    def _vimeo_embed_url(value: str) -> str | None:
        try:
            parsed = urlparse(value)
        except Exception:
            return None
        host = parsed.netloc.lower().split(":", 1)[0]
        if host.startswith("www."):
            host = host[4:]
        if host not in {"vimeo.com", "player.vimeo.com"}:
            return None
        ids = re.findall(r"(?:^|/)(\d{5,})(?:/|$)", parsed.path)
        return f"https://player.vimeo.com/video/{ids[-1]}" if ids else None

    def convert_video(self, text: str, ctx: NoteContext) -> str:
        pattern = re.compile(r"<Video\b(?P<attrs>.*?)/>", re.DOTALL)

        def repl(m: re.Match[str]) -> str:
            attrs = m.group("attrs")
            value = self.parse_jsx_string_attr(attrs, "url") or self.parse_jsx_string_attr(attrs, "src")
            if not value:
                return self.callout("warning", "Vidéo", "URL non reconnue.", collapsible=True)
            self.report.videos += 1

            youtube = self._youtube_watch_url(value)
            if youtube:
                return f"![]({youtube})"

            vimeo = self._vimeo_embed_url(value)
            if vimeo:
                return (
                    f'<iframe class="cem-video" src="{vimeo}" width="100%" height="480" frameborder="0" '
                    'allow="autoplay; fullscreen; picture-in-picture" allowfullscreen></iframe>'
                )

            if not self.is_external_target(value):
                resolved = self.resolve_local_reference(ctx.source_note, value)
                if resolved and resolved.is_file() and resolved.suffix.lower() in {".mp4", ".mov", ".mkv", ".webm", ".ogv"}:
                    copied = self.copy_asset(resolved, ctx)
                    rel_link = os.path.relpath(copied, ctx.output_note.parent).replace(os.sep, "/")
                    return f"![](<{rel_link}>)"

            return f"[▶ Ouvrir la vidéo]({value})"

        return pattern.sub(repl, text)

    @staticmethod
    def _tab_label(attrs: str) -> str:
        label = re.search(r'\blabel=["\']([^"\']+)["\']', attrs)
        value = re.search(r'\bvalue=["\']([^"\']+)["\']', attrs)
        title = label or value
        return title.group(1) if title else "Option"

    @staticmethod
    def _extract_single_code_fence(body: str) -> tuple[str, str, str] | None:
        """Return (language, code, remaining_markdown) if body has exactly one fenced block."""
        fence_re = re.compile(
            r"(?ms)^(?P<fence>`{3,})(?P<lang>[^\n`]*)\n(?P<code>.*?)^(?P=fence)[ \t]*$"
        )
        matches = list(fence_re.finditer(body))
        if len(matches) != 1:
            return None
        m = matches[0]
        lang = m.group("lang").strip().split()[0] if m.group("lang").strip() else "text"
        code = m.group("code").rstrip()
        remaining = (body[:m.start()] + body[m.end():]).strip()
        return lang, code, remaining

    def convert_tabs(self, text: str) -> str:
        """Convert Docusaurus Tabs.

        Code-comparison tabs become Codeblock Customizer groups. This preserves normal fenced
        code blocks (and Execute Code compatibility) while giving Obsidian clickable tabs.
        Complex tabs that cannot be represented as one code block per tab fall back to headings,
        so content is never silently lost.
        """
        tabs_re = re.compile(r"<Tabs\b[^>]*>(?P<body>.*?)</Tabs>", re.DOTALL)
        tab_re = re.compile(r"<TabItem\b(?P<attrs>[^>]*)>(?P<body>.*?)</TabItem>", re.DOTALL)
        group_index = 0

        def tabs_repl(tm: re.Match[str]) -> str:
            nonlocal group_index
            raw = tm.group("body")
            items = list(tab_re.finditer(raw))
            if not items:
                return raw

            parsed: list[tuple[str, str, str, str]] = []
            for item in items:
                label = self._tab_label(item.group("attrs"))
                body = self.normalize_indentation(item.group("body")).strip()
                extracted = self._extract_single_code_fence(body)
                if extracted is None:
                    # Safe fallback for mixed/nested tabs.
                    pieces = []
                    for fallback in items:
                        shown = self._tab_label(fallback.group("attrs"))
                        pieces.append(f"#### {shown}\n\n{self.normalize_indentation(fallback.group('body')).strip()}")
                        self.report.tabs += 1
                    return "\n\n".join(pieces)
                lang, code, remaining = extracted
                parsed.append((label, lang, code, remaining))

            group_index += 1
            group = f"cem-tabs-{group_index}"
            code_blocks: list[str] = []
            explanations: list[str] = []
            for label, lang, code, remaining in parsed:
                safe_label = label.replace('"', "'")
                fence = "````" if "```" in code else "```"
                code_blocks.append(
                    f'{fence}{lang} group:{group} tab:"{safe_label}"\n{code}\n{fence}'
                )
                if remaining:
                    explanations.append(self.callout("note", f"{label} — explication", remaining, collapsible=True))
                self.report.tabs += 1

            result = "\n\n".join(code_blocks)
            if explanations:
                result += "\n\n" + "\n\n".join(explanations)
            return result

        converted = tabs_re.sub(tabs_repl, text)
        # Old or malformed standalone TabItem tags: preserve the previous safe behavior.
        def orphan_repl(m: re.Match[str]) -> str:
            shown = self._tab_label(m.group(1))
            self.report.tabs += 1
            return f"\n#### {shown}\n"
        converted = re.sub(r"<TabItem\b([^>]*)>", orphan_repl, converted)
        converted = re.sub(r"</TabItem>", "", converted)
        converted = re.sub(r"</?Tabs\b[^>]*>", "", converted)
        return converted

    def convert_layout_rows(self, text: str) -> str:
        """Preserve CEM <Row>/<Column> layouts as responsive Obsidian callout grids."""
        row_re = re.compile(r"<Row\b[^>]*>(?P<body>.*?)</Row>", re.DOTALL)
        col_re = re.compile(r"<Column\b[^>]*>(?P<body>.*?)</Column>", re.DOTALL)

        def row_repl(m: re.Match[str]) -> str:
            columns = list(col_re.finditer(m.group("body")))
            if len(columns) < 2:
                return re.sub(r"</?Column\b[^>]*>", "", m.group("body"))

            out = ["> [!cem-columns]", ">"]
            for pos, cm in enumerate(columns):
                body = self.normalize_indentation(cm.group("body")).strip()
                out.append(">> [!cem-column]")
                if body:
                    for line in body.splitlines():
                        if not line:
                            out.append(">>")
                        elif line.startswith(">"):
                            out.append(">>" + line)
                        else:
                            out.append(">> " + line)
                if pos + 1 < len(columns):
                    out.append(">")
            self.report.layout_rows += 1
            return "\n".join(out)

        return row_re.sub(row_repl, text)

    @staticmethod
    def strip_layout_wrappers(text: str) -> str:
        for tag in ("Row", "Column", "Highlight"):
            text = re.sub(rf"</?{tag}\b[^>]*>", "", text)
        text = re.sub(r"</?center\b[^>]*>", "", text, flags=re.IGNORECASE)
        return text

    def convert_admonitions(self, text: str) -> str:
        lines = text.splitlines()
        out: list[str] = []
        stack: list[tuple[str, str]] = []
        opener = re.compile(r"^\s*:::(note|tip|info|warning|danger|caution)(?:\[([^\]]+)\]|(?:\s+(.*?)))?\s*$", re.IGNORECASE)
        for line in lines:
            m = opener.match(line)
            if m:
                kind = m.group(1).lower()
                if kind == "caution":
                    kind = "warning"
                title = (m.group(2) or m.group(3) or "").strip()
                stack.append((kind, title))
                prefix = "> " * len(stack)
                out.append(f"{prefix}[!{kind}]" + (f" {title}" if title else ""))
                self.report.admonitions += 1
                continue
            if line.strip() == ":::" and stack:
                stack.pop()
                out.append("> " * len(stack) if stack else "")
                continue
            if stack:
                prefix = "> " * len(stack)
                out.append(prefix.rstrip() if not line else prefix + line)
            else:
                out.append(line)
        return "\n".join(out)

    def rewrite_markdown_links(self, text: str, ctx: NoteContext) -> str:
        pattern = re.compile(r"(!?)\[([^\]]*)\]\(([^)]+)\)")

        def repl(m: re.Match[str]) -> str:
            bang, label, target = m.groups()
            # Keep optional Markdown link title untouched only when URL is clearly remote.
            raw_target = target.strip()
            if self.is_external_target(raw_target) or raw_target.startswith("?"):
                return m.group(0)

            path_part, anchor = self.split_anchor(raw_target)
            resolved = self.resolve_local_reference(ctx.source_note, path_part)
            if not resolved:
                resolved = self.resolve_local_reference_from_label(ctx.source_note, path_part, label)
            if resolved and resolved.is_file():
                if resolved.suffix.lower() in MARKDOWN_EXTS:
                    mapped = self.output_map.get(resolved.resolve())
                    if mapped is not None:
                        rel_link = os.path.relpath(self.output_root / mapped, ctx.output_note.parent).replace(os.sep, "/")
                        return f"{bang}[{label}](<{rel_link}{anchor}>)"
                    # Helper Markdown under underscore folders is supporting material, not a visible
                    # Obsidian note. If something links to it directly, keep a local asset copy.
                    copied = self.copy_asset(resolved, ctx)
                    rel_link = os.path.relpath(copied, ctx.output_note.parent).replace(os.sep, "/")
                    return f"{bang}[{label}](<{rel_link}{anchor}>)"
                copied = self.copy_asset(resolved, ctx)
                rel_link = os.path.relpath(copied, ctx.output_note.parent).replace(os.sep, "/")
                return f"{bang}[{label}](<{rel_link}{anchor}>)"

            self.report.unresolved_local_links.append((str(ctx.rel_note), raw_target))
            return m.group(0)

        # Do not rewrite examples shown literally inside fenced/inline code or content that
        # upstream authors intentionally disabled with HTML comments.
        chunks = re.split(r"(```.*?```|`[^`\n]*`|<!--.*?-->)", text, flags=re.DOTALL)
        for i in range(0, len(chunks), 2):
            chunks[i] = pattern.sub(repl, chunks[i])
        return "".join(chunks)

    def rewrite_html_sources(self, text: str, ctx: NoteContext) -> str:
        pattern = re.compile(r'(?P<prefix>\b(?:src|href)=)(?P<q>["\'])(?P<target>[^"\']+)(?P=q)', re.IGNORECASE)

        def repl(m: re.Match[str]) -> str:
            target = m.group("target")
            if self.is_external_target(target) or target.startswith("#"):
                return m.group(0)
            path_part, anchor = self.split_anchor(target)
            resolved = self.resolve_local_reference(ctx.source_note, path_part)
            if not resolved or not resolved.is_file():
                return m.group(0)
            copied = self.copy_asset(resolved, ctx)
            rel_link = os.path.relpath(copied, ctx.output_note.parent).replace(os.sep, "/")
            return f"{m.group('prefix')}{m.group('q')}{rel_link}{anchor}{m.group('q')}"

        return pattern.sub(repl, text)

    @staticmethod
    def is_external_target(target: str) -> bool:
        target = target.strip().strip("<>")
        parsed = urlparse(target)
        return bool(parsed.scheme in {"http", "https", "mailto", "tel", "data"}) or target.startswith("#")

    @staticmethod
    def split_anchor(target: str) -> tuple[str, str]:
        """Return the local path and Markdown anchor, ignoring Docusaurus UI query state.

        Course links frequently use query strings only to select a Docusaurus tab
        (``?onglet=...``). Obsidian cannot reproduce that UI state, but it can still link
        to the correct local note, so resolve the path while dropping the query.
        """
        target = target.strip().strip("<>")
        parsed = urlparse(target)
        anchor = f"#{parsed.fragment}" if parsed.fragment else ""
        return unquote(parsed.path), anchor

    def resolve_local_reference(self, note: Path, target: str) -> Path | None:
        if not target:
            return None
        target = target.strip()
        if target.startswith("?"):
            return None

        # Docusaurus aliases for static assets.
        if target.startswith("@site/static/"):
            candidate = (self.source / "web" / "static" / target[len("@site/static/"):]).resolve()
            if candidate.exists():
                return candidate
        if target.startswith("pathname:///"):
            candidate = (self.source / "web" / "static" / target[len("pathname:///"):]).resolve()
            if candidate.exists():
                return candidate

        # First try literal filesystem semantics for ordinary Markdown/assets.
        candidates: list[Path] = []
        if target.startswith("/"):
            clean = target.lstrip("/")
            candidates.extend([
                self.source / "web" / "static" / clean,
                self.source / "static" / clean,
                self.docs_root / clean,
                self.source / clean,
            ])
        else:
            candidates.append(note.parent / target)

        expanded: list[Path] = []
        for c in candidates:
            c = c.resolve()
            expanded.append(c)
            if not c.suffix:
                expanded.extend([
                    Path(str(c) + ".md"),
                    Path(str(c) + ".mdx"),
                    c / "index.md",
                    c / "index.mdx",
                ])
        for c in expanded:
            try:
                c.relative_to(self.source)
            except ValueError:
                continue
            if c.exists():
                return c

        # Then resolve using Docusaurus document routes. CEM uses numeric filename/folder
        # prefixes (`01-notes/01-rencontre...`) that disappear from URLs (`notes/rencontre...`).
        route_target = target
        if route_target.endswith((".md", ".mdx")):
            route_target = str(Path(route_target).with_suffix("")).replace(os.sep, "/")
        if route_target.startswith("/"):
            route_key = posixpath.normpath(route_target.lstrip("/"))
        else:
            current_route = self.route_for_note(note)
            route_key = posixpath.normpath(posixpath.join(posixpath.dirname(current_route), route_target))
        route_key = route_key.lstrip("./").strip("/")
        if route_key in self.route_index:
            return self.route_index[route_key]

        # Last resort: unique route basename. Useful for a few hand-written links in older repos.
        base = posixpath.basename(route_key)
        matches = {p for key, p in self.route_index.items() if posixpath.basename(key) == base}
        if len(matches) == 1:
            return next(iter(matches))
        return None

    def resolve_local_reference_from_label(self, note: Path, target: str, label: str) -> Path | None:
        """Repair a narrow class of obvious syllabus route typos using the visible label.

        Some course homepages label a meeting as e.g. ``9.1`` but accidentally link to
        ``cours/r8.3``. When the target basename is an ``rN.N`` meeting route and the label
        starts with another meeting number, try that label-derived route. The repair is used
        only when the original link is unresolved and the derived route actually exists.
        """
        clean_label = re.sub(r"[*_`~]", "", label).strip()
        hint = re.match(r"(\d+\.\d+)\b", clean_label)
        if not hint:
            return None
        target = target.strip()
        base = posixpath.basename(target)
        if not re.fullmatch(r"r\d+\.\d+", base, re.IGNORECASE):
            return None
        corrected = posixpath.join(posixpath.dirname(target), f"r{hint.group(1)}")
        if target.startswith("/") and not corrected.startswith("/"):
            corrected = "/" + corrected
        return self.resolve_local_reference(note, corrected)

    def copy_asset(self, source_file: Path, ctx: NoteContext) -> Path:
        dest_dir = ctx.asset_dir
        dest_dir.mkdir(parents=True, exist_ok=True)
        dest = dest_dir / source_file.name
        if dest.exists() and self._asset_sources.get(dest) not in {None, source_file.resolve()}:
            digest = hashlib.sha1(str(source_file).encode("utf-8")).hexdigest()[:8]
            dest = dest.with_name(f"{dest.stem}-{digest}{dest.suffix}")
        if not dest.exists():
            shutil.copy2(source_file, dest)
            self.report.assets += 1
        self._asset_sources[dest] = source_file.resolve()
        return dest

    def copy_source_asset(self, source_file: Path, ctx: NoteContext) -> Path:
        dest_dir = ctx.asset_dir / "sources"
        dest_dir.mkdir(parents=True, exist_ok=True)
        dest = dest_dir / source_file.name
        if not dest.exists():
            shutil.copy2(source_file, dest)
            self.report.assets += 1
        return dest

    def copy_static_trees(self) -> None:
        for static in (self.source / "web" / "static", self.source / "static"):
            if static.is_dir():
                target = self.output_root / "_assets" / "_static"
                shutil.copytree(static, target, dirs_exist_ok=True)

    def handle_unknown_components(self, text: str, ctx: NoteContext) -> str:
        known_htmlish = {
            "Row", "Column", "Highlight", "NonVoyant", "Tabs", "TabItem", "Video",
            "JavaScriptConsole", "ReactPreview", "DataFlowPlayer", "GHCode", "Quiz",
            "DocsViewer", "MainDocsGrid", "MainDocsCalendar", "WeeklySchedule",
            "ConsoleWindow", "GithubDownload", "SlideImage", "SlidePage",
            "ExampleFrame", "ExamplePeek", "TopicBadges", "KeyPoint",
            "ProjectStepHero", "ProjectJourney", "StyleSwitcher", "Feedback", "PlanDeCoursMenu",
        }

        # Never interpret fenced code OR inline code (`useState<T>()`) as MDX components.
        # Ignore generic type identifiers that can otherwise look like MDX tags: T,
        # TKey, Int, String, IActionResult, HTMLInputElement, etc.
        chunks = re.split(r"(```.*?```|`[^`\n]*`)", text, flags=re.DOTALL)
        for i in range(0, len(chunks), 2):
            chunk = chunks[i]
            # Inventory first, mutate second. That keeps report counts accurate even for nested JSX.
            counts = Counter(re.findall(r"(?<!\\)<([A-Z][A-Za-z0-9_]*)\b", chunk))
            counts = Counter({name: count for name, count in counts.items() if name not in known_htmlish})
            for name, count in sorted(counts.items()):
                self.report.unknown_components[name] += count
                self.report.warn(ctx.rel_note, f"Composant MDX non reconnu: {name}")

            for name in sorted(counts, key=len, reverse=True):
                self_closing = re.compile(rf"<{re.escape(name)}\b.*?/>", re.DOTALL)
                chunk = self_closing.sub(
                    lambda m, n=name: self.callout(
                        "warning", f"Composant `{n}` non converti",
                        "Le contenu dynamique de ce composant n'a pas été supprimé silencieusement; "
                        "consulte le rapport de conversion et la source officielle si nécessaire."
                    ),
                    chunk,
                )
                chunk = re.sub(
                    rf"<{re.escape(name)}\b[^>]*>",
                    self.callout("warning", f"Composant `{name}` simplifié", "Le contenu interne est conservé ci-dessous.") + "\n",
                    chunk,
                )
                chunk = re.sub(rf"</{re.escape(name)}>", "", chunk)
            chunks[i] = chunk
        return "".join(chunks)

    def relative_markdown_link(self, from_note: Path, to_note: Path, label: str) -> str:
        rel = os.path.relpath(to_note, from_note.parent).replace(os.sep, "/")
        return f"[{label}](<{rel}>)"

    def add_navigation_footer(self, text: str, ctx: NoteContext) -> str:
        """Add a compact Docusaurus-like previous/next footer.

        Previous and next remain the only card-like controls. The course index
        is a quiet text link above them so navigation does not turn into a
        three-card dashboard.
        """
        home = self.output_root / "00 - Navigation.md"
        note = ctx.source_note.resolve()
        prev: Path | None = None
        nxt: Path | None = None

        if note in self.navigation_sequence:
            idx = self.navigation_sequence.index(note)
            if idx > 0:
                prev = self.output_root / self.output_map[self.navigation_sequence[idx - 1]]
            if idx + 1 < len(self.navigation_sequence):
                nxt = self.output_root / self.output_map[self.navigation_sequence[idx + 1]]
        elif not self.sidebar_entries:
            return text

        body: list[str] = [
            "> [!cem-nav]",
            f"> {self.relative_markdown_link(ctx.output_note, home, '⌂ Sommaire')}",
        ]

        if prev is not None:
            prev_label = prev.stem
            body.extend([
                ">",
                "> > [!cem-prev] Précédent",
                f"> > {self.relative_markdown_link(ctx.output_note, prev, f'← {prev_label}')}",
            ])

        if nxt is not None:
            next_label = nxt.stem
            body.extend([
                ">",
                "> > [!cem-next] Suivant",
                f"> > {self.relative_markdown_link(ctx.output_note, nxt, f'{next_label} →')}",
            ])

        return text.rstrip() + "\n\n---\n\n" + "\n".join(body) + "\n"

    @staticmethod
    def ensure_course_cssclass(text: str) -> str:
        """Attach a CSS class to imported notes so visual tweaks stay course-local."""
        cls = "cem-course"
        if not text.startswith("---"):
            return f"---\ncssclasses:\n  - {cls}\n---\n\n{text.lstrip()}"

        end = text.find("\n---", 3)
        if end < 0:
            return text
        fm = text[3:end]
        if re.search(rf"(?m)^\s*-\s*{re.escape(cls)}\s*$", fm):
            return text
        if re.search(rf"(?m)^cssclasses\s*:\s*\[[^\]]*\b{re.escape(cls)}\b[^\]]*\]\s*$", fm):
            return text

        scalar = re.search(r"(?m)^cssclasses\s*:\s*([^\n\[]+?)\s*$", fm)
        if scalar:
            existing = scalar.group(1).strip().strip("'\"")
            replacement = f"cssclasses:\n  - {existing}\n  - {cls}" if existing else f"cssclasses:\n  - {cls}"
            fm = fm[:scalar.start()] + replacement + fm[scalar.end():]
            return "---" + fm + text[end:]

        inline = re.search(r"(?m)^cssclasses\s*:\s*\[([^\]]*)\]\s*$", fm)
        if inline:
            inside = inline.group(1).strip()
            replacement = f"cssclasses: [{inside}, {cls}]" if inside else f"cssclasses: [{cls}]"
            fm = fm[:inline.start()] + replacement + fm[inline.end():]
            return "---" + fm + text[end:]

        block = re.search(r"(?m)^cssclasses\s*:\s*$", fm)
        if block:
            insert_at = block.end()
            fm = fm[:insert_at] + f"\n  - {cls}" + fm[insert_at:]
            return "---" + fm + text[end:]

        fm = fm.rstrip() + f"\ncssclasses:\n  - {cls}\n"
        return "---" + fm + text[end:]

    @staticmethod
    def callout(kind: str, title: str, body: str, collapsible: bool = False) -> str:
        body = body.strip()
        marker = "-" if collapsible else ""
        lines = [f"> [!{kind}]{marker} {title}"]
        if body:
            lines.extend("> " + line if line else ">" for line in body.splitlines())
        return "\n".join(lines)

    @staticmethod
    def normalize_indentation(text: str) -> str:
        lines = text.expandtabs(4).splitlines()
        nonblank = [len(line) - len(line.lstrip()) for line in lines if line.strip()]
        amount = min(nonblank) if nonblank else 0
        return "\n".join(line[amount:] if len(line) >= amount else line for line in lines)

    @staticmethod
    def code_block(source: Path, text: str) -> str:
        lang = CODE_LANG.get(source.suffix.lower(), source.suffix.lstrip("."))
        fence = "```"
        if "```" in text:
            fence = "````"
        return f"{fence}{lang}\n{text.rstrip()}\n{fence}"

    @staticmethod
    def cleanup_whitespace(text: str) -> str:
        # An empty Mermaid fence is valid source Markdown but Obsidian renders it as
        # a loud parser error. It conveys no diagram, so remove only truly empty fences.
        text = re.sub(
            r"(?ms)^[ \t]*```mermaid[ \t]*\n(?:[ \t]*\n)*[ \t]*```[ \t]*(?:\n|$)",
            "",
            text,
        )
        text = re.sub(r"[ \t]+\n", "\n", text)
        text = re.sub(r"\n{4,}", "\n\n\n", text)
        return text.strip() + "\n"

    @staticmethod
    def sidebar_section_label(section: str) -> str:
        labels = {
            "docs": "Notes de cours",
            "cours": "Cours",
            "tp": "Travaux pratiques",
            "recettes": "Recettes",
            "labos": "Laboratoires",
            "labo": "Laboratoires",
            "autres": "Autres",
            "angular": "Angular",
        }
        return labels.get(section.lower(), section.replace("_", " ").replace("-", " ").title())

    def wikilink_from_root(self, target: Path, label: str) -> str:
        rel = target.relative_to(self.output_root).with_suffix("")
        return f"[[{str(rel).replace(os.sep, '/')}|{label}]]"

    def write_navigation(self) -> None:
        """Create a human-friendly course index based on the real Docusaurus sidebars."""
        nav = self.output_root / "00 - Navigation.md"
        lines = [
            "# 🧭 Navigation du cours",
            "",
            "> [!info] Copie locale Obsidian",
            "> Cette page est générée à partir de la navigation Docusaurus du cours. Les intitulés et l’ordre suivent le site officiel lorsque `sidebars.js` les fournit.",
            "",
        ]
        referenced: set[Path] = set()
        if self.sidebar_entries:
            current_section: str | None = None
            for entry in self.sidebar_entries:
                if current_section != entry.section:
                    current_section = entry.section
                    lines += [f"## {self.sidebar_section_label(current_section)}", ""]
                if entry.source_note is None or entry.source_note.resolve() not in self.output_map:
                    lines.append(f"- {entry.label} *(page non résolue)*")
                    continue
                target = self.output_root / self.output_map[entry.source_note.resolve()]
                referenced.add(entry.source_note.resolve())
                lines.append(f"- {self.wikilink_from_root(target, entry.label)}")
            lines.append("")
        else:
            lines += ["## Documents", ""]

        # Keep documents that are intentionally outside the sidebar reachable too.
        extras = [n for n in self.content_notes if n.resolve() not in referenced]
        if extras:
            lines += ["## Autres documents", ""]
            for note in extras:
                target = self.output_root / self.output_map[note.resolve()]
                lines.append(f"- {self.wikilink_from_root(target, self.extract_document_title(note))}")
            lines.append("")

        nav.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")

    def write_report(self) -> None:
        """Write diagnostics outside the generated notes tree.

        Reports are development artifacts, not course content.  Keeping them in a
        separate directory leaves the Obsidian vault clean while preserving all
        information needed to improve the converter.
        """
        report_dir = self.report_dir
        report_dir.mkdir(parents=True, exist_ok=True)
        lines = [
            "# Rapport d'import CEM → Obsidian",
            "",
            f"- Source : `{self.report_source}`",
            f"- Dossier docs détecté : `{self.docs_root.relative_to(self.source)}`",
            f"- Notes converties : **{self.report.notes}**",
            f"- Assets copiés : **{self.report.assets}**",
            f"- Snippets incorporés : **{self.report.snippets_inlined}**",
            f"- DataFlow → Mermaid : **{self.report.dataflows}**",
            f"- Vidéos transformées en liens : **{self.report.videos}**",
            f"- Admonitions → callouts : **{self.report.admonitions}**",
            f"- Rangées multi-colonnes : **{self.report.layout_rows}**",
            f"- ReactPreview → Code Playground : **{self.report.react_playgrounds}**",
            "",
            "> [!info] Principe de sécurité",
            "> L'importeur ne supprime jamais volontairement un composant MDX inconnu sans le signaler.",
            "> Les composants non pris en charge et les liens locaux non résolus sont listés ci-dessous.",
            "",
        ]
        if self.report.unknown_components:
            lines += ["## Composants MDX inconnus", ""]
            for name, count in self.report.unknown_components.most_common():
                lines.append(f"- `{name}` : {count} occurrence(s)")
            lines.append("")
        if self.report.unresolved_local_links:
            lines += ["## Liens locaux non résolus", ""]
            for note, target in self.report.unresolved_local_links:
                lines.append(f"- `{note}` → `{target}`")
            lines.append("")
        if self.report.warnings:
            lines += ["## Avertissements", ""]
            for note, msg in self.report.warnings:
                lines.append(f"- `{note}` : {msg}")
            lines.append("")
        if not self.report.unknown_components and not self.report.unresolved_local_links and not self.report.warnings:
            lines += ["## Résultat", "", "Aucun problème de conversion détecté. ✅", ""]
        (report_dir / "report.md").write_text("\n".join(lines), encoding="utf-8")

        # Machine-readable companion used by the interactive launcher to build
        # an aggregate summary when several course repositories are imported.
        # Warnings generated solely to mirror an unknown-component entry are
        # excluded from the warning count so the same issue is not counted twice.
        independent_warnings = [
            (note, message)
            for note, message in self.report.warnings
            if not message.startswith("Composant MDX non reconnu:")
        ]
        unknown_occurrences = sum(self.report.unknown_components.values())
        unresolved_count = len(self.report.unresolved_local_links)
        warning_count = len(independent_warnings)
        report_json = {
            "source": str(self.source),
            "docs_root": str(self.docs_root.relative_to(self.source)),
            "stats": {
                "notes": self.report.notes,
                "assets": self.report.assets,
                "snippets_inlined": self.report.snippets_inlined,
                "dataflows": self.report.dataflows,
                "videos": self.report.videos,
                "admonitions": self.report.admonitions,
                "layout_rows": self.report.layout_rows,
                "react_playgrounds": self.report.react_playgrounds,
            },
            "issues": {
                "count": unknown_occurrences + unresolved_count + warning_count,
                "unknown_component_occurrences": unknown_occurrences,
                "unknown_component_types": len(self.report.unknown_components),
                "unknown_components": dict(self.report.unknown_components),
                "unresolved_local_links": unresolved_count,
                "warnings": warning_count,
            },
            "details": {
                "unknown_components": dict(self.report.unknown_components),
                "unresolved_local_links": [
                    {"note": note, "target": target}
                    for note, target in self.report.unresolved_local_links
                ],
                "warnings": [
                    {"note": note, "message": message}
                    for note, message in independent_warnings
                ],
            },
        }
        (report_dir / "report.json").write_text(
            json.dumps(report_json, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )


def is_git_url(value: str) -> bool:
    return value.startswith(("https://", "http://", "git@", "ssh://")) or value.endswith(".git")


def clone_repo(url: str, ref: str | None) -> tuple[tempfile.TemporaryDirectory, Path]:
    temp = tempfile.TemporaryDirectory(prefix="cem-obsidian-")
    dest = Path(temp.name) / "repo"
    cmd = ["git", "clone", "--depth", "1"]
    if ref:
        cmd += ["--branch", ref]
    cmd += [url, str(dest)]
    try:
        subprocess.run(cmd, check=True)
    except (subprocess.CalledProcessError, FileNotFoundError) as exc:
        temp.cleanup()
        raise RuntimeError(f"Impossible de cloner le repo avec Git: {exc}") from exc
    return temp, dest


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Convertit un repo de cours Docusaurus/MDX du CEM en dossier prêt pour Obsidian."
    )
    parser.add_argument("--version", action="version", version=f"cem-obsidian-importer {VERSION}")
    parser.add_argument("repo", help="Chemin local du repo OU URL Git à cloner.")
    parser.add_argument("-o", "--output", type=Path, default=Path("obsidian-export"),
                        help="Dossier parent de sortie (défaut: ./obsidian-export).")
    parser.add_argument("--course-name", help="Nom du dossier de cours dans la sortie.")
    parser.add_argument("--ref", help="Branche/tag à cloner lorsque repo est une URL.")
    parser.add_argument("--force", action="store_true", help="Remplace la sortie existante.")
    parser.add_argument("--copy-all-static", action="store_true",
                        help="Copie aussi tout web/static ou static sous _assets/_static.")
    parser.add_argument("--report-dir", type=Path,
                        help="Dossier où écrire report.md/report.json (hors des notes).")
    parser.add_argument("--report-source",
                        help="Libellé de source à afficher dans le rapport (ex. URL du repo).")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    temp: tempfile.TemporaryDirectory | None = None
    try:
        if is_git_url(args.repo):
            temp, source = clone_repo(args.repo, args.ref)
            inferred_name = Path(urlparse(args.repo).path).name.removesuffix(".git") or "course"
        else:
            source = Path(args.repo).expanduser().resolve()
            inferred_name = source.name
            if not source.is_dir():
                raise FileNotFoundError(f"Repo local introuvable: {source}")

        importer = CEMImporter(
            source=source,
            output_parent=args.output.expanduser(),
            course_name=args.course_name or inferred_name,
            force=args.force,
            copy_all_static=args.copy_all_static,
            report_dir=args.report_dir,
            report_source=args.report_source,
        )
        result = importer.run()
        print(f"✅ Import terminé: {result}")
        print(f"📄 Rapport: {importer.report_dir / 'report.md'}")
        return 0
    except Exception as exc:
        print(f"❌ {exc}", file=sys.stderr)
        return 1
    finally:
        if temp is not None:
            temp.cleanup()


if __name__ == "__main__":
    raise SystemExit(main())

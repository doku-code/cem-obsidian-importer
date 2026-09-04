from pathlib import Path
import json
import re
import tempfile
import unittest
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import cem_to_obsidian as module
import cem_importer as manager
from cem_to_obsidian import CEMImporter


class ImporterConversionTests(unittest.TestCase):
    @staticmethod
    def converted(importer: CEMImporter, source_note: Path, result: Path) -> str:
        return (result / importer.output_map[source_note.resolve()]).read_text(encoding="utf-8")

    @staticmethod
    def report(importer: CEMImporter) -> str:
        return (importer.report_dir / "report.md").read_text(encoding="utf-8")


    def test_supported_top_level_sections_are_normalized_conservatively(self):
        cases = {
            "01-cours": "Cours",
            "01-notes": "Cours",
            "02-tp": "TP",
            "04-tps": "TP",
            "03-laboratoire": "Laboratoire",
            "03-labos": "Laboratoire",
            "04-laboratoires": "Laboratoire",
            "03-recettes": "Recettes",
            "04-aidememoire": "Aide-mémoire",
            "04-solution": "Solution",
            "05-extra": "Extra",
            "06-defis": "Défis",
            "03-autres": "Autres",
            "02-info": "Informations",
            "03-exercices": "Exercices",
            "05-anciens": "Archives",
            "tp_archives_idees": "Archives",
            "04-angular": "Angular",
            "03-python": "Python",
            "04-colab": "Colab",
            "05-numpykeras": "NumPy & Keras",
            "06-googlecloud": "Google Cloud",
            "03-projet-web": "Projet Web",
            "04-dans-autobus": "Dans l'autobus",
        }
        for source, expected in cases.items():
            with self.subTest(source=source):
                self.assertEqual(CEMImporter.canonical_section_name(source), expected)

    def test_output_uses_canonical_section_names_but_keeps_note_numbering(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td) / "4W6-WebServices"
            notes = root / "web" / "docs" / "01-notes"
            labs = root / "web" / "docs" / "03-labos"
            notes.mkdir(parents=True)
            labs.mkdir(parents=True)
            lesson = notes / "01-intro.md"
            lab = labs / "02-api.md"
            lesson.write_text("# Introduction\n", encoding="utf-8")
            lab.write_text("# API\n", encoding="utf-8")

            importer = CEMImporter(root, Path(td) / "out")
            self.assertEqual(importer.output_map[lesson.resolve()].parent, Path("Cours"))
            self.assertEqual(importer.output_map[lab.resolve()].parent, Path("Laboratoire"))
            self.assertTrue(importer.output_map[lesson.resolve()].name.startswith("01 - "))
            self.assertTrue(importer.output_map[lab.resolve()].name.startswith("02 - "))

    def test_unknown_top_level_section_keeps_legacy_prefix(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td) / "future-course"
            docs = root / "web" / "docs" / "07-nouveau-truc"
            docs.mkdir(parents=True)
            note = docs / "01-demo.md"
            note.write_text("# Démo\n", encoding="utf-8")
            importer = CEMImporter(root, Path(td) / "out")
            self.assertEqual(
                importer.output_map[note.resolve()].parent,
                Path("07 - Nouveau truc"),
            )

    def test_canonical_section_collision_falls_back_instead_of_merging(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td) / "future-course"
            tp1 = root / "web" / "docs" / "02-tp"
            tp2 = root / "web" / "docs" / "04-tps"
            tp1.mkdir(parents=True)
            tp2.mkdir(parents=True)
            n1 = tp1 / "01-a.md"
            n2 = tp2 / "01-b.md"
            n1.write_text("# A\n", encoding="utf-8")
            n2.write_text("# B\n", encoding="utf-8")
            importer = CEMImporter(root, Path(td) / "out")
            self.assertEqual(importer.output_map[n1.resolve()].parent, Path("02 - TP"))
            self.assertEqual(importer.output_map[n2.resolve()].parent, Path("04 - TP"))
            self.assertTrue(any("fusion ambiguë" in msg for _, msg in importer.report.warnings))

    def test_representative_4w6_mdx(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td) / "4W6-WebServices"
            docs = root / "web" / "docs" / "01-notes"
            assets = docs / "_01-demo"
            docs.mkdir(parents=True)
            assets.mkdir()
            (assets / "img.png").write_bytes(b"fake-png")
            (assets / "demo.js").write_text("console.log('allo');\n", encoding="utf-8")
            spec = {
                "nodes": [{"id": "browser", "text": "Navigateur"}, {"id": "api", "text": "Serveur"}],
                "packets": [{"id": "req", "kind": "http_packet", "packet_content": {"header": "GET /users"}}],
                "timeline": [{"type": "move", "object": "req", "from": "browser", "to": "api"}],
            }
            (assets / "flow.ts").write_text("export default " + json.dumps(spec) + ";", encoding="utf-8")
            note = docs / "01-demo.mdx"
            note.write_text(
                """---\ntitle: Démo\n---\n\nimport demo from '!!raw-loader!./_01-demo/demo.js';\nimport flow from './_01-demo/flow';\n\n:::warning Attention\nImportant\n:::\n\n<center>![image](./_01-demo/img.png)</center>\n\n<JavaScriptConsole code={demo} />\n\n<DataFlowPlayer spec={flow} theme=\"auto\" />\n\n<NonVoyant>Le navigateur appelle le serveur.</NonVoyant>\n""",
                encoding="utf-8",
            )
            importer = CEMImporter(root, Path(td) / "out")
            result = importer.run()
            converted = self.converted(importer, note, result)
            self.assertIn("> [!warning] Attention", converted)
            self.assertIn("console.log('allo');", converted)
            self.assertIn("```mermaid", converted)
            self.assertIn("> [!info]- Description de la démonstration", converted)
            self.assertIn("_assets", converted)
            self.assertTrue((importer.report_dir / "report.md").exists())
            self.assertFalse((result / "_assets" / "_conversion").exists())
            report_json = json.loads(
                (importer.report_dir / "report.json").read_text(encoding="utf-8")
            )
            self.assertIn("issues", report_json)
            self.assertIn("details", report_json)
            self.assertEqual(report_json["issues"]["count"], 0)

    def test_3m5_layout_and_video(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td) / "3M5-Intro-Mobile"
            docs = root / "web" / "docs" / "01-cours"
            docs.mkdir(parents=True)
            note = docs / "10.1-demo.mdx"
            note.write_text(
                """# Démo\n\n<Row>\n<Column>\n:::warning Avant la séance (2h)\n- Lire la doc\n<Video url=\"https://youtu.be/example\" />\n:::\n</Column>\n<Column>\n:::info À faire\n- Exercice\n:::\n</Column>\n</Row>\n""",
                encoding="utf-8",
            )
            importer = CEMImporter(root, Path(td) / "out")
            result = importer.run()
            converted = self.converted(importer, note, result)
            self.assertNotIn("<Row>", converted)
            self.assertIn("> [!warning] Avant la séance (2h)", converted)
            self.assertIn("![](https://www.youtube.com/watch?v=example)", converted)
            self.assertIn("> [!cem-columns]", converted)
            self.assertIn(">>> [!warning] Avant la séance (2h)", converted)
            self.assertNotIn("Lecteur YouTube intégré", converted)

    def test_3w6_static_asset_resolution(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td) / "3W6-Web-Transactionelle"
            docs = root / "web" / "docs" / "01-cours"
            static_img = root / "web" / "static" / "img" / "Modeles"
            docs.mkdir(parents=True)
            static_img.mkdir(parents=True)
            (static_img / "Modele_classe.png").write_bytes(b"fake")
            note = docs / "04-rencontre4.md"
            note.write_text("# Rencontre 4\n\n![Diagramme](../../static/img/Modeles/Modele_classe.png)\n", encoding="utf-8")
            importer = CEMImporter(root, Path(td) / "out")
            result = importer.run()
            converted = self.converted(importer, note, result)
            self.assertIn("_assets", converted)
            self.assertIn("Modele_classe.png", converted)

    def test_unknown_component_is_reported(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td) / "course"
            docs = root / "web" / "docs"
            docs.mkdir(parents=True)
            note = docs / "x.mdx"
            note.write_text("# X\n\n<MagicThing foo=\"bar\" />\n", encoding="utf-8")
            importer = CEMImporter(root, Path(td) / "out")
            result = importer.run()
            converted = self.converted(importer, note, result)
            self.assertIn("Composant `MagicThing` non converti", converted)
            self.assertIn("`MagicThing`", self.report(importer))

    def test_docusaurus_routes_follow_renamed_output(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td) / "4W6-WebServices"
            notes = root / "web" / "docs" / "01-notes"
            labs = root / "web" / "docs" / "03-labos"
            notes.mkdir(parents=True)
            labs.mkdir(parents=True)
            course = notes / "01-rencontre1.1.mdx"
            course.write_text("---\ntitle: 1.1 - Intro\n---\n# Cours\n", encoding="utf-8")
            lab = labs / "01-labo1.1.md"
            lab.write_text("[Créer un projet](/notes/rencontre1.1#creer-un-projet)\n", encoding="utf-8")
            importer = CEMImporter(root, Path(td) / "out")
            result = importer.run()
            converted = self.converted(importer, lab, result)
            target_name = importer.output_map[course.resolve()].name
            self.assertIn(target_name, converted)
            self.assertNotIn("/notes/rencontre1.1", self.report(importer))

    def test_generics_are_not_mdx_components(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td) / "course"
            docs = root / "web" / "docs"
            docs.mkdir(parents=True)
            note = docs / "x.md"
            note.write_text(r"Use `useState<T>()`, `Array<Int>` et List\<Double\>, Array\<String\>.\n", encoding="utf-8")
            importer = CEMImporter(root, Path(td) / "out")
            result = importer.run()
            report = self.report(importer)
            for name in ("T", "Int", "Double", "String"):
                self.assertNotIn(f"`{name}`", report)

    def test_underscore_number_prefix_routes(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td) / "3W6-Web-Transactionelle"
            courses = root / "web" / "docs" / "01-cours"
            others = root / "web" / "docs" / "03-autres"
            courses.mkdir(parents=True)
            others.mkdir(parents=True)
            github = others / "02_gitHub.md"
            fork = others / "03_fork.md"
            github.write_text("# GitHub\n", encoding="utf-8")
            fork.write_text("# Fork\n", encoding="utf-8")
            note = courses / "01-rencontre1.md"
            note.write_text("[GitHub](/autres/gitHub) et [Fork](/autres/fork)\n", encoding="utf-8")
            importer = CEMImporter(root, Path(td) / "out")
            result = importer.run()
            converted = self.converted(importer, note, result)
            self.assertIn(importer.output_map[github.resolve()].name, converted)
            self.assertIn(importer.output_map[fork.resolve()].name, converted)
            self.assertNotIn("Liens locaux non résolus", self.report(importer))

    def test_ghcode_becomes_local_code(self):
        class FakeResponse:
            def __enter__(self): return self
            def __exit__(self, *args): return False
            def read(self): return b"line1\nline2\nline3\nline4\n"

        old_urlopen = module.urlopen
        module.urlopen = lambda *args, **kwargs: FakeResponse()
        try:
            with tempfile.TemporaryDirectory() as td:
                root = Path(td) / "3M5-Intro-Mobile"
                docs = root / "web" / "docs" / "02-recettes"
                docs.mkdir(parents=True)
                note = docs / "demo.mdx"
                note.write_text('<GHCode repo="3N5-Prog3" filePath="code/Main.kt" startLine="2" endLine="3" />\n', encoding="utf-8")
                importer = CEMImporter(root, Path(td) / "out")
                result = importer.run()
                converted = self.converted(importer, note, result)
                self.assertIn("line2\nline3", converted)
                self.assertNotIn("<GHCode", converted)
                self.assertNotIn("Code GitHub copié localement", converted)
                self.assertNotIn("Source originale :", converted)
                self.assertTrue(any(p.name == "Main.kt" for p in (result / "_assets").rglob("Main.kt")))
        finally:
            module.urlopen = old_urlopen

    def test_quiz_is_converted(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td) / "4W6-WebServices"
            docs = root / "web" / "docs" / "01-notes"
            assets = docs / "_03-demo"
            docs.mkdir(parents=True)
            assets.mkdir()
            (assets / "q1.md").write_text("Que vaut `x` ?", encoding="utf-8")
            (assets / "quiz.ts").write_text(
                'import q1 from "!!raw-loader!./q1.md";\nconst quiz = { titre: "Test", questions: [{ texte: q1, choix: ["1", "2"], reponse: 1, duree: 30 }] };\nexport default quiz;\n',
                encoding="utf-8",
            )
            note = docs / "03-demo.md"
            note.write_text("import quiz from './_03-demo/quiz';\n\n<Quiz file={quiz} />\n", encoding="utf-8")
            importer = CEMImporter(root, Path(td) / "out")
            result = importer.run()
            converted = self.converted(importer, note, result)
            self.assertIn("### 🧠 Test", converted)
            self.assertIn("Que vaut `x` ?", converted)
            self.assertIn("[!success]- Réponse", converted)
            self.assertNotIn("<Quiz", converted)

    def test_docsviewer_homepage_becomes_local_index(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td) / "4W6-WebServices"
            docs = root / "web" / "docs"
            (docs / "01-notes").mkdir(parents=True)
            (docs / "02-tp").mkdir(parents=True)
            (docs / "01-notes" / "01-demo.md").write_text("# Demo", encoding="utf-8")
            note = docs / "accueil.mdx"
            note.write_text("# Accueil\n\n<DocsViewer tabs={[{ component: <MainDocsGrid /> }]} defaultTabId=\"grid\" />\n", encoding="utf-8")
            importer = CEMImporter(root, Path(td) / "out")
            result = importer.run()
            converted = self.converted(importer, note, result)
            self.assertIn("Tableau de bord du site simplifié", converted)
            self.assertNotIn("<DocsViewer", converted)

    def test_indented_docusaurus_code_fence_renders_as_real_fence(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td) / "4W6-WebServices"
            docs = root / "web" / "docs" / "01-notes"
            docs.mkdir(parents=True)
            note = docs / "01-demo.md"
            note.write_text(
                """# Démo\n\n<Tabs>\n<TabItem value=\"a\" label=\"Sans public\">\n\n    ```js showLineNumbers\n    class Cat{\n        name: string;\n    }\n    ```\n\n</TabItem>\n</Tabs>\n""",
                encoding="utf-8",
            )
            importer = CEMImporter(root, Path(td) / "out")
            result = importer.run()
            converted = self.converted(importer, note, result)
            self.assertIn('```js group:cem-tabs-1 tab:"Sans public"', converted)
            self.assertIn("class Cat{\n    name: string;\n}", converted)
            self.assertNotIn("```js showLineNumbers", converted)
            self.assertNotIn("    ```js", converted)

    def test_sidebar_titles_drive_filenames_and_navigation(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td) / "4W6-WebServices"
            docs = root / "web" / "docs" / "01-notes"
            docs.mkdir(parents=True)
            (root / "web" / "sidebars.js").write_text(
                '''const sidebars = {\n  docs: [\n    { type: "doc", label: "1.1 - Intro à React / Next.js 🏁", id: "notes/rencontre1.1" },\n    { type: "doc", label: "1.2 - Composant dynamique 🏃", id: "notes/rencontre1.2" },\n  ],\n};''',
                encoding="utf-8",
            )
            n1 = docs / "01-rencontre1.1.mdx"
            n2 = docs / "02-rencontre1.2.md"
            n1.write_text("# Whatever\n", encoding="utf-8")
            n2.write_text("# Whatever 2\n", encoding="utf-8")
            importer = CEMImporter(root, Path(td) / "out")
            result = importer.run()
            p1 = importer.output_map[n1.resolve()]
            p2 = importer.output_map[n2.resolve()]
            self.assertEqual(p1.parent.name, "Cours")
            self.assertTrue(p1.name.startswith("1.1 - Intro à React"))
            self.assertTrue(p2.name.startswith("1.2 - Composant dynamique"))
            nav = (result / "00 - Navigation.md").read_text(encoding="utf-8")
            self.assertLess(nav.index("1.1 - Intro"), nav.index("1.2 - Composant"))
            self.assertIn("## Cours", nav)

    def test_obsidian_angle_bracket_link_is_not_mistaken_for_mdx(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td) / "course"
            docs = root / "web" / "docs" / "01-cours"
            docs.mkdir(parents=True)
            source = docs / "01-source.md"
            target = docs / "02-target.md"
            source.write_text("# Source\n\n[Voir la navigation](02-target.md)\n", encoding="utf-8")
            target.write_text("# Navigation avancée\n", encoding="utf-8")

            importer = CEMImporter(root, Path(td) / "out")
            result = importer.run()
            converted = self.converted(importer, source, result)

            # The rewritten destination contains spaces and is therefore wrapped in <...>.
            self.assertIn("](<", converted)
            self.assertIn("Navigation avancée.md", converted)
            self.assertFalse(importer.report.unknown_components)
            self.assertNotIn("Composant `Navigation`", converted)

    def test_helper_markdown_folders_do_not_pollute_tree(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td) / "course"
            docs = root / "web" / "docs" / "01-notes"
            helper = docs / "_03-rencontre2.1"
            docs.mkdir(parents=True)
            helper.mkdir()
            note = docs / "03-rencontre2.1.md"
            note.write_text("# Cours\n", encoding="utf-8")
            (helper / "question1.md").write_text("Question helper", encoding="utf-8")
            importer = CEMImporter(root, Path(td) / "out")
            result = importer.run()
            visible_md = [p for p in result.rglob("*.md") if "_assets" not in p.parts]
            self.assertEqual(len([p for p in visible_md if p.name != "00 - Navigation.md"]), 1)
            self.assertFalse(any("_03-rencontre2.1" in str(p.relative_to(result)) for p in visible_md))


    def test_docusaurus_bracket_title_admonition_becomes_callout(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td) / "3M5-Intro-Mobile"
            docs = root / "web" / "docs" / "01-cours"
            docs.mkdir(parents=True)
            note = docs / "1.1-accueil.md"
            note.write_text(
                "# Accueil\n\n:::info[Séance 1]\n\n- Mettre en place un projet Kotlin\n- Commencer les exercices\n\n:::\n",
                encoding="utf-8",
            )
            importer = CEMImporter(root, Path(td) / "out")
            result = importer.run()
            converted = self.converted(importer, note, result)
            self.assertIn("> [!info] Séance 1", converted)
            self.assertIn("> - Mettre en place un projet Kotlin", converted)
            self.assertNotIn(":::info", converted)

    def test_code_comparison_tabs_become_codeblock_customizer_group(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td) / "3M5-Intro-Mobile"
            docs = root / "web" / "docs" / "01-cours"
            docs.mkdir(parents=True)
            note = docs / "tabs.md"
            note.write_text(
                """# Comparaison\n\n<Tabs>\n<TabItem value="a" label="AndroidView">\n\nUne première manière.\n\n```kotlin\nAndroidView(factory = {})\n```\n\n</TabItem>\n<TabItem value="b" label="factory">\n\nUne autre manière.\n\n```kotlin\nfactory = {}\n```\n\n</TabItem>\n</Tabs>\n""",
                encoding="utf-8",
            )
            importer = CEMImporter(root, Path(td) / "out")
            result = importer.run()
            converted = self.converted(importer, note, result)
            self.assertIn('```kotlin group:cem-tabs-1 tab:"AndroidView"', converted)
            self.assertIn('```kotlin group:cem-tabs-1 tab:"factory"', converted)
            self.assertIn('> [!note]- AndroidView — explication', converted)
            self.assertNotIn("<Tabs>", converted)
            self.assertNotIn("#### AndroidView", converted)

    def test_complex_tabs_fall_back_without_losing_content(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td) / "course"
            docs = root / "web" / "docs"
            docs.mkdir(parents=True)
            note = docs / "tabs.md"
            note.write_text(
                """<Tabs>\n<TabItem label="A">Texte sans code.</TabItem>\n<TabItem label="B">Autre texte.</TabItem>\n</Tabs>\n""",
                encoding="utf-8",
            )
            importer = CEMImporter(root, Path(td) / "out")
            result = importer.run()
            converted = self.converted(importer, note, result)
            self.assertIn("#### A", converted)
            self.assertIn("Texte sans code.", converted)
            self.assertIn("#### B", converted)
            self.assertIn("Autre texte.", converted)

    def test_vimeo_video_gets_inline_player(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td) / "course"
            docs = root / "web" / "docs"
            docs.mkdir(parents=True)
            note = docs / "video.md"
            note.write_text('<Video url="https://vimeo.com/123456789" />\n', encoding="utf-8")
            importer = CEMImporter(root, Path(td) / "out")
            result = importer.run()
            converted = self.converted(importer, note, result)
            self.assertIn('src="https://player.vimeo.com/video/123456789"', converted)
            self.assertIn("allowfullscreen", converted)

    def test_new_cem_component_family_is_safely_converted(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td) / "z03"
            docs = root / "web" / "docs"
            static = root / "web" / "static" / "examples"
            pdfdir = root / "web" / "static" / "pdf"
            docs.mkdir(parents=True)
            static.mkdir(parents=True)
            pdfdir.mkdir(parents=True)
            (static / "demo.html").write_text("<h1>Demo</h1>", encoding="utf-8")
            (pdfdir / "plan.pdf").write_bytes(b"pdf")
            note = docs / "x.mdx"
            note.write_text(
                """# X\n\n<ConsoleWindow title=\"Terminal\" language=\"bash\">echo allo</ConsoleWindow>\n\n<SlideImage src=\"/examples/demo.png\" alt=\"demo\" />\n\n<ExamplePeek src=\"/examples/demo.html\" title=\"Aperçu\" />\n\n<TopicBadges topics={[\"html\", \"css\"]} />\n\n<KeyPoint type=\"remember\" title=\"Important\">Garde ceci.</KeyPoint>\n\n<ProjectStepHero step={2} />\n<ProjectJourney />\n<StyleSwitcher />\n<Feedback surveyId=\"x\" />\n<PlanDeCoursMenu />\n""",
                encoding="utf-8",
            )
            importer = CEMImporter(root, Path(td) / "out")
            result = importer.run()
            converted = self.converted(importer, note, result)
            self.assertIn("```bash\necho allo\n```", converted)
            self.assertIn("[↗ Ouvrir l'exemple HTML local]", converted)
            self.assertIn("**Repères :** HTML · CSS", converted)
            self.assertIn("> [!tip] Important", converted)
            self.assertIn("Projet Web — étape 2", converted)
            self.assertNotIn("Rétroaction du site", converted)
            self.assertNotIn("Widget de rétroaction en ligne omis", converted)
            self.assertIn("plan.pdf", converted)
            self.assertNotIn("<StyleSwitcher", converted)
            self.assertFalse(importer.report.unknown_components)

    def test_slidepage_sections_are_flattened(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td) / "5W5-Web-Avancee"
            docs = root / "web" / "docs"
            docs.mkdir(parents=True)
            note = docs / "slides.mdx"
            note.write_text("<SlidePage><section>## Titre\n\nTexte</section></SlidePage>", encoding="utf-8")
            importer = CEMImporter(root, Path(td) / "out")
            result = importer.run()
            converted = self.converted(importer, note, result)
            self.assertIn("## Titre", converted)
            self.assertIn("Texte", converted)
            self.assertNotIn("<section>", converted)
            self.assertNotIn("<SlidePage>", converted)


    def test_javascript_console_multiple_files_becomes_tabs_without_converter_note(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td) / "4W6-WebServices"
            docs = root / "web" / "docs" / "01-notes"
            assets = docs / "_01-demo"
            docs.mkdir(parents=True)
            assets.mkdir()
            (assets / "a.js").write_text("console.log('js')\n", encoding="utf-8")
            (assets / "b.ts").write_text("console.log('ts')\n", encoding="utf-8")
            note = docs / "01-demo.mdx"
            note.write_text(
                """import a from '!!raw-loader!./_01-demo/a.js';
import b from '!!raw-loader!./_01-demo/b.ts';

<JavaScriptConsole files={{ "/index.js": a, "/index.ts": b }} />
""",
                encoding="utf-8",
            )
            importer = CEMImporter(root, Path(td) / "out")
            result = importer.run()
            converted = self.converted(importer, note, result)
            self.assertIn('```javascript group:cem-console-1 tab:"/index.js"', converted)
            self.assertIn('```typescript group:cem-console-1 tab:"/index.ts"', converted)
            self.assertNotIn("Exemple exécutable local", converted)
            self.assertNotIn("Avec Execute Code", converted)

    def test_generated_video_and_ghcode_notes_are_not_added(self):
        class FakeResponse:
            def __enter__(self): return self
            def __exit__(self, *args): return False
            def read(self): return b"one\ntwo\nthree\n"

        old_urlopen = module.urlopen
        module.urlopen = lambda *args, **kwargs: FakeResponse()
        try:
            with tempfile.TemporaryDirectory() as td:
                root = Path(td) / "course"
                docs = root / "web" / "docs"
                docs.mkdir(parents=True)
                note = docs / "x.mdx"
                note.write_text(
                    '<Video url="https://youtu.be/dQw4w9WgXcQ" />\n\n'
                    '<GHCode repo="demo" filePath="Main.kt" startLine="1" endLine="2" />\n',
                    encoding="utf-8",
                )
                importer = CEMImporter(root, Path(td) / "out")
                result = importer.run()
                converted = self.converted(importer, note, result)
                self.assertIn("![](https://www.youtube.com/watch?v=dQw4w9WgXcQ)", converted)
                self.assertIn("```kotlin\none\ntwo\n```", converted)
                self.assertNotIn("Vidéo du cours", converted)
                self.assertNotIn("Code GitHub copié localement", converted)
        finally:
            module.urlopen = old_urlopen

    def test_row_column_layout_and_cssclass_are_preserved(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td) / "3M5-Intro-Mobile"
            docs = root / "web" / "docs" / "01-cours"
            docs.mkdir(parents=True)
            note = docs / "1.1-accueil.md"
            note.write_text(
                """---
title: Accueil
---

<Row>
<Column>

## Gauche

Texte gauche.

</Column>
<Column>

## Droite

:::info[Séance 1]
- Exercice
:::

</Column>
</Row>
""",
                encoding="utf-8",
            )
            importer = CEMImporter(root, Path(td) / "out")
            result = importer.run()
            converted = self.converted(importer, note, result)
            self.assertIn("cssclasses:", converted)
            self.assertIn("  - cem-course", converted)
            self.assertIn("> [!cem-columns]", converted)
            self.assertEqual(converted.count(">> [!cem-column]"), 2)
            self.assertIn(">>> [!info] Séance 1", converted)
            self.assertNotIn("<Row>", converted)
            self.assertNotIn("<Column>", converted)

    def test_nonvoyant_is_folded_by_default(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td) / "course"
            docs = root / "web" / "docs"
            docs.mkdir(parents=True)
            note = docs / "x.mdx"
            note.write_text("<NonVoyant>Description secondaire.</NonVoyant>\n", encoding="utf-8")
            importer = CEMImporter(root, Path(td) / "out")
            result = importer.run()
            converted = self.converted(importer, note, result)
            self.assertIn("> [!info]- Description de la démonstration", converted)

    def test_ghcode_ignore_ranges_match_course_component(self):
        class FakeResponse:
            def __enter__(self): return self
            def __exit__(self, *args): return False
            def read(self): return b"1\n2\n3\n4\n5\n6\n"

        old_urlopen = module.urlopen
        module.urlopen = lambda *args, **kwargs: FakeResponse()
        try:
            with tempfile.TemporaryDirectory() as td:
                root = Path(td) / "course"
                docs = root / "web" / "docs"
                docs.mkdir(parents=True)
                note = docs / "x.mdx"
                note.write_text(
                    '<GHCode repo="demo" filePath="Main.kt" startLine="1" endLine="6" ignore="2-4" />\n',
                    encoding="utf-8",
                )
                importer = CEMImporter(root, Path(td) / "out")
                result = importer.run()
                converted = self.converted(importer, note, result)
                self.assertIn("```kotlin\n1\n5\n6\n```", converted)
                self.assertNotIn("\n2\n", converted)
        finally:
            module.urlopen = old_urlopen


    def test_navigation_footer_uses_styled_callout_cards(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td) / "course"
            docs = root / "web" / "docs"
            docs.mkdir(parents=True)
            (root / "web" / "sidebars.js").write_text(
                """const sidebars = {
  docs: [
    { type: "doc", label: "A", id: "a" },
    { type: "doc", label: "B", id: "b" },
    { type: "doc", label: "C", id: "c" },
  ],
};""",
                encoding="utf-8",
            )
            a = docs / "a.md"
            b = docs / "b.md"
            c = docs / "c.md"
            a.write_text("# A\n", encoding="utf-8")
            b.write_text("# B\n", encoding="utf-8")
            c.write_text("# C\n", encoding="utf-8")
            importer = CEMImporter(root, Path(td) / "out")
            result = importer.run()
            converted = self.converted(importer, b, result)
            self.assertIn("> [!cem-nav]", converted)
            self.assertIn("> > [!cem-prev] Précédent", converted)
            self.assertIn("← A", converted)
            self.assertNotIn("> > [!cem-home]", converted)
            self.assertIn("⌂ Sommaire", converted)
            self.assertIn("> > [!cem-next] Suivant", converted)
            self.assertIn("C →", converted)
            self.assertNotIn(" · ", converted)

    def test_highlight_preserves_cem_colour_and_badge_markup(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td) / "course"
            docs = root / "web" / "docs"
            docs.mkdir(parents=True)
            note = docs / "x.md"
            note.write_text(
                '<Highlight color="caution">Attention</Highlight>\n'
                '<Highlight color="tip">3 points</Highlight>\n',
                encoding="utf-8",
            )
            importer = CEMImporter(root, Path(td) / "out")
            result = importer.run()
            converted = self.converted(importer, note, result)
            self.assertIn('class="cem-highlight cem-highlight-caution">Attention</span>', converted)
            self.assertIn('class="cem-highlight cem-highlight-tip">3 points</span>', converted)
            self.assertNotIn("==Attention==", converted)

    def test_unknown_highlight_colour_falls_back_to_portable_markdown(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td) / "course"
            docs = root / "web" / "docs"
            docs.mkdir(parents=True)
            note = docs / "x.md"
            note.write_text('<Highlight color="hotpink">Texte</Highlight>\n', encoding="utf-8")
            importer = CEMImporter(root, Path(td) / "out")
            result = importer.run()
            converted = self.converted(importer, note, result)
            self.assertIn("==Texte==", converted)




    def test_zero_width_html_entity_is_removed_from_prose(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td) / "3M5-Intro-Mobile"
            docs = root / "web" / "docs" / "03-tp"
            docs.mkdir(parents=True)
            note = docs / "01-tp1.md"
            note.write_text(
                '# TP1\n\n&#8203;<Highlight color="tip">1 point</Highlight> Consigne.\n\n```html\n&#8203;\n```\n',
                encoding="utf-8",
            )
            importer = CEMImporter(root, Path(td) / "out")
            result = importer.run()
            converted = self.converted(importer, note, result)
            self.assertNotIn("&#8203;<span", converted)
            self.assertIn('class="cem-highlight cem-highlight-tip">1 point</span> Consigne.', converted)
            # Preserve code examples verbatim; only prose/layout hacks are stripped.
            self.assertIn("```html\n&#8203;\n```", converted)


    def test_react_preview_multifile_falls_back_to_one_tab_group(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td) / "4W6-WebServices"
            docs = root / "web" / "docs" / "01-notes"
            assets = docs / "_02-demo"
            docs.mkdir(parents=True)
            assets.mkdir()
            (assets / "form-list-page.tsx").write_text(
                "export default function Page(){ return <div>Hi</div>; }\n", encoding="utf-8"
            )
            (assets / "item-class.ts").write_text(
                "export class Item { constructor(public name: string) {} }\n", encoding="utf-8"
            )
            note = docs / "02-demo.md"
            note.write_text(
                "import formListPage from '!!raw-loader!./_02-demo/form-list-page.tsx';\n"
                "import itemClass from '!!raw-loader!./_02-demo/item-class.ts';\n\n"
                '<ReactPreview code={formListPage} files={{ "/_types/item.ts": itemClass }} />\n',
                encoding="utf-8",
            )
            importer = CEMImporter(root, Path(td) / "out")
            result = importer.run()
            converted = self.converted(importer, note, result)
            self.assertIn('group:cem-react-1 tab:"page.tsx"', converted)
            self.assertIn('group:cem-react-1 tab:"_types/item.ts"', converted)
            self.assertNotIn("##### `/page.tsx`", converted)

    def test_react_preview_becomes_code_playground_when_plugin_is_installed(self):
        with tempfile.TemporaryDirectory() as td:
            td = Path(td)
            root = td / "4W6-WebServices"
            docs = root / "web" / "docs" / "01-notes"
            assets = docs / "_02-demo"
            docs.mkdir(parents=True)
            assets.mkdir()
            (assets / "form-list-page.tsx").write_text(
                "'use client';\nimport { Item } from './_types/item';\nexport default function Page(){ return <div>Hi</div>; }\n",
                encoding="utf-8",
            )
            (assets / "item-class.ts").write_text(
                "export class Item { constructor(public name: string) {} }\n", encoding="utf-8"
            )
            note = docs / "02-demo.md"
            note.write_text(
                "import formListPage from '!!raw-loader!./_02-demo/form-list-page.tsx';\n"
                "import itemClass from '!!raw-loader!./_02-demo/item-class.ts';\n\n"
                '<ReactPreview code={formListPage} files={{ "/_types/item.ts": itemClass }} previewHeight={300} />\n',
                encoding="utf-8",
            )

            vault = td / "Vault"
            plugin = vault / ".obsidian" / "plugins" / "code-playground"
            plugin.mkdir(parents=True)
            (plugin / "manifest.json").write_text('{"id":"code-playground"}', encoding="utf-8")
            output_parent = vault / "School"
            output_parent.mkdir(parents=True)

            importer = CEMImporter(root, output_parent)
            result = importer.run()
            converted = self.converted(importer, note, result)
            self.assertIn("```code-playground", converted)
            config_match = re.search(r"```code-playground\n(\{.*?\})\n```", converted, re.DOTALL)
            self.assertIsNotNone(config_match)
            config = json.loads(config_match.group(1))
            self.assertEqual(config["template"], "react-ts")
            self.assertTrue(config["showFileTabs"])

            sidecar = vault / "_playgrounds" / f'{config["id"]}.json'
            self.assertTrue(sidecar.is_file())
            data = json.loads(sidecar.read_text(encoding="utf-8"))
            self.assertEqual(data["activeFile"], "/page.tsx")
            self.assertIn("/page.tsx", data["files"])
            self.assertIn("/_types/item.ts", data["files"])
            self.assertIn("/App.tsx", data["files"])
            self.assertIn("/styles.css", data["files"])
            self.assertIn("/App.tsx", data["hiddenFiles"])
            self.assertEqual(importer.report.react_playgrounds, 1)



    def test_420_sn1_static_mdx_helpers_and_pycode_are_inlined(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td) / "420-SN1"
            docs = root / "web" / "docs"
            components = docs / "_components"
            components.mkdir(parents=True)
            (components / "PyCode.mdx").write_text(
                'export const S = ({children}) => <span>{children}</span>;\n'
                'export const C = ({children}) => <span>{children}</span>;\n',
                encoding="utf-8",
            )
            (components / "AideMemoireListe.mdx").write_text(
                "import { S, C } from '@site/docs/_components/PyCode.mdx';\n\n"
                "| Opération | Syntaxe |\n|---|---|\n"
                '| Créer | <C>heros = [<S>"Mario"</S>]</C> |\n',
                encoding="utf-8",
            )
            note = docs / "x.mdx"
            note.write_text(
                "import AideMemoireListe from '@site/docs/_components/AideMemoireListe.mdx';\n"
                "import { S, C } from '@site/docs/_components/PyCode.mdx';\n\n"
                "# Démo\n\n<AideMemoireListe />\n\n<C>x = <S>\"allo\"</S></C>\n",
                encoding="utf-8",
            )
            importer = CEMImporter(root, Path(td) / "out")
            result = importer.run()
            converted = self.converted(importer, note, result)
            report = self.report(importer)
            self.assertIn("| Opération | Syntaxe |", converted)
            self.assertIn('`heros = ["Mario"]`', converted)
            self.assertIn('`x = "allo"`', converted)
            self.assertNotIn("<AideMemoireListe", converted)
            self.assertNotIn("<C>", converted)
            self.assertNotIn("Composants MDX inconnus", report)

    def test_docusaurus_image_require_is_copied_and_preserves_width(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td) / "5N6-mobile-2"
            docs = root / "web" / "docs" / "03-recettes"
            assets = docs / "_demo"
            assets.mkdir(parents=True)
            (assets / "capture.png").write_bytes(b"fake-png")
            note = docs / "x.md"
            note.write_text(
                '<center>\n<Image alt="Capture" img={require(\'./_demo/capture.png\')} width="300" />\n</center>\n',
                encoding="utf-8",
            )
            importer = CEMImporter(root, Path(td) / "out")
            result = importer.run()
            converted = self.converted(importer, note, result)
            self.assertIn('<img src="', converted)
            self.assertIn('alt="Capture"', converted)
            self.assertIn('width="300"', converted)
            self.assertIn("capture.png", converted)
            self.assertNotIn("<Image", converted)
            report_json = json.loads((importer.report_dir / "report.json").read_text(encoding="utf-8"))
            self.assertEqual(report_json["issues"]["unknown_component_occurrences"], 0)

    def test_docusaurus_query_links_resolve_and_inline_code_links_are_ignored(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td) / "course"
            docs = root / "web" / "docs"
            course_dir = docs / "01-cours"
            recipe_dir = docs / "03-recettes"
            course_dir.mkdir(parents=True)
            recipe_dir.mkdir(parents=True)
            target = course_dir / "01-rencontre1.mdx"
            target.write_text("# Rencontre 1\n", encoding="utf-8")
            note = recipe_dir / "x.mdx"
            note.write_text(
                "[Types](/cours/rencontre1?onglet=types)\n\n"
                "Exemple littéral : `![alt](chemin/vers/image.png)`\n",
                encoding="utf-8",
            )
            importer = CEMImporter(root, Path(td) / "out")
            result = importer.run()
            converted = self.converted(importer, note, result)
            self.assertIn(importer.output_map[target.resolve()].name, converted)
            self.assertIn("`![alt](chemin/vers/image.png)`", converted)
            report_json = json.loads((importer.report_dir / "report.json").read_text(encoding="utf-8"))
            self.assertEqual(report_json["issues"]["unresolved_local_links"], 0)



    def test_quiz_static_json_path_is_converted(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td) / "1P6"
            docs = root / "web" / "docs" / "01-cours"
            quiz_dir = root / "web" / "static" / "quiz"
            docs.mkdir(parents=True)
            quiz_dir.mkdir(parents=True)
            (quiz_dir / "2.1-base.json").write_text(
                json.dumps({
                    "titre": "Quiz JSON",
                    "questions": [{
                        "texte": "Que vaut x ?",
                        "code": "int x = 2 + 2;",
                        "choix": ["3", "4"],
                        "reponse": 1,
                    }],
                }),
                encoding="utf-8",
            )
            note = docs / "03-ifelse.md"
            nbsp = "\u00a0"
            note.write_text(f"# Conditions\n\n<Quiz{nbsp}file=\"/quiz/2.1-base.json\"{nbsp}/>\n", encoding="utf-8")
            importer = CEMImporter(root, Path(td) / "out")
            result = importer.run()
            converted = self.converted(importer, note, result)
            self.assertIn("### 🧠 Quiz JSON", converted)
            self.assertIn("Que vaut x ?", converted)
            self.assertIn("int x = 2 + 2;", converted)
            self.assertIn("**2. 4**", converted)
            self.assertNotIn("Quiz trouvé mais attribut file non reconnu", self.report(importer))

    def test_markdown_links_inside_html_comments_are_not_reported(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td) / "5W5"
            docs = root / "web" / "docs"
            docs.mkdir(parents=True)
            note = docs / "old.md"
            note.write_text(
                "# Ancien\n\n<!--\n![image](missing.png)\n![bad]((also-missing.png)\n-->\n",
                encoding="utf-8",
            )
            importer = CEMImporter(root, Path(td) / "out")
            importer.run()
            self.assertNotIn("Liens locaux non résolus", self.report(importer))

    def test_broken_meeting_route_can_be_repaired_from_visible_label(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td) / "3U4"
            docs = root / "web" / "docs"
            courses = docs / "01-cours"
            courses.mkdir(parents=True)
            target = courses / "17-r9.1.md"
            target.write_text("# Rencontre 9.1\n", encoding="utf-8")
            note = docs / "accueil.md"
            note.write_text("# Accueil\n\n[9.1 → Inventaire](cours/r8.3)\n", encoding="utf-8")
            importer = CEMImporter(root, Path(td) / "out")
            result = importer.run()
            converted = self.converted(importer, note, result)
            self.assertIn(importer.output_map[target.resolve()].name, converted)
            self.assertNotIn("cours/r8.3", self.report(importer))

    def test_leading_underscore_file_is_helper_not_visible_note(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td) / "420-SN1"
            docs = root / "web" / "docs" / "03-recettes"
            docs.mkdir(parents=True)
            visible = docs / "010-visible.md"
            hidden = docs / "_090-autres-recettes.mdx"
            visible.write_text("# Visible\n", encoding="utf-8")
            hidden.write_text("# Draft\n\n[bad](/recettes/autres-recettes?onglet=x)\n", encoding="utf-8")
            importer = CEMImporter(root, Path(td) / "out")
            importer.run()
            self.assertIn(visible.resolve(), importer.output_map)
            self.assertNotIn(hidden.resolve(), importer.output_map)
            self.assertNotIn("autres-recettes", self.report(importer))

    def test_420_sn1_tab_helpers_do_not_turn_prose_into_code_and_require_images_are_local(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td) / "420-SN1"
            docs = root / "web" / "docs" / "01-cours"
            components = root / "web" / "docs" / "_components"
            static_icons = root / "web" / "static" / "img" / "icons"
            docs.mkdir(parents=True)
            components.mkdir(parents=True)
            static_icons.mkdir(parents=True)
            (static_icons / "copier.png").write_bytes(b"fake")
            (components / "Reminder.mdx").write_text(":::tip Rappel\nContenu du rappel.\n:::\n", encoding="utf-8")
            note = docs / "01-rencontre1.mdx"
            source = (
                "import Tabs from '@theme/Tabs';\n"
                "import TabItem from '@theme/TabItem';\n"
                "import Reminder from '@site/docs/_components/Reminder.mdx';\n\n"
                "<Tabs>\n"
                "    <TabItem value=\"intro\" label=\"Intro\">\n"
                "        <Reminder />\n\n"
                "        ### Environnements de développement\n\n"
                "        Texte normal qui ne doit pas devenir un bloc de code.\n\n"
                "        Pour copier : <img src={require('/img/icons/copier.png').default} width=\"24\" style={{ verticalAlign: 'middle' }}/>\n"
                "    </TabItem>\n"
                "</Tabs>\n"
            )
            note.write_text(source, encoding="utf-8")
            importer = CEMImporter(root, Path(td) / "out")
            result = importer.run()
            converted = self.converted(importer, note, result)
            self.assertIn("#### Intro", converted)
            self.assertIn("### Environnements de développement", converted)
            self.assertIn("Texte normal qui ne doit pas devenir un bloc de code.", converted)
            self.assertNotIn("        ### Environnements", converted)
            self.assertNotIn("src={require", converted)
            self.assertIn('class="cem-inline-image"', converted)
            self.assertIn("copier.png", converted)
            self.assertEqual(sum(importer.report.unknown_components.values()), 0)

    def test_420_sn1_indented_mixed_tab_with_code_fence_dedents_as_a_unit(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td) / "420-SN1"
            docs = root / "web" / "docs" / "01-cours"
            docs.mkdir(parents=True)
            note = docs / "01-rencontre1.mdx"
            note.write_text(
                "<Tabs>\n"
                "    <TabItem value=\"intro\" label=\"Intro\">\n\n"
                "        ### Exemple\n\n"
                "        - Copiez le code :\n"
                "            ```python\n"
                "            nombre1 = 30\n"
                "            print(nombre1)\n"
                "            ```\n"
                "            - Puis sauvegardez le fichier.\n\n"
                "        ### Environnements de développement (IDE)\n\n"
                "        Ce paragraphe doit rester du texte normal.\n\n"
                "        ```python\n"
                "        print(\"fin\")\n"
                "        ```\n"
                "    </TabItem>\n"
                "</Tabs>\n",
                encoding="utf-8",
            )
            importer = CEMImporter(root, Path(td) / "out")
            result = importer.run()
            converted = self.converted(importer, note, result)
            self.assertIn("#### Intro", converted)
            self.assertIn("```python\nnombre1 = 30\nprint(nombre1)\n```", converted)
            self.assertIn("### Environnements de développement (IDE)", converted)
            self.assertIn("Ce paragraphe doit rester du texte normal.", converted)
            self.assertNotIn("        ### Environnements", converted)
            self.assertNotIn("        Ce paragraphe", converted)

    def test_420_sn1_four_colon_nested_admonitions_render_as_callouts(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td) / "420-SN1"
            docs = root / "web" / "docs" / "01-cours"
            docs.mkdir(parents=True)
            note = docs / "01-rencontre1.mdx"
            note.write_text(
                '<Tabs>\n'
                '    <TabItem value="variables" label="Variables">\n\n'
                '        ::::info Syntaxe pour créer une variable\n\n'
                '        Il faut écrire le nom de la variable.\n\n'
                '        ```python\n'
                '        nom_de_ma_variable = expression\n'
                '        ```\n'
                '        - `nom_de_ma_variable` est unique.\n\n'
                '        :::tip\n'
                "        L'opérateur `=` est évalué après l'expression.\n"
                '        :::\n\n'
                '        Exemples :\n\n'
                '        ```python\n'
                '        x = 5 * 6\n'
                '        ```\n\n'
                '        ::::     \n'
                '    </TabItem>\n'
                '</Tabs>\n',
                encoding="utf-8",
            )
            importer = CEMImporter(root, Path(td) / "out")
            result = importer.run()
            converted = self.converted(importer, note, result)
            self.assertIn("> [!info] Syntaxe pour créer une variable", converted)
            self.assertIn("> > [!tip]", converted)
            self.assertIn("> ```python\n> nom_de_ma_variable = expression\n> ```", converted)
            self.assertNotIn("::::", converted)
            self.assertNotIn("    Il faut écrire", converted)

    def test_420_sn1_nt_admonitions_are_supported(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td) / "420-SN1"
            docs = root / "web" / "docs"
            docs.mkdir(parents=True)
            note = docs / "x.mdx"
            note.write_text(
                ":::info-nt Information\nTexte.\n:::\n\n"
                ":::tip-nt Astuce\nConseil.\n:::\n\n"
                ":::danger-nt Danger\nAttention.\n:::\n",
                encoding="utf-8",
            )
            importer = CEMImporter(root, Path(td) / "out")
            result = importer.run()
            converted = self.converted(importer, note, result)
            self.assertIn("> [!info] Information", converted)
            self.assertIn("> [!tip] Astuce", converted)
            self.assertIn("> [!danger] Danger", converted)
            self.assertNotIn("-nt", converted)

    def test_generated_asset_links_are_not_re_reported_as_unresolved(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td) / "420-SN1"
            docs = root / "web" / "docs" / "01-cours"
            static = root / "web" / "static" / "img"
            docs.mkdir(parents=True)
            static.mkdir(parents=True)
            (static / "capture.png").write_bytes(b"fake")
            note = docs / "x.mdx"
            note.write_text("<img src={require('/img/capture.png').default} alt=\"Capture\" />\n", encoding="utf-8")
            importer = CEMImporter(root, Path(td) / "out")
            result = importer.run()
            converted = self.converted(importer, note, result)
            self.assertIn("_assets", converted)
            payload = json.loads((importer.report_dir / "report.json").read_text(encoding="utf-8"))
            self.assertEqual(payload["issues"]["unresolved_local_links"], 0)

    def test_docusaurus_baseurl_prefixed_static_image_resolves(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td) / "420-SN1"
            docs = root / "web" / "docs"
            static = root / "web" / "static" / "img"
            docs.mkdir(parents=True)
            static.mkdir(parents=True)
            (static / "logo.svg").write_text("<svg></svg>", encoding="utf-8")
            note = docs / "accueil.mdx"
            note.write_text('<img src="/420-SN1/img/logo.svg" alt="Logo" />\n', encoding="utf-8")
            importer = CEMImporter(root, Path(td) / "out")
            result = importer.run()
            converted = self.converted(importer, note, result)
            self.assertIn("logo.svg", converted)
            self.assertNotIn("/420-SN1/img/logo.svg", converted)
            self.assertNotIn("Image Docusaurus introuvable", self.report(importer))

    def test_feedback_widget_is_omitted_without_placeholder_noise(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td) / "420-SN1"
            docs = root / "web" / "docs"
            docs.mkdir(parents=True)
            note = docs / "x.mdx"
            note.write_text("Avant\n<Feedback surveyId=\"x\" />\nAprès\n", encoding="utf-8")
            importer = CEMImporter(root, Path(td) / "out")
            result = importer.run()
            converted = self.converted(importer, note, result)
            self.assertIn("Avant", converted)
            self.assertIn("Après", converted)
            self.assertNotIn("Feedback", converted)
            self.assertNotIn("Rétroaction", converted)


    def test_empty_mermaid_fence_is_removed(self):
        cleaned = CEMImporter.cleanup_whitespace("Avant\n\n```mermaid\n\n```\n\nAprès\n")
        self.assertNotIn("```mermaid", cleaned)
        self.assertIn("Avant", cleaned)
        self.assertIn("Après", cleaned)


class PublicConfigurationTests(unittest.TestCase):
    def test_default_course_width_is_1400px(self):
        css = (Path(__file__).resolve().parents[1] / "obsidian-wide-notes.css").read_text(encoding="utf-8")
        self.assertIn("--file-line-width: 1400px;", css)

    def test_transform_pipeline_is_explicit_and_ordered(self):
        names = [step.name for step in CEMImporter.TRANSFORM_PIPELINE]
        self.assertEqual(names[0], "imported-mdx-components")
        self.assertLess(names.index("imported-mdx-components"), names.index("pycode-components"))
        self.assertLess(names.index("pycode-components"), names.index("nonvoyant"))
        self.assertIn("react-preview", names)
        self.assertLess(names.index("react-preview"), names.index("tabs"))
        self.assertLess(names.index("highlight"), names.index("admonitions"))

    def test_manager_config_round_trip(self):
        original = manager.CONFIG_PATH
        try:
            with tempfile.TemporaryDirectory() as td:
                manager.CONFIG_PATH = Path(td) / ".cem-importer.json"
                expected = {"destination": str(Path(td) / "Vault" / "School")}
                manager.save_config(expected)
                self.assertEqual(manager.load_config(), expected)
        finally:
            manager.CONFIG_PATH = original

    def test_course_catalog_contains_known_cem_repositories(self):
        repos = {course.repo for course in manager.COURSES}
        self.assertEqual(len(manager.COURSES), 13)
        self.assertIn("https://github.com/departement-info-cem/3M5-Intro-Mobile.git", repos)
        self.assertIn("https://github.com/departement-info-cem/4W6-WebServices.git", repos)
        self.assertIn("https://github.com/departement-info-cem/z03.git", repos)

    def test_course_catalog_uses_human_course_names(self):
        folders = {course.code: course.folder for course in manager.COURSES}
        self.assertEqual(folders["1P6"], "1P6 - Introduction à la programmation")
        self.assertEqual(folders["3M5"], "3M5 - Introduction à la programmation mobile")
        self.assertEqual(folders["4W6"], "4W6 - Programmation Web orientée services")
        self.assertEqual(folders["5N6"], "5N6 - Applications mobiles avancées")
        self.assertEqual(folders["Z03"], "Z03 - Introduction à la programmation web")

    def test_course_catalog_groups_courses_by_session(self):
        sessions = {course.code: course.session for course in manager.COURSES}
        self.assertEqual(sessions["1P6"], 1)
        self.assertEqual(sessions["2P6"], 2)
        self.assertEqual(sessions["3W6"], 3)
        self.assertEqual(sessions["3M5"], 4)
        self.assertEqual(sessions["4D5"], 5)
        self.assertEqual(sessions["5N6"], 6)
        self.assertIsNone(sessions["Z03"])

    def test_reports_are_flat_and_reset_between_runs(self):
        with tempfile.TemporaryDirectory() as td:
            original = manager.REPORTS_ROOT
            try:
                manager.REPORTS_ROOT = Path(td) / "reports"
                legacy = manager.REPORTS_ROOT / "3M5"
                legacy.mkdir(parents=True)
                (legacy / "report.md").write_text("legacy", encoding="utf-8")
                manager.reset_reports_root()
                self.assertTrue(manager.REPORTS_ROOT.is_dir())
                self.assertEqual(list(manager.REPORTS_ROOT.iterdir()), [])
            finally:
                manager.REPORTS_ROOT = original

    def test_launcher_generated_content_folder_is_cours(self):
        self.assertEqual(manager.DEFAULT_NOTES_FOLDER, "Cours")

    def test_multi_selection_accepts_numbers_ranges_and_commas(self):
        self.assertEqual(manager._parse_selection("1, 3 5-7", 10), [0, 2, 4, 5, 6])


    def test_destination_accepts_shell_quoted_absolute_path(self):
        with tempfile.TemporaryDirectory() as td:
            vault = Path(td) / "Vault with spaces"
            (vault / ".obsidian").mkdir(parents=True)
            destination = vault / "School" / "Cégep Édouard-Montpetit"
            quoted = f"'{destination}'"
            normalized = manager.normalize_destination(quoted)
            self.assertEqual(normalized, destination.resolve())
            self.assertEqual(manager.find_vault_root(normalized), vault.resolve())

    def test_destination_accepts_shell_escaped_spaces(self):
        with tempfile.TemporaryDirectory() as td:
            vault = Path(td) / "Vault with spaces"
            (vault / ".obsidian").mkdir(parents=True)
            destination = vault / "School Folder" / "CEM"
            escaped = str(destination).replace(" ", "\\ ")
            normalized = manager.normalize_destination(escaped)
            self.assertEqual(normalized, destination.resolve())
            self.assertEqual(manager.find_vault_root(normalized), vault.resolve())

    def test_sync_css_finds_vault_above_course_destination(self):
        expected_css = manager.CSS_SOURCE.read_text(encoding="utf-8")
        with tempfile.TemporaryDirectory() as td:
            vault = Path(td) / "Vault"
            (vault / ".obsidian").mkdir(parents=True)
            dest = vault / "School" / "CEM"
            dest.mkdir(parents=True)
            installed = manager.sync_css(dest, quiet=True)
            self.assertIsNotNone(installed)
            self.assertEqual(installed.read_text(encoding="utf-8"), expected_css)

    def test_aggregate_report_is_one_detailed_flat_report(self):
        with tempfile.TemporaryDirectory() as td:
            original = manager.REPORTS_ROOT
            try:
                manager.REPORTS_ROOT = Path(td) / "reports"
                course = manager.COURSES[0]
                report_data = {
                    "stats": {"notes": 12, "assets": 4},
                    "details": {
                        "unknown_components": {},
                        "unresolved_local_links": [
                            {"note": "01-demo.md", "target": "/missing"}
                        ],
                        "warnings": [
                            {"note": "02-demo.md", "message": "Démo incomplète"}
                        ],
                    },
                }
                result = manager.ImportResult(
                    course=course,
                    succeeded=True,
                    issue_count=2,
                    unresolved_links=1,
                    warnings=1,
                    report_data=report_data,
                )
                md, js = manager.write_aggregate_report([result], Path(td) / "Vault" / "School")
                self.assertEqual(md, manager.REPORTS_ROOT / "detail-summary.md")
                self.assertEqual(js, manager.REPORTS_ROOT / "summary.json")
                self.assertTrue(md.is_file())
                self.assertTrue(js.is_file())
                self.assertEqual(sorted(p.name for p in manager.REPORTS_ROOT.iterdir()), ["detail-summary.md", "summary.json"])
                report_text = md.read_text(encoding="utf-8")
                self.assertIn(course.code, report_text)
                self.assertIn("01-demo.md", report_text)
                self.assertIn("/missing", report_text)
                self.assertIn("Démo incomplète", report_text)
                payload = json.loads(js.read_text(encoding="utf-8"))
                self.assertEqual(payload["courses"][0]["details"]["unresolved_local_links"][0]["target"], "/missing")
            finally:
                manager.REPORTS_ROOT = original

    def test_department_git_guide_is_written_to_shared_resources(self):
        with tempfile.TemporaryDirectory() as td:
            destination = Path(td) / "School" / "Cégep Édouard-Montpetit"
            destination.mkdir(parents=True)
            source = (
                '<div class="container"><div class="row">'
                '<div class="col-md alert"><h4>Types de commits</h4>'
                '<span class="badge text-bg-warning">FCT</span></div>'
                '</div></div>'
            )
            target = manager.sync_department_git_guide(
                destination,
                quiet=True,
                fetcher=lambda _url: source,
            )
            self.assertEqual(
                target,
                destination / "Git - Consignes du département.md",
            )
            rendered = target.read_text(encoding="utf-8")
            self.assertIn("source: https://info.cegepmontpetit.ca/git", rendered)
            self.assertIn("cssclasses:\n  - cem-course", rendered)
            self.assertIn('<div class="cem-dept-git">', rendered)
            self.assertIn("Types de commits", rendered)
            self.assertIn("text-bg-warning", rendered)

    def test_department_git_guide_uses_actual_angular_component_markup(self):
        source = (
            '\ufeff<div class="container"><div class="row">'
            '<div class="col-md alert alert-dark"><strong>Nom du dépôt</strong></div>'
            '<div class="col-md alert"><h4>Types de commits</h4>'
            '<span class="badge text-bg-warning">BUGFIX</span></div>'
            '</div></div>'
        )
        rendered = manager.build_department_git_note(source)
        self.assertIn('<div class="cem-dept-git">', rendered)
        self.assertIn("Nom du dépôt", rendered)
        self.assertIn("BUGFIX", rendered)
        self.assertNotIn("```mermaid", rendered)
        self.assertNotIn("<script", rendered.lower())

    def test_department_git_html_is_flush_left_so_obsidian_does_not_make_code_blocks(self):
        source = (
            '<div class="container">\n'
            '  <div class="row">\n'
            '    <div class="col-md alert">\n'
            '      <h4>Exemple de commit</h4>\n'
            '      <div class="alert alert-success">\n'
            '        <strong>titre :</strong> FCT sauvegarde\n'
            '      </div>\n'
            '    </div>\n'
            '  </div>\n'
            '</div>'
        )
        rendered = manager.build_department_git_note(source)
        body = rendered.split('---\n\n', 1)[1]
        for line in body.splitlines():
            if line.strip():
                self.assertEqual(line, line.lstrip())
        self.assertIn('<div class="alert alert-success">', rendered)
        self.assertNotIn('    <div class="alert alert-success">', rendered)

    def test_department_git_css_recreates_card_grid(self):
        css = (Path(__file__).resolve().parents[1] / "obsidian-wide-notes.css").read_text(encoding="utf-8")
        self.assertIn(".cem-dept-git .row", css)
        self.assertIn("grid-template-columns: repeat(3", css)
        self.assertIn(".badge.text-bg-warning", css)
        self.assertIn("img.cem-inline-image", css)

    def test_dataview_does_not_hijack_equals_inline_code(self):
        source = "### ⚠️ `=` vs `==`\n\n- `=` : affectation\n- `==` : comparaison\n- `x = 5` reste normal\n"
        rendered = CEMImporter.escape_dataview_inline_query_collisions(source)
        self.assertIn("<code>=</code> vs <code>==</code>", rendered)
        self.assertIn("<code>=</code> : affectation", rendered)
        self.assertIn("<code>==</code> : comparaison", rendered)
        self.assertIn("`x = 5` reste normal", rendered)
        self.assertNotIn("`=`", rendered)
        self.assertNotIn("`==`", rendered)

    def test_dataview_collision_fix_preserves_fenced_code(self):
        source = "Avant `=`\n\n```text\n`=`\n`==`\n```\n\nAprès `$= demo`\n"
        rendered = CEMImporter.escape_dataview_inline_query_collisions(source)
        self.assertIn("Avant <code>=</code>", rendered)
        self.assertIn("```text\n`=`\n`==`\n```", rendered)
        self.assertIn("Après <code>$= demo</code>", rendered)

    def test_public_version_is_semantic(self):
        self.assertRegex(module.VERSION, r"^\d+\.\d+\.\d+$")
        version_file = (Path(__file__).resolve().parents[1] / "VERSION").read_text(encoding="utf-8").strip()
        self.assertEqual(module.VERSION, version_file)
        self.assertEqual(manager.VERSION, version_file)


if __name__ == "__main__":
    unittest.main()

"""Regression tests for the validator's documented Markdown subset."""

from pathlib import Path
import os
import subprocess
import sys
import tempfile
import unittest


sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from check_docs import IGNORED_DIRS, validate  # noqa: E402


class CheckDocsTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)

    def write(self, name, content):
        path = self.root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")

    def test_fences_match_character_and_minimum_length_and_hide_examples(self):
        self.write("README.md", "# Start\n````md\n[[missing]]\n```\n~~~\n`````\n> ~~~text\n> [x](absent.md)\n> ~~~~\n`[[also-missing]]`\n")
        report = validate(self.root)
        self.assertEqual(report.errors, [])
        self.assertEqual(report.local_links, 0)
        self.write("broken.md", "# Broken\n> ````\n> ```\n> ~~~~\n")
        self.assertIn("unclosed ```` fence", "\n".join(validate(self.root).errors))

    def test_unicode_spaces_encoded_destinations_and_wiki_aliases(self):
        self.write("章节/复杂 知识.md", "# 中文 标题\n")
        self.write("notes/start.md", "\n".join([
            "[[章节/复杂 知识#中文 标题|说明]]",
            r"[[复杂 知识\|表格显示名]]",
            "[[../章节/复杂 知识.md]]",
            "[编码](../%E7%AB%A0%E8%8A%82/复杂%20知识.md#中文-标题)",
            "[尖括号](<../章节/复杂 知识.md#中文-标题>)",
            "[根路径](/章节/复杂%20知识.md)",
        ]))
        report = validate(self.root)
        self.assertEqual(report.errors, [])
        self.assertEqual(report.local_links, 6)

    def test_missing_ambiguous_targets_and_cli_failure_are_visible(self):
        self.write("a/same.md", "# Same\n")
        self.write("b/same.md", "# Same\n")
        self.write("README.md", "[[same]]\n[[absent]]\n[x](missing.md)\n")
        report = validate(self.root)
        self.assertEqual(len(report.errors), 3)
        self.assertIn("ambiguous Wiki target", report.errors[0])
        result = subprocess.run([sys.executable, str(Path(__file__).resolve().parents[1] / "check_docs.py"), "--root", str(self.root)], capture_output=True)
        self.assertEqual(result.returncode, 1)
        self.assertIn(b"errors: 3", result.stdout)

    def test_heading_text_slug_duplicates_and_missing_anchor(self):
        self.write("target.md", "# Hello, **World**!\n## Hello, **World**!\n> ## 中文 标题\n```\n# Fake\n```\n")
        self.write("README.md", "\n".join([
            "[[target#Hello, World!]]", "[first](target.md#hello-world)",
            "[duplicate](target.md#hello-world-1)", "[[target#中文 标题]]",
            "[missing](target.md#fake)",
        ]))
        report = validate(self.root)
        self.assertEqual(len(report.errors), 1)
        self.assertIn("missing heading #fake", report.errors[0])

    def test_ignored_directories_are_pruned_at_any_depth(self):
        self.write("README.md", "# Good\n")
        for ignored in IGNORED_DIRS:
            self.write(f"nested/{ignored}/broken.md", "[[missing]]\n```\n")
        report = validate(self.root)
        self.assertEqual(report.documents, 1)
        self.assertEqual(report.errors, [])

    def test_external_urls_skipped_and_assets_and_parentheses_checked(self):
        self.write("asset (v1).txt", "example")
        self.write("README.md", "\n".join([
            "[asset](asset%20(v1).txt)", "[asset](<asset (v1).txt>)",
            "[web](https://example.invalid/missing.md#no-heading)",
            "[mail](mailto:reader@example.invalid)", "[web](//example.invalid/page)",
            "[self](#root)", "# Root",
        ]))
        report = validate(self.root)
        self.assertEqual(report.errors, [])
        self.assertEqual(report.local_links, 3)
        self.assertEqual(report.external_links, 3)

    def test_only_table_wiki_aliases_need_escaping_and_errors_use_utf8(self):
        self.write("target.md", "# Target\n")
        self.write("中文表格.md", "\n".join([
            "[[target|普通段落]]", "> [[target|引用段落]]", "",
            "| Header | Link |", "| --- | --- |",
            "| bad | [[target|未转义]] |",
            r"| good | [[target\|已转义]] |",
            "| example | `[[target|代码示例]]` |", "",
            "> | Header | Link |", "> | :--- | ---: |",
            "> | bad | [[target|引用表格未转义]] |",
            r"> | good | [[target\|引用表格已转义]] |", "",
            "Header | Link", "--- | ---", "row | [[target|没有外侧管道]]", "",
            "```md", "| Header | Link |", "| --- | --- |",
            "| example | [[missing|不检查代码块]] |", "```",
        ]))
        report = validate(self.root)
        self.assertEqual(len(report.errors), 3)
        self.assertTrue(all("unescaped Wiki alias in table" in error for error in report.errors))
        result = subprocess.run(
            [sys.executable, str(Path(__file__).resolve().parents[1] / "check_docs.py"), "--root", str(self.root)],
            capture_output=True, env={**os.environ, "PYTHONIOENCODING": "ascii"},
        )
        self.assertEqual(result.returncode, 1)
        self.assertIn("中文表格.md", result.stdout.decode("utf-8"))


if __name__ == "__main__":
    unittest.main()

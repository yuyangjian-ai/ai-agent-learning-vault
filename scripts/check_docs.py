"""Check this vault's local links and fenced code blocks (Python 3.10+, no deps).

Usage: python scripts/check_docs.py [--root PATH]

Scope: ATX (#) headings, Obsidian [[path#heading|alias]] / embeds, and ordinary
inline Markdown links/images, including <destinations with spaces>, %-encoding,
fragments and balanced destination parentheses. Wiki aliases inside Markdown
tables (including blockquoted tables) must escape the separator as \\|.
Wiki paths are vault-root paths, explicit ./../ paths, or unique basenames.
Markdown paths are relative to the current note; / means the vault root.
Markdown fragments use GitHub-style slugs for ordinary text headings, including
duplicate suffixes; Wiki fragments use heading text or those slugs.

This is intentionally not a full Markdown renderer: reference-style links,
Setext headings, HTML anchors/links, Obsidian block IDs/nested heading paths and
complex nested link labels are outside its scope. Use ordinary ATX headings and
inline links in maintained notes. External URLs are never fetched. Fenced code
(backticks or tildes, also in blockquotes) and inline code are not link-checked.
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass, field
import html
import os
from pathlib import Path
import re
import sys
import unicodedata
from urllib.parse import unquote, urlsplit


IGNORED_DIRS = {".git", ".idea", ".obsidian", ".agents", ".codex", ".venv", "__pycache__", "node_modules", "dist"}
FENCE = re.compile(r"^ {0,3}(`{3,}|~{3,})(.*)$")
HEADING = re.compile(r"^ {0,3}#{1,6}[ \t]+(.+?)\s*$")
WIKI = re.compile(r"(?<!\\)\[\[([^\]\n]+)\]\]")
INLINE_START = re.compile(r"(?<!\\)!?\[(?:\\.|[^\[\]\\])*\]\(")
INLINE_CODE = re.compile(r"(`+)(?!`)(.*?)\1(?!`)")
SCHEME = re.compile(r"^[A-Za-z][A-Za-z0-9+.-]*:")


@dataclass
class Document:
    path: Path
    lines: list[tuple[int, str]]
    headings: set[str] = field(default_factory=set)
    anchors: set[str] = field(default_factory=set)


@dataclass
class Report:
    documents: int = 0
    local_links: int = 0
    external_links: int = 0
    errors: list[str] = field(default_factory=list)


def without_quote(line: str) -> str:
    """Remove one or more Markdown blockquote prefixes, preserving indentation."""
    while re.match(r"^ {0,3}>[ \t]?", line):
        line = re.sub(r"^ {0,3}>[ \t]?", "", line, count=1)
    return line


def plain_heading(text: str) -> str:
    text = re.sub(r"\s+#+\s*$", "", text)
    text = re.sub(r"\[([^\]]+)\]\([^)]*\)", r"\1", text)
    text = re.sub(r"<[^>]+>", "", text)
    return html.unescape(re.sub(r"[*`~]", "", text)).strip()


def heading_slug(text: str) -> str:
    text = plain_heading(text).lower()
    text = "".join(
        char for char in text
        if char in "_-" or char.isspace() or unicodedata.category(char)[0] in "LNM"
    )
    return re.sub(r"\s", "-", text)


def read_document(path: Path, root: Path, report: Report) -> Document:
    visible: list[tuple[int, str]] = []
    opened: tuple[str, int, int] | None = None
    try:
        lines = path.read_text(encoding="utf-8-sig").splitlines()
    except (OSError, UnicodeError) as exc:
        report.errors.append(f"{path.relative_to(root)}: cannot read UTF-8: {exc}")
        return Document(path, visible)
    for number, original in enumerate(lines, 1):
        line = without_quote(original)
        fence = FENCE.match(line)
        if opened:
            if fence and fence[1][0] == opened[0] and len(fence[1]) >= opened[1] and not fence[2].strip():
                opened = None
            continue
        if fence:
            opened = (fence[1][0], len(fence[1]), number)
            continue
        visible.append((number, line))
    if opened:
        report.errors.append(f"{path.relative_to(root)}:{opened[2]}: unclosed {opened[0] * opened[1]} fence")
    doc = Document(path, visible)
    for _, line in visible:
        match = HEADING.match(line)
        if match:
            title = plain_heading(match[1])
            doc.headings.add(title.casefold())
            base = heading_slug(title)
            slug, suffix = base, 0
            while slug in doc.anchors:
                suffix += 1
                slug = f"{base}-{suffix}"
            doc.anchors.add(slug)
    return doc


def markdown_destinations(line: str):
    """Read common inline destinations, not a full nested Markdown grammar."""
    for match in INLINE_START.finditer(line):
        index = match.end()
        while index < len(line) and line[index].isspace():
            index += 1
        if index < len(line) and line[index] == "<":
            end = line.find(">", index + 1)
            if end >= 0:
                yield line[index + 1:end]
            continue
        start, depth = index, 0
        while index < len(line):
            char = line[index]
            if char == "\\" and index + 1 < len(line):
                index += 2
                continue
            if char == "(":
                depth += 1
            elif char == ")":
                if depth == 0:
                    break
                depth -= 1
            elif char.isspace() and depth == 0:
                break
            index += 1
        if index < len(line):
            yield re.sub(r"\\([\\() ])", r"\1", line[start:index])


def table_line_numbers(lines: list[tuple[int, str]]) -> set[int]:
    """Locate pipe-table headers/rows using their Markdown separator line."""
    result: set[int] = set()
    for index in range(1, len(lines)):
        number, line = lines[index]
        cells = line.strip().strip("|").split("|")
        if "|" not in line or not all(re.fullmatch(r":?-{3,}:?", cell.strip()) for cell in cells):
            continue
        previous_number, header = lines[index - 1]
        if previous_number + 1 != number or "|" not in header:
            continue
        result.add(previous_number)
        next_index, previous_number = index + 1, number
        while next_index < len(lines):
            row_number, row = lines[next_index]
            if row_number != previous_number + 1 or not row.strip() or "|" not in row:
                break
            result.add(row_number)
            previous_number, next_index = row_number, next_index + 1
    return result


def has_unescaped_pipe(text: str) -> bool:
    for match in re.finditer(r"\|", text):
        before = text[:match.start()]
        backslashes = len(before) - len(before.rstrip("\\"))
        if backslashes % 2 == 0:
            return True
    return False


def validate(root: Path) -> Report:
    root = root.resolve()
    report = Report()
    files: set[Path] = set()
    for directory, children, names in os.walk(root):
        children[:] = sorted(name for name in children if name not in IGNORED_DIRS)
        for name in names:
            path = Path(directory) / name
            # Do not read symlink targets outside the selected vault.
            if path.is_file() and not path.is_symlink():
                files.add(path.resolve())
    docs = {
        path: read_document(path, root, report)
        for path in sorted(files) if path.suffix.lower() == ".md"
    }
    report.documents = len(docs)
    if not docs:
        report.errors.append(f"{root}: no Markdown documents found")

    def lookup_wiki(source: Path, target: str) -> tuple[Path | None, str | None]:
        if not target:
            return source, None
        target = unquote(target).replace("\\", "/")
        names = [target] if Path(target).suffix else [target + ".md", target]
        if "/" in target:
            bases = [root] if target.startswith("/") else [source.parent] if target.startswith(".") else [root, source.parent]
            for base in bases:
                for name in names:
                    candidate = (base / name.lstrip("/")).resolve()
                    if candidate in files:
                        return candidate, None
        else:
            matches = {path for path in files if path.name in names}
            if len(matches) == 1:
                return matches.pop(), None
            if len(matches) > 1:
                return None, f"ambiguous Wiki target: {target}; use a vault path"
        return None, f"missing Wiki target: {target}"

    def check(source: Path, number: int, raw: str, wiki: bool) -> None:
        if not wiki and (SCHEME.match(raw) or raw.startswith("//")):
            report.external_links += 1
            return
        report.local_links += 1
        if wiki:
            raw = re.split(r"\\?\|", raw, maxsplit=1)[0].strip()
            target, _, fragment = raw.partition("#")
            resolved, error = lookup_wiki(source, target.strip())
        else:
            parts = urlsplit(raw)
            target, fragment = unquote(parts.path), parts.fragment
            resolved = source if not target else ((root / target.lstrip("/")) if target.startswith("/") else (source.parent / target)).resolve()
            error = None
            if not resolved.is_relative_to(root) or not resolved.exists():
                error = f"missing or outside-vault Markdown target: {target}"
        prefix = f"{source.relative_to(root)}:{number}"
        if error:
            report.errors.append(f"{prefix}: {error}")
            return
        if fragment and resolved and resolved.suffix.lower() == ".md":
            fragment = unquote(fragment).strip()
            doc = docs.get(resolved)
            exists = doc and (fragment in doc.anchors or (wiki and fragment.casefold() in doc.headings))
            if not exists:
                report.errors.append(f"{prefix}: missing heading #{fragment} in {resolved.relative_to(root)}")

    for source, doc in docs.items():
        table_rows = table_line_numbers(doc.lines)
        for number, line in doc.lines:
            line = INLINE_CODE.sub("", line)
            for match in WIKI.finditer(line):
                if number in table_rows and has_unescaped_pipe(match[1]):
                    report.errors.append(
                        f"{source.relative_to(root)}:{number}: unescaped Wiki alias in table; use \\| instead of |"
                    )
                check(source, number, match[1], wiki=True)
            for destination in markdown_destinations(WIKI.sub("", line)):
                check(source, number, destination, wiki=False)
    return report


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    args = parser.parse_args()
    report = validate(args.root)
    for error in report.errors:
        print(error)
    print(f"Docs: {report.documents}; local links: {report.local_links}; external links skipped: {report.external_links}; errors: {len(report.errors)}")
    return 1 if report.errors else 0


if __name__ == "__main__":
    sys.exit(main())

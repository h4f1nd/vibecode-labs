from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

REQUIRED = [
    "README.md",
    "AGENTS.md",
    "CLAUDE.md",
    "CONTRIBUTING.md",
    "CHANGELOG.md",
    "THIRD_PARTY_NOTICES.md",
    "docs/USAGE.md",
    "docs/CLAVIEW.md",
    "docs/ARCHITECTURE.md",
    "docs/FORMAT.md",
    "docs/PLAN.md",
    "docs/GLOSSARY.md",
    "build/launcher.py",
    "build/build.ps1",
    "benchmarks/bench_read.py",
]

# The repository is a monorepo, so the pull-request template lives at its root
# and covers both projects. Accept a project-local copy too, for standalone use.
PR_TEMPLATE = ROOT / ".github" / "PULL_REQUEST_TEMPLATE.md"
ROOT_PR_TEMPLATE = ROOT.parent / ".github" / "PULL_REQUEST_TEMPLATE.md"

LINK = re.compile(r"\[[^\]]+\]\(([^)]+)\)")


def markdown_files() -> list[Path]:
    return sorted(
        path
        for path in ROOT.rglob("*.md")
        if ".venv" not in path.parts and "build" not in path.parts
    )


def test_required_documents_exist() -> None:
    for name in REQUIRED:
        path = ROOT / name
        assert path.is_file(), name
        assert path.stat().st_size > 100, name

    template = PR_TEMPLATE if PR_TEMPLATE.is_file() else ROOT_PR_TEMPLATE
    assert template.is_file(), "no pull-request template in the project or repository root"
    assert template.stat().st_size > 100


def test_readme_links_resolve() -> None:
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    for target in LINK.findall(readme):
        if target.startswith(("http://", "https://", "#", "mailto:")):
            continue
        path = (ROOT / target.split("#", 1)[0]).resolve()
        assert path.exists(), f"README link broken: {target}"


def test_docs_links_resolve() -> None:
    for document in (ROOT / "docs").glob("*.md"):
        text = document.read_text(encoding="utf-8")
        for target in LINK.findall(text):
            if target.startswith(("http://", "https://", "#", "mailto:")):
                continue
            path = (document.parent / target.split("#", 1)[0]).resolve()
            assert path.exists(), f"{document.name} link broken: {target}"


def test_required_project_facts() -> None:
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    assert "DOTDAT" in readme
    assert "Clarion 2.x" in readme
    assert "read-only" in readme.lower()
    assert "reference set" in readme
    assert "dotdat.exe" in readme
    assert "functional copy of Clarion Viewer" in readme

    changelog = (ROOT / "CHANGELOG.md").read_text(encoding="utf-8")
    assert "0.1.0" in changelog

    claview = (ROOT / "docs" / "CLAVIEW.md").read_text(encoding="utf-8")
    assert "copy version" in claview
    assert "reverse engineering" in claview
    assert "General Information" in claview
    assert "roughly nine minutes" in claview
    assert "0x0030" in claview

    format_doc = (ROOT / "docs" / "FORMAT.md").read_text(encoding="utf-8")
    assert "0x3343" in format_doc
    assert "1800-12-28" in format_doc
    assert "0x10" in format_doc
    assert "27" in format_doc
    assert "85" in format_doc


def test_no_external_gui_assets() -> None:
    for name in ("index.html", "style.css", "app.js"):
        text = (ROOT / "src" / "dotdat" / "ui" / "web" / name).read_text(encoding="utf-8")
        assert "http://" not in text
        assert "https://" not in text
        assert "<img" not in text.lower()


def test_no_placeholders() -> None:
    for document in markdown_files():
        text = document.read_text(encoding="utf-8")
        assert "TODO" not in text, document


def test_pyproject_points_at_readme() -> None:
    text = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    assert 'readme = "README.md"' in text
    assert "dotdat = \"dotdat.cli:main\"" in text

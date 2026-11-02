"""Documentation is tested, not trusted.

A wrong flag in ``docs/USAGE.md`` is the first bug a new user hits, and a broken
relative link is the second. These tests make both impossible to merge.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest
from typer.testing import CliRunner

from thermaldots.cli import app
from thermaldots.models import DitherMode, OutputFormat

ROOT = Path(__file__).resolve().parents[1]
DOCS = ROOT / "docs"

FLAG = re.compile(r"--[a-z][a-z0-9-]*")
ANSI = re.compile(r"\x1b\[[0-9;]*m")
COMMAND_HEADING = re.compile(r"^## .*?`tdots ([a-z]+)`")
MARKDOWN_LINK = re.compile(r"\[[^\]]*\]\(([^)]+)\)")
TABLE_FIRST_CELL = re.compile(r"^\| `([a-z0-9]+)`", re.MULTILINE)


def _plain(text: str) -> str:
    """Drop terminal styling so option names stay contiguous."""
    return ANSI.sub("", text)


def _command_names() -> list[str]:
    names = []
    for command in app.registered_commands:
        name = command.name or getattr(command.callback, "__name__", "")
        if name:
            names.append(name)
    return sorted(names)


def _usage_sections() -> dict[str, str]:
    """Map each command to the body of its ``## n. `tdots <command>``` section."""
    text = (DOCS / "USAGE.md").read_text(encoding="utf-8")
    sections: dict[str, str] = {}
    for chunk in re.split(r"(?m)^## ", text)[1:]:
        heading, _, body = chunk.partition("\n")
        match = COMMAND_HEADING.match(f"## {heading}")
        if match:
            sections[match.group(1)] = body
    return sections


def _documented_flags(command: str) -> set[str]:
    """Flags named in the option tables of a command's section.

    Only table rows count: the surrounding prose and examples mention flags of
    *other* commands, and treating those as this command's flags is how the
    first version of this test produced a false failure.
    """
    body = _usage_sections()[command]
    rows = [line for line in body.splitlines() if line.lstrip().startswith("|")]
    return set(FLAG.findall("\n".join(rows)))


def _markdown_files() -> list[Path]:
    root_files = [ROOT / name for name in ("README.md", "AGENTS.md", "CONTRIBUTING.md", "CHANGELOG.md")]
    return [path for path in root_files + sorted(DOCS.glob("*.md")) if path.exists()]


def _slugs(markdown: str) -> set[str]:
    slugs: set[str] = set()
    for line in markdown.splitlines():
        if not line.startswith("#"):
            continue
        heading = line.lstrip("#").strip().lower()
        heading = re.sub(r"[^\w\s-]", "", heading)
        slugs.add(re.sub(r"\s+", "-", heading))
    return slugs


def test_every_command_is_documented() -> None:
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    usage = (DOCS / "USAGE.md").read_text(encoding="utf-8")
    for name in _command_names():
        assert f"tdots {name}" in readme, f"README.md does not mention 'tdots {name}'"
        assert f"tdots {name}" in usage, f"docs/USAGE.md has no section for 'tdots {name}'"


@pytest.mark.parametrize("command", sorted(_usage_sections()))
def test_documented_flags_exist_in_help(command: str) -> None:
    documented = _documented_flags(command)
    if not documented:
        pytest.skip(f"{command} has no options to document")

    result = CliRunner().invoke(app, [command, "--help"], env={"COLUMNS": "200"})
    assert result.exit_code == 0, f"'tdots {command} --help' failed"
    output = _plain(result.output)
    missing = sorted(flag for flag in documented if flag not in output)
    assert not missing, f"docs/USAGE.md documents flags that --help does not accept: {missing}"


def test_convert_help_flags_are_all_documented() -> None:
    """The inverse check: no accepted flag may be missing from the docs."""
    result = CliRunner().invoke(app, ["convert", "--help"], env={"COLUMNS": "200"})
    assert result.exit_code == 0
    accepted = set(FLAG.findall(_plain(result.output))) - {"--help"}
    documented = _documented_flags("convert")
    assert accepted == documented, (
        f"undocumented: {sorted(accepted - documented)}; "
        f"documented but unknown: {sorted(documented - accepted)}"
    )


def test_readme_dither_table_matches_enum() -> None:
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    section = readme.split("## Dither modes", 1)[1].split("\n## ", 1)[0]
    documented = set(TABLE_FIRST_CELL.findall(section))
    assert documented == {mode.value for mode in DitherMode}


def test_readme_format_table_matches_enum() -> None:
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    section = readme.split("## Output formats", 1)[1].split("\n## ", 1)[0]
    documented = set(re.findall(r"-f ([a-z]+)", section))
    assert documented == {fmt.value for fmt in OutputFormat}


@pytest.mark.parametrize("path", _markdown_files(), ids=lambda path: path.name)
def test_relative_links_resolve(path: Path) -> None:
    for target in MARKDOWN_LINK.findall(path.read_text(encoding="utf-8")):
        if target.startswith(("http://", "https://", "mailto:")):
            continue

        file_part, _, anchor = target.partition("#")
        if not file_part:  # same-page anchor
            assert anchor in _slugs(path.read_text(encoding="utf-8")), (
                f"{path.name}: missing anchor #{anchor}"
            )
            continue

        resolved = (path.parent / file_part).resolve()
        assert resolved.exists(), f"{path.name}: broken link -> {target}"

        if anchor and resolved.suffix == ".md":
            assert anchor in _slugs(resolved.read_text(encoding="utf-8")), (
                f"{path.name}: missing anchor #{anchor} in {file_part}"
            )

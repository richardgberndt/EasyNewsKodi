#!/usr/bin/env python3
"""Cut a release of the EasyNews Kodi add-on.

The script bumps every tracked version location, rebuilds the repo index
(``addons.xml`` and ``addons.xml.md5``) from the add-on sources, and writes
install zips into a configurable datadir. Hosting URLs are read from
``tools/release.json`` and may be overridden on the command line. They are
copied into a repository add-on only when that source tree exists and the
URL is non-empty.

Examples::

    python3 tools/release.py --check
    python3 tools/release.py 6.6.2 --news "- What changed." --dry-run
    python3 tools/release.py 6.6.2 --news "- What changed."
"""

from __future__ import annotations

import argparse
import difflib
import hashlib
import json
import re
import sys
import xml.etree.ElementTree as ET
import zipfile
from pathlib import Path
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parent.parent
CONFIG_NAME = "release.json"

VERSION_RE = re.compile(r"^\d+\.\d+\.\d+(?:\.\d+)*$")
NEWS_HEADER_RE = re.compile(r"^v(\d+\.\d+\.\d+(?:\.\d+)*)\s*$")

DEFAULTS = {
    "plugin_id": "plugin.video.easynewsx",
    "datadir": "dist",
    "info_url": "",
    "checksum_url": "",
    "datadir_url": "",
}

JUNK_DIR_NAMES = {"__MACOSX", "__pycache__"}
JUNK_FILE_NAMES = {".DS_Store", "Thumbs.db"}
JUNK_SUFFIXES = {".pyc", ".pyo"}

ADDON_TAG_RE = re.compile(r"<addon\b[^>]*>", re.DOTALL)
ADDON_ELEMENT_RE = re.compile(r"<addon\b.*?</addon>", re.DOTALL)
NEWS_ELEMENT_RE = re.compile(r"<news>(.*?)</news>", re.DOTALL)
LATEST_HEADING_RE = re.compile(
    r"^## Latest release v(\d+\.\d+\.\d+(?:\.\d+)*)[ \t]*$",
    re.MULTILINE,
)
PREVIOUS_HEADING_RE = re.compile(r"^## Previous releases[^\n]*\n", re.MULTILINE)
CONSTANT_RE = re.compile(r'^(ADDON_VERSION\s*=\s*")[^"]+(")', re.MULTILINE)
WELCOME_RE = re.compile(r"\(v\d+\.\d+\.\d+(?:\.\d+)*\)")


class ReleaseError(Exception):
    """A release step cannot be completed."""


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        config = load_config(args)
        if args.check:
            return run_check(config)
        if not args.version:
            raise ReleaseError("pass a version, or use --check")
        version = normalize_version(args.version)
        news = None if args.news is None else "\n".join(args.news).strip()
        return run_release(config, version, news, dry_run=args.dry_run)
    except ReleaseError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1


def parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Bump EasyNews version locations, rebuild addons.xml, and pack "
            "the add-on zip. Hosting URLs come from tools/release.json."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "examples:\n"
            "  python3 tools/release.py --check\n"
            "  python3 tools/release.py 6.6.2 --news \"- What changed.\" --dry-run\n"
            "  python3 tools/release.py 6.6.2 --news \"- What changed.\""
        ),
    )
    parser.add_argument(
        "version",
        nargs="?",
        help="New version, for example 6.6.2 (a leading v is accepted)",
    )
    parser.add_argument(
        "--news",
        action="append",
        help="Release notes inserted at the top of <news> and the README. Repeat to add lines.",
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="Verify version locations agree and addons.xml.md5 matches. Write nothing.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print the changes and zip paths without writing files.",
    )
    parser.add_argument(
        "--config",
        help="Path to a JSON config file (default: tools/release.json)",
    )
    parser.add_argument("--datadir", help="Local directory that receives built zips")
    parser.add_argument("--info-url", help="Public URL of addons.xml")
    parser.add_argument("--checksum-url", help="Public URL of addons.xml.md5")
    parser.add_argument(
        "--datadir-url",
        help="Public base URL used as <datadir zip=\"true\">",
    )
    args = parser.parse_args(argv)
    if args.check and args.version:
        parser.error("--check does not take a version")
    if args.check and args.dry_run:
        parser.error("--check already writes nothing; omit --dry-run")
    if args.check and args.news:
        parser.error("--check does not take --news")
    return args


def load_config(args: argparse.Namespace) -> dict[str, str]:
    path = Path(args.config) if args.config else ROOT / "tools" / CONFIG_NAME
    if args.config and not path.is_file():
        raise ReleaseError(f"config not found: {path}")
    data = dict(DEFAULTS)
    if path.is_file():
        try:
            loaded = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise ReleaseError(f"{path}: {exc}") from exc
        if not isinstance(loaded, dict):
            raise ReleaseError(f"{path} must contain a JSON object")
        unknown = sorted(set(loaded) - set(DEFAULTS))
        if unknown:
            raise ReleaseError(
                f"{path} has unknown keys: {', '.join(unknown)}"
            )
        for key, value in loaded.items():
            if not isinstance(value, str):
                raise ReleaseError(f"{path}: {key} must be a string")
            data[key] = value
    overrides = {
        "datadir": args.datadir,
        "info_url": args.info_url,
        "checksum_url": args.checksum_url,
        "datadir_url": args.datadir_url,
    }
    for key, value in overrides.items():
        if value is not None:
            data[key] = value
    for key in ("info_url", "checksum_url", "datadir_url"):
        validate_url(key, data[key])
    if not data["plugin_id"] or "/" in data["plugin_id"] or "\\" in data["plugin_id"]:
        raise ReleaseError(f"invalid plugin_id {data['plugin_id']!r}")
    if not data["datadir"]:
        raise ReleaseError("datadir is empty")
    return data


def validate_url(name: str, value: str) -> None:
    if value == "":
        return
    if any(ch.isspace() for ch in value) or "<" in value or ">" in value:
        raise ReleaseError(f"{name} must be an http(s) URL without spaces")
    parsed = urlparse(value)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise ReleaseError(f"{name} must be an http(s) URL, got {value!r}")


def normalize_version(raw: str) -> str:
    version = raw[1:] if raw.startswith("v") else raw
    if not VERSION_RE.match(version):
        raise ReleaseError(
            f"version must look like 6.6.2, got {raw!r}"
        )
    return version


def run_check(config: dict[str, str]) -> int:
    problems = collect_problems(config)
    if problems:
        print("Version check failed:", file=sys.stderr)
        for problem in problems:
            print(f"  {problem}", file=sys.stderr)
        return 1
    version = read_versions(config)["plugin addon.xml version"]
    print(f"Versions agree at {version}")
    for label in version_labels():
        print(f"  {label}")
    print("addons.xml.md5 matches addons.xml")
    print(format_hosting(config))
    return 0


def run_release(
    config: dict[str, str],
    version: str,
    news: str | None,
    dry_run: bool,
) -> int:
    plugin_id = config["plugin_id"]
    locations = source_paths(plugin_id)
    for label, path in locations.items():
        if not path.is_file():
            raise ReleaseError(f"missing {label}: {path.relative_to(ROOT)}")

    original = {label: path.read_text(encoding="utf-8") for label, path in locations.items()}
    updated = dict(original)
    updated["addon.xml"] = update_addon_xml(original["addon.xml"], version, news)
    updated["constants.py"] = update_constants(original["constants.py"], version)
    updated["userguide.json"] = update_userguide(original["userguide.json"], version)
    updated["README.md"] = update_readme(original["README.md"], version, news)

    repo_dirs = repository_dirs(plugin_id)
    repo_updates: dict[Path, tuple[str, str]] = {}
    for repo_dir in repo_dirs:
        path = repo_dir / "addon.xml"
        old = path.read_text(encoding="utf-8")
        new = update_repository_urls(
            old,
            config["info_url"],
            config["checksum_url"],
            config["datadir_url"],
        )
        repo_updates[path] = (old, new)

    addon_sources = collect_addon_sources(plugin_id, updated["addon.xml"], repo_updates)
    addons_xml = render_addons_xml(addon_sources)
    parse_xml_text(addons_xml, "addons.xml")
    md5_text = hashlib.md5(addons_xml.encode("utf-8")).hexdigest() + "\n"

    index_path = ROOT / "addons.xml"
    md5_path = ROOT / "addons.xml.md5"
    text_changes: list[tuple[Path, str, str]] = [
        (path, original[label], updated[label]) for label, path in locations.items()
    ]
    text_changes.append((index_path, read_optional(index_path), addons_xml))
    text_changes.append((md5_path, read_optional(md5_path), md5_text))
    for path, (old, new) in repo_updates.items():
        text_changes.append((path, old, new))

    print(f"Release {plugin_id} {version}")
    print(format_hosting(config))
    if repo_dirs and not any(config[key] for key in ("info_url", "checksum_url", "datadir_url")):
        print("Repository add-on URLs left unchanged (hosting URLs are empty).")
    elif not repo_dirs:
        print(
            "No repository add-on source directory found. "
            "Hosting URLs were not written into an add-on."
        )
    print()

    for path, old, new in text_changes:
        rel = display_path(path)
        if old == new:
            print(f"unchanged {rel}")
            continue
        print(f"update {rel}")
        sys.stdout.writelines(unified_diff(rel, old, new))

    datadir = resolve_datadir(config["datadir"])
    zip_plans = plan_zips(plugin_id, version, addon_sources, datadir)
    print()
    for plan in zip_plans:
        print(
            f"zip {display_path(plan['dest'])} "
            f"({plan['count']} files, top folder {plan['addon_id']}/)"
        )

    if dry_run:
        print("\nDry run; no files written.")
        return 0

    for path, _old, new in text_changes:
        current = path.read_text(encoding="utf-8") if path.is_file() else None
        if current != new:
            write_text(path, new)
    for plan in zip_plans:
        write_zip(plan["source_dir"], plan["dest"], plan["addon_id"])
        verify_zip(plan["dest"], plan["addon_id"], plan["version"])

    problems = collect_problems(config)
    if problems:
        raise ReleaseError(
            "release wrote files but versions still disagree:\n  "
            + "\n  ".join(problems)
        )
    print("\nRelease files written. Version check passed.")
    return 0


def source_paths(plugin_id: str) -> dict[str, Path]:
    plugin = ROOT / plugin_id
    return {
        "addon.xml": plugin / "addon.xml",
        "constants.py": plugin / "resources" / "lib" / "easynews" / "constants.py",
        "userguide.json": plugin / "resources" / "userguide.json",
        "README.md": ROOT / "README.md",
    }


def version_labels() -> list[str]:
    return [
        "plugin addon.xml version",
        "plugin addon.xml news",
        "ADDON_VERSION",
        "userguide welcome",
        "addons.xml",
        "README latest release",
    ]


def read_versions(config: dict[str, str]) -> dict[str, str]:
    plugin_id = config["plugin_id"]
    paths = source_paths(plugin_id)
    versions: dict[str, str] = {}

    addon_text = paths["addon.xml"].read_text(encoding="utf-8")
    addon_root = parse_xml_text(addon_text, str(paths["addon.xml"].relative_to(ROOT)))
    if addon_root.tag != "addon":
        raise ReleaseError("plugin addon.xml root is not <addon>")
    if addon_root.attrib.get("id") != plugin_id:
        raise ReleaseError(
            f"plugin addon.xml id is {addon_root.attrib.get('id')!r}, expected {plugin_id}"
        )
    versions["plugin addon.xml version"] = addon_root.attrib.get("version", "")
    news_el = addon_root.find("./extension[@point='xbmc.addon.metadata']/news")
    news_text = (news_el.text or "").lstrip("\r\n") if news_el is not None else ""
    news_line = news_text.splitlines()[0] if news_text.splitlines() else ""
    news_match = NEWS_HEADER_RE.match(news_line)
    versions["plugin addon.xml news"] = news_match.group(1) if news_match else ""

    constants = paths["constants.py"].read_text(encoding="utf-8")
    constant_match = re.search(r'^ADDON_VERSION\s*=\s*"([^"]*)"', constants, re.MULTILINE)
    versions["ADDON_VERSION"] = constant_match.group(1) if constant_match else ""

    guide = json.loads(paths["userguide.json"].read_text(encoding="utf-8"))
    title = guide[0]["title"] if isinstance(guide, list) and guide else ""
    welcome = re.search(r"\(v(\d+\.\d+\.\d+(?:\.\d+)*)\)", title)
    versions["userguide welcome"] = welcome.group(1) if welcome else ""

    index_path = ROOT / "addons.xml"
    index_root = ET.parse(index_path).getroot()
    found = ""
    for addon in index_root.findall("addon"):
        if addon.attrib.get("id") == plugin_id:
            found = addon.attrib.get("version", "")
            break
    versions["addons.xml"] = found

    readme = paths["README.md"].read_text(encoding="utf-8")
    readme_match = LATEST_HEADING_RE.search(readme)
    versions["README latest release"] = readme_match.group(1) if readme_match else ""
    return versions


def collect_problems(config: dict[str, str]) -> list[str]:
    problems: list[str] = []
    index_path = ROOT / "addons.xml"
    md5_path = ROOT / "addons.xml.md5"
    try:
        versions = read_versions(config)
    except (ReleaseError, ET.ParseError, json.JSONDecodeError, OSError, IndexError, KeyError) as exc:
        return [str(exc)]

    present = [versions[label] for label in version_labels()]
    unique = {value for value in present if value}
    if "" in present or len(unique) != 1:
        for label in version_labels():
            value = versions[label] or "(missing)"
            problems.append(f"{label}: {value}")
    elif not VERSION_RE.match(next(iter(unique))):
        problems.append(f"version {next(iter(unique))!r} is not x.y.z")

    try:
        ET.parse(index_path)
    except ET.ParseError as exc:
        problems.append(f"addons.xml does not parse: {exc}")
    try:
        digest = hashlib.md5(index_path.read_bytes()).hexdigest()
    except OSError as exc:
        problems.append(f"addons.xml: {exc}")
        digest = ""
    try:
        recorded = md5_path.read_text(encoding="utf-8").strip().split()
    except OSError as exc:
        problems.append(f"addons.xml.md5: {exc}")
        recorded = []
    if digest and (not recorded or recorded[0].lower() != digest):
        got = recorded[0] if recorded else "(missing)"
        problems.append(f"addons.xml.md5 is {got}, expected {digest}")
    return problems


def update_addon_xml(text: str, version: str, news: str | None) -> str:
    return update_news(update_version_attribute(text, version), version, news)


def update_version_attribute(text: str, version: str) -> str:
    match = ADDON_TAG_RE.search(text)
    if not match:
        raise ReleaseError("addon.xml has no <addon> tag")
    tag = match.group(0)
    new_tag, count = re.subn(
        r'\bversion="[^"]*"',
        f'version="{version}"',
        tag,
        count=1,
    )
    if count != 1:
        raise ReleaseError("addon.xml <addon> tag has no version attribute")
    return text[: match.start()] + new_tag + text[match.end() :]


def update_news(text: str, version: str, news: str | None) -> str:
    match = NEWS_ELEMENT_RE.search(text)
    if not match:
        raise ReleaseError("addon.xml has no <news> element")
    body = match.group(1)
    trailing = ""
    trailing_match = re.search(r"(\n[ \t]*)$", body)
    if trailing_match:
        trailing = trailing_match.group(1)
        core = body[: trailing_match.start()]
    else:
        core = body
    lines = core.splitlines()
    current = lines[0] if lines else ""
    already = NEWS_HEADER_RE.match(current) and NEWS_HEADER_RE.match(current).group(1) == version
    if already and news is None:
        return text
    if already:
        rest_lines = lines[1:]
        split_at = len(rest_lines)
        for index, line in enumerate(rest_lines):
            if NEWS_HEADER_RE.match(line):
                split_at = index
                break
        older = "\n".join(rest_lines[split_at:])
    else:
        older = core
    section = f"v{version}"
    if news:
        section += "\n" + xml_text(news.strip())
    section += "\n\n"
    new_core = section + older if older else section.rstrip("\n")
    new_body = new_core + trailing
    return text[: match.start()] + "<news>" + new_body + "</news>" + text[match.end() :]


def xml_text(value: str) -> str:
    return value.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def update_constants(text: str, version: str) -> str:
    new, count = CONSTANT_RE.subn(rf"\g<1>{version}\2", text, count=1)
    if count != 1:
        raise ReleaseError('ADDON_VERSION = "..." was not found in constants.py')
    return new


def update_userguide(text: str, version: str) -> str:
    new, count = WELCOME_RE.subn(f"(v{version})", text, count=1)
    if count != 1:
        raise ReleaseError("userguide.json is missing a welcome '(vX.Y.Z)' marker")
    try:
        guide = json.loads(new)
        title = guide[0]["title"]
    except (json.JSONDecodeError, IndexError, KeyError, TypeError) as exc:
        raise ReleaseError(f"userguide.json could not be read after the version bump: {exc}") from exc
    if f"(v{version})" not in title:
        raise ReleaseError("the first userguide entry is not the welcome version line")
    return new


def update_readme(text: str, version: str, news: str | None) -> str:
    match = LATEST_HEADING_RE.search(text)
    if not match:
        raise ReleaseError("README is missing a '## Latest release vX.Y.Z' heading")
    old_version = match.group(1)
    next_heading = re.search(r"^## ", text[match.end() :], re.MULTILINE)
    if not next_heading:
        raise ReleaseError("README Latest release section has no following heading")
    body_end = match.end() + next_heading.start()
    old_body = text[match.end() : body_end].strip("\n")
    if old_version == version and news is None:
        return text
    block = f"## Latest release v{version}\n\n"
    if news:
        block += news.strip() + "\n\n"
    updated = text[: match.start()] + block + text[body_end:]
    if old_version == version:
        return updated
    previous = PREVIOUS_HEADING_RE.search(updated)
    if not previous:
        raise ReleaseError("README is missing a '## Previous releases' heading")
    rest = updated[previous.end() :].lstrip("\n")
    archive = f"\n{old_version}\n\n"
    if old_body:
        archive += old_body + "\n\n"
    return updated[: previous.end()] + archive + rest


def repository_dirs(plugin_id: str) -> list[Path]:
    found: list[Path] = []
    for path in addon_dirs():
        if path.name == plugin_id:
            continue
        text = (path / "addon.xml").read_text(encoding="utf-8")
        if is_repository(text):
            found.append(path)
    return found


def addon_dirs() -> list[Path]:
    dirs: list[Path] = []
    for path in sorted(ROOT.iterdir(), key=lambda item: item.name):
        if path.is_dir() and (path / "addon.xml").is_file():
            dirs.append(path)
    return dirs


def is_repository(text: str) -> bool:
    try:
        root = ET.fromstring(text)
    except ET.ParseError as exc:
        raise ReleaseError(f"invalid addon.xml: {exc}") from exc
    return any(
        ext.attrib.get("point") == "xbmc.addon.repository"
        for ext in root.findall("extension")
    )


def update_repository_urls(text: str, info_url: str, checksum_url: str, datadir_url: str) -> str:
    replacements = (
        ("info", info_url),
        ("checksum", checksum_url),
        ("datadir", datadir_url),
    )
    for tag, value in replacements:
        if not value:
            continue
        text = replace_element_text(text, tag, value)
    return text


def replace_element_text(text: str, tag: str, value: str) -> str:
    pattern = re.compile(rf"(<{tag}\b[^>]*>)(.*?)(</{tag}>)", re.DOTALL)

    def replacer(match: re.Match[str]) -> str:
        return match.group(1) + xml_text(value) + match.group(3)

    new, count = pattern.subn(replacer, text)
    if count == 0:
        raise ReleaseError(f"repository addon.xml has no <{tag}> element")
    return new


def collect_addon_sources(
    plugin_id: str,
    plugin_addon_xml: str,
    repo_updates: dict[Path, tuple[str, str]],
) -> list[tuple[str, str]]:
    """Return (addon id, addon element text) for every add-on directory."""
    sources: list[tuple[str, str]] = []
    seen: set[str] = set()
    for path in addon_dirs():
        addon_path = path / "addon.xml"
        if path.name == plugin_id:
            text = plugin_addon_xml
        elif addon_path in repo_updates:
            text = repo_updates[addon_path][1]
        else:
            text = addon_path.read_text(encoding="utf-8")
        element = extract_addon_element(text, addon_path)
        addon_id = ET.fromstring(element).attrib.get("id", "")
        if not addon_id:
            raise ReleaseError(f"{display_path(addon_path)} has no addon id")
        if addon_id != path.name:
            raise ReleaseError(
                f"{display_path(addon_path)} id {addon_id} does not match directory {path.name}"
            )
        if addon_id in seen:
            raise ReleaseError(f"duplicate addon id {addon_id}")
        seen.add(addon_id)
        sources.append((addon_id, element))
    sources.sort(key=lambda item: item[0])
    if plugin_id not in seen:
        raise ReleaseError(f"no add-on directory named {plugin_id}")
    return sources


def extract_addon_element(text: str, path: Path) -> str:
    match = ADDON_ELEMENT_RE.search(text)
    if not match:
        raise ReleaseError(f"{display_path(path)} has no <addon> element")
    element = match.group(0).strip()
    parse_xml_text(element, display_path(path))
    return element


def render_addons_xml(sources: list[tuple[str, str]]) -> str:
    body = "\n\n".join(element for _addon_id, element in sources)
    return (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        "<addons>\n"
        f"{body}\n"
        "</addons>\n"
    )


def plan_zips(
    plugin_id: str,
    version: str,
    sources: list[tuple[str, str]],
    datadir: Path,
) -> list[dict[str, object]]:
    plans: list[dict[str, object]] = []
    source_versions = {addon_id: version_of_element(element) for addon_id, element in sources}
    for addon_dir in addon_dirs():
        addon_id = addon_dir.name
        if addon_id not in source_versions:
            continue
        addon_version = source_versions[addon_id]
        if addon_id == plugin_id and addon_version != version:
            raise ReleaseError(
                f"{plugin_id} addon.xml version is {addon_version}, expected {version}"
            )
        files = list(iter_pack_files(addon_dir))
        if not files:
            raise ReleaseError(f"{addon_id} has no files to pack")
        dest = datadir / addon_id / f"{addon_id}-{addon_version}.zip"
        plans.append(
            {
                "addon_id": addon_id,
                "version": addon_version,
                "source_dir": addon_dir,
                "dest": dest,
                "count": len(files),
            }
        )
    return plans


def version_of_element(element: str) -> str:
    return ET.fromstring(element).attrib.get("version", "")


def iter_pack_files(addon_dir: Path) -> list[Path]:
    files: list[Path] = []
    for path in addon_dir.rglob("*"):
        if not path.is_file() or path.is_symlink():
            continue
        relative = path.relative_to(addon_dir)
        if any(part in JUNK_DIR_NAMES for part in relative.parts):
            continue
        if path.name in JUNK_FILE_NAMES or path.name.startswith("._"):
            continue
        if path.suffix in JUNK_SUFFIXES:
            continue
        files.append(path)
    files.sort()
    return files


def write_zip(addon_dir: Path, dest: Path, addon_id: str) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_suffix(dest.suffix + ".tmp")
    if tmp.exists():
        tmp.unlink()
    with zipfile.ZipFile(tmp, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for path in iter_pack_files(addon_dir):
            arcname = f"{addon_id}/{path.relative_to(addon_dir).as_posix()}"
            if "\\" in arcname or arcname.startswith("/"):
                raise ReleaseError(f"refusing zip entry {arcname}")
            archive.write(path, arcname=arcname)
    tmp.replace(dest)


def verify_zip(dest: Path, addon_id: str, version: str) -> None:
    with zipfile.ZipFile(dest) as archive:
        names = archive.namelist()
        if not names:
            raise ReleaseError(f"{display_path(dest)} is empty")
        for name in names:
            if "\\" in name or name.startswith("/") or not name.startswith(f"{addon_id}/"):
                raise ReleaseError(f"{display_path(dest)} has unexpected entry {name}")
            base = name.rsplit("/", 1)[-1]
            if (
                "__MACOSX" in name.split("/")
                or base in JUNK_FILE_NAMES
                or base.startswith("._")
                or name.endswith(tuple(JUNK_SUFFIXES))
            ):
                raise ReleaseError(f"{display_path(dest)} contains junk entry {name}")
        addon_xml_name = f"{addon_id}/addon.xml"
        if addon_xml_name not in names:
            raise ReleaseError(f"{display_path(dest)} is missing {addon_xml_name}")
        root = ET.fromstring(archive.read(addon_xml_name))
        if root.attrib.get("id") != addon_id or root.attrib.get("version") != version:
            raise ReleaseError(
                f"{display_path(dest)} addon.xml is "
                f"{root.attrib.get('id')} {root.attrib.get('version')}"
            )


def resolve_datadir(value: str) -> Path:
    path = Path(value)
    if not path.is_absolute():
        path = ROOT / path
    return path


def read_optional(path: Path) -> str:
    if not path.is_file():
        return ""
    return path.read_text(encoding="utf-8")


def write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_bytes(text.encode("utf-8"))
    tmp.replace(path)


def parse_xml_text(text: str, label: str) -> ET.Element:
    try:
        return ET.fromstring(text)
    except ET.ParseError as exc:
        raise ReleaseError(f"{label} is not valid XML: {exc}") from exc


def unified_diff(label: str, old: str, new: str) -> list[str]:
    def lines(text: str) -> list[str]:
        parts = text.splitlines(keepends=True)
        if parts and not parts[-1].endswith(("\n", "\r")):
            parts[-1] += "\n"
        return parts

    return list(
        difflib.unified_diff(
            lines(old),
            lines(new),
            fromfile=f"a/{label}",
            tofile=f"b/{label}",
            n=2,
        )
    )


def display_path(path: Path) -> str:
    try:
        return path.relative_to(ROOT).as_posix()
    except ValueError:
        return str(path)


def format_hosting(config: dict[str, str]) -> str:
    datadir = resolve_datadir(config["datadir"])
    lines = [
        "Hosting:",
        f"  datadir: {datadir}",
        f"  info_url: {config['info_url'] or '(empty)'}",
        f"  checksum_url: {config['checksum_url'] or '(empty)'}",
        f"  datadir_url: {config['datadir_url'] or '(empty)'}",
    ]
    return "\n".join(lines)


if __name__ == "__main__":
    sys.exit(main())

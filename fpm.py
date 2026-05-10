#!/usr/bin/env python3
"""
fpm - Flux Package Manager

Copyright (C) 2026 Karac V. Thweatt

Downloads and manages Flux standard library and third-party packages.

Usage:
    fpm install <package>       Install a specific package
    fpm install --stdlib        Install the full standard library
    fpm install --all           Install everything (stdlib + registered packages)
    fpm list                    List installed packages
    fpm list --available        List all available packages
    fpm remove <package>        Remove an installed package
    fpm update <package>        Update a package to latest
    fpm update --all            Update all installed packages
    fpm info <package>          Show package details
    fpm create                  Interactively scaffold a new Flux package
    fpm addsource <url>         Add a remote package source
    fpm removesource <url>      Remove a package source
    fpm sources                 List configured sources
    fpm publish <package>       Publish a local package to the fpm server on port 8080
"""

import os
import sys
import json
import argparse
import urllib.request
import urllib.error
import urllib.parse
import shutil
from pathlib import Path
from typing import Optional

# ─── Constants ────────────────────────────────────────────────────────────────

# Resolve project root: prefer FLUXC_SRCDIR env var (set by fxc.py), fall back
# to a sibling-of-this-script heuristic so fpm can also be run standalone.
FLUXC_SRCDIR    = Path(os.environ.get("FLUXC_SRCDIR", Path(__file__).parent)).resolve()

FPM_DIR         = FLUXC_SRCDIR / ".fpm"
STDLIB_DIR      = FLUXC_SRCDIR / "src" / "stdlib"
PACKAGES_DIR    = FPM_DIR / "packages"
REGISTRY_FILE   = FPM_DIR / "registry.json"
INSTALLED_FILE  = FPM_DIR / "installed.json"
SOURCES_FILE    = FPM_DIR / "sources.json"
STDLIB_BASE_URL = "https://raw.githubusercontent.com/kvthweatt/FluxLang/main/src/stdlib"
FPM_USER_AGENT  = "FluxPackageManager-1.0.0"
FPM_SERVER_PORT = 8080

# Loaded from STDLIB_DIR/package.json at startup — do not hardcode here
STDLIB_PACKAGES = {}


# ─── Stdlib helpers ───────────────────────────────────────────────────────────

def load_stdlib_json() -> dict:
    """Read STDLIB_DIR/package.json and return the packages dict."""
    stdlib_json = STDLIB_DIR / "package.json"
    if not stdlib_json.exists():
        print(f"WARNING: stdlib package.json not found at {stdlib_json}")
        return {}
    with open(stdlib_json) as f:
        data = json.load(f)
    packages = {}
    for name, pkg in data.get("packages", {}).items():
        entry = dict(pkg)
        entry.setdefault("path", "")
        packages[name] = entry
    return packages


def fetch_remote_stdlib_json() -> dict:
    """Fetch the stdlib package.json from GitHub and return the packages dict."""
    url = f"{STDLIB_BASE_URL}/package.json"
    require_https(url)
    try:
        with urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": FPM_USER_AGENT}), timeout=15) as response:
            data = json.loads(response.read().decode("utf-8"))
        packages = {}
        for name, pkg in data.get("packages", {}).items():
            entry = dict(pkg)
            entry.setdefault("path", "")
            packages[name] = entry
        return packages
    except urllib.error.HTTPError as e:
        print(f"  ERROR: HTTP {e.code} fetching remote stdlib package.json")
        return {}
    except urllib.error.URLError as e:
        print(f"  ERROR: Could not reach GitHub — {e.reason}")
        return {}


def is_stdlib_package(name: str) -> bool:
    return name in STDLIB_PACKAGES


def get_stdlib_files(pkg: dict) -> list[Path]:
    """Return a list of resolved stdlib Paths for a package (handles entry and entries)."""
    sub_path = pkg.get("path", "")
    if "entries" in pkg:
        base = STDLIB_DIR / sub_path if sub_path else STDLIB_DIR
        return [base / filename for filename in pkg["entries"].values()]
    entry = pkg["entry"]
    if sub_path:
        return [STDLIB_DIR / sub_path / entry]
    return [STDLIB_DIR / entry]


def stdlib_installed_entry(name: str) -> dict:
    pkg   = STDLIB_PACKAGES[name]
    files = get_stdlib_files(pkg)
    rec = {
        "version": pkg["version"],
        "path":    pkg.get("path", ""),
        "files":   [str(f) for f in files],
        "source":  "stdlib"
    }
    if "entries" in pkg:
        rec["entries"] = pkg["entries"]
    else:
        rec["entry"] = pkg["entry"]
        rec["file"]  = str(files[0])
    return rec


# ─── Version constraint parsing ───────────────────────────────────────────────

def parse_version(version_str: str) -> tuple:
    """Parse a version string like '1.2.3' into a comparable tuple."""
    try:
        return tuple(int(x) for x in version_str.strip().split("."))
    except ValueError:
        return (0, 0, 0)


def check_version_constraint(installed_version: str, constraint: str) -> bool:
    """
    Check if an installed version satisfies a constraint string.
    Supports: '1.0.0' (exact), '>1.0.0', '<1.0.0', '>=1.0.0', '<=1.0.0',
              '>1.0.0 <2.0.0' (range), '>=1.0.0 <2.0.0' (inclusive range)
    """
    installed = parse_version(installed_version)
    parts = constraint.strip().split()

    def evaluate(part):
        if part.startswith(">="):
            return installed >= parse_version(part[2:])
        elif part.startswith("<="):
            return installed <= parse_version(part[2:])
        elif part.startswith(">"):
            return installed > parse_version(part[1:])
        elif part.startswith("<"):
            return installed < parse_version(part[1:])
        else:
            return installed == parse_version(part)

    return all(evaluate(p) for p in parts)


# ─── HTTP helpers ─────────────────────────────────────────────────────────────

def require_https(url: str):
    """
    Abort with a clear error if url is not HTTPS.
    fpm only ever communicates over encrypted connections.
    """
    if not url.lower().startswith("https://"):
        print(f"  ERROR: Refusing to connect over plain HTTP: {url}")
        print("  All fpm sources must use HTTPS.")
        sys.exit(1)


def download_file(url: str, dest: Path) -> bool:
    """Download a file from a URL to a destination path. Returns True on success."""
    require_https(url)
    try:
        with urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": FPM_USER_AGENT}), timeout=15) as response:
            dest.parent.mkdir(parents=True, exist_ok=True)
            with open(dest, "wb") as f:
                f.write(response.read())
        return True
    except urllib.error.HTTPError as e:
        print(f"  ERROR: HTTP {e.code} fetching {url}")
        return False
    except urllib.error.URLError as e:
        print(f"  ERROR: Could not reach {url} — {e.reason}")
        return False


# ─── Installed package tracking ───────────────────────────────────────────────

def load_installed() -> dict:
    """Load installed.json and overlay stdlib packages so they are always known."""
    installed = {}
    if INSTALLED_FILE.exists():
        with open(INSTALLED_FILE) as f:
            installed = json.load(f)
    for name in STDLIB_PACKAGES:
        installed[name] = stdlib_installed_entry(name)
    return installed


def save_installed(installed: dict):
    FPM_DIR.mkdir(parents=True, exist_ok=True)
    # Don't persist stdlib entries — they are always regenerated from package.json
    to_save = {k: v for k, v in installed.items() if v.get("source") != "stdlib"}
    with open(INSTALLED_FILE, "w") as f:
        json.dump(to_save, f, indent=2)


# ─── Sources ──────────────────────────────────────────────────────────────────
#
# sources.json format:
# {
#   "UTTCex": {
#     "source-owner": "Karac Thweatt",
#     "source-url":   "https://www.uttcex.net/flux/fpm/public"
#   },
#   ...
# }
#
# Each source exposes a packages.json at <source-url>/packages.json:
# {
#   "test-pack1": "https://fluxpacks.site.com/test-pack1/package.json",
#   "test-pack2": "https://fluxpacks.site.com/test-pack2/package.json"
# }
#
# Each package.json URL points to an individual package manifest.

def load_sources() -> dict:
    """Load sources.json — dict of {name: {source-owner, source-url}}."""
    if SOURCES_FILE.exists():
        with open(SOURCES_FILE) as f:
            return json.load(f)
    return {}


def save_sources(sources: dict):
    FPM_DIR.mkdir(parents=True, exist_ok=True)
    with open(SOURCES_FILE, "w") as f:
        json.dump(sources, f, indent=2)


def fetch_packages_index(base_url: str) -> dict:
    """
    Fetch <base_url>/packages.json — the index for a source.
    Returns {pkg_name: package_json_url} or {} on failure.
    """
    base_url = base_url.rstrip("/")
    url = f"{base_url}/packages.json"
    require_https(url)
    try:
        with urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": FPM_USER_AGENT}), timeout=15) as response:
            data = json.loads(response.read().decode("utf-8"))
        if not isinstance(data, dict):
            print(f"  ERROR: {url} did not return a JSON object.")
            return {}
        return data
    except urllib.error.HTTPError as e:
        print(f"  ERROR: HTTP {e.code} fetching {url}")
        return {}
    except urllib.error.URLError as e:
        print(f"  ERROR: Could not reach {url} — {e.reason}")
        return {}


def fetch_package_manifest(pkg_name: str, pkg_json_url: str, source_name: str) -> Optional[dict]:
    """
    Fetch an individual package.json URL and return the package metadata dict,
    or None on failure.
    """
    require_https(pkg_json_url)
    try:
        with urllib.request.urlopen(urllib.request.Request(pkg_json_url, headers={"User-Agent": FPM_USER_AGENT}), timeout=15) as response:
            data = json.loads(response.read().decode("utf-8"))
        # package.json may be wrapped in {"packages": {name: {...}}} or be the
        # metadata dict directly — handle both.
        if "packages" in data:
            inner = data["packages"]
            pkg = inner.get(pkg_name) or next(iter(inner.values()), None)
        else:
            pkg = data
        if not isinstance(pkg, dict):
            print(f"  ERROR: Unexpected format in {pkg_json_url}")
            return None
        pkg = dict(pkg)
        pkg.setdefault("path", "")
        pkg["_source_url"]  = pkg_json_url
        pkg["_source_name"] = source_name
        return pkg
    except urllib.error.HTTPError as e:
        print(f"  ERROR: HTTP {e.code} fetching {pkg_json_url}")
        return None
    except urllib.error.URLError as e:
        print(f"  ERROR: Could not reach {pkg_json_url} — {e.reason}")
        return None


def fetch_source(source_name: str, source_info: dict) -> dict:
    """
    Given a source entry from sources.json, fetch its packages.json index and
    then fetch each individual package manifest.
    Returns {pkg_name: metadata_dict}.
    """
    base_url = source_info.get("source-url", "").rstrip("/")
    if not base_url:
        print(f"  ERROR: Source '{source_name}' has no 'source-url'.")
        return {}
    if not base_url.lower().startswith("https://"):
        print(f"  ERROR: Source '{source_name}' uses plain HTTP ({base_url}).")
        print("  Edit sources.json and change the URL to HTTPS, then retry.")
        return {}

    index = fetch_packages_index(base_url)
    if not index:
        return {}

    packages = {}
    for pkg_name, pkg_json_url in index.items():
        manifest = fetch_package_manifest(pkg_name, pkg_json_url, source_name)
        if manifest is not None:
            packages[pkg_name] = manifest
    return packages


def cmd_addsource(args, sources: dict):
    print("\n╔══════════════════════════════════════════╗")
    print("║      fpm addsource — Source Wizard       ║")
    print("╚══════════════════════════════════════════╝")
    print("  Press Ctrl-C at any time to abort.\n")

    # ── Step 1: Source name ───────────────────────────────────────────────────
    _divider("Step 1 of 3 — Source Name")
    print("  A short identifier for this source (e.g. UTTCex, fluxpacks).")
    print("  Used with 'fpm removesource <name>'.\n")
    name = ""
    while not name:
        name = _ask("Source name", "")
        if not name:
            print("  Source name is required.")
        elif name in sources:
            print(f"  '{name}' is already configured ({sources[name]['source-url']}).")
            if _ask_yn("  Overwrite it?", default=False):
                break
            name = ""

    # ── Step 2: Owner ─────────────────────────────────────────────────────────
    _divider("Step 2 of 3 — Owner")
    print("  The name of the person or organization hosting this source.")
    print("  This is displayed in 'fpm sources' so users know who to trust.\n")
    owner = ""
    while not owner:
        owner = _ask("Owner name", "")
        if not owner:
            print("  Owner is required — source hosts must identify themselves.")

    # ── Step 3: URL ───────────────────────────────────────────────────────────
    _divider("Step 3 of 3 — Source URL")
    print("  The base URL of the source. fpm will fetch <url>/packages.json")
    print("  to verify the source before saving.\n")
    url = ""
    index = {}
    while not url:
        raw = _ask("Source URL", "")
        if not raw:
            print("  URL is required.")
            continue
        raw = raw.rstrip("/")
        if not raw.lower().startswith("https://"):
            print("  ERROR: Source URLs must use HTTPS. Plain HTTP is not allowed.")
            continue
        print(f"\n  Verifying {raw}/packages.json...")
        index = fetch_packages_index(raw)
        if not index:
            print(f"  ERROR: Could not fetch a valid packages.json from that URL.")
            if not _ask_yn("  Try a different URL?", default=True):
                print("  Aborted.")
                return
        else:
            url = raw

    # ── Confirm ───────────────────────────────────────────────────────────────
    _divider("Summary")
    print(f"  Name:     {name}")
    print(f"  Owner:    {owner}")
    print(f"  URL:      {url}")
    print(f"  Packages: {len(index)} available ({', '.join(sorted(index.keys()))})")

    _divider()
    if not _ask_yn("Add this source?", default=True):
        print("  Cancelled.")
        return

    sources[name] = {"source-owner": owner, "source-url": url}
    save_sources(sources)
    print(f"\n✔  Source '{name}' added.")
    print(f"   Run 'fpm install <package>' to install any of the available packages.")


def cmd_removesource(args, sources: dict):
    name = args.name
    if name not in sources:
        print(f"  Not found: '{name}'")
        print(f"  Run 'fpm sources' to see configured sources.")
        return
    removed_url = sources.pop(name)["source-url"]
    save_sources(sources)
    print(f"  Removed source: '{name}' ({removed_url})")


def cmd_listsources(sources: dict):
    if not sources:
        print("No sources configured.")
        print("  Add one with: fpm addsource <name> <url>")
        return
    print(f"Configured sources ({len(sources)}):\n")
    for name, info in sources.items():
        owner = info.get("source-owner", "")
        url   = info.get("source-url", "")
        owner_str = f"  (owner: {owner})" if owner else ""
        print(f"  {name:<20} {url}{owner_str}")


# ─── Registry ─────────────────────────────────────────────────────────────────

def load_registry() -> dict:
    """Load stdlib + fpm_registry.json + all configured sources."""
    registry = dict(STDLIB_PACKAGES)
    # Local registry file
    if REGISTRY_FILE.exists():
        with open(REGISTRY_FILE) as f:
            registry.update(json.load(f))
    # All configured sources
    for source_name, source_info in load_sources().items():
        packages = fetch_source(source_name, source_info)
        registry.update(packages)
    return registry


# ─── Dependency resolution ────────────────────────────────────────────────────

def resolve_dependencies(package_name: str, registry: dict, installed: dict,
                          resolved: list = None, seen: set = None) -> list:
    """
    Recursively resolve dependencies for a package.
    Returns ordered list of package names to install (dependencies first).
    """
    if resolved is None:
        resolved = []
    if seen is None:
        seen = set()

    if package_name in seen:
        return resolved
    seen.add(package_name)

    if package_name not in registry:
        print(f"  WARNING: Package '{package_name}' not found in registry.")
        return resolved

    pkg = registry[package_name]
    for dep_name, constraint in pkg.get("dependencies", {}).items():
        if dep_name in installed:
            if not check_version_constraint(installed[dep_name]["version"], constraint):
                print(f"  WARNING: Installed '{dep_name}' v{installed[dep_name]['version']} "
                      f"does not satisfy '{constraint}' required by '{package_name}'.")
                print(f"    Run: fpm update {dep_name}")
        else:
            resolve_dependencies(dep_name, registry, installed, resolved, seen)

    if package_name not in resolved:
        resolved.append(package_name)

    return resolved


# ─── Core install/update logic ────────────────────────────────────────────────

def install_package(package_name: str, registry: dict, installed: dict,
                    force: bool = False) -> bool:
    """Download and register a third-party package. Returns True on success."""
    if package_name not in registry:
        print(f"  ERROR: '{package_name}' not found in registry.")
        return False

    pkg     = registry[package_name]
    version = pkg["version"]

    if package_name in installed and not force:
        installed_ver = installed[package_name]["version"]
        print(f"  Already installed: {package_name} v{installed_ver}  (use --force to reinstall)")
        return True

    source_url = pkg.get("_source_url", "")

    def make_url(base: str, filename: str) -> str:
        base = base.rstrip("/")
        if base.endswith(".json"):
            base = base.rsplit("/", 1)[0]
        return f"{base}/{filename}"

    def try_download(filename: str, dest: Path) -> bool:
        candidate_urls = []
        if source_url:
            candidate_urls.append(make_url(source_url, filename))
        candidate_urls.append(make_url(STDLIB_BASE_URL, filename))
        for url in candidate_urls:
            if download_file(url, dest):
                return True
            print(f"  Trying next source...")
        return False

    pkg_dir = PACKAGES_DIR / package_name
    print(f"  Downloading {package_name} v{version}...")

    # Always download package.json alongside the source files
    try_download("package.json", pkg_dir / "package.json")

    if "entries" in pkg:
        # Multi-file package
        downloaded_files = {}
        for label, filename in pkg["entries"].items():
            dest = pkg_dir / filename
            if not try_download(filename, dest):
                print(f"  ERROR: Could not download '{filename}' for '{package_name}' from any source.")
                return False
            downloaded_files[label] = str(dest)
            print(f"  Installed:  {filename} -> {dest}")

        installed[package_name] = {
            "version": version,
            "entries": pkg["entries"],
            "files":   list(downloaded_files.values()),
            "source":  "remote"
        }
    else:
        # Single-file package
        entry = pkg["entry"]
        dest  = pkg_dir / entry
        if not try_download(entry, dest):
            print(f"  ERROR: Could not download '{package_name}' from any source.")
            return False

        installed[package_name] = {
            "version": version,
            "entry":   entry,
            "file":    str(dest),
            "files":   [str(dest)],
            "source":  "remote"
        }
        print(f"  Installed:  {package_name} v{version} -> {dest}")

    return True


def update_stdlib_package(name: str, remote_pkg: dict, installed: dict) -> bool:
    """
    Compare local vs remote version for a stdlib package.
    Download and overwrite file(s) in STDLIB_DIR if remote is newer.
    Also updates the local package.json to reflect the new version.
    """
    local_version  = STDLIB_PACKAGES.get(name, {}).get("version", "0.0.0")
    remote_version = remote_pkg.get("version", "0.0.0")

    if parse_version(remote_version) <= parse_version(local_version):
        print(f"  Up to date: {name} v{local_version}")
        return True

    print(f"  Updating {name}: v{local_version} -> v{remote_version}")

    sub_path = remote_pkg.get("path", "")

    def base_url():
        return f"{STDLIB_BASE_URL}/{sub_path}" if sub_path else STDLIB_BASE_URL

    def base_dest():
        return STDLIB_DIR / sub_path if sub_path else STDLIB_DIR

    if "entries" in remote_pkg:
        for label, filename in remote_pkg["entries"].items():
            url  = f"{base_url()}/{filename}"
            dest = base_dest() / filename
            if not download_file(url, dest):
                return False
            print(f"  Updated:    {filename} -> {dest}")
    else:
        entry = remote_pkg["entry"]
        url   = f"{base_url()}/{entry}"
        dest  = base_dest() / entry
        if not download_file(url, dest):
            return False
        print(f"  Updated:    {name} v{remote_version} -> {dest}")

    # Update in-memory STDLIB_PACKAGES and installed record
    STDLIB_PACKAGES[name] = remote_pkg
    installed[name] = stdlib_installed_entry(name)

    # Persist new version to local package.json
    stdlib_json_path = STDLIB_DIR / "package.json"
    if stdlib_json_path.exists():
        with open(stdlib_json_path) as f:
            data = json.load(f)
        if name in data.get("packages", {}):
            data["packages"][name]["version"] = remote_version
            with open(stdlib_json_path, "w") as f:
                json.dump(data, f, indent=2)

    return True


# ─── Commands ─────────────────────────────────────────────────────────────────

def cmd_install(args, registry: dict, installed: dict):
    force = getattr(args, "force", False)

    if args.stdlib:
        targets = list(STDLIB_PACKAGES.keys())
        print(f"Installing full Flux standard library ({len(targets)} packages)...\n")
    elif args.all:
        targets = list(registry.keys())
        print(f"Installing all available packages ({len(targets)})...\n")
    elif args.package:
        targets = args.package
        print(f"Resolving dependencies for: {', '.join(targets)}\n")
        resolved = []
        seen = set()
        for name in targets:
            resolve_dependencies(name, registry, installed, resolved, seen)
        targets = resolved
    else:
        print("ERROR: Specify a package name, --stdlib, or --all.")
        return

    success = 0
    failed  = 0
    for name in targets:
        if is_stdlib_package(name):
            print(f"  Stdlib:   {name} is part of the Flux standard library (always available)")
            success += 1
            continue
        if install_package(name, registry, installed, force=force):
            success += 1
        else:
            failed += 1

    save_installed(installed)
    print(f"\nDone. {success} installed, {failed} failed.")


def cmd_remove(args, registry: dict, installed: dict):
    for name in args.package:
        if is_stdlib_package(name):
            print(f"  Protected: {name} is part of the Flux standard library and cannot be removed.")
            continue
        if name not in installed:
            print(f"  Not installed: {name}")
            continue
        pkg_dir = PACKAGES_DIR / name
        if pkg_dir.exists():
            shutil.rmtree(pkg_dir)
        del installed[name]
        print(f"  Removed: {name}")
    save_installed(installed)


def cmd_update(args, registry: dict, installed: dict):
    # Determine which packages the user wants to update
    if args.all or not args.package:
        targets = list(installed.keys())
    else:
        targets = args.package

    # ── Fetch latest metadata from all sources ────────────────────────────────
    sources = load_sources()
    remote_registry: dict = {}
    if sources:
        print(f"  Fetching package index from {len(sources)} source(s)...")
        for source_name, source_info in sources.items():
            url = source_info.get("source-url", "")
            print(f"    [{source_name}] {url}/packages.json")
            pkgs = fetch_source(source_name, source_info)
            remote_registry.update(pkgs)
        print()

    # ── Fetch remote stdlib if any stdlib targets ─────────────────────────────
    stdlib_targets = [n for n in targets if is_stdlib_package(n)]
    remote_stdlib: dict = {}
    if stdlib_targets:
        print("  Fetching remote stdlib package.json...")
        remote_stdlib = fetch_remote_stdlib_json()
        if not remote_stdlib:
            print("  WARNING: Could not fetch remote stdlib package.json.")

    # ── Update each target ────────────────────────────────────────────────────
    success = 0
    skipped = 0
    failed  = 0

    for name in targets:
        if name not in installed:
            print(f"  Skipping '{name}': not installed  (use: fpm install {name})")
            skipped += 1
            continue

        if is_stdlib_package(name):
            if name not in remote_stdlib:
                print(f"  Not found:  '{name}' not in remote stdlib package.json")
                failed += 1
                continue
            if update_stdlib_package(name, remote_stdlib[name], installed):
                success += 1
            else:
                failed += 1

        elif name in remote_registry:
            remote_pkg     = remote_registry[name]
            remote_version = remote_pkg.get("version", "0.0.0")
            local_version  = installed[name].get("version", "0.0.0")

            if parse_version(remote_version) <= parse_version(local_version):
                print(f"  Up to date: {name} v{local_version}")
                skipped += 1
                continue

            print(f"  Updating {name}: v{local_version} -> v{remote_version}")
            # Merge remote metadata into registry so install_package can find it
            registry[name] = remote_pkg
            if install_package(name, registry, installed, force=True):
                success += 1
            else:
                failed += 1

        elif name in registry:
            # Fallback: no remote source data, try with existing registry entry
            print(f"  Updating {name} (no remote version info available)...")
            if install_package(name, registry, installed, force=True):
                success += 1
            else:
                failed += 1

        else:
            print(f"  Not found: '{name}' is not in any configured source.")
            failed += 1

    save_installed(installed)
    print(f"\nUpdate complete. {success} updated, {skipped} skipped, {failed} failed.")


def cmd_list(args, registry: dict, installed: dict):
    if args.available:
        print(f"Available packages ({len(registry)}):\n")
        for name, pkg in sorted(registry.items()):
            desc   = pkg.get("description", "")
            marker = " [installed]" if name in installed else ""
            print(f"  {name:<30} v{pkg['version']:<10} {desc}{marker}")
    else:
        if not installed:
            print("No packages installed. Run: fpm install --stdlib")
            return
        print(f"Installed packages ({len(installed)}):\n")
        for name, pkg in sorted(installed.items()):
            source = pkg.get("source", "remote")
            tag    = "[stdlib]" if source == "stdlib" else "[local]" if source == "local" else "[remote]"
            print(f"  {name:<30} v{pkg['version']}  {tag}")


def cmd_info(args, registry: dict, installed: dict):
    for name in args.package:
        pkg = registry.get(name)
        if not pkg:
            print(f"  '{name}' not found in registry.")
            continue

        print(f"\n  Package:      {name}")
        print(f"  Version:      {pkg['version']}")
        print(f"  Description:  {pkg.get('description', 'N/A')}")
        if "entries" in pkg:
            print(f"  Entries:")
            for label, filename in pkg["entries"].items():
                print(f"    {label}: {filename}")
        else:
            print(f"  Entry:        {pkg['entry']}")
        deps = pkg.get("dependencies", {})
        if deps:
            print(f"  Dependencies:")
            for dep, constraint in deps.items():
                print(f"    {dep}  {constraint}")
        else:
            print(f"  Dependencies: none")

        if name in installed:
            source = installed[name].get("source", "remote")
            tag    = "stdlib" if source == "stdlib" else "local" if source == "local" else "remote"
            files  = installed[name].get("files", [installed[name].get("file", "?")])
            if len(files) == 1:
                print(f"  Status:       installed [{tag}] -> {files[0]}")
            else:
                print(f"  Status:       installed [{tag}]")
                for f in files:
                    print(f"                -> {f}")
        else:
            print(f"  Status:       not installed")


# ─── Package creation wizard ──────────────────────────────────────────────────

def _ask(prompt: str, default: str = "") -> str:
    """Prompt the user for input, returning default if they press Enter."""
    suffix = f" [{default}]" if default else ""
    try:
        val = input(f"  {prompt}{suffix}: ").strip()
    except (KeyboardInterrupt, EOFError):
        print("\n\nAborted.")
        sys.exit(0)
    return val if val else default


def _ask_yn(prompt: str, default: bool = True) -> bool:
    """Yes/no prompt. Returns bool."""
    choices = "Y/n" if default else "y/N"
    raw = _ask(f"{prompt} ({choices})", "")
    if not raw:
        return default
    return raw.lower().startswith("y")


def _divider(title: str = ""):
    width = 60
    if title:
        pad = (width - len(title) - 2) // 2
        print(f"\n{'─' * pad} {title} {'─' * (width - pad - len(title) - 2)}")
    else:
        print(f"\n{'─' * width}")


def _collect_entries(existing_registry: dict) -> tuple[bool, dict]:
    """
    Ask whether the package is single-file or multi-file.
    Returns (is_multi, entry_or_entries_dict).
    For single-file: entries_dict == {"entry": "<filename>"}
    For multi-file:  entries_dict == {"entries": {label: filename, ...}}
    """
    multi = _ask_yn("Does this package contain multiple .fx files?", default=False)
    if not multi:
        entry = _ask("Entry filename (e.g. mypackage.fx)", "mypackage.fx")
        if not entry.endswith(".fx"):
            entry += ".fx"
        return False, {"entry": entry}

    print("\n  Enter each entry label and filename. Leave label blank to finish.")
    entries: dict = {}
    idx = 1
    while True:
        label = _ask(f"  Entry {idx} label (e.g. core, utils)")
        if not label:
            if not entries:
                print("  At least one entry is required.")
                continue
            break
        fname = _ask(f"  Entry {idx} filename", f"{label}.fx")
        if not fname.endswith(".fx"):
            fname += ".fx"
        entries[label] = fname
        idx += 1
    return True, {"entries": entries}


def _collect_dependencies(registry: dict) -> dict:
    """Interactively build a dependencies dict {pkg_name: version_constraint}."""
    deps: dict = {}
    print("\n  Add dependencies one at a time. Leave package name blank to finish.")
    while True:
        name = _ask("  Dependency name")
        if not name:
            break
        if name not in registry and registry:
            print(f"  WARNING: '{name}' is not in the current registry — adding anyway.")
        constraint = _ask(f"  Version constraint for '{name}'", ">=1.0.0")
        deps[name] = constraint
    return deps


def _generate_boilerplate(pkg_name: str, description: str,
                           is_multi: bool, entry_info: dict) -> dict[str, str]:
    """
    Return a dict of {filename: source_code} for every .fx file in the package.
    """
    header = (
        f"// {pkg_name}.fx - {description}\n"
        f"// Generated by fpm create\n\n"
        f"#import \"standard.fx\";\n\n"
        f"using standard::io::console;\n\n"
        f"namespace {pkg_name.replace("-","_")}\n{{\n"
    )
    footer = "\n};\n"
    body = (
        "    // TODO: implement your package here\n"
        "    def main() -> int\n"
        "    {\n"
        "        print(\"Hello from " + pkg_name + "!\\0\");\n"
        "        return 0;\n"
        "    };\n"
    )

    files: dict[str, str] = {}
    if not is_multi:
        filename = entry_info["entry"]
        files[filename] = header + body + footer
    else:
        for label, filename in entry_info["entries"].items():
            label_body = (
                f"    // TODO: implement '{label}' functionality here\n"
                f"    def {label}_init() -> void\n"
                "    {\n"
                f"        print(\"{pkg_name.replace("-","_")}::{label} loaded!\\0\");\n"
                "    };\n"
            )
            files[filename] = header + label_body + footer
    return files


def cmd_create(args, registry: dict):
    """Interactive wizard to scaffold a new Flux package."""
    print("\n╔══════════════════════════════════════════╗")
    print("║       fpm create — Package Wizard        ║")
    print("╚══════════════════════════════════════════╝")
    print("  Press Ctrl-C at any time to abort.\n")

    # ── Step 1: Basic metadata ────────────────────────────────────────────────
    _divider("Step 1 of 5 — Basic Info")
    name = ""
    while not name:
        name = _ask("Package name (lowercase, no spaces)", "")
        if not name:
            print("  Package name is required.")
        elif " " in name or any(c.isupper() for c in name):
            print("  Use lowercase letters, digits, hyphens or underscores only.")
            name = ""
        else:
            # Check for collision in registry and on disk
            existing_location = None
            if name in registry:
                src = registry[name].get("source", "registry")
                existing_location = f"already exists in the registry (source: {src})"
            elif (PACKAGES_DIR / name).exists():
                existing_location = f"already exists on disk at {PACKAGES_DIR / name}"

            if existing_location:
                print(f"\n  WARNING: A package named '{name}' {existing_location}.")
                print(f"  Creating it will overwrite the existing package.")
                if not _ask_yn("  Continue anyway?", default=False):
                    name = ""  # loop and ask for a different name

    version    = _ask("Version", "1.0.0")
    description = _ask("Short description", f"A Flux package called {name}")
    author     = _ask("Author name / email", "")
    license_   = _ask("License", "MIT")

    # ── Step 2: Entry files ───────────────────────────────────────────────────
    _divider("Step 2 of 5 — Entry Files")
    is_multi, entry_info = _collect_entries(registry)

    # ── Step 3: Optional sub-path ─────────────────────────────────────────────
    _divider("Step 3 of 5 — Package Path")
    print("  If your package lives in a subdirectory (e.g. 'net/http'),")
    print("  enter it here. Leave blank for the package root.")
    sub_path = _ask("Sub-path", "")

    # ── Step 4: Dependencies ──────────────────────────────────────────────────
    _divider("Step 4 of 5 — Dependencies")
    deps = _collect_dependencies(registry)

    # ── Step 5: Output location ───────────────────────────────────────────────
    _divider("Step 5 of 5 — Output Location")
    # Default to FLUXC_SRCDIR/.fpm/packages/<name> so the compiler can find
    # the package immediately without any extra configuration.
    default_out = str(PACKAGES_DIR / name)
    out_dir_str = _ask("Where to create the package directory", default_out)
    out_dir     = Path(out_dir_str).expanduser().resolve()

    # ── Confirm ───────────────────────────────────────────────────────────────
    _divider("Summary")
    print(f"  Name:        {name}")
    print(f"  Version:     {version}")
    print(f"  Description: {description}")
    if author:
        print(f"  Author:      {author}")
    print(f"  License:     {license_}")
    if sub_path:
        print(f"  Sub-path:    {sub_path}")
    if is_multi:
        print(f"  Entries:")
        for lbl, fn in entry_info["entries"].items():
            print(f"    {lbl}: {fn}")
    else:
        print(f"  Entry:       {entry_info['entry']}")
    if deps:
        print(f"  Dependencies:")
        for d, c in deps.items():
            print(f"    {d}  {c}")
    else:
        print(f"  Dependencies: none")
    print(f"  Output dir:  {out_dir}")

    _divider()
    if not _ask_yn("Create this package?", default=True):
        print("  Cancelled.")
        return

    # ── Write files ───────────────────────────────────────────────────────────
    out_dir.mkdir(parents=True, exist_ok=True)

    # Build package.json entry
    pkg_entry: dict = {
        "version":     version,
        "description": description,
        "path":        sub_path,
    }
    if author:
        pkg_entry["author"] = author
    pkg_entry["license"] = license_
    if is_multi:
        pkg_entry["entries"] = entry_info["entries"]
    else:
        pkg_entry["entry"] = entry_info["entry"]
    if deps:
        pkg_entry["dependencies"] = deps

    package_json = {"packages": {name: pkg_entry}}
    pkg_json_path = out_dir / "package.json"
    with open(pkg_json_path, "w") as f:
        json.dump(package_json, f, indent=2)
    print(f"\n  Created: {pkg_json_path}")

    # Write .fx boilerplate files
    fx_files = _generate_boilerplate(name, description, is_multi, entry_info)
    for filename, source in fx_files.items():
        dest = out_dir / filename
        dest.parent.mkdir(parents=True, exist_ok=True)
        with open(dest, "w") as f:
            f.write(source)
        print(f"  Created: {dest}")

    # Optionally register in the local fpm registry
    _divider()
    if _ask_yn("Register this package in your local fpm registry?", default=True):
        FPM_DIR.mkdir(parents=True, exist_ok=True)
        local_reg: dict = {}
        if REGISTRY_FILE.exists():
            with open(REGISTRY_FILE) as f:
                local_reg = json.load(f)
        local_reg[name] = pkg_entry
        with open(REGISTRY_FILE, "w") as f:
            json.dump(local_reg, f, indent=2)
        print(f"  Registered '{name}' in {REGISTRY_FILE}")

    print(f"\n✔  Package '{name}' created at {out_dir}")
    print(f"   Next steps:")
    print(f"     cd {out_dir}")
    if is_multi:
        for fn in entry_info["entries"].values():
            print(f"     $EDITOR {fn}")
    else:
        print(f"     $EDITOR {entry_info['entry']}")
    print(f"   When ready, share package.json so others can add it via:")
    print(f"     fpm addsource <url-to-your-package.json>")


# ─── Publish ──────────────────────────────────────────────────────────────────

def cmd_publish(args):
    """
    Publish a local package to a named source's fpm server on port 8080.
    Looks up the source in sources.json to get the base URL, then PUTs
    the package.json and all .fx files to <host>:8080/publish/<n>/<file>.
    """
    name        = args.package
    source_name = args.source
    sources     = load_sources()

    if source_name not in sources:
        print(f"  ERROR: Source '{source_name}' not found.")
        print(f"  Run 'fpm sources' to see configured sources.")
        return

    base_url = sources[source_name].get("source-url", "").rstrip("/")
    parsed   = urllib.parse.urlparse(base_url)
    server   = f"{parsed.scheme}://{parsed.hostname}:{FPM_SERVER_PORT}"

    pkg_dir  = PACKAGES_DIR / name
    manifest = pkg_dir / "package.json"

    if not pkg_dir.exists():
        print(f"  ERROR: Package directory not found: {pkg_dir}")
        print(f"  Create the package first with: fpm create")
        return
    if not manifest.exists():
        print(f"  ERROR: No package.json found in {pkg_dir}")
        return

    print(f"\n  Publishing '{name}' to {source_name} ({server}) ...\n")

    # Read package.json to find exactly which files to upload
    with open(manifest) as mf:
        pkg_data = json.load(mf)
    pkg_meta = pkg_data.get("packages", {}).get(name, pkg_data)
    sub_path = pkg_meta.get("path", "")
    base_dir = pkg_dir / sub_path if sub_path else pkg_dir

    files_to_upload = [manifest]  # always include package.json
    if "entries" in pkg_meta:
        for filename in pkg_meta["entries"].values():
            files_to_upload.append(base_dir / filename)
    elif "entry" in pkg_meta:
        files_to_upload.append(base_dir / pkg_meta["entry"])

    success = 0
    failed  = 0
    for f in files_to_upload:
        if not f.exists():
            print(f"  ERROR: File not found: {f}")
            failed += 1
            continue
        rel   = f.relative_to(pkg_dir).as_posix()
        url   = f"{server}/publish/{name}/{rel}"
        data  = f.read_bytes()
        ctype = "application/json" if f.suffix == ".json" else "text/plain"
        req   = urllib.request.Request(
            url, data=data, method="PUT",
            headers={"User-Agent": FPM_USER_AGENT, "Content-Type": ctype}
        )
        try:
            with urllib.request.urlopen(req, timeout=15) as resp:
                print(f"  ✔  {rel}  ({resp.status})")
                success += 1
        except urllib.error.HTTPError as e:
            print(f"  ERROR: HTTP {e.code} uploading {rel}")
            failed += 1
        except urllib.error.URLError as e:
            print(f"  ERROR: Could not reach server — {e.reason}")
            failed += 1

    print(f"\n  Done. {success} file(s) uploaded, {failed} failed.")


# ─── Fix Dependencies ─────────────────────────────────────────────────────────

def _scan_imports(fx_path: Path) -> list[str]:
    """
    Parse a .fx file and return a list of imported filenames.
    Handles both single and multi-import forms:
        #import "math.fx";
        #import "math.fx", "vectors.fx";
    Ignores lines inside block comments and skips #import inside #ifndef guards
    that aren't terminated (best-effort; handles the common stdlib pattern).
    """
    import re
    filenames = []
    # Match one or more quoted filenames after #import
    pattern = re.compile(r'#import\s+((?:"[^"]+"\s*,\s*)*"[^"]+")')
    try:
        text = fx_path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return filenames
    for line in text.splitlines():
        stripped = line.strip()
        # Skip blank lines and pure comments
        if not stripped or stripped.startswith("//"):
            continue
        m = pattern.search(stripped)
        if m:
            # Extract every quoted token from the matched group
            for fn in re.findall(r'"([^"]+)"', m.group(1)):
                filenames.append(fn)
    return filenames


def _build_filename_to_package_map(packages: dict) -> dict[str, str]:
    """
    Build a reverse map: entry filename -> package name.
    e.g. {"math.fx": "flux-math", "vectors.fx": "flux-vectors", ...}
    Handles both single-entry and multi-entry packages.
    """
    mapping = {}
    for pkg_name, pkg in packages.items():
        if "entries" in pkg:
            for fn in pkg["entries"].values():
                mapping[fn] = pkg_name
        elif "entry" in pkg:
            mapping[pkg["entry"]] = pkg_name
    return mapping


def cmd_fixdeps(args):
    """
    Scan each package's .fx source file(s) for #import directives and
    rewrite the 'dependencies' field in package.json to match what is
    actually imported, using the versions already listed in the registry.
    """
    pack_name = args.pack_name  # e.g. "flux-stdlib"

    # ── Locate package.json ───────────────────────────────────────────────────
    # Prefer the local stdlib package.json; fall back to the fpm registry file.
    stdlib_json_path = STDLIB_DIR / "package.json"
    if stdlib_json_path.exists():
        json_path = stdlib_json_path
    elif REGISTRY_FILE.exists():
        json_path = REGISTRY_FILE
    else:
        print(f"  ERROR: No package.json found. "
              f"Expected at {stdlib_json_path} or {REGISTRY_FILE}")
        return

    with open(json_path) as f:
        root = json.load(f)

    # Support both flat {packages: {...}} and bare {pkg: {...}} layouts
    if "packages" in root:
        packages = root["packages"]
        wrap_key = "packages"
    else:
        packages = root
        wrap_key = None

    # Verify the requested pack name is actually a key inside the JSON
    # (for flux-stdlib this is the top-level "pack" field, not a package name;
    # we use it only as a label — the command always operates on all packages
    # in the file).
    top_pack = root.get("pack", "")
    if pack_name != top_pack and pack_name not in packages:
        print(f"  ERROR: '{pack_name}' is not a known pack or package in {json_path}")
        print(f"  Top-level pack name in that file: '{top_pack}'")
        return

    # ── Build filename → package-name reverse map ─────────────────────────────
    fn_to_pkg = _build_filename_to_package_map(packages)

    # ── Scan each package ─────────────────────────────────────────────────────
    print(f"\n  fixdeps — scanning packages in '{json_path}'\n")

    changed_count = 0
    skipped_count = 0

    for pkg_name, pkg in packages.items():
        sub_path = pkg.get("path", "")

        # Collect the .fx file(s) to scan
        if "entries" in pkg:
            base = STDLIB_DIR / sub_path if sub_path else STDLIB_DIR
            fx_files = [base / fn for fn in pkg["entries"].values()]
        else:
            entry = pkg.get("entry", "")
            if not entry:
                continue
            base = STDLIB_DIR / sub_path if sub_path else STDLIB_DIR
            fx_files = [base / entry]

        # Gather all imports across all files for this package
        imported_filenames: set[str] = set()
        for fx_path in fx_files:
            if fx_path.exists():
                for fn in _scan_imports(fx_path):
                    imported_filenames.add(fn)
            else:
                print(f"  WARNING: Source file not found, skipping scan: {fx_path}")

        if not imported_filenames:
            # No imports found — clear deps only if there were some before
            old_deps = pkg.get("dependencies", {})
            if old_deps:
                print(f"  {pkg_name}: no imports found — clearing {list(old_deps.keys())}")
                pkg["dependencies"] = {}
                changed_count += 1
            else:
                skipped_count += 1
            continue

        # Map filenames → package names, skip self-imports and unknowns
        new_deps: dict[str, str] = {}
        unknown_imports: list[str] = []
        for fn in sorted(imported_filenames):
            dep_pkg_name = fn_to_pkg.get(fn)
            if dep_pkg_name is None:
                unknown_imports.append(fn)
                continue
            if dep_pkg_name == pkg_name:
                continue  # self-import, ignore
            dep_version = packages[dep_pkg_name]["version"]
            new_deps[dep_pkg_name] = f">={dep_version}"

        old_deps = pkg.get("dependencies", {})

        if unknown_imports:
            print(f"  {pkg_name}: unrecognized import(s) (no matching package): "
                  f"{', '.join(unknown_imports)}")

        if new_deps == old_deps:
            skipped_count += 1
            continue

        # Show a diff-style summary
        added   = {k: v for k, v in new_deps.items() if k not in old_deps}
        removed = {k: v for k, v in old_deps.items() if k not in new_deps}
        updated = {k: v for k, v in new_deps.items()
                   if k in old_deps and old_deps[k] != v}

        print(f"  {pkg_name}:")
        for k, v in added.items():
            print(f"    + {k}: {v}")
        for k, v in removed.items():
            print(f"    - {k} (was {v})")
        for k, v in updated.items():
            print(f"    ~ {k}: {old_deps[k]} → {v}")

        pkg["dependencies"] = new_deps
        changed_count += 1

    # ── Write back ────────────────────────────────────────────────────────────
    if changed_count == 0:
        print(f"  All {skipped_count} package(s) already up-to-date. Nothing to write.")
        return

    if wrap_key:
        root[wrap_key] = packages
    else:
        root = packages

    with open(json_path, "w") as f:
        json.dump(root, f, indent=2)
        f.write("\n")

    print(f"\n✔  Updated {changed_count} package(s), "
          f"{skipped_count} unchanged.")
    print(f"   Written to: {json_path}")


# ─── Entry point ──────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        prog="fpm",
        description="Flux Package Manager"
    )
    subparsers = parser.add_subparsers(dest="command")

    # install
    p_install = subparsers.add_parser("install", help="Install packages")
    p_install.add_argument("package", nargs="*", help="Package name(s) to install")
    p_install.add_argument("--stdlib", action="store_true", help="Install full standard library")
    p_install.add_argument("--all",    action="store_true", help="Install all available packages")
    p_install.add_argument("--force",  action="store_true", help="Reinstall even if already installed")

    # remove
    p_remove = subparsers.add_parser("remove", help="Remove installed packages")
    p_remove.add_argument("package", nargs="+", help="Package name(s) to remove")

    # update
    p_update = subparsers.add_parser("update", help="Update installed packages")
    p_update.add_argument("package", nargs="*", help="Package name(s) to update")
    p_update.add_argument("--all", action="store_true", help="Update all installed packages")

    # create
    subparsers.add_parser("create", help="Interactively scaffold a new Flux package")

    # addsource
    subparsers.add_parser("addsource", help="Interactively add a named package source")

    # removesource
    p_remsrc = subparsers.add_parser("removesource", help="Remove a package source by name")
    p_remsrc.add_argument("name", help="Source name to remove")

    # sources
    subparsers.add_parser("sources", help="List configured sources")

    # publish
    p_publish = subparsers.add_parser("publish", help="Publish a local package to the fpm server")
    p_publish.add_argument("package", help="Package name to publish")
    p_publish.add_argument("--source", required=True, help="Named source to publish to (from fpm sources)")

    # fixdeps
    p_fixdeps = subparsers.add_parser(
        "fixdeps",
        help="Scan .fx source files and fix dependencies in package.json"
    )
    p_fixdeps.add_argument(
        "pack_name",
        help="Pack name to fix (e.g. flux-stdlib)"
    )

    # list
    p_list = subparsers.add_parser("list", help="List packages")
    p_list.add_argument("--available", action="store_true", help="Show all available packages")

    # info
    p_info = subparsers.add_parser("info", help="Show package details")
    p_info.add_argument("package", nargs="+", help="Package name(s)")

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        return

    FPM_DIR.mkdir(parents=True, exist_ok=True)
    PACKAGES_DIR.mkdir(parents=True, exist_ok=True)

    # Load stdlib from package.json — must happen before everything else
    STDLIB_PACKAGES.update(load_stdlib_json())

    sources   = load_sources()
    registry  = load_registry()
    installed = load_installed()

    if args.command == "install":
        cmd_install(args, registry, installed)
    elif args.command == "create":
        cmd_create(args, registry)
    elif args.command == "remove":
        cmd_remove(args, registry, installed)
    elif args.command == "update":
        cmd_update(args, registry, installed)
    elif args.command == "list":
        cmd_list(args, registry, installed)
    elif args.command == "info":
        cmd_info(args, registry, installed)
    elif args.command == "addsource":
        cmd_addsource(args, sources)
    elif args.command == "removesource":
        cmd_removesource(args, sources)
    elif args.command == "sources":
        cmd_listsources(sources)
    elif args.command == "publish":
        cmd_publish(args)
    elif args.command == "fixdeps":
        cmd_fixdeps(args)


if __name__ == "__main__":
    main()
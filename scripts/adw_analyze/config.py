"""sources.json, and the guard that keeps reports out of a public checkout (spec §5.1)."""
from __future__ import annotations

import dataclasses
import json
import os
import re
import subprocess
from dataclasses import dataclass, field


class ConfigError(Exception):
    pass


class PublicRepoError(Exception):
    pass


@dataclass
class Repo:
    name: str
    slug: str
    checkout: str = ""
    base: str = "main"
    transcripts: list = field(default_factory=list)
    watch: list = field(default_factory=list)
    gates: dict = field(default_factory=dict)
    role: str = "app"


KEYS = {f.name for f in dataclasses.fields(Repo)}
GITHUB = re.compile(r"github\.com[:/]([^/\s]+)/([^/\s]+?)(?:\.git)?/?$")


def load_sources(reports_dir: str) -> list[Repo]:
    path = os.path.join(reports_dir, "sources.json")
    try:
        with open(path) as f:
            data = json.load(f)
    except FileNotFoundError:
        raise ConfigError(f"no sources.json in {reports_dir}")
    except json.JSONDecodeError as e:
        raise ConfigError(f"sources.json is not JSON: {e}")
    if data.get("schema") != 1:
        raise ConfigError("sources.json: schema must be 1")
    repos = []
    for r in data.get("repos") or []:
        unknown = sorted(set(r) - KEYS)
        if unknown:
            raise ConfigError(f"sources.json: unknown key {', '.join(unknown)} in repo {r.get('name')}")
        if not r.get("name") or not r.get("slug"):
            raise ConfigError("sources.json: every repo needs a name and a slug")
        if r.get("role", "app") not in ("app", "contract"):
            raise ConfigError(f"sources.json: role of {r['name']} must be app or contract")
        repos.append(Repo(**r))
    if not repos:
        raise ConfigError("sources.json lists no repos")
    return repos


def resolve_reports_dir(flag: str | None) -> str:
    d = flag or os.environ.get("ADW_ANALYSIS_DIR")
    if not d:
        raise ConfigError("name the reports dir with --reports or ADW_ANALYSIS_DIR")
    return os.path.abspath(os.path.expanduser(d))


def check_reports_dir(path: str) -> None:
    """Allowed: no checkout, or a checkout with no GitHub remote. A GitHub remote must be PRIVATE or INTERNAL."""
    top = subprocess.run(["git", "-C", path, "rev-parse", "--show-toplevel"], capture_output=True, text=True)
    if top.returncode != 0:
        return
    remotes = subprocess.run(["git", "-C", path, "remote", "-v"], capture_output=True, text=True).stdout
    slugs = set()
    for line in remotes.splitlines():
        parts = line.split()
        m = GITHUB.search(parts[1]) if len(parts) > 1 else None
        if m:
            slugs.add(f"{m.group(1)}/{m.group(2)}")
    for slug in sorted(slugs):
        r = subprocess.run(["gh", "repo", "view", slug, "--json", "visibility", "-q", ".visibility"],
                           capture_output=True, text=True)
        vis = r.stdout.strip()
        if r.returncode != 0 or vis not in ("PRIVATE", "INTERNAL"):
            raise PublicRepoError(f"{path} is a checkout of {slug}, which is {vis or 'unverifiable'}; reports go only to a private repo")

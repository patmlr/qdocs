"""
Commands for the theme itself. Run from a checkout of the qdocs repository:

    python -m qdocs css
    python -m qdocs preview <docs> [build | serve] [jekyll options]

- css: the Pygments styles _sass/qdocs/pycode.scss.
- preview: builds or serves a site with the theme of this checkout instead of its remote_theme, e.g. to try theme
  changes before they are pushed. The site and the theme are copied into a temporary folder, rerun after changes.
"""

import argparse
import os
import re
import shutil
import subprocess
import sys
import tempfile

from qdocs import tutorials
from qdocs.build import write

THEME = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
THEME_DIRS = ["_layouts", "_includes", "_sass", "assets"]
PYCODE_FILE = os.path.join(THEME, "_sass", "qdocs", "pycode.scss")


def preview(docs: str, command: str, options: list[str]) -> int:
    docs = os.path.abspath(docs)
    site = os.path.join(tempfile.gettempdir(), "qdocs-preview", os.path.basename(os.path.dirname(docs)))
    if os.path.exists(site):
        shutil.rmtree(site)
    for d in THEME_DIRS:
        shutil.copytree(os.path.join(THEME, d), os.path.join(site, d))
    ignore = shutil.ignore_patterns("_site", ".jekyll-cache", ".jekyll-metadata")
    shutil.copytree(docs, site, ignore=ignore, dirs_exist_ok=True)  # Files of the site override the theme.

    config = os.path.join(site, "_config.yml")
    with open(config, encoding="utf-8") as f:
        text = re.sub(r"^remote_theme:.*$", "", f.read(), flags=re.MULTILINE)
    write(config, text)

    env = dict(os.environ, BUNDLE_GEMFILE=os.path.join(docs, "Gemfile"))
    # The copy is not a git repository, site.github needs the repository of the site.
    origin = subprocess.run(
        ["git", "-C", docs, "remote", "get-url", "origin"], capture_output=True, text=True, check=False
    ).stdout
    m = re.search(r"github\.com[:/](.+?)(?:\.git)?\s*$", origin)
    if m and "PAGES_REPO_NWO" not in env:
        env["PAGES_REPO_NWO"] = m.group(1)
    args = ["bundle", "exec", "jekyll", command, "-d", os.path.join(site, "_site"), *options]
    print(f"Running {' '.join(args)} in {site}")
    return subprocess.call(args, cwd=site, env=env, shell=sys.platform == "win32")


def main() -> None:
    parser = argparse.ArgumentParser(description="Commands for the qdocs theme.")
    sub = parser.add_subparsers(dest="target", required=True)
    sub.add_parser("css", help="Generate _sass/qdocs/pycode.scss.")
    p = sub.add_parser("preview", help="Build or serve a site with the theme of this checkout.")
    p.add_argument("docs", help="The Jekyll site, e.g. ../qspec/docs.")
    p.add_argument("command", nargs="?", default="serve", choices=["build", "serve"])
    args, options = parser.parse_known_args()

    if not os.path.isdir(os.path.join(THEME, "_sass", "qdocs")):
        sys.exit("The theme files are not next to the qdocs package. Run this from a checkout of the repository.")
    if args.target == "css":
        write(PYCODE_FILE, tutorials.pycode_css())
        print(f"Wrote {os.path.relpath(PYCODE_FILE, THEME)}.")
    else:
        sys.exit(preview(args.docs, args.command, options))


if __name__ == "__main__":
    main()

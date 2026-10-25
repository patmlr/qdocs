"""
Highlighted tutorial code blocks from marked regions in the example scripts:

    # docs: hfs-0
    import qspec as qs
    ...
    # docs: end

Each region becomes docs/_includes/code/<name>.html, which a tutorial page includes with
{% include code/<name>.html %}. A file may contain several regions.
"""

import glob
import os
import re
import textwrap
from collections.abc import Callable

from pygments import highlight
from pygments.formatters import HtmlFormatter
from pygments.lexers import get_lexer_by_name
from pygments.styles import get_style_by_name

from qdocs.project import Project

STYLE = "catppuccin-latte"
STYLE_DARK = "catppuccin-mocha"
MARKER = re.compile(r"^\s*# docs: (\S+)\s*$")
INCLUDE = re.compile(r"{%\s*include\s+code/(\S+?)\.html\s*%}")


def find_regions(paths: list[str]) -> tuple[dict[str, str], list[str]]:
    """
    :param paths: The paths of the example scripts.
    :returns: (regions, errors) The code of each region by name and a list of errors.
    """
    regions: dict[str, str] = {}
    errors = []
    for path in paths:
        name, start, lines = None, 0, []
        with open(path, encoding="utf-8") as f:
            for i, line in enumerate(f.read().splitlines(), start=1):
                m = MARKER.match(line)
                if m is None:
                    if name is not None:
                        lines.append(line)
                elif m.group(1) == "end":
                    if name is None:
                        errors.append(f"{path}:{i}: '# docs: end' without an open region")
                        continue
                    if name in regions:
                        errors.append(f"{path}:{start}: duplicate region '{name}'")
                    regions[name] = textwrap.dedent("\n".join(lines)).strip("\n")
                    name, lines = None, []
                else:
                    if name is not None:
                        errors.append(f"{path}:{i}: region '{m.group(1)}' starts inside region '{name}'")
                    name, start, lines = m.group(1), i, []
        if name is not None:
            errors.append(f"{path}:{start}: region '{name}' is not closed")
    return regions, errors


def to_html(code: str) -> str:
    lexer = get_lexer_by_name("python", stripall=True)
    formatter = HtmlFormatter(cssclass="py-source", style=get_style_by_name(STYLE))
    return highlight(code, lexer, formatter)


def build(project: Project, write: Callable[[str, str], None]) -> list[str]:
    """
    :param project: The documented project.
    :param write: A function `write(path, text)`.
    :returns: A list of errors.
    """
    regions, errors = find_regions(sorted(glob.glob(os.path.join(project.examples, "*.py"))))
    out_dir = os.path.join(project.docs, "_includes", "code")
    for f in glob.glob(os.path.join(out_dir, "*.html")):
        os.remove(f)
    for name, code in regions.items():
        write(os.path.join(out_dir, f"{name}.html"), to_html(code))
    print(f"Wrote {len(regions)} tutorial code blocks.")

    used = set()
    for page in sorted(glob.glob(os.path.join(project.docs, "tutorials", "*.html"))):
        with open(page, encoding="utf-8") as f:
            for name in INCLUDE.findall(f.read()):
                used.add(name)
                if name not in regions:
                    errors.append(f"{os.path.relpath(page, project.root)}: no region '{name}' in examples/")
    for name in sorted(set(regions) - used):
        print(f"  note: region '{name}' is not included by any tutorial page")
    return errors


def pycode_css() -> str:
    """
    :returns: The SCSS of the light (STYLE) and the dark (STYLE_DARK) code highlighting.
     The dark style applies under the same conditions as the dark colors in assets/css/style.scss.
     Both use the code block background of the page instead of the background of the style.
    """
    # The selector argument is needed to also get the default text color of the style ('.py-source { color: ... }').
    light = HtmlFormatter(cssclass="py-source", style=get_style_by_name(STYLE)).get_style_defs(".py-source")
    dark = HtmlFormatter(cssclass="py-source", style=get_style_by_name(STYLE_DARK)).get_style_defs(".py-source")
    bg = ".py-source { background-color: var(--pre-bg-color); }"
    dark = textwrap.indent(f"{dark}\n{bg}", "    ")  # type: ignore
    return (
        f"// Light mode: {STYLE}.\n{light}\n{bg}\n\n"
        f"// Dark mode: {STYLE_DARK}.\n"
        f"@mixin pycode-dark {{\n{dark}\n}}\n\n"
        ':root[data-theme="dark"] { @include pycode-dark; }\n'
        "@media (prefers-color-scheme: dark) {\n"
        '    :root:not([data-theme="light"]) { @include pycode-dark; }\n'
        "}\n"
    )

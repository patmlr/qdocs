"""
Generates the generated parts of a website that uses the qdocs theme. A site calls `main` from its build script:

    python docs/_gen/build.py [api | tutorials | logo | all]

- api: the API pages in docs/doc/functions/ and the navigation docs/_includes/api-nav.html.
- tutorials: the highlighted code blocks docs/_includes/code/*.html from the marked regions in examples/*.py.
- logo: the dark mode logo (logo_dark.svg) from the light one (logo.svg).
"""

import argparse
import enum
import html
import inspect
import os
import re
import shutil
import sys
from typing import Any

from jinja2 import Environment, FileSystemLoader, StrictUndefined

from qdocs import annotations, collect, docstring, markup, tutorials
from qdocs.project import Project

# Jinja delimiters that do not clash with the Liquid syntax ({{ }}, {% %}) that Jekyll renders afterward.
env = Environment(
    loader=FileSystemLoader(os.path.join(os.path.dirname(os.path.abspath(__file__)), "templates")),
    block_start_string="[%",
    block_end_string="%]",
    variable_start_string="[[",
    variable_end_string="]]",
    comment_start_string="[#",
    comment_end_string="#]",
    undefined=StrictUndefined,
    keep_trailing_newline=True,
)

# The colors of the light logo and their replacements in the dark logo.
DARK_LOGO_COLORS = {"#000000": "#e8e6ed", "#808080": "#a9a6b0"}


def write(path: str, text: str):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        f.write(text)


def _default(value) -> tuple[str, str]:
    """
    :returns: (text, color_class) The HTML text of a default value and the CSS class that colors it.
    """
    if isinstance(value, bool):
        return str(value), "bool"
    if isinstance(value, str):
        return html.escape(f"'{value}'"), "string"
    if isinstance(value, (int, float, tuple)):
        return html.escape(str(value)), "num"
    if callable(value):
        return html.escape(value.__name__), ""
    return html.escape(str(value)), ""


def _is_enum(obj) -> bool:
    return inspect.isclass(obj) and issubclass(obj, enum.Enum)


class ApiBuilder:
    """
    Builds the API pages of a project. Subclass it to customize how attributes and values are shown,
    see `attributes` and `format_value`.
    """

    def __init__(self, project: Project):
        self.project = project
        self.modules = collect.collect(project)
        self.index = collect.build_index(project, self.modules)
        self.errors: list[str] = []
        self.warnings: dict[str, list[str]] = {}
        self._current = ""

        class_urls = {}
        for module in self.modules:
            for entry in module.entries:
                if entry.kind == "class":
                    class_urls[entry.name] = entry.url
                    class_urls[entry.qualname] = entry.url
        aliases, aliases_url = set(), ""
        if project.type_aliases is not None:
            aliases = annotations.module_aliases(f"{project.package}.{project.type_aliases}")
            aliases_url = f"/doc/modules/{project.type_aliases}.html"
        self.link_types = annotations.Linker(class_urls, aliases, aliases_url)
        self.convert = markup.Converter(self._resolve)

    def _resolve(self, name: str) -> str:
        entries = self.index.get(name, [])
        if len(entries) == 1:
            return entries[0].url
        if not entries:
            self.errors.append(f"{self._current}: unknown reference [`{name}`]")
        else:
            options = ", ".join(e.qualname for e in entries)
            self.errors.append(f"{self._current}: ambiguous reference [`{name}`], use one of {options}")
        return "#"

    def attributes(self, entry: collect.Entry) -> list[tuple[str, Any]]:
        """
        :param entry: A namespace or an enum.
        :returns: (name, value) The attributes listed on the page of the entry. These are the members of an enum
         and the public class attributes of a namespace that are neither methods nor properties.
        """
        cls = entry.obj
        if _is_enum(cls):
            return [(m.name, m.value) for m in cls]
        return [
            (name, value)
            for name, value in inspect.getmembers(cls)
            if not name.startswith("_")
            and not inspect.isroutine(value)
            and not isinstance(inspect.getattr_static(cls, name), property)
        ]

    def format_value(self, value) -> str:
        """
        :param value: A default value of a parameter or the value of an attribute.
        :returns: The HTML of the value. Parts are colored with the classes string, bool, num, class and func
         inside a `default_value` span.
        """
        if isinstance(value, enum.Enum):
            return (
                f'<span class="default_value"><span class="class">{html.escape(type(value).__name__)}</span>.'
                f'<span class="func">{html.escape(value.name)}</span></span>'
            )
        text, color_class = _default(value)
        return f'<span class="default_value{" " + color_class if color_class else ""}">{text}</span>'

    def page(self, entry: collect.Entry) -> str:
        self._current = entry.qualname
        is_namespace = entry.kind == "namespace" or _is_enum(entry.obj)
        is_class = entry.kind in ("class", "namespace")
        source = dict(zip(("path", "start", "stop"), collect.source_location(self.project, entry.obj)))
        source["branch"] = self.project.branch
        if entry.kind == "method":
            prename, classname = entry.owner.namespace, entry.owner.name  # type: ignore
        else:
            prename, classname = entry.namespace, ""
        context = dict(
            title=entry.qualname,
            prename=prename,
            classname=classname,
            name=entry.name,
            is_class=is_class,
            is_namespace=is_namespace,
            source=source,
            sig=[],
            attributes=[],
            params=[],
            returns=None,
            raises=[],
        )

        if is_namespace:
            doc = docstring.parse(inspect.getdoc(entry.obj))
            warnings = docstring.validate(doc, [], True)
            context["attributes"] = [dict(name=n, value=self.format_value(v)) for n, v in self.attributes(entry)]
        else:
            self._signature(entry, context)
            doc = context.pop("doc")
            warnings = context.pop("warnings")
        if warnings:
            self.warnings[entry.qualname] = warnings
        context["description"] = self.convert(doc.description)
        context["raises"] = [
            dict(error=html.escape(err), description=self.convert(desc)) for err, desc in doc.raises
        ]
        return env.get_template("function.html").render(**context)

    def _signature(self, entry: collect.Entry, context: dict):
        """Add the signature, the parameters and the returns of a function, class or method to the page context."""
        func = entry.func
        is_class = entry.kind == "class"
        sig = inspect.signature(entry.obj)
        params = [(n, p) for n, p in sig.parameters.items() if n != "self"]

        if is_class:
            doc = docstring.parse(func.__doc__ or entry.obj.__doc__)
        else:  # Overridden methods without a docstring inherit the docstring of the base class.
            doc = docstring.parse(inspect.getdoc(func))
        param_types, return_type = annotations.source_annotations(func)

        for name, p in params:
            star = {p.VAR_POSITIONAL: "*", p.VAR_KEYWORD: "**"}.get(p.kind, "")
            default = None if p.default is p.empty else self.format_value(p.default)
            context["sig"].append(dict(star=star, name=name, default=default))

        context["params"] = [
            dict(
                name=name,
                type=self.link_types(param_types[name]) if name in param_types else None,
                description=self.convert(doc.params.get(name, "")),
            )
            for name, _ in params
        ]

        # Functions without a return value and without a returns description get no Returns section.
        if not is_class and ((doc.returns and doc.returns.description) or return_type not in (None, "None")):
            label, desc = (doc.returns.label, doc.returns.description) if doc.returns else ("out", "")
            context["returns"] = dict(
                label=label,
                type=self.link_types(return_type) if return_type else None,
                description=self.convert(desc),
            )
        context["doc"] = doc
        context["warnings"] = docstring.validate(doc, [n for n, _ in params], is_class)

    def build(self) -> list[str]:
        """
        :returns: A list of errors.
        """
        functions_dir = os.path.join(self.project.docs, "doc", "functions")
        nav_file = os.path.join(self.project.docs, "_includes", "api-nav.html")
        if os.path.exists(functions_dir):
            shutil.rmtree(functions_dir)
        n = 0
        for entry in collect.iter_pages(self.modules):
            write(os.path.join(self.project.docs, entry.url.lstrip("/")), self.page(entry))
            n += 1
        write(nav_file, env.get_template("nav.html").render(package=self.project.package, modules=self.modules))
        print(f"Wrote {n} API pages and {os.path.relpath(nav_file, self.project.root)}.")

        if self.warnings:
            print(f"\nDocstring warnings ({sum(len(w) for w in self.warnings.values())}):")
            for name, warnings in self.warnings.items():
                for w in warnings:
                    print(f"  {name}: {w}")
        return self.errors


def dark_logo(svg: str) -> str:
    """
    :param svg: The SVG of the light logo.
    :returns: The SVG of the dark logo, with the colors in `DARK_LOGO_COLORS` replaced.
    """
    pattern = re.compile("|".join(re.escape(c) for c in DARK_LOGO_COLORS), re.IGNORECASE)
    return pattern.sub(lambda m: DARK_LOGO_COLORS[m.group(0).lower()], svg)


def main(project: Project, builder: type[ApiBuilder] = ApiBuilder, argv: list[str] | None = None):
    """
    :param project: The documented project.
    :param builder: The class that builds the API pages, a subclass of `ApiBuilder` for customizations.
    :param argv: The command line arguments. Defaults to `sys.argv[1:]`.
    """
    parser = argparse.ArgumentParser(description=f"Generate the {project.package} website.")
    parser.add_argument("target", nargs="?", default="all", choices=["api", "tutorials", "logo", "all"])
    args = parser.parse_args(argv)
    sys.path.insert(0, project.root)

    errors = []
    if args.target in ("api", "all"):
        errors += builder(project).build()
    if args.target in ("tutorials", "all"):
        errors += tutorials.build(project, write)
    if args.target in ("logo", "all"):
        light = os.path.join(project.docs, project.logo)
        dark = light.replace(".svg", "_dark.svg")
        with open(light, encoding="utf-8") as f:
            write(dark, dark_logo(f.read()))
        print(f"Wrote {os.path.relpath(dark, project.root)}.")
    if errors:
        print(f"\nErrors ({len(errors)}):")
        for e in errors:
            print(f"  {e}")
        sys.exit(1)

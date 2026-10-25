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
from dataclasses import dataclass
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

# The value of an attribute that has none on the class, e.g. an instance attribute or a property.
EMPTY = inspect.Parameter.empty


@dataclass
class Attribute:
    """An attribute listed on the page of a class."""

    name: str
    value: Any = EMPTY
    type: str | None = None  # The annotation source text.
    description: str = ""


def write(path: str, text: str) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        f.write(text)


def _default(value: Any) -> tuple[str, str]:
    """
    :returns: (text, color_class) The HTML text of a default value and the CSS class that colors it.
    """
    if isinstance(value, bool):
        return str(value), "bool"
    if isinstance(value, str):
        return html.escape(repr(value)), "string"  # Quotes and control characters as in the source.
    if isinstance(value, (int, float, tuple)):
        return html.escape(str(value)), "num"
    if callable(value):
        return html.escape(value.__name__), ""
    return html.escape(str(value)), ""


def _is_enum(obj: Any) -> bool:
    return inspect.isclass(obj) and issubclass(obj, enum.Enum)


class ApiBuilder:
    """
    Builds the API pages of a project. Subclass it to customize how attributes and values are shown,
    see `attributes` and `format_value`.
    """

    def __init__(self, project: Project) -> None:
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

    def attributes(self, entry: collect.Entry) -> list[Attribute]:
        """
        :param entry: A class, namespace or enum.
        :returns: The attributes listed on the page of the entry. These are the members of an enum, and the public
         class attributes, annotated instance attributes (including `__slots__`) and properties of a class, sorted by
         name. Types and descriptions are the annotations and the docstrings below the attributes in the class body
         (or of its bases), and the return annotations and docstrings of the properties.
        """
        cls = entry.obj
        source = annotations.class_attributes(cls)
        if _is_enum(cls):
            return [Attribute(m.name, m.value, description=source.get(m.name, (None, ""))[1]) for m in cls]

        ret = []
        for name, value in inspect.getmembers(cls):
            if name.startswith("_") or inspect.isroutine(value):
                continue
            static = inspect.getattr_static(cls, name)
            annotation, description = source.get(name, (None, ""))
            if isinstance(static, property):
                doc = docstring.parse(inspect.getdoc(static))
                returns = annotations.source_annotations(static.fget)[1] if static.fget else None
                desc = doc.description or (doc.returns.description if doc.returns else "")
                ret.append(Attribute(name, type=returns, description=desc))
            elif inspect.isdatadescriptor(static) or inspect.ismethoddescriptor(static):
                if name in source:  # A slot of an annotated attribute, not a descriptor of a builtin base.
                    ret.append(Attribute(name, type=annotation, description=description))
            else:
                ret.append(Attribute(name, value, annotation, description))
        # Annotated instance attributes without a class attribute.
        for name, (annotation, description) in source.items():
            if annotation is not None and not name.startswith("_") and not hasattr(cls, name):
                ret.append(Attribute(name, type=annotation, description=description))
        return sorted(ret, key=lambda a: a.name)

    def format_value(self, value: Any) -> str:
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
        path, start, stop = collect.source_location(self.project, entry.obj)
        source = dict(path=path, start=start, stop=stop, branch=self.project.branch)
        if entry.kind == "method":
            prename, classname = entry.owner.namespace, entry.owner.name  # type: ignore
        else:
            prename, classname = entry.namespace, ""
        context: dict[str, Any] = dict(
            title=entry.qualname,
            prename=prename,
            classname=classname,
            name=entry.name,
            is_class=is_class,
            has_sig=False,
            source=source,
            sig=[],
            attributes=[],
            params=[],
            returns=None,
            raises=[],
        )

        # Namespaces and classes without their own __init__ or __new__ have no signature.
        if is_namespace or (entry.kind == "class" and entry.func is None):
            doc = docstring.parse(inspect.getdoc(entry.obj))
            warnings = docstring.validate(doc, [], True)
        else:
            doc, warnings = self._signature(entry, context)
        if is_class:
            context["attributes"] = [
                dict(
                    name=a.name,
                    type=self.link_types(a.type) if a.type else None,
                    value=None if a.value is EMPTY else self.format_value(a.value),
                    description=self.convert(a.description),
                )
                for a in self.attributes(entry)
            ]
        if warnings:
            self.warnings[entry.qualname] = warnings
        context["description"] = self.convert(doc.description)
        context["raises"] = [dict(error=html.escape(err), description=self.convert(desc)) for err, desc in doc.raises]
        return env.get_template("function.html").render(**context)

    def _signature(self, entry: collect.Entry, context: dict[str, Any]) -> tuple[docstring.Docstring, list[str]]:
        """
        Add the signature, the parameters and the returns of a function, class or method to the page context.

        :returns: (doc, warnings) The parsed docstring and the warnings about it.
        """
        func = entry.func
        assert func is not None, "classes without __init__ or __new__ have no signature"
        is_class = entry.kind == "class"
        sig = inspect.signature(entry.obj)
        params = [(n, p) for n, p in sig.parameters.items() if n != "self"]
        context["has_sig"] = True

        doc = docstring.parse((func.__doc__ or entry.obj.__doc__) if is_class else inspect.getdoc(func))
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
        # A __new__ returns the instance, so it may document ':returns:'.
        no_returns = is_class and func.__name__ != "__new__"
        return doc, docstring.validate(doc, [n for n, _ in params], no_returns)

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


def main(project: Project, builder: type[ApiBuilder] = ApiBuilder, argv: list[str] | None = None) -> None:
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

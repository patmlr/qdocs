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
import numbers
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

TYPES_INCLUDE = re.compile(r"{%\s*include\s+types/(\S+?)\.html\s*%}")

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


def _ctor_args(value: Any) -> list[tuple[str | None, Any]] | None:
    """
    :param value: An object.
    :returns: The arguments that recreate the object with its class, as (keyword, value) pairs. The keyword is `None`
     for positional arguments. `None` if the class takes no arguments, `*args` or `**kwargs`, or if a parameter is not
     an attribute of the object.
    """
    try:
        params = list(inspect.signature(type(value)).parameters.values())
    except (TypeError, ValueError):
        return None
    if not params or any(p.kind in (p.VAR_POSITIONAL, p.VAR_KEYWORD) for p in params):
        return None
    args = []
    for p in params:
        try:
            arg = getattr(value, p.name)
        except Exception:
            return None
        args.append((p.name if p.kind == p.KEYWORD_ONLY else None, arg))
    return args


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
        alias_urls: dict[str, dict[str, str]] = {}
        for module in self.modules:
            for alias in module.aliases:
                alias_urls.setdefault(alias.name, {})[module.name] = alias.url
        self.link_types = annotations.Linker(class_urls, alias_urls)
        self.convert = markup.Converter(self._resolve)
        self._class_urls = {
            entry.obj: entry.url
            for module in self.modules
            for entry in module.entries
            if entry.kind in ("class", "namespace")
        }
        self._formatting: set[int] = set()

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
         name. Enums and namespaces keep the source order. Types and descriptions are the annotations and the
         docstrings below the attributes in the class body (or of its bases), and the return annotations and
         docstrings of the properties.
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
        ret.sort(key=lambda a: a.name)
        if entry.kind == "namespace":
            order: dict[str, int] = {}
            for name in [*source, *(n for c in reversed(cls.__mro__) for n in vars(c))]:
                order.setdefault(name, len(order))
            ret.sort(key=lambda a: order.get(a.name, len(order)))
        return ret

    def format_value(self, value: Any) -> str:
        """
        :param value: A default value of a parameter, the value of an attribute or a part of such a value.
        :returns: The HTML of the value, with its parts colored by the classes string, bool, num, class and func.
         Tuples, lists, sets and dicts are formatted item by item, sets sorted. Other objects are shown as the call
         of their class that recreates them, e.g. `Unit(1000.0, frozenset({('km', 1)}), Length, Context.I)`, if all
         parameters of the class are attributes of the object, otherwise as `str(value)`. Documented classes are
         linked to their pages.
        """
        if isinstance(value, enum.Enum):
            return f'{self._class(type(value))}.<span class="func">{html.escape(value.name)}</span>'
        if isinstance(value, bool):
            return f'<span class="bool">{value}</span>'
        if isinstance(value, str):
            return f'<span class="string">{html.escape(repr(value))}</span>'  # Quotes and escapes as in the source.
        if isinstance(value, numbers.Number):
            return f'<span class="num">{html.escape(str(value))}</span>'
        if value is None:
            return "None"
        if inspect.isclass(value):
            return self._class(value)
        if inspect.isroutine(value):
            return f'<span class="func">{html.escape(value.__name__)}</span>'
        if id(value) in self._formatting:
            return "..."
        self._formatting.add(id(value))
        try:
            return self._format_object(value)
        finally:
            self._formatting.discard(id(value))

    def _format_object(self, value: Any) -> str:
        cls = type(value)
        if cls is tuple:
            items = [self.format_value(v) for v in value]
            return f"({', '.join(items)}{',' if len(items) == 1 else ''})"
        if cls is list:
            return f"[{', '.join(self.format_value(v) for v in value)}]"
        if cls is dict:
            return f"{{{', '.join(f'{self.format_value(k)}: {self.format_value(v)}' for k, v in value.items())}}}"
        if cls in (set, frozenset):
            items = sorted(self.format_value(v) for v in value)
            if not items:
                return f"{self._class(cls)}()"
            braced = f"{{{', '.join(items)}}}"
            return braced if cls is set else f"{self._class(cls)}({braced})"
        args = _ctor_args(value)
        if args is None:
            return html.escape(str(value))
        parts = [(f"{keyword}=" if keyword else "") + self.format_value(arg) for keyword, arg in args]
        return f"{self._class(cls)}({', '.join(parts)})"

    def _class(self, cls: type) -> str:
        name = f'<span class="class">{html.escape(cls.__name__)}</span>'
        url = self._class_urls.get(cls)
        return name if url is None else f"<a href=\"{{{{ '{url}' | relative_url }}}}\">{name}</a>"

    def _value(self, value: Any) -> str:
        return f'<span class="default_value">{self.format_value(value)}</span>'

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
                    type=self.link_types(a.type, entry.module) if a.type else None,
                    value=None if a.value is EMPTY else self._value(a.value),
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

        if is_class:
            doc = docstring.merge(docstring.parse(entry.obj.__doc__), docstring.parse(func.__doc__))
        else:
            doc = docstring.parse(inspect.getdoc(func))
        param_types, return_type = annotations.source_annotations(func)

        for name, p in params:
            star = {p.VAR_POSITIONAL: "*", p.VAR_KEYWORD: "**"}.get(p.kind, "")
            default = None if p.default is p.empty else self._value(p.default)
            context["sig"].append(dict(star=star, name=name, default=default))

        context["params"] = [
            dict(
                name=name,
                type=self.link_types(param_types[name], entry.module) if name in param_types else None,
                description=self.convert(doc.params.get(name, "")),
            )
            for name, _ in params
        ]

        # Functions without a return value and without a returns description get no Returns section.
        if not is_class and ((doc.returns and doc.returns.description) or return_type not in (None, "None")):
            label, desc = (doc.returns.label, doc.returns.description) if doc.returns else ("out", "")
            context["returns"] = dict(
                label=label,
                type=self.link_types(return_type, entry.module) if return_type else None,
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
        self._write_types()

        if self.warnings:
            print(f"\nDocstring warnings ({sum(len(w) for w in self.warnings.values())}):")
            for name, warnings in self.warnings.items():
                for w in warnings:
                    print(f"  {name}: {w}")
        return self.errors

    def types(self, module: collect.Module) -> str:
        """
        :param module: A module with type aliases.
        :returns: The HTML of the list of the type aliases of the module, included by its module page.
        """
        self._current = f"{self.project.package}.{module.name}"
        aliases = [
            dict(
                name=a.name,
                params=html.escape(a.params),
                value=self.link_types(a.value, module.name),
                description=self.convert(a.description),
            )
            for a in module.aliases
        ]
        return env.get_template("types.html").render(aliases=aliases)

    def _write_types(self) -> None:
        """
        Write the type alias lists `_includes/types/<module>.html` and check that the module pages include them.
        """
        types_dir = os.path.join(self.project.docs, "_includes", "types")
        if os.path.exists(types_dir):
            shutil.rmtree(types_dir)
        with_aliases = {m.name for m in self.modules if m.aliases}
        for module in self.modules:
            if module.aliases:
                write(os.path.join(types_dir, f"{module.name}.html"), self.types(module))
        if with_aliases:
            print(f"Wrote the type alias lists of {', '.join(sorted(with_aliases))} to _includes/types/.")

        for module in self.modules:
            page = os.path.join(self.project.docs, module.url.lstrip("/"))
            text = ""
            if os.path.exists(page):
                with open(page, encoding="utf-8") as f:
                    text = f.read()
            included = set(TYPES_INCLUDE.findall(text))
            path = os.path.relpath(page, self.project.root)
            if module.name in with_aliases and module.name not in included:
                print(f"  note: {path} does not include types/{module.name}.html, its type aliases are not listed")
            for name in sorted(included - with_aliases):
                self.errors.append(f"{path}: includes types/{name}.html, but module '{name}' has no type aliases")


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

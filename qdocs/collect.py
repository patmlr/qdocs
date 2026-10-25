"""
Introspection of the documented package: which modules, functions, classes and methods are documented, and where their
pages live on the website.
"""

import importlib
import inspect
import os
from collections.abc import Callable, Iterator
from dataclasses import dataclass, field
from typing import Any

from qdocs.project import Project


@dataclass
class Entry:
    """A documented function, class, namespace or method."""

    name: str
    obj: Any  # The function, class or method. None for modules.
    module: str  # The module (file) this entry is documented in, e.g. "analyze".
    namespace: str  # The public namespace, e.g. "qspec.analyze" or "qspec.models.Model".
    url: str  # The site url of the page, e.g. "/doc/functions/analyze/york_fit.html".
    kind: str  # "function", "class", "namespace", "method" or "module" (only used as a reference target).
    owner: "Entry | None" = None  # The class of a method.
    methods: list["Method"] = field(default_factory=list)  # The methods of a class.

    @property
    def qualname(self) -> str:
        return f"{self.namespace}.{self.name}"

    @property
    def func(self) -> Callable[..., Any] | None:
        """
        The function whose signature and docstring describe this entry. For a class this is `__init__`, or `__new__`
        if only that is overridden. None for a class that overrides neither.
        """
        if self.kind != "class":
            return self.obj
        for name in ("__init__", "__new__"):
            func = getattr(self.obj, name)
            if func is not getattr(object, name):
                return func
        return None


@dataclass
class Method:
    """A public method of a class, either defined in that class (page) or inherited (link to the defining class)."""

    name: str
    entry: Entry  # The entry of the page that documents this method.
    inherited_from: Entry | None = None  # The documented class the method is inherited from.


@dataclass
class Module:
    name: str
    url: str
    entries: list[Entry]


def _public_methods(cls: type) -> list[str]:
    return [name for name, _ in inspect.getmembers(cls, inspect.isfunction) if not name.startswith("_")]


def _defining_class(cls: type, name: str) -> type:
    for c in cls.__mro__:
        if name in vars(c):
            return c
    return cls


def collect(project: Project) -> list[Module]:
    """
    :param project: The documented project.
    :returns: The documented modules with their functions and classes. Class methods are only documented on the page
     of the class that defines them, as long as that class is documented itself.
    """
    modules = []
    classes = {}  # class object -> Entry
    for file in project.modules:
        mod = importlib.import_module(f"{project.package}.{file}")
        namespace = f"{project.package}.{file}" if file in project.namespaced else project.package
        include = project.include.get(file)
        names = sorted(n for n in mod.__all__ if callable(getattr(mod, n)) and (include is None or n in include))
        entries = []
        for name in names:
            obj = getattr(mod, name)
            if f"{namespace}.{name}" in project.namespaces:
                entry = Entry(name, obj, file, namespace, f"/doc/functions/{file}/{name}.html", "namespace")
            elif inspect.isclass(obj):
                entry = Entry(name, obj, file, namespace, f"/doc/functions/{file}/{name}/{name}.html", "class")
                classes[obj] = entry
            else:
                entry = Entry(name, obj, file, namespace, f"/doc/functions/{file}/{name}.html", "function")
            entries.append(entry)
        modules.append(Module(file, f"/doc/modules/{file}.html", entries))

    # Methods are resolved after all classes are known, so inherited methods can link across modules.
    for cls, entry in classes.items():
        for name in _public_methods(cls):
            definer = classes.get(_defining_class(cls, name))
            if definer is None or definer is entry:
                url = f"/doc/functions/{entry.module}/{entry.name}/{name}.html"
                m_entry = Entry(name, getattr(cls, name), entry.module, entry.qualname, url, "method", owner=entry)
                entry.methods.append(Method(name, m_entry))
            else:
                entry.methods.append(Method(name, None, inherited_from=definer))  # type: ignore

    # Resolve the entries of inherited methods once all own methods exist.
    for entry in classes.values():
        for m in entry.methods:
            if m.inherited_from is not None:
                m.entry = next(_m.entry for _m in m.inherited_from.methods if _m.name == m.name)
    return modules


def iter_pages(modules: list[Module]) -> Iterator[Entry]:
    """Yield every entry that gets its own page."""
    for module in modules:
        for entry in module.entries:
            yield entry
            for m in entry.methods:
                if m.inherited_from is None:
                    yield m.entry


def build_index(project: Project, modules: list[Module]) -> dict[str, list[Entry]]:
    """
    :param project: The documented project.
    :param modules: The documented modules.
    :returns: A map from every name an entry can be referenced by in docstrings to the matching entries.
     Names are the short name (`fit`), `Class.method`, the fully qualified name (`qspec.models.fit`)
     and the module names (`qspec.analyze`).
    """
    index: dict[str, list[Entry]] = {}
    package = project.package

    def add(key: str, entry: Entry) -> None:
        bucket = index.setdefault(key, [])
        if entry not in bucket:
            bucket.append(entry)

    for entry in iter_pages(modules):
        add(entry.name, entry)
        add(entry.qualname, entry)
        # Entries of modules in the package namespace are also reachable through their module, e.g. qspec.physics.f.
        add(entry.qualname.replace(f"{package}.", f"{package}.{entry.module}.", 1), entry)
        if entry.owner is not None:
            add(f"{entry.owner.name}.{entry.name}", entry)
    for module in modules:
        add(f"{package}.{module.name}", Entry(module.name, None, module.name, package, module.url, "module"))
        for entry in module.entries:
            for m in entry.methods:  # Inherited methods are also reachable as Subclass.method.
                add(f"{entry.name}.{m.name}", m.entry)
                add(f"{entry.qualname}.{m.name}", m.entry)
    return index


def source_location(project: Project, obj: Any) -> tuple[str, int, int]:
    """
    :param project: The documented project.
    :param obj: A function or class.
    :returns: (path, start, stop) The path of the source file relative to the repository root (posix style)
     and the first and last line of the object.
    """
    lines, start = inspect.getsourcelines(obj)
    path = os.path.relpath(inspect.getfile(obj), project.root).replace(os.sep, "/")
    return path, start, start + len(lines) - 1

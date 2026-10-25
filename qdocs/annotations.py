"""
Type annotations exactly as written in the source code, with documented classes and type aliases linked.
"""

import ast
import html
import importlib
import inspect
import re
import textwrap
from collections.abc import Callable
from typing import Any

IDENTIFIER = re.compile(r"[A-Za-z_][A-Za-z0-9_.]*")


def module_aliases(module: str) -> set[str]:
    """
    :param module: The fully qualified name of a module.
    :returns: The type aliases (`type x = ...`, `x = ...`) and classes defined in the module.
    """
    tree = ast.parse(inspect.getsource(importlib.import_module(module)))
    names = set()
    for node in tree.body:
        if isinstance(node, ast.TypeAlias):
            names.add(node.name.id)  # type: ignore
        elif isinstance(node, ast.Assign):
            names.update(t.id for t in node.targets if isinstance(t, ast.Name) and not t.id.startswith("_"))
        elif isinstance(node, ast.ClassDef):
            names.add(node.name)
    return names - {"__all__"}


def _strip_quotes(text: str) -> str:
    if len(text) >= 2 and text[0] == text[-1] and text[0] in "'\"":
        return text[1:-1]
    return text


def source_annotations(func: Callable[..., Any]) -> tuple[dict[str, str], str | None]:
    """
    :param func: A function or method.
    :returns: (params, returns) The annotation source text of each annotated parameter
     and of the return value (`None` if not annotated).
    """
    try:
        source = textwrap.dedent(inspect.getsource(func))
        node = ast.parse(source).body[0]
    except (OSError, TypeError, SyntaxError, IndexError):
        return _fallback(func)
    if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
        return _fallback(func)

    args = node.args
    params = {}
    for arg in [*args.posonlyargs, *args.args, args.vararg, *args.kwonlyargs, args.kwarg]:
        if arg is not None and arg.annotation is not None:
            params[arg.arg] = _strip_quotes(ast.get_source_segment(source, arg.annotation))  # type: ignore
    returns = None
    if node.returns is not None:
        returns = _strip_quotes(ast.get_source_segment(source, node.returns))  # type: ignore
    return params, returns


def class_attributes(cls: type) -> dict[str, tuple[str | None, str]]:
    """
    :param cls: A class.
    :returns: (annotation, description) The annotation source text (`None` if not annotated) and the docstring below
     the attribute ("" if there is none) of each attribute that is assigned or annotated in the body of the class or
     of its bases. A subclass inherits the annotation and the docstring of an attribute it only reassigns.
    """
    ret: dict[str, tuple[str | None, str]] = {}
    for c in reversed(cls.__mro__[:-1]):  # Bases first, without object.
        try:
            source = textwrap.dedent(inspect.getsource(c))
            node = ast.parse(source).body[0]
        except (OSError, TypeError, SyntaxError, IndexError):
            continue  # Builtins and classes created at runtime.
        if not isinstance(node, ast.ClassDef):
            continue
        for stmt, after in zip(node.body, [*node.body[1:], None]):
            if isinstance(stmt, ast.AnnAssign) and isinstance(stmt.target, ast.Name):
                names = [stmt.target.id]
                annotation = _strip_quotes(ast.get_source_segment(source, stmt.annotation))  # type: ignore
            elif isinstance(stmt, ast.Assign):
                names, annotation = [t.id for t in stmt.targets if isinstance(t, ast.Name)], None
            else:
                continue
            doc = ""
            if isinstance(after, ast.Expr) and isinstance(getattr(after.value, "value", None), str):
                doc = inspect.cleandoc(after.value.value)  # type: ignore
            for name in names:
                base_annotation, base_doc = ret.get(name, (None, ""))
                ret[name] = (annotation or base_annotation, doc or base_doc)
    return ret


def _fallback(func: Callable[..., Any]) -> tuple[dict[str, str], str | None]:
    sig = inspect.signature(func)
    params = {
        name: inspect.formatannotation(p.annotation)
        for name, p in sig.parameters.items()
        if p.annotation is not inspect.Parameter.empty
    }
    returns = None
    if sig.return_annotation is not inspect.Signature.empty:
        returns = inspect.formatannotation(sig.return_annotation)
    return params, returns


class Linker:
    def __init__(self, class_urls: dict[str, str], aliases: set[str] = frozenset(), aliases_url: str = "") -> None:  # type: ignore
        """
        :param class_urls: A map from class names (short and fully qualified) to their site urls.
        :param aliases: The names of type aliases, linked to `aliases_url`.
        :param aliases_url: The site url of the module page that describes the type aliases.
        """
        self.class_urls = class_urls
        self.aliases = aliases
        self.aliases_url = aliases_url

    def __call__(self, annotation: str) -> str:
        """
        :param annotation: The annotation source text.
        :returns: The HTML of the annotation with documented classes and type aliases linked.
        """
        out = []
        last = 0
        for m in IDENTIFIER.finditer(annotation):
            name = m.group(0)
            url = self.class_urls.get(name)
            if url is None and name in self.aliases:
                url = self.aliases_url
            if url is None:
                continue
            out.append(html.escape(annotation[last : m.start()]))
            out.append(f"<a href=\"{{{{ '{url}' | relative_url }}}}\">{html.escape(name)}</a>")
            last = m.end()
        out.append(html.escape(annotation[last:]))
        return "".join(out)

"""
Type annotations exactly as written in the source code, with documented classes and type aliases linked.
"""

import ast
import html
import importlib
import inspect
import re
import textwrap

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


def source_annotations(func) -> tuple[dict[str, str], str | None]:
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


def _fallback(func) -> tuple[dict[str, str], str | None]:
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
    def __init__(self, class_urls: dict[str, str], aliases: set[str] = frozenset(), aliases_url: str = ""):  # type: ignore
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

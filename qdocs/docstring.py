"""
A parser for the reST field style of the docstrings:

    Description, possibly over several paragraphs.

    :param name: Description, continued on
     indented lines.
    :returns: (label) Description. The optional label in parentheses names the return value(s).
    :raises ValueError: Description.
    :raises (ValueError, TypeError): Description.
"""

import inspect
import re
from dataclasses import dataclass, field

FIELD = re.compile(r"^:(\w+)(?:\s+([^:]+?))?\s*:(?:\s+(.*))?$")
FIELD_KINDS = {
    "param": "param",
    "returns": "returns",
    "return": "returns",
    "raises": "raises",
    "raise": "raises",
}


@dataclass
class Returns:
    label: str
    description: str


@dataclass
class Docstring:
    description: str = ""
    params: dict[str, str] = field(default_factory=dict)
    returns: Returns | None = None
    raises: list[tuple[str, str]] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


def _split_label(text: str) -> tuple[str, str]:
    """Split a leading '(label)' from a returns description. A single name loses its parentheses."""
    if not text.startswith("("):
        return "out", text
    j = text.find(")") + 1
    label = text[:j]
    if "," not in label:
        label = label[1:-1]
    return label, text[j:].strip()


def parse(doc: str | None) -> Docstring:
    ret = Docstring()
    if not doc:
        return ret

    description: list[str] = []
    fields: list[tuple[str, str, list[str]]] = []  # (kind, argument, lines)
    for line in inspect.cleandoc(doc).splitlines():
        m = FIELD.match(line)
        if m:
            name, arg, text = m.group(1), (m.group(2) or "").strip(), m.group(3) or ""
            kind = FIELD_KINDS.get(name)
            if kind is None:
                ret.warnings.append(f"unknown field ':{name}:'")
                kind = name
            fields.append((kind, arg, [text]))
        elif fields:
            fields[-1][2].append(line)
        else:
            description.append(line)

    ret.description = "\n".join(description).strip()
    for kind, arg, lines in fields:
        # Continuation lines are indented relative to the field. Remove the common indentation.
        text = lines[0] + ("\n" + inspect.cleandoc("\n".join(lines[1:])) if len(lines) > 1 else "")
        text = text.strip()
        if kind == "param":
            if arg in ret.params:
                ret.warnings.append(f"parameter '{arg}' documented twice")
            ret.params[arg] = text
        elif kind == "returns":
            if ret.returns is not None:
                ret.warnings.append("':returns:' documented twice")
            ret.returns = Returns(*_split_label(text))
        elif kind == "raises":
            ret.raises.append((arg, text))
    return ret


def merge(first: Docstring, second: Docstring) -> Docstring:
    """
    :param first: A parsed docstring, e.g. of a class.
    :param second: A parsed docstring that adds to the first, e.g. of its `__init__`.
    :returns: The descriptions of both, separated by a blank line, and their fields. The fields of `second` override
     those of `first`.
    """
    descriptions = [first.description, second.description]
    if first.description == second.description:
        descriptions = [first.description]
    return Docstring(
        description="\n\n".join(d for d in descriptions if d),
        params={**first.params, **second.params},
        returns=second.returns or first.returns,
        raises=[*first.raises, *second.raises],
        warnings=[*first.warnings, *second.warnings],
    )


def validate(doc: Docstring, params: list[str], is_class: bool) -> list[str]:
    """
    :param doc: The parsed docstring.
    :param params: The parameter names of the signature (without self).
    :param is_class: Whether the docstring belongs to a class (no ':returns:' expected).
    :returns: Warnings about mismatches between the docstring and the signature.
    """
    warnings = list(doc.warnings)
    for p in doc.params:
        if p not in params:
            warnings.append(f"documented parameter '{p}' is not in the signature")
    for p in params:
        if p not in doc.params:
            warnings.append(f"parameter '{p}' is not documented")
    if is_class and doc.returns is not None:
        warnings.append("class documents ':returns:'")
    return warnings

"""
The configuration of a documented package.
"""

import os
from dataclasses import dataclass, field


@dataclass
class Project:
    """
    The package and the website it is documented on. The website is a Jekyll site in `docs` that uses the qdocs theme.

    :param package: The name of the documented package, e.g. "qspec".
    :param modules: The documented modules (files or folders) of the package, e.g. ["algebra", "analyze"].
    :param root: The repository root. Source links on the website are relative to it.
    :param namespaced: The modules that are their own namespace (qspec.models.Model).
     The entries of the other modules live in the package namespace (qspec.fit).
    :param include: The modules for which only the listed names are documented.
    :param namespaces: The fully qualified names of classes that are documented as a namespace of attributes
     (no signature, no methods), e.g. a registry class used like a module. Enums are documented this way, too.
    :param type_aliases: The module whose type aliases and classes are linked to its module page in annotations.
    :param branch: The branch of the source links.
    :param docs: The Jekyll site. Defaults to `root/docs`.
    :param examples: The example scripts with the tutorial code regions. Defaults to `root/examples`.
    :param logo: The light logo of the site, relative to `docs`. The `logo` target derives the dark logo from it.
    """

    package: str
    modules: list[str]
    root: str
    namespaced: set[str] = field(default_factory=set)
    include: dict[str, set[str]] = field(default_factory=dict)
    namespaces: set[str] = field(default_factory=set)
    type_aliases: str | None = None
    branch: str = "main"
    docs: str = ""
    examples: str = ""
    logo: str = "assets/img/logo.svg"

    def __post_init__(self):
        self.root = os.path.abspath(self.root)
        self.docs = os.path.abspath(self.docs or os.path.join(self.root, "docs"))
        self.examples = os.path.abspath(self.examples or os.path.join(self.root, "examples"))
        self.modules = sorted(self.modules)

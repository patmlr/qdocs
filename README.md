# qdocs

The website theme and generator of [qspec](https://github.com/patmlr/qspec) and
[qunits](https://github.com/patmlr/qunits). This repository is both:

- a Jekyll theme (`_layouts/`, `_includes/`, `_sass/`, `assets/`) that GitHub Pages loads with `remote_theme`, and
- a Python package (`qdocs/`) that generates the API pages and the tutorial code blocks of a site.

## Use it in a site

`docs/_config.yml`:

```yaml
title: qunits
logo: /assets/img/logo.svg          # The dark logo is logo_dark.svg next to it.
description: A performant, verbose and generic physical unit system.
show_downloads: true                # The PyPi, GitHub and .zip links.
accent_color: "#2a7fff"             # The color of the logo.
copyright: 2026 Patrick M&#252;ller. All rights reserved.
remote_theme: patmlr/qdocs@v0.2.0   # Pin a tag, so theme changes do not reach the site unnoticed.
plugins:
  - jekyll-remote-theme
  - jekyll-seo-tag
```

The site provides `_data/navigation.yml` (top navigation), `_data/tutorials.yml` (tutorial list),
`_includes/badges.html` (optional) and its logos `assets/img/logo.svg`, `logo_dark.svg` and `logo_small.svg`.
Any theme file can be overridden by a file at the same path in the site. Extra styles go in `_sass/custom.scss`,
extra `<head>` tags in `_includes/head-custom.html`.

`docs/requirements.txt`, with the same version as `remote_theme`:

```text
qdocs==0.2.0
```

`docs/_gen/build.py`:

```python
import os

from qdocs import Project, main

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

PROJECT = Project(
    package="qspec",
    modules=["algebra", "analyze", "models", "physics"],
    root=ROOT,
    namespaced={"analyze", "models"},  # qspec.models.Model instead of qspec.Model.
)

if __name__ == "__main__":
    main(PROJECT)
```

```bash
python docs/_gen/build.py [api | tutorials | logo | all]
```

| Target      | Source                                    | Output                                           |
|-------------|-------------------------------------------|--------------------------------------------------|
| `api`       | docstrings and signatures of the package  | `doc/functions/**`, `_includes/api-nav.html`,    |
|             |                                           | `_includes/types/<module>.html`                  |
| `tutorials` | `# docs: <name>` regions in `examples/`   | `_includes/code/<name>.html`                     |
| `logo`      | `assets/img/logo.svg`                     | `assets/img/logo_dark.svg`                       |

The module pages `doc/modules/<module>.html` and the overview `doc/doc.html` are written by hand with the `api`
layout, which adds the navigation. See `Project` in [`qdocs/project.py`](qdocs/project.py) for all options.

The type aliases of a module (`type scalar = int | float`) are listed in `_includes/types/<module>.html`. Include the
list in the module page with `{% include types/<module>.html %}`. Type aliases in annotations link to their entry in
that list, and the build notes module pages that do not include their list.

### Customizations

Every class page has an Attributes section with the public class attributes, the annotated instance attributes
(including `__slots__`) and the properties of the class, sorted by name. Classes listed in `Project.namespaces` are
documented like a module of constants: no signature and no methods, only the description and the attributes in source
order. Enums are documented this way automatically.

Default values in signatures and attribute values are shown as Python source:

- Strings, numbers, booleans, enum members, classes and functions as written in code. Documented classes are linked.
- Tuples, lists, sets and dicts item by item. Sets are sorted, so the pages do not change between builds.
- Other objects as the call of their class that recreates them, e.g. `Unit(1000.0, frozenset({('km', 1)}), Length,
  Context.I)`, if every parameter of the class is an attribute of the object, otherwise as `str(value)`.

Subclass `ApiBuilder` to change which attributes are listed (`attributes` returns a list of `Attribute`) or how
values are shown:

```python
from qdocs import ApiBuilder, Project, main


class Builder(ApiBuilder):
    def format_value(self, value) -> str:
        if isinstance(value, Unit):
            return f'<span class="class">Unit</span>({self.format_value(value.scale)})'
        return super().format_value(value)


main(PROJECT, Builder)
```

`format_value` returns the HTML of a value or of a part of a value, and is called for the items of containers and
the arguments of objects, too. Color the parts with the classes `string`, `bool`, `num`, `class` and `func`.

## Docstrings

reST fields, with a small markup for the description texts:

```python
def york_fit(x, y, sigma_x=None, ...):
    r"""
    A linear regression algorithm ... points $\vec{\mu}_i\in\mathbb{R}^2$ ...

    $$\vec{\mu} = \begin{pmatrix}x\\y\end{pmatrix}.$$

    The algorithm is described in
    [<a href="https://doi.org/10.1119/1.1632486">York et al., Am. J. Phys. 72, 367 (2004)</a>].
    See also [`linear_fit`].

    :param x: The $x$ data.
    :param sigma_x: The standard deviation $\sigma_x$ of the `x` data (unit of `x`).
    :returns: (popt, pcov) The best y-intercept and slope and their covariance matrix.
    :raises ValueError: If ...
    :raises (ValueError, TypeError): Several exceptions in one field.
    """
```

- `` `code` `` and raw HTML (e.g. links to papers) are passed through.
- `$inline$` and `$$block$$` math is rendered by MathJax. Block math always stands on its own line on the website.
- `` [`name`] `` links to a documented object: `fit`, `King.fit`, `qspec.models.fit`, `qspec.physics.doppler`,
  a module such as `qspec.analyze` or a type alias such as `scalar`. Unknown or ambiguous names stop the build.
- Blank lines separate paragraphs, lines starting with `- ` form a list.
- A leading `(name)` in `:returns:` labels the return value(s), otherwise it is shown as `out`.
- Types are taken from the annotations as written in the source.
- Methods without a docstring inherit the docstring of the overridden method.
- The signature and the parameters of a class are those of `__init__`, or of `__new__` if only that is overridden.
  A class that overrides neither has no signature.
- The description of a class is its docstring, followed by the description in the docstring of `__init__` or
  `__new__`. The fields can be in either docstring.
- Type aliases are described by a string on the line right below them (a string after a blank line is not taken):

  ```python
  type ExpMap = frozenset[tuple[str, int]]
  """An exponent map, a frozenset of (symbol, exponent) pairs."""
  ```

- Attributes are described by a string below their assignment or annotation in the class body, properties by their
  docstring:

  ```python
  class Unit:
      scale: float
      """The scale factor of the unit relative to the SI unit of its dimension."""
  ```

The generator warns about parameters that are missing in the docstring or the signature.

## Tutorial code

Mark a block in an example script and include it in a tutorial page:

```python
# examples/tutorial_2.py
# docs: hfs-0
import qspec as qs

...
# docs: end
```

```html
<!-- docs/tutorials/hfs.html -->
{% include code/hfs-0.html %}
```

A script may contain several regions. The generator fails on unclosed or duplicate regions and on includes without a
matching region.

## Developing the theme

```bash
pip install -e .
python -m qdocs css                          # _sass/qdocs/pycode.scss from the Pygments styles in qdocs/tutorials.py.
python -m qdocs preview ../qspec/docs        # Serve a site with this checkout instead of its remote_theme.
python -m qdocs preview ../qunits/docs build
```

`preview` copies the theme and the site into a temporary folder, rerun it after changes.

All colors are CSS custom properties in [`assets/css/style.scss`](assets/css/style.scss): the light values on `:root`,
the dark values in the `dark-colors` mixin. The code highlighting styles are `STYLE` and `STYLE_DARK` in
[`qdocs/tutorials.py`](qdocs/tutorials.py).

To release, run the workflow on main (Actions > Build and release > Run workflow) and choose the version bump. It
publishes the package to PyPI and creates the tag `vX.Y.Z` and a GitHub release. Then update `remote_theme` and
`requirements.txt` of the sites. The version of a checkout is derived from the latest tag with hatch-vcs.

The base styles and the Noto Sans fonts are from [jekyll-theme-minimal](https://github.com/pages-themes/minimal)
(CC0 1.0).

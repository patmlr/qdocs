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
remote_theme: patmlr/qdocs@v0.1.0   # Pin a tag, so theme changes do not reach the site unnoticed.
plugins:
  - jekyll-remote-theme
  - jekyll-seo-tag
```

The site provides `_data/navigation.yml` (top navigation), `_data/tutorials.yml` (tutorial list),
`_includes/badges.html` (optional) and its logos `assets/img/logo.svg`, `logo_dark.svg` and `logo_small.svg`.
Any theme file can be overridden by a file at the same path in the site. Extra styles go in `_sass/custom.scss`,
extra `<head>` tags in `_includes/head-custom.html`.

`docs/requirements.txt`:

```text
qdocs @ git+https://github.com/patmlr/qdocs@v0.1.0
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
    type_aliases="qtypes",             # Optional: link these type aliases in annotations to their module page.
)

if __name__ == "__main__":
    main(PROJECT)
```

```bash
python docs/_gen/build.py [api | tutorials | logo | all]
```

| Target      | Source                                    | Output                                           |
|-------------|-------------------------------------------|--------------------------------------------------|
| `api`       | docstrings and signatures of the package  | `doc/functions/**`, `_includes/api-nav.html`     |
| `tutorials` | `# docs: <name>` regions in `examples/`   | `_includes/code/<name>.html`                     |
| `logo`      | `assets/img/logo.svg`                     | `assets/img/logo_dark.svg`                       |

The module pages `doc/modules/<module>.html` and the overview `doc/doc.html` are written by hand with the `api`
layout, which adds the navigation. See `Project` in [`qdocs/project.py`](qdocs/project.py) for all options.

### Customizations

Classes listed in `Project.namespaces` are documented like a module of constants: no signature and no methods, but an
Attributes section with their public class attributes. Enums are documented this way automatically. Subclass
`ApiBuilder` to change which attributes are listed or how values are shown:

```python
from qdocs import ApiBuilder, Project, main


class Builder(ApiBuilder):
    def format_value(self, value) -> str:
        if isinstance(value, Unit):
            return f'<span class="default_value"><span class="class">Unit</span>(...)</span>'
        return super().format_value(value)


main(PROJECT, Builder)
```

`format_value` is used for default values in signatures and for attribute values. Color the parts of a value with
the classes `string`, `bool`, `num`, `class` and `func` inside a `default_value` span.

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
- `` [`name`] `` links to a documented object: `fit`, `King.fit`, `qspec.models.fit`, `qspec.physics.doppler`
  or a module such as `qspec.analyze`. Unknown or ambiguous names stop the build.
- Blank lines separate paragraphs, lines starting with `- ` form a list.
- A leading `(name)` in `:returns:` labels the return value(s), otherwise it is shown as `out`.
- Types are taken from the annotations as written in the source.
- Methods without a docstring inherit the docstring of the overridden method.

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
pip install -e . --config-settings editable_mode=compat
python -m qdocs css                          # _sass/qdocs/pycode.scss from the Pygments styles in qdocs/tutorials.py.
python -m qdocs preview ../qspec/docs        # Serve a site with this checkout instead of its remote_theme.
python -m qdocs preview ../qunits/docs build
```

`preview` copies the theme and the site into a temporary folder, rerun it after changes.

All colors are CSS custom properties in [`assets/css/style.scss`](assets/css/style.scss): the light values on `:root`,
the dark values in the `dark-colors` mixin. The code highlighting styles are `STYLE` and `STYLE_DARK` in
[`qdocs/tutorials.py`](qdocs/tutorials.py).

To release, tag the commit (`git tag v0.1.1 && git push --tags`) and update `remote_theme` and `requirements.txt` of
the sites.

The base styles and the Noto Sans fonts are from [jekyll-theme-minimal](https://github.com/pages-themes/minimal)
(CC0 1.0).

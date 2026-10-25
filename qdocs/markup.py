"""
Conversion of docstring prose to HTML. Supported markup:

- `code`
- [`name`] references to other documented objects
- $inline$ and $$block$$ LaTeX math (rendered by MathJax on the website)
- blank lines separate paragraphs, lines starting with '- ' form lists
- raw HTML, e.g. <a href="https://doi.org/...">...</a>, is passed through
"""

import html
import re
from collections.abc import Callable

BLOCK_MATH = re.compile(r"\$\$(.+?)\$\$", re.DOTALL)
INLINE_MATH = re.compile(r"(?<![\\$])\$(?!\$)(.+?)(?<![\\$])\$", re.DOTALL)
REF = re.compile(r"\[`([^`]+)`\]")
CODE = re.compile(r"`([^`]+)`")
PLACEHOLDER = re.compile(r"\x00(\d+)\x00")


def _escape(text: str) -> str:
    return html.escape(text, quote=False)


class Converter:
    def __init__(self, resolve: Callable[[str], str]) -> None:
        """
        :param resolve: Returns the site url of a referenced name. Must raise a `KeyError` for unknown names.
        """
        self.resolve = resolve

    def __call__(self, text: str) -> str:
        stash: list[tuple[str, str]] = []  # (kind, html)

        def put(kind: str, value: str) -> str:
            stash.append((kind, value))
            return f"\x00{len(stash) - 1}\x00"

        text = BLOCK_MATH.sub(lambda m: put("block", f"$${_escape(m.group(1))}$$"), text)
        text = INLINE_MATH.sub(lambda m: put("inline", f"${_escape(m.group(1))}$"), text)
        text = REF.sub(lambda m: put("inline", self._ref(m.group(1))), text)
        text = CODE.sub(lambda m: put("inline", f"<code>{_escape(m.group(1))}</code>"), text)

        out = []
        for block in re.split(r"\n\s*\n", text.strip()):
            out.extend(self._block(block, stash))
        ret = "\n".join(out)
        return PLACEHOLDER.sub(lambda m: stash[int(m.group(1))][1], ret)

    def _ref(self, name: str) -> str:
        url = self.resolve(name)
        return f"<a href=\"{{{{ '{url}' | relative_url }}}}\"><code>{_escape(name)}</code></a>"

    @staticmethod
    def _block(block: str, stash: list[tuple[str, str]]) -> list[str]:
        """Split a block into paragraphs, block math and lists."""
        out = []
        para: list[str] = []
        items: list[list[str]] = []

        def flush_para() -> None:
            if para:
                out.append("<p>" + "\n".join(para) + "</p>")
                para.clear()

        def flush_items() -> None:
            if items:
                out.append("<ul>" + "".join("<li>" + "\n".join(i) + "</li>" for i in items) + "</ul>")
                items.clear()

        for line in block.splitlines():
            stripped = line.strip()
            # Block math always stands on its own, even if written inside a sentence.
            parts = re.split(r"(\x00\d+\x00)", stripped)
            if any(stash[int(p[1:-1])][0] == "block" for p in parts if PLACEHOLDER.fullmatch(p)):
                flush_items()
                for p in parts:
                    if PLACEHOLDER.fullmatch(p) and stash[int(p[1:-1])][0] == "block":
                        flush_para()
                        out.append(f'<div class="math-block">{p}</div>')
                    elif p.strip():
                        para.append(p.strip())
                continue
            if stripped.startswith("- "):
                flush_para()
                items.append([stripped[2:]])
            elif items and line[:1].isspace():
                items[-1].append(stripped)
            else:
                flush_items()
                if stripped:
                    para.append(stripped)
        flush_para()
        flush_items()
        return out

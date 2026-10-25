
// Mark the current page in the API navigation and open the tree down to it.
function markCurrentNavEntry() {
  const nav = document.querySelector(".bd-content-table-content .extern");
  if (!nav) return;
  const link = [...nav.querySelectorAll("a:not(.inherited)")].find(a => a.pathname === location.pathname);
  if (!link) return;
  const li = link.parentElement;
  li.classList.add("table-current");
  const own = li.querySelector(":scope > details");
  if (own) own.open = true;
  for (let d = li.closest("details"); d; d = d.parentElement.closest("details")) d.open = true;
}

// Switch between light and dark mode. The choice is stored and applied before the first paint (see default.html).
function setupThemeToggle() {
  const button = document.querySelector(".theme-toggle");
  if (!button) return;
  button.addEventListener("click", () => {
    const root = document.documentElement;
    const dark = root.dataset.theme
      ? root.dataset.theme === "dark"
      : matchMedia("(prefers-color-scheme: dark)").matches;
    root.dataset.theme = dark ? "light" : "dark";
    try {
      localStorage.setItem("theme", root.dataset.theme);
    } catch (e) {}
  });
}

// Search the pages of the site from the top navigation. The index (assets/search.json) is loaded on first focus.
// A page matches if all words of the query occur in its title or text. Title matches rank first.
const SEARCH_MAX_RESULTS = 10;

function setupSearch() {
  const box = document.querySelector(".topnav-search");
  if (!box) return;
  const input = box.querySelector(".topnav-search-input");
  const list = box.querySelector(".topnav-search-results");
  let index = null;
  let active = -1;

  // The index holds the text of the pages with HTML entities, e.g. &nbsp;.
  const decoder = document.createElement("textarea");
  const decode = s => ((decoder.innerHTML = s), decoder.value.replace(/\s+/g, " "));

  const load = () => {
    index ??= fetch(box.dataset.index)
      .then(r => r.json())
      .then(pages => pages.map(p => {
        const title = decode(p.title), text = decode(p.text);
        return { url: p.url, title, text, titleLower: title.toLowerCase(), textLower: text.toLowerCase() };
      }))
      .catch(() => (index = null, []));
    return index;
  };

  const show = open => {
    list.hidden = !open;
    input.setAttribute("aria-expanded", open);
  };

  const select = i => {
    const items = list.querySelectorAll("a");
    if (!items.length) return;
    active = (i + items.length) % items.length;
    items.forEach((a, j) => a.classList.toggle("active", j === active));
    items[active].scrollIntoView({ block: "nearest" });
  };

  // The text around the first occurrence of the word in the text of a page.
  const snippet = (page, word) => {
    const at = page.textLower.indexOf(word);
    if (at < 0) return page.text.slice(0, 100);
    const start = Math.max(0, at - 40);
    return (start ? "…" : "") + page.text.slice(start, at + 60) + "…";
  };

  const search = async () => {
    const query = input.value;
    const words = query.toLowerCase().split(/\s+/).filter(Boolean);
    const pages = words.length ? await load() : [];
    if (input.value !== query) return;  // A newer search has run while the index loaded.
    list.replaceChildren();
    active = -1;
    if (!words.length) return show(false);
    const results = pages
      .filter(p => words.every(w => p.titleLower.includes(w) || p.textLower.includes(w)))
      .map(p => ({ p, score: words.filter(w => p.titleLower.includes(w)).length * 10 - p.title.length / 100 }))
      .sort((a, b) => b.score - a.score)
      .slice(0, SEARCH_MAX_RESULTS);
    if (!results.length) {
      const li = document.createElement("li");
      li.className = "topnav-search-empty";
      li.textContent = "No results";
      list.append(li);
    }
    for (const { p } of results) {
      const a = document.createElement("a");
      a.href = p.url;
      const title = document.createElement("strong");
      title.textContent = p.title;
      const text = document.createElement("span");
      text.textContent = snippet(p, words.find(w => !p.titleLower.includes(w)) ?? words[0]);
      a.append(title, text);
      const li = document.createElement("li");
      li.setAttribute("role", "option");
      li.append(a);
      list.append(li);
    }
    show(true);
  };

  input.addEventListener("focus", () => {
    load();
    if (list.childElementCount) show(true);
  });
  input.addEventListener("input", search);
  input.addEventListener("keydown", e => {
    if (e.key === "ArrowDown" || e.key === "ArrowUp") {
      e.preventDefault();
      select(active + (e.key === "ArrowDown" ? 1 : -1));
    } else if (e.key === "Enter") {
      const a = list.querySelectorAll("a")[Math.max(active, 0)];
      if (a) location.href = a.href;
    } else if (e.key === "Escape") {
      show(false);
      input.blur();
    }
  });
  document.addEventListener("click", e => {
    if (!box.contains(e.target)) show(false);
  });
}

function navContent() {
  return document.querySelector(".bd-content-table-content");
}

window.addEventListener("beforeunload", () => {
  const content = navContent();
  if (!content) return;
  try {
    localStorage.setItem("scrollPositon", content.scrollTop);
  } catch (e) {}
});

window.addEventListener("DOMContentLoaded", () => {
  setupThemeToggle();
  setupSearch();
  markCurrentNavEntry();
  const content = navContent();
  if (!content) return;
  try {
    content.scrollTop = localStorage.getItem("scrollPositon") || 0;
  } catch (e) {}
});

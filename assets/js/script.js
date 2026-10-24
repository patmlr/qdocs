
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
  markCurrentNavEntry();
  const content = navContent();
  if (!content) return;
  try {
    content.scrollTop = localStorage.getItem("scrollPositon") || 0;
  } catch (e) {}
});

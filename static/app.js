function spaced(code) {
  return code && code.length === 6 ? `${code.slice(0, 3)} ${code.slice(3)}` : code;
}

const themeMedia = window.matchMedia("(prefers-color-scheme: dark)");

function applyTheme(preference) {
  const dark = preference === "dark" || (preference === "system" && themeMedia.matches);
  document.documentElement.dataset.theme = dark ? "dark" : "light";
  document.documentElement.dataset.themePreference = preference;
  document.querySelectorAll("[data-theme-value]").forEach((button) => {
    button.classList.toggle("selected", button.dataset.themeValue === preference);
  });
  const label = document.querySelector("[data-theme-label]");
  const icon = document.querySelector("[data-theme-icon]");
  if (label) label.textContent = { light: "浅色", dark: "深色", system: "跟随系统" }[preference];
  if (icon) icon.textContent = { light: "☀", dark: "☾", system: "▣" }[preference];
}

const savedTheme = localStorage.getItem("theme") || "system";
applyTheme(savedTheme);
document.querySelectorAll("[data-theme-value]").forEach((button) => {
  button.addEventListener("click", () => {
    const preference = button.dataset.themeValue;
    localStorage.setItem("theme", preference);
    applyTheme(preference);
    button.closest("details").removeAttribute("open");
  });
});
themeMedia.addEventListener("change", () => {
  if ((localStorage.getItem("theme") || "system") === "system") applyTheme("system");
});

async function copyText(value, button) {
  await navigator.clipboard.writeText(value);
  const original = button.textContent;
  button.textContent = "已复制";
  setTimeout(() => { button.textContent = original; }, 1400);
}

document.querySelectorAll("[data-copy]").forEach((button) => {
  button.addEventListener("click", () => copyText(button.dataset.copy, button));
});

document.querySelectorAll("[data-confirm]").forEach((form) => {
  form.addEventListener("submit", (event) => {
    if (!window.confirm(form.dataset.confirm)) event.preventDefault();
  });
});

document.querySelectorAll("[data-open-dialog]").forEach((button) => {
  button.addEventListener("click", () => document.getElementById(button.dataset.openDialog).showModal());
});
document.querySelectorAll("[data-close-dialog]").forEach((button) => {
  button.addEventListener("click", () => button.closest("dialog").close());
});

const adminRows = document.querySelectorAll("[data-code-row]");
if (adminRows.length) {
  async function refreshAdminCodes() {
    try {
      const response = await fetch("/api/admin/codes", { cache: "no-store" });
      if (!response.ok) return;
      const codes = await response.json();
      codes.forEach((item) => {
        const row = document.querySelector(`[data-code-row="${item.id}"]`);
        if (!row) return;
        row.querySelector("[data-otp]").textContent = spaced(item.code);
        row.querySelector("[data-remaining]").textContent = item.remaining;
      });
    } catch (_) {}
  }
  refreshAdminCodes();
  setInterval(refreshAdminCodes, 1000);
}

const memberFilters = document.querySelector("[data-member-filters]");
if (memberFilters) {
  const search = memberFilters.querySelector("[data-member-search]");
  const category = memberFilters.querySelector("[data-category-filter]");
  const status = memberFilters.querySelector("[data-status-filter]");
  const visibleCount = memberFilters.querySelector("[data-visible-count]");
  const rows = [...document.querySelectorAll("[data-member-row]")];
  const emptyRow = document.querySelector("[data-filter-empty]");

  function applyMemberFilters() {
    const query = search.value.trim().toLowerCase();
    let visible = 0;
    rows.forEach((row) => {
      const haystack = `${row.dataset.name} ${row.dataset.code} ${row.dataset.account}`;
      const matchesSearch = !query || haystack.includes(query);
      const matchesCategory = !category.value || row.dataset.category === category.value;
      const matchesStatus = !status.value || row.dataset.status === status.value;
      const show = matchesSearch && matchesCategory && matchesStatus;
      row.hidden = !show;
      if (show) visible += 1;
    });
    visibleCount.textContent = visible;
    if (emptyRow) emptyRow.hidden = visible !== 0;
  }

  search.addEventListener("input", applyMemberFilters);
  category.addEventListener("change", applyMemberFilters);
  status.addEventListener("change", applyMemberFilters);
}

const sharePage = document.querySelector("[data-share-token]");
if (sharePage) {
  let rawCode = "";
  const token = sharePage.dataset.shareToken;
  const codeElement = sharePage.querySelector("[data-share-otp]");
  const remainingElement = sharePage.querySelector("[data-share-remaining]");
  const ring = sharePage.querySelector(".share-countdown");
  const copyButton = sharePage.querySelector("[data-copy-code]");

  async function refreshShareCode() {
    try {
      const response = await fetch(`/api/s/${encodeURIComponent(token)}/code`, { cache: "no-store" });
      if (!response.ok) return;
      const item = await response.json();
      rawCode = item.code;
      codeElement.textContent = spaced(item.code);
      remainingElement.textContent = item.remaining;
      ring.style.setProperty("--progress", `${item.remaining * 12}deg`);
    } catch (_) {}
  }
  copyButton.addEventListener("click", () => rawCode && copyText(rawCode, copyButton));
  refreshShareCode();
  setInterval(refreshShareCode, 1000);
}

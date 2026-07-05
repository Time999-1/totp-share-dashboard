function spaced(code) {
  return code && code.length === 6 ? `${code.slice(0, 3)} ${code.slice(3)}` : code;
}

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


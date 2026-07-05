(() => {
  const saved = localStorage.getItem("theme") || "system";
  const dark = saved === "dark" || (
    saved === "system" && window.matchMedia("(prefers-color-scheme: dark)").matches
  );
  document.documentElement.dataset.theme = dark ? "dark" : "light";
  document.documentElement.dataset.themePreference = saved;
})();

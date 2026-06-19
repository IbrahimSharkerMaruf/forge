(function () {
  const saved = localStorage.getItem('forge_theme');
  if (saved === 'light') document.documentElement.setAttribute('data-theme', 'light');
})();

function initThemeToggle(buttonId) {
  const btn = document.getElementById(buttonId);
  if (!btn) return;
  btn.addEventListener('click', () => {
    const isLight = document.documentElement.getAttribute('data-theme') === 'light';
    if (isLight) {
      document.documentElement.removeAttribute('data-theme');
      localStorage.setItem('forge_theme', 'dark');
    } else {
      document.documentElement.setAttribute('data-theme', 'light');
      localStorage.setItem('forge_theme', 'light');
    }
  });
}

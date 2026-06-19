function initialsFor(name) {
  const parts = name.trim().split(/\s+/);
  return parts.length > 1
    ? (parts[0][0] + parts[1][0]).toUpperCase()
    : name.slice(0, 2).toUpperCase();
}

function accountMenuHTML() {
  return `
    <button class="avatar-btn" id="avatar-btn" type="button" aria-label="Open account menu">
      <span id="avatar-initials">—</span>
    </button>
    <div class="avatar-menu" id="avatar-menu">
      <a href="dashboard.html" class="menu-item">Profile dashboard</a>
      <button class="menu-item" id="menu-theme-btn" type="button">
        <span>Theme</span>
        <span class="menu-theme-icons">
          <svg class="icon-sun" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6"><circle cx="12" cy="12" r="4"/><path d="M12 2v2M12 20v2M4.93 4.93l1.41 1.41M17.66 17.66l1.41 1.41M2 12h2M20 12h2M4.93 19.07l1.41-1.41M17.66 6.34l1.41-1.41"/></svg>
          <svg class="icon-moon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6"><path d="M21 12.79A9 9 0 1111.21 3 7 7 0 0021 12.79z"/></svg>
        </span>
      </button>
      <button class="menu-item menu-item-danger" id="menu-logout-btn" type="button">Log out</button>
    </div>
  `;
}

// Injects the avatar + dropdown into #avatar-wrap when logged in, hiding
// whatever logged-out-only nav controls (login links, signup CTA) exist.
// No-ops (leaving logged-out controls visible) when there's no valid session.
async function setupAccountMenu() {
  const avatarWrap = document.getElementById('avatar-wrap');
  if (!avatarWrap || !getToken()) return;

  let user;
  try {
    user = await apiFetch('/auth/me');
  } catch {
    clearToken();
    return;
  }

  avatarWrap.innerHTML = accountMenuHTML();
  avatarWrap.style.display = '';
  document.getElementById('avatar-initials').textContent = initialsFor(user.name);
  document.querySelectorAll('.logged-out-only').forEach((el) => (el.style.display = 'none'));

  const avatarMenu = document.getElementById('avatar-menu');
  document.getElementById('avatar-btn').addEventListener('click', (e) => {
    e.stopPropagation();
    avatarMenu.classList.toggle('open');
  });
  document.addEventListener('click', (e) => {
    if (!avatarWrap.contains(e.target)) avatarMenu.classList.remove('open');
  });
  initThemeToggle('menu-theme-btn');
  document.getElementById('menu-theme-btn').addEventListener('click', () => {
    avatarMenu.classList.remove('open');
  });
  document.getElementById('menu-logout-btn').addEventListener('click', () => {
    clearToken();
    window.location.href = 'login.html';
  });
}

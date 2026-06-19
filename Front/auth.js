const API_BASE = '';

if (window.location.protocol === 'file:') {
  document.addEventListener('DOMContentLoaded', () => {
    const banner = document.createElement('div');
    banner.textContent =
      'This page was opened as a local file, so login/signup will fail. Start the server (uvicorn api:app --port 8000) and open it at http://localhost:8000/' +
      window.location.pathname.split('/').pop();
    banner.style.cssText =
      'position:fixed;top:0;left:0;right:0;z-index:9999;background:#FF7A3D;color:#0E0F12;' +
      'font-family:sans-serif;font-size:14px;font-weight:600;text-align:center;padding:10px;';
    document.body.prepend(banner);
  });
}

function saveToken(token) {
  localStorage.setItem('forge_token', token);
}

function getToken() {
  return localStorage.getItem('forge_token');
}

function clearToken() {
  localStorage.removeItem('forge_token');
}

async function apiFetch(path, options = {}) {
  const token = getToken();
  const headers = { 'Content-Type': 'application/json', ...(options.headers || {}) };
  if (token) headers.Authorization = `Bearer ${token}`;

  const res = await fetch(`${API_BASE}${path}`, { ...options, headers });
  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    throw new Error(body.detail || `Request failed (${res.status})`);
  }
  if (res.status === 204) return null;
  return res.json();
}

async function requireLogin() {
  if (!getToken()) {
    window.location.href = 'login.html';
    return null;
  }
  try {
    return await apiFetch('/auth/me');
  } catch {
    clearToken();
    window.location.href = 'login.html';
    return null;
  }
}

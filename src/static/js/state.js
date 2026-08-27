// ==========================================
// Локальное состояние интерфейса
// ==========================================

export function readPreference(key, fallback = null) {
  try {
    return window.localStorage.getItem(key) ?? fallback;
  } catch {
    return fallback;
  }
}

export function writePreference(key, value) {
  try {
    window.localStorage.setItem(key, value);
  } catch {
    // Локальные настройки не должны ломать страницу.
  }
}

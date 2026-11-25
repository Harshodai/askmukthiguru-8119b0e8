// Apply the saved theme before first paint so the page never flashes the wrong one.
// Loaded as an external 'self' script to comply with strict CSP (no 'unsafe-inline').
(function () {
  try {
    var pref = (JSON.parse(localStorage.getItem('askmukthiguru_profile') || '{}') || {}).theme || 'system';
    var dark = pref === 'dark' || (pref === 'system' && window.matchMedia('(prefers-color-scheme: dark)').matches);
    document.documentElement.classList.toggle('dark', dark);
    document.documentElement.style.colorScheme = dark ? 'dark' : 'light';
  } catch (e) { /* storage unavailable: keep the default */ }
})();

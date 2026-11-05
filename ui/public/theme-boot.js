// Runs before the first paint (a blocking script in index.html), so a dark choice never
// flashes a light page. Keep in step with src/lib/theme.ts (theme.test.ts runs this file).
;(function () {
  var choice = null
  try {
    choice = window.localStorage.getItem('ayo.theme')
  } catch {
    // Blocked storage: follow the system.
  }
  var dark =
    choice === 'dark' ||
    (choice !== 'light' && window.matchMedia('(prefers-color-scheme: dark)').matches)
  document.documentElement.classList.toggle('dark', dark)
})()

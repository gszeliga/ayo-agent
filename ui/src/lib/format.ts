const MINUTE = 60
const HOUR = 60 * MINUTE
const DAY = 24 * HOUR

const DATE = new Intl.DateTimeFormat('en-GB', {
  day: 'numeric',
  month: 'short',
  year: 'numeric',
  timeZone: 'UTC',
})

/** "just now", "5 min ago", "3 h ago", "2 d ago", then a date ("5 Oct 2026") after 30 days. */
export function relativeTime(iso: string, now: number = Date.now()): string {
  const seconds = Math.floor((now - Date.parse(iso)) / 1000)
  if (seconds < MINUTE) return 'just now' // also a timestamp slightly ahead of this clock
  if (seconds < HOUR) return `${String(Math.floor(seconds / MINUTE))} min ago`
  if (seconds < DAY) return `${String(Math.floor(seconds / HOUR))} h ago`
  if (seconds < 30 * DAY) return `${String(Math.floor(seconds / DAY))} d ago`
  return DATE.format(new Date(iso))
}

/** The exact time, for a tooltip: "2026-11-05 10:14 UTC". */
export function formatUtc(iso: string): string {
  const date = new Date(iso)
  return `${date.toISOString().slice(0, 16).replace('T', ' ')} UTC`
}

/** 1024-based, one decimal: "512 B", "4.2 KB", "1.5 MB". */
export function formatBytes(bytes: number): string {
  if (bytes < 1024) return `${String(bytes)} B`
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`
}

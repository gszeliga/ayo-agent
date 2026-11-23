/** A resizable column's widths in pixels, and the most of its row it may take. */
export interface PanelLimits {
  min: number
  default: number
  max: number
  /** Of the row's width, so the chat keeps room. */
  share: number
}

export const INSPECTOR_LIMITS: PanelLimits = { min: 320, default: 448, max: 800, share: 0.6 }
export const CASES_LIMITS: PanelLimits = { min: 240, default: 320, max: 560, share: 0.4 }

export const INSPECTOR_WIDTH_KEY = 'ayo.chat.inspector-width'
export const CASES_WIDTH_KEY = 'ayo.chat.cases-width'

/**
 * `width` kept between the limits: the fixed ones and, when the row's width is known
 * (`rowWidth > 0`), its share of the row.
 */
export function clampWidth(width: number, limits: PanelLimits, rowWidth = 0): number {
  const share = rowWidth > 0 ? Math.floor(rowWidth * limits.share) : limits.max
  const max = Math.max(limits.min, Math.min(limits.max, share))
  return Math.round(Math.min(max, Math.max(limits.min, width)))
}

/**
 * A column's width as last left: a number of pixels, never content. A per-browser
 * convenience: unreadable or out of range, it is the default.
 */
export function loadWidth(key: string, limits: PanelLimits): number {
  try {
    const stored = window.localStorage.getItem(key)
    const width = stored !== null && /^\d{3,4}$/.test(stored) ? Number(stored) : NaN
    return width >= limits.min && width <= limits.max ? width : limits.default
  } catch {
    return limits.default
  }
}

export function saveWidth(key: string, width: number): void {
  try {
    window.localStorage.setItem(key, String(width))
  } catch {
    // The default next time.
  }
}

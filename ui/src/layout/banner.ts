const KEY = 'ayo.internal-banner-dismissed'

/** A per-browser convenience: losing it only shows the banner again. */
export function isBannerDismissed(): boolean {
  try {
    return window.localStorage.getItem(KEY) === '1'
  } catch {
    return false
  }
}

export function dismissBanner(): void {
  try {
    window.localStorage.setItem(KEY, '1')
  } catch {
    // Shown again next time.
  }
}

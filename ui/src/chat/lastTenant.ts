const KEY = 'ayo.chat.last-tenant'

/**
 * The tenant of the last new conversation: a name, never content. With the column widths
 * (`panelWidth.ts`), all the test chat keeps in browser storage. A per-browser convenience: losing it only clears the
 * preselection.
 */
export function loadLastTenant(): string | null {
  try {
    return window.localStorage.getItem(KEY)
  } catch {
    return null
  }
}

export function saveLastTenant(tenant: string): void {
  try {
    window.localStorage.setItem(KEY, tenant)
  } catch {
    // Not preselected next time.
  }
}

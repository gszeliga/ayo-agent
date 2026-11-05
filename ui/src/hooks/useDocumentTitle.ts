import { useEffect } from 'react'

const APP = 'AYO Admin'

/** "‹title› · AYO Admin" in the browser tab while the page is shown; null keeps the app name. */
export function useDocumentTitle(title: string | null): void {
  useEffect(() => {
    document.title = title ? `${title} · ${APP}` : APP
  }, [title])
}

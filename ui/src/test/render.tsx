import { QueryClientProvider } from '@tanstack/react-query'
import { render } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import type { ReactNode } from 'react'
import { MemoryRouter, useLocation, useNavigate } from 'react-router'

import { createQueryClient } from '@/api/queryClient'
import { Toaster } from '@/components/ui/sonner'
import { TooltipProvider } from '@/components/ui/tooltip'
import { ConnectionProvider } from '@/connection/ConnectionProvider'
import { i18n } from '@/i18n'
import { LanguageProvider } from '@/layout/LanguageProvider'
import { ThemeProvider } from '@/layout/ThemeProvider'
import { saveConnection, type Connection } from '@/connection/storage'
import { saveLanguageChoice, type Language } from '@/lib/language'
import { AppRoutes } from '@/routes'

export const API = 'http://api.test'
export const KEY = 'test-admin-key'
export const CONNECTION: Connection = { baseUrl: API, apiKey: KEY }

/** Where the router is now (`data-testid="location"`), and the browser's Back button. */
function LocationProbe() {
  const location = useLocation()
  const navigate = useNavigate()
  return (
    <>
      <output data-testid="location">{location.pathname + location.search}</output>
      <button
        type="button"
        data-testid="back"
        aria-label="Back (test)"
        onClick={() => {
          void navigate(-1)
        }}
      />
    </>
  )
}

/**
 * The app's routes at `path`, optionally already connected. `language` starts it in that
 * language, as a stored choice would (English otherwise: the browser's in jsdom).
 */
export function renderApp(
  path: string,
  {
    connected = false,
    routes,
    language,
  }: { connected?: boolean; routes?: ReactNode; language?: Language } = {},
) {
  if (connected) saveConnection(CONNECTION)
  if (language) {
    saveLanguageChoice(language)
    void i18n.changeLanguage(language)
  }
  const user = userEvent.setup()
  const queryClient = createQueryClient({ retryDelay: 0 })
  const result = render(
    <MemoryRouter initialEntries={[path]}>
      <ThemeProvider>
        <LanguageProvider>
          <QueryClientProvider client={queryClient}>
            <TooltipProvider>
              <ConnectionProvider>
                {routes ?? <AppRoutes />}
                <LocationProbe />
              </ConnectionProvider>
              <Toaster />
            </TooltipProvider>
          </QueryClientProvider>
        </LanguageProvider>
      </ThemeProvider>
    </MemoryRouter>,
  )
  return { user, queryClient, ...result }
}

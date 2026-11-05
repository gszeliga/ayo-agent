import { render } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import type { ReactNode } from 'react'
import { MemoryRouter, useLocation } from 'react-router'

import { ConnectionProvider } from '@/connection/ConnectionProvider'
import { saveConnection, type Connection } from '@/connection/storage'
import { AppRoutes } from '@/routes'

export const API = 'http://api.test'
export const KEY = 'test-admin-key'
export const CONNECTION: Connection = { baseUrl: API, apiKey: KEY }

/** Where the router is now, for assertions (`data-testid="location"`). */
function LocationProbe() {
  const location = useLocation()
  return <output data-testid="location">{location.pathname + location.search}</output>
}

/** The app's routes at `path`, optionally already connected. */
export function renderApp(
  path: string,
  { connected = false, routes }: { connected?: boolean; routes?: ReactNode } = {},
) {
  if (connected) saveConnection(CONNECTION)
  const user = userEvent.setup()
  const result = render(
    <MemoryRouter initialEntries={[path]}>
      <ConnectionProvider>
        {routes ?? <AppRoutes />}
        <LocationProbe />
      </ConnectionProvider>
    </MemoryRouter>,
  )
  return { user, ...result }
}

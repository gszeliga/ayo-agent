import { BrowserRouter } from 'react-router'

import { ConnectionProvider } from '@/connection/ConnectionProvider'
import { AppRoutes } from '@/routes'

export function App() {
  return (
    <BrowserRouter>
      <ConnectionProvider>
        <AppRoutes />
      </ConnectionProvider>
    </BrowserRouter>
  )
}

import { QueryClientProvider, type QueryClient } from '@tanstack/react-query'
import { useState } from 'react'
import { BrowserRouter } from 'react-router'

import { createQueryClient } from '@/api/queryClient'
import { TooltipProvider } from '@/components/ui/tooltip'
import { ConnectionProvider } from '@/connection/ConnectionProvider'
import { AppRoutes } from '@/routes'

export function App() {
  const [queryClient] = useState<QueryClient>(() => createQueryClient())
  return (
    <BrowserRouter>
      <QueryClientProvider client={queryClient}>
        <TooltipProvider delayDuration={300}>
          <ConnectionProvider>
            <AppRoutes />
          </ConnectionProvider>
        </TooltipProvider>
      </QueryClientProvider>
    </BrowserRouter>
  )
}

import { QueryClient } from '@tanstack/react-query'

import { ApiError } from './errors'

/**
 * Answers with a status are definite (a 4xx won't change, a 5xx is the API's to fix), so
 * only a network failure is retried, once. Data counts as fresh for 30 s; the window
 * regaining focus refetches stale data, so changes made elsewhere show up.
 */
export function createQueryClient({ retryDelay }: { retryDelay?: number } = {}): QueryClient {
  return new QueryClient({
    defaultOptions: {
      queries: {
        staleTime: 30_000,
        refetchOnWindowFocus: true,
        retry: (failureCount, error) =>
          error instanceof ApiError && error.isNetworkError && failureCount < 1,
        ...(retryDelay === undefined ? {} : { retryDelay }),
      },
    },
  })
}

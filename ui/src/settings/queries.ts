import { useQuery } from '@tanstack/react-query'

import { unwrap } from '@/api/client'
import { useApiClient } from '@/connection/context'

const SETTINGS_KEY = ['settings'] as const

function useSettingsQueryOptions() {
  const client = useApiClient()
  return {
    queryKey: SETTINGS_KEY,
    queryFn: ({ signal }: { signal: AbortSignal }) =>
      unwrap(client.GET('/admin/settings', { signal })),
  }
}

/** The current indexing settings and document counts (`GET /admin/settings`). */
export function useIndexingSettings() {
  return useQuery(useSettingsQueryOptions())
}

/**
 * The copilot's models, from the same response and cache. They change only with an API
 * restart, so this reader never refetches cached data (`staleTime` is per reader: the
 * Settings page still refreshes its document counts as usual).
 */
export function useCopilotSettings() {
  return useQuery({
    ...useSettingsQueryOptions(),
    staleTime: Infinity,
    select: (settings) => settings.copilot,
  })
}

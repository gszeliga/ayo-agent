import { useQuery } from '@tanstack/react-query'

import { unwrap } from '@/api/client'
import { useApiClient } from '@/connection/context'
import { Q_MAX_LENGTH, TENANT_PATTERN } from '@/documents/listParams'
import { useDebouncedValue } from '@/hooks/useDebouncedValue'

export const EXISTING_CHECK_DELAY_MS = 400

/**
 * The stored document an upload would replace: same tenant and same `source_key`. The API
 * replaces it silently, so the dialog warns. `q` matches substrings of the title or the
 * source key; only an exact `source_key` counts.
 */
export function useExistingDocument(tenant: string, sourceKey: string, enabled: boolean) {
  const client = useApiClient()
  const target = useDebouncedValue({ tenant, sourceKey }, EXISTING_CHECK_DELAY_MS)
  const checkable =
    enabled &&
    TENANT_PATTERN.test(target.tenant) &&
    target.sourceKey !== '' &&
    target.sourceKey.length <= Q_MAX_LENGTH
  const query = useQuery({
    queryKey: ['existing-document', target.tenant, target.sourceKey],
    queryFn: ({ signal }) =>
      unwrap(
        client.GET('/admin/documents', {
          params: { query: { tenant: target.tenant, q: target.sourceKey, limit: 100 } },
          signal,
        }),
      ),
    enabled: checkable,
    staleTime: 0,
  })
  const current = target.tenant === tenant && target.sourceKey === sourceKey
  if (!checkable || !current) return null
  return query.data?.items.find((doc) => doc.source_key === target.sourceKey) ?? null
}

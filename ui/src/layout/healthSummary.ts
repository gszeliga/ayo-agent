import type { components } from '@/api/schema'

type ServiceHealth = components['schemas']['ServiceHealth']

/** What the header's pill says: one word for the whole service (decision 2, nav-progress). */
export type HealthSummary =
  'ok' | 'databaseDown' | 'embeddingsDown' | 'bothDown' | 'checking' | 'unknown'

export function summarizeHealth(
  health: ServiceHealth | undefined,
  isPending: boolean,
): HealthSummary {
  if (health === undefined) return isPending ? 'checking' : 'unknown'
  const databaseDown = health.database.status === 'down'
  const embeddingsDown = health.embeddings.status === 'down'
  if (databaseDown && embeddingsDown) return 'bothDown'
  if (databaseDown) return 'databaseDown'
  if (embeddingsDown) return 'embeddingsDown'
  return 'ok'
}

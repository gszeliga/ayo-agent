import { RefreshCw } from 'lucide-react'
import type { ReactNode } from 'react'

import { describeError } from '@/api/errors'
import type { components } from '@/api/schema'
import { Button } from '@/components/ui/button'
import { useConnection } from '@/connection/context'
import { formatUtc, relativeTime } from '@/lib/format'
import { cn } from '@/lib/utils'

import { useServiceHealth } from './healthQuery'

type ServiceState = components['schemas']['DatabaseHealth']['status'] | 'unknown'

export function StatusDot({ state }: { state: ServiceState }) {
  return (
    <span
      aria-hidden="true"
      className={cn(
        'inline-block size-2 flex-none rounded-full',
        state === 'up' && 'bg-success',
        state === 'down' && 'bg-destructive',
        state === 'unknown' && 'bg-muted-foreground/50',
      )}
    />
  )
}

const STATE_TEXT: Record<ServiceState, string> = { up: 'Up', down: 'Down', unknown: 'Unknown' }

function When({ iso, now }: { iso: string | null; now: number }) {
  if (iso === null) return <span className="text-muted-foreground">none since the API started</span>
  return (
    <time dateTime={iso} title={formatUtc(iso)}>
      {relativeTime(iso, now)}
    </time>
  )
}

function Row({ label, children }: { label: string; children: ReactNode }) {
  return (
    <>
      <dt className="text-muted-foreground">{label}</dt>
      <dd className="min-w-0 break-words">{children}</dd>
    </>
  )
}

/** Database and embeddings in full, with Check now: the popover and the Services card. */
export function ServiceDetails() {
  const health = useServiceHealth()
  const { connection } = useConnection()
  const data = health.data
  const now = health.dataUpdatedAt

  if (!data) {
    return (
      <div className="space-y-3 text-[13px]">
        <p className="text-muted-foreground">
          {health.isError
            ? `Status unknown: ${describeError(health.error, connection?.baseUrl ?? '')}`
            : 'Checking…'}
        </p>
        <CheckNow onCheck={health.checkNow} checking={health.checking} />
      </div>
    )
  }
  const { database, embeddings } = data
  return (
    <div className="space-y-4 text-[13px]">
      <section aria-label="Database service" className="space-y-1.5">
        <h3 className="flex items-center gap-2 font-semibold">
          <StatusDot state={database.status} /> Database: {STATE_TEXT[database.status]}
        </h3>
        <dl className="grid grid-cols-[auto_1fr] gap-x-4 gap-y-1">
          <Row label="Latency">{database.latency_ms} ms</Row>
          {database.error && <Row label="Error">{database.error}</Row>}
        </dl>
      </section>
      <section aria-label="Embeddings service" className="space-y-1.5">
        <h3 className="flex items-center gap-2 font-semibold">
          <StatusDot state={embeddings.status} /> Embeddings: {STATE_TEXT[embeddings.status]}
        </h3>
        <dl className="grid grid-cols-[auto_1fr] gap-x-4 gap-y-1">
          <Row label="Provider">{embeddings.provider}</Row>
          <Row label="Checked">
            <When iso={embeddings.checked_at} now={now} />
            {embeddings.cached && <span className="text-muted-foreground"> (cached)</span>},{' '}
            {embeddings.latency_ms} ms
          </Row>
          {embeddings.error && <Row label="Error">{embeddings.error}</Row>}
          <Row label="Last success">
            <When iso={embeddings.last_success_at} now={now} />
          </Row>
          <Row label="Last error">
            <When iso={embeddings.last_error_at} now={now} />
            {embeddings.last_error && <span>: {embeddings.last_error}</span>}
          </Row>
        </dl>
      </section>
      <CheckNow onCheck={health.checkNow} checking={health.checking} />
    </div>
  )
}

function CheckNow({ onCheck, checking }: { onCheck: () => Promise<unknown>; checking: boolean }) {
  return (
    <Button
      variant="outline"
      size="sm"
      disabled={checking}
      onClick={() => {
        // Errors show through the query's state.
        onCheck().catch(() => undefined)
      }}
    >
      <RefreshCw aria-hidden="true" className={checking ? 'animate-spin' : undefined} />
      {checking ? 'Checking…' : 'Check now'}
    </Button>
  )
}

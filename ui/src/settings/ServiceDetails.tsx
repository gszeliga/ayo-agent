import { RefreshCw } from 'lucide-react'
import type { ReactNode } from 'react'
import { useTranslation } from 'react-i18next'

import { describeError } from '@/api/errors'
import type { components } from '@/api/schema'
import { Button } from '@/components/ui/button'
import { useConnection } from '@/connection/context'
import { useLanguage } from '@/layout/languageContext'
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

function When({ iso, now }: { iso: string | null; now: number }) {
  const { t } = useTranslation('settings')
  const { language } = useLanguage()
  if (iso === null) return <span className="text-muted-foreground">{t('service.none')}</span>
  return (
    <time dateTime={iso} title={formatUtc(iso)}>
      {relativeTime(iso, language, now)}
    </time>
  )
}

/** "PostgreSQL 18.1 · pgvector 0.8.7": product names, the same in every language. */
function databaseVersions(postgres: string, pgvector: string | null): string {
  return pgvector ? `PostgreSQL ${postgres} · pgvector ${pgvector}` : `PostgreSQL ${postgres}`
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
  const { t } = useTranslation('settings')
  const { language } = useLanguage()
  const health = useServiceHealth()
  const { connection } = useConnection()
  const data = health.data
  const now = health.dataUpdatedAt

  if (!data) {
    return (
      <div className="space-y-3 text-[13px]">
        <p className="text-muted-foreground">
          {health.isError
            ? t('service.unknown', {
                error: describeError(health.error, connection?.baseUrl ?? '', language),
              })
            : t('service.checking')}
        </p>
        <CheckNow onCheck={health.checkNow} checking={health.checking} />
      </div>
    )
  }
  const { database, embeddings } = data
  return (
    <div className="space-y-4 text-[13px]">
      <section aria-label={t('service.databaseLabel')} className="space-y-1.5">
        <h3 className="flex items-center gap-2 font-semibold">
          <StatusDot state={database.status} />{' '}
          {t('service.database', { state: t(`service.state.${database.status}`) })}
        </h3>
        <dl className="grid grid-cols-[auto_1fr] gap-x-4 gap-y-1">
          <Row label={t('service.runsOn')}>{t(`service.location.${database.location}`)}</Row>
          {database.postgres_version && (
            <Row label={t('service.version')}>
              {databaseVersions(database.postgres_version, database.pgvector_version)}
            </Row>
          )}
          <Row label={t('service.latency')}>{t('service.ms', { n: database.latency_ms })}</Row>
          {database.error && <Row label={t('service.error')}>{database.error}</Row>}
        </dl>
      </section>
      <section aria-label={t('service.embeddingsLabel')} className="space-y-1.5">
        <h3 className="flex items-center gap-2 font-semibold">
          <StatusDot state={embeddings.status} />{' '}
          {t('service.embeddings', { state: t(`service.state.${embeddings.status}`) })}
        </h3>
        <dl className="grid grid-cols-[auto_1fr] gap-x-4 gap-y-1">
          <Row label={t('service.provider')}>{embeddings.provider}</Row>
          <Row label={t('service.checked')}>
            <When iso={embeddings.checked_at} now={now} />
            {embeddings.cached && (
              <span className="text-muted-foreground"> {t('service.cached')}</span>
            )}
            , {t('service.ms', { n: embeddings.latency_ms })}
          </Row>
          {embeddings.error && <Row label={t('service.error')}>{embeddings.error}</Row>}
          <Row label={t('service.lastSuccess')}>
            <When iso={embeddings.last_success_at} now={now} />
          </Row>
          <Row label={t('service.lastError')}>
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
  const { t } = useTranslation('settings')
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
      {checking ? t('service.checking') : t('service.checkNow')}
    </Button>
  )
}

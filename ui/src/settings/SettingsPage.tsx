import type { ReactNode } from 'react'
import { Trans, useTranslation } from 'react-i18next'
import { Link } from 'react-router'

import type { components } from '@/api/schema'
import { CopyButton } from '@/components/CopyButton'
import { LoadError } from '@/components/LoadError'
import { Alert, AlertDescription } from '@/components/ui/alert'
import { Skeleton } from '@/components/ui/skeleton'
import { DEFAULT_PARAMS, toSearchParams } from '@/documents/listParams'
import { OUTDATED_REASONS, outdatedReasonLabel } from '@/documents/status'
import { useDocumentTitle } from '@/hooks/useDocumentTitle'
import { useLanguage } from '@/layout/languageContext'
import { formatBytes } from '@/lib/format'
import { cn } from '@/lib/utils'
import { ROUTES } from '@/paths'

import { useIndexingSettings } from './queries'
import { ServiceDetails } from './ServiceDetails'

type IndexingSettings = components['schemas']['IndexingSettings']

function Card({ title, children }: { title: string; children: ReactNode }) {
  return (
    <section aria-label={title} className="bg-card space-y-4 rounded-xl border p-5">
      <h2 className="font-semibold">{title}</h2>
      {children}
    </section>
  )
}

/** A setting, with the environment variable that sets it. */
function Setting({
  label,
  env,
  children,
  className,
}: {
  label: string
  env?: string
  children: ReactNode
  className?: string
}) {
  return (
    <div
      className={cn('flex flex-wrap items-baseline justify-between gap-x-4 gap-y-0.5', className)}
    >
      <dt>
        {label}
        {env && <code className="text-muted-foreground ml-2 font-mono text-[12px]">{env}</code>}
      </dt>
      <dd className="font-medium tabular-nums">{children}</dd>
    </div>
  )
}

function Config({ label, copy, value }: { label: string; copy: string; value: string }) {
  return (
    <div className="space-y-1">
      <div className="text-muted-foreground text-xs font-medium">{label}</div>
      <div className="bg-secondary flex items-center gap-1 rounded-md py-1 pr-1 pl-2.5">
        <code className="min-w-0 flex-1 font-mono text-[12px] break-all">{value}</code>
        <CopyButton value={value} label={copy} />
      </div>
    </div>
  )
}

// Every tenant's outdated documents, in the list's default order.
const outdatedSearch = toSearchParams({ ...DEFAULT_PARAMS, status: 'outdated' })
const OUTDATED_DOCUMENTS = `${ROUTES.documents}?${outdatedSearch.toString()}`

function DocumentsCard({ counts }: { counts: IndexingSettings['documents'] }) {
  const { t } = useTranslation('settings')
  const { language } = useLanguage()
  const { total, indexed, outdated } = counts
  const reasons = OUTDATED_REASONS.map((reason) => ({ reason, count: outdated[reason] }))
  const outdatedTotal = reasons.reduce((sum, r) => sum + r.count, 0)
  const share = (n: number) => (total === 0 ? 0 : (n / total) * 100)
  return (
    <Card title={t('card.documents')}>
      <p>
        <span className="text-2xl font-semibold tabular-nums">{total}</span>{' '}
        <span className="text-muted-foreground">{t('documents.stored')}</span>
      </p>
      {total > 0 && (
        <div aria-hidden="true" className="bg-warning-muted flex h-2 overflow-hidden rounded-full">
          <div className="bg-success" style={{ width: `${String(share(indexed))}%` }} />
          <div className="bg-warning" style={{ width: `${String(share(outdatedTotal))}%` }} />
        </div>
      )}
      <dl className="space-y-1.5">
        <Setting label={t('documents.indexed')}>{indexed}</Setting>
        <Setting label={t('documents.outdated')}>{outdatedTotal}</Setting>
        {reasons.map(({ reason, count }) => (
          <Setting
            key={reason}
            label={outdatedReasonLabel(reason, language)}
            className="text-muted-foreground pl-4 text-[13px]"
          >
            {count}
          </Setting>
        ))}
      </dl>
      {outdatedTotal > 0 && (
        <p className="text-muted-foreground text-[13px]">
          {t('documents.note', { count: outdatedTotal })}{' '}
          <Link
            to={OUTDATED_DOCUMENTS}
            className="text-foreground font-medium underline-offset-4 hover:underline"
          >
            {t('documents.showOutdated')}
          </Link>
        </p>
      )}
    </Card>
  )
}

function CopilotCard({ copilot }: { copilot: IndexingSettings['copilot'] }) {
  const { t } = useTranslation('settings')
  const fallback = copilot.summary_model_source === 'llm_model'
  const code = { code: <code className="font-mono" /> }
  return (
    <Card title={t('card.copilot')}>
      <dl className="space-y-1.5">
        <Setting label={t('copilot.conversationModel')} env="LLM_MODEL">
          <code className="font-mono text-[12.5px] break-all">{copilot.model}</code>
        </Setting>
        <Setting label={t('copilot.summaryModel')} env="SUMMARY_MODEL">
          <code className="font-mono text-[12.5px] break-all">{copilot.summary_model}</code>
          {fallback && (
            <span className="text-muted-foreground ml-2 text-[12px] font-normal">
              <Trans t={t} i18nKey="copilot.fromEnv" components={code} />
            </span>
          )}
        </Setting>
        <Setting label={t('copilot.promptsVersion')} env="PROMPTS_VERSION">
          <code className="font-mono text-[12.5px]">{copilot.prompts_version}</code>
        </Setting>
        <Setting label={t('copilot.summaryPromptsVersion')} env="SUMMARY_PROMPTS_VERSION">
          <code className="font-mono text-[12.5px]">{copilot.summary_prompts_version}</code>
        </Setting>
        <Setting label={t('copilot.longestSummary')} env="SUMMARY_MAX_TOKENS">
          {t('copilot.tokens', { n: copilot.summary_max_tokens })}
        </Setting>
      </dl>
      {!copilot.configured && (
        <Alert role="note" className="bg-warning-muted text-warning border-transparent">
          <AlertDescription className="text-warning">
            <Trans t={t} i18nKey="copilot.noKey" components={code} />
          </AlertDescription>
        </Alert>
      )}
    </Card>
  )
}

export function SettingsPage() {
  const { t } = useTranslation('settings')
  const { language } = useLanguage()
  useDocumentTitle(t('pageTitle'))
  const settings = useIndexingSettings()
  const data = settings.data

  return (
    <div className="space-y-5">
      <div>
        <h1 className="text-xl font-semibold">{t('heading')}</h1>
        <p className="text-muted-foreground mt-1">{t('intro')}</p>
      </div>
      {settings.isError && !data ? (
        <LoadError error={settings.error} onRetry={() => void settings.refetch()} />
      ) : !data ? (
        <div aria-busy="true" aria-label={t('loading')} className="grid gap-4 md:grid-cols-2">
          {[0, 1, 2, 3].map((i) => (
            <Skeleton key={i} className="h-48 rounded-xl" />
          ))}
        </div>
      ) : (
        <div className="grid items-start gap-4 md:grid-cols-2">
          <DocumentsCard counts={data.documents} />
          <Card title={t('card.services')}>
            <ServiceDetails />
          </Card>
          <Card title={t('card.chunking')}>
            <dl className="space-y-1.5">
              <Setting label={t('chunking.version')}>
                <code className="font-mono text-[12.5px]">{data.chunking.chunker_version}</code>
              </Setting>
              <Setting label={t('chunking.size')} env="CHUNK_SIZE">
                {t('chunking.characters', { n: data.chunking.chunk_size })}
              </Setting>
              <Setting label={t('chunking.overlap')} env="CHUNK_OVERLAP">
                {t('chunking.characters', { n: data.chunking.chunk_overlap })}
              </Setting>
              <Setting label={t('chunking.minSize')} env="MIN_CHUNK_SIZE">
                {t('chunking.characters', { n: data.chunking.min_chunk_size })}
              </Setting>
            </dl>
            <Config
              label={t('chunking.config')}
              copy={t('chunking.copyConfig')}
              value={data.chunking.chunker_config}
            />
          </Card>
          <Card title={t('card.embeddings')}>
            <dl className="space-y-1.5">
              <Setting label={t('embedding.provider')} env="EMBEDDING_PROVIDER">
                {data.embedding.provider}
              </Setting>
              <Setting label={t('embedding.model')} env="EMBEDDING_MODEL">
                {data.embedding.model}
              </Setting>
              <Setting label={t('embedding.dimensions')} env="EMBEDDING_DIMENSIONS">
                {data.embedding.dimensions}
              </Setting>
              <Setting label={t('embedding.batchSize')} env="EMBEDDING_BATCH_SIZE">
                {t('embedding.perRequest', { n: data.embedding.batch_size })}
              </Setting>
            </dl>
            {data.embedding.provider === 'fake' && (
              <Alert role="note" className="bg-warning-muted text-warning border-transparent">
                <AlertDescription className="text-warning">{t('embedding.fake')}</AlertDescription>
              </Alert>
            )}
            <Config
              label={t('embedding.config')}
              copy={t('embedding.copyConfig')}
              value={data.embedding.embedder_config}
            />
          </Card>
          <CopilotCard copilot={data.copilot} />
          <Card title={t('card.uploads')}>
            <dl className="space-y-1.5">
              <Setting label={t('uploads.largest')} env="MAX_UPLOAD_BYTES">
                {formatBytes(data.uploads.max_upload_bytes, language)}
              </Setting>
            </dl>
          </Card>
        </div>
      )}
    </div>
  )
}

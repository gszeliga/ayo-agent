import type { ReactNode } from 'react'
import { Link } from 'react-router'

import type { components } from '@/api/schema'
import { CopyButton } from '@/components/CopyButton'
import { LoadError } from '@/components/LoadError'
import { Alert, AlertDescription } from '@/components/ui/alert'
import { Skeleton } from '@/components/ui/skeleton'
import { DEFAULT_PARAMS, toSearchParams } from '@/documents/listParams'
import { OUTDATED_REASONS } from '@/documents/status'
import { useDocumentTitle } from '@/hooks/useDocumentTitle'
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

function Config({ label, value }: { label: string; value: string }) {
  return (
    <div className="space-y-1">
      <div className="text-muted-foreground text-xs font-medium">{label}</div>
      <div className="bg-secondary flex items-center gap-1 rounded-md py-1 pr-1 pl-2.5">
        <code className="min-w-0 flex-1 font-mono text-[12px] break-all">{value}</code>
        <CopyButton value={value} label={`Copy ${label.toLowerCase()}`} />
      </div>
    </div>
  )
}

// Every tenant's outdated documents, in the list's default order.
const outdatedSearch = toSearchParams({ ...DEFAULT_PARAMS, status: 'outdated' })
const OUTDATED_DOCUMENTS = `${ROUTES.documents}?${outdatedSearch.toString()}`

const plural = (n: number, one: string, many: string) => `${String(n)} ${n === 1 ? one : many}`

function DocumentsCard({ counts }: { counts: IndexingSettings['documents'] }) {
  const { total, indexed, outdated } = counts
  const reasons = (Object.keys(OUTDATED_REASONS) as (keyof typeof OUTDATED_REASONS)[]).map(
    (reason) => ({ reason, count: outdated[reason] }),
  )
  const outdatedTotal = reasons.reduce((sum, r) => sum + r.count, 0)
  const share = (n: number) => (total === 0 ? 0 : (n / total) * 100)
  return (
    <Card title="Documents">
      <p>
        <span className="text-2xl font-semibold tabular-nums">{total}</span>{' '}
        <span className="text-muted-foreground">stored</span>
      </p>
      {total > 0 && (
        <div aria-hidden="true" className="bg-warning-muted flex h-2 overflow-hidden rounded-full">
          <div className="bg-success" style={{ width: `${String(share(indexed))}%` }} />
          <div className="bg-warning" style={{ width: `${String(share(outdatedTotal))}%` }} />
        </div>
      )}
      <dl className="space-y-1.5">
        <Setting label="Indexed with the current settings">{indexed}</Setting>
        <Setting label="Outdated">{outdatedTotal}</Setting>
        {reasons.map(({ reason, count }) => (
          <Setting
            key={reason}
            label={OUTDATED_REASONS[reason]}
            className="text-muted-foreground pl-4 text-[13px]"
          >
            {count}
          </Setting>
        ))}
      </dl>
      {outdatedTotal > 0 && (
        <p className="text-muted-foreground text-[13px]">
          {plural(outdatedTotal, 'document is', 'documents are')} outdated: reprocess a document to
          bring it up to date.{' '}
          <Link
            to={OUTDATED_DOCUMENTS}
            className="text-foreground font-medium underline-offset-4 hover:underline"
          >
            Show outdated documents
          </Link>
        </p>
      )}
    </Card>
  )
}

export function SettingsPage() {
  useDocumentTitle('Indexing settings')
  const settings = useIndexingSettings()
  const data = settings.data

  return (
    <div className="space-y-5">
      <div>
        <h1 className="text-xl font-semibold">Indexing settings</h1>
        <p className="text-muted-foreground mt-1">
          Settings come from the API&apos;s environment: changing one needs a restart, and makes
          documents outdated until they are reprocessed.
        </p>
      </div>
      {settings.isError && !data ? (
        <LoadError error={settings.error} onRetry={() => void settings.refetch()} />
      ) : !data ? (
        <div aria-busy="true" aria-label="Loading settings" className="grid gap-4 md:grid-cols-2">
          {[0, 1, 2, 3].map((i) => (
            <Skeleton key={i} className="h-48 rounded-xl" />
          ))}
        </div>
      ) : (
        <div className="grid items-start gap-4 md:grid-cols-2">
          <DocumentsCard counts={data.documents} />
          <Card title="Services">
            <ServiceDetails />
          </Card>
          <Card title="Chunking">
            <dl className="space-y-1.5">
              <Setting label="Chunker version">
                <code className="font-mono text-[12.5px]">{data.chunking.chunker_version}</code>
              </Setting>
              <Setting label="Chunk size" env="CHUNK_SIZE">
                {data.chunking.chunk_size} characters
              </Setting>
              <Setting label="Overlap" env="CHUNK_OVERLAP">
                {data.chunking.chunk_overlap} characters
              </Setting>
              <Setting label="Minimum chunk size" env="MIN_CHUNK_SIZE">
                {data.chunking.min_chunk_size} characters
              </Setting>
            </dl>
            <Config label="Chunker config" value={data.chunking.chunker_config} />
          </Card>
          <Card title="Embeddings">
            <dl className="space-y-1.5">
              <Setting label="Provider" env="EMBEDDING_PROVIDER">
                {data.embedding.provider}
              </Setting>
              <Setting label="Model" env="EMBEDDING_MODEL">
                {data.embedding.model}
              </Setting>
              <Setting label="Dimensions" env="EMBEDDING_DIMENSIONS">
                {data.embedding.dimensions}
              </Setting>
              <Setting label="Batch size" env="EMBEDDING_BATCH_SIZE">
                {data.embedding.batch_size} texts per request
              </Setting>
            </dl>
            {data.embedding.provider === 'fake' && (
              <Alert role="note" className="bg-warning-muted text-warning border-transparent">
                <AlertDescription className="text-warning">
                  The fake provider: deterministic vectors that carry no meaning. Fine for tests and
                  local runs, useless for retrieval.
                </AlertDescription>
              </Alert>
            )}
            <Config label="Embedder config" value={data.embedding.embedder_config} />
          </Card>
          <Card title="Uploads">
            <dl className="space-y-1.5">
              <Setting label="Largest file" env="MAX_UPLOAD_BYTES">
                {formatBytes(data.uploads.max_upload_bytes)}
              </Setting>
            </dl>
          </Card>
        </div>
      )}
    </div>
  )
}

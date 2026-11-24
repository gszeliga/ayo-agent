import type { ReactNode } from 'react'
import { useTranslation } from 'react-i18next'

import type { components } from '@/api/schema'
import { CopyButton } from '@/components/CopyButton'
import { useLanguage } from '@/layout/languageContext'
import { formatBytes, formatUtc, relativeTime } from '@/lib/format'
import type { Language } from '@/lib/language'
import { chunkerDiff, differsNote, embedderDiff } from '@/settings/configDiff'
import { useIndexingSettings } from '@/settings/queries'

type Document = components['schemas']['Document']

function NotRecorded() {
  const { t } = useTranslation('document')
  return <span className="text-muted-foreground italic">{t('facts.notRecorded')}</span>
}

function Fact({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div className="space-y-0.5">
      <dt className="text-muted-foreground text-xs font-medium">{label}</dt>
      <dd className="min-w-0">{children}</dd>
    </div>
  )
}

function Time({ iso, now }: { iso: string | null; now: number }) {
  const { language } = useLanguage()
  if (iso === null) return <NotRecorded />
  return (
    <time dateTime={iso} title={formatUtc(iso)}>
      {relativeTime(iso, language, now)}
    </time>
  )
}

/** A long value shortened to 12 characters, the full one copied. */
function Hash({ value, label }: { value: string; label: string }) {
  return (
    <span className="flex items-center gap-1">
      <code className="font-mono text-[12.5px]" title={value}>
        {value.slice(0, 12)}…
      </code>
      <CopyButton value={value} label={label} />
    </span>
  )
}

/**
 * A stored config and, when the current one differs, what changed. A config never recorded
 * gets no note: the status badge already says why the document is outdated.
 */
function Config({
  value,
  current,
  compare,
}: {
  value: string | null
  current: string | undefined
  compare: (stored: string, current: string, language: Language) => string[] | null
}) {
  const { language } = useLanguage()
  if (value === null) return <NotRecorded />
  const note =
    current === undefined ? null : differsNote(compare(value, current, language), language)
  return (
    <>
      <code className="font-mono text-[12.5px] break-all">{value}</code>
      {note && <p className="text-warning mt-1 text-[13px] font-medium">{note}</p>}
    </>
  )
}

export function FactsPanel({ document, now }: { document: Document; now: number }) {
  const { t } = useTranslation('document')
  const { language } = useLanguage()
  const current = useIndexingSettings().data
  return (
    <aside aria-label={t('facts.label')} className="bg-card rounded-xl border p-5">
      <dl className="space-y-4">
        <Fact label={t('facts.sourceKey')}>
          <code className="font-mono text-[12.5px] break-all">{document.source_key}</code>
        </Fact>
        <Fact label={t('facts.created')}>
          <Time iso={document.created_at} now={now} />
        </Fact>
        <Fact label={t('facts.updated')}>
          <Time iso={document.updated_at} now={now} />
        </Fact>
        <Fact label={t('facts.chunkedEmbedded')}>
          <Time iso={document.chunked_at} now={now} /> /{' '}
          <Time iso={document.embedded_at} now={now} />
        </Fact>
        <Fact label={t('facts.size')}>
          {document.size_bytes === null ? (
            <NotRecorded />
          ) : (
            formatBytes(document.size_bytes, language)
          )}
        </Fact>
        <Fact label={t('facts.chunks')}>{document.chunk_count}</Fact>
        <Fact label={t('facts.contentHash')}>
          <Hash value={document.content_hash} label={t('facts.copyContentHash')} />
        </Fact>
        <Fact label={t('facts.embedSignature')}>
          <Hash value={document.embed_signature} label={t('facts.copyEmbedSignature')} />
        </Fact>
        <Fact label={t('facts.chunkerConfig')}>
          <Config
            value={document.chunker_config}
            current={current?.chunking.chunker_config}
            compare={chunkerDiff}
          />
        </Fact>
        <Fact label={t('facts.embedderConfig')}>
          <Config
            value={document.embedder_config}
            current={current?.embedding.embedder_config}
            compare={embedderDiff}
          />
        </Fact>
      </dl>
    </aside>
  )
}

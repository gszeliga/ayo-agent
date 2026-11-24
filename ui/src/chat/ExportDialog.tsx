import { useQuery, useQueryClient, type InfiniteData } from '@tanstack/react-query'
import { Download } from 'lucide-react'
import { useState } from 'react'
import { useTranslation } from 'react-i18next'

import { unwrap } from '@/api/client'
import type { components } from '@/api/schema'
import { LoadError } from '@/components/LoadError'
import { Button } from '@/components/ui/button'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import { useApiClient } from '@/connection/context'
import { useLanguage } from '@/layout/languageContext'

import { downloadFile } from './download'
import {
  exportFileName,
  exportJson,
  exportMarkdown,
  missingRanges,
  type ExportFormat,
} from './exportCase'
import { caseTurnsKey } from './queries'

type CaseDetail = components['schemas']['CaseDetail']
type CaseTurn = components['schemas']['CaseTurn']
type CaseTurnPage = components['schemas']['CaseTurnPage']

/** The largest page the API serves. */
const EXPORT_PAGE_SIZE = 50

interface Props {
  detail: CaseDetail
  open: boolean
  onOpenChange: (open: boolean) => void
}

/** Export as Markdown or JSON, made in the browser from the API's data: nothing is uploaded. */
export function ExportDialog({ detail, open, onOpenChange }: Props) {
  const { t } = useTranslation('chat')
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-2xl">
        <DialogHeader>
          <DialogTitle>{t('exportDialog.title')}</DialogTitle>
          <DialogDescription>{t('exportDialog.description')}</DialogDescription>
        </DialogHeader>
        {/* Mounted only while open: each opening reads the turns afresh. */}
        <ExportBody detail={detail} />
      </DialogContent>
    </Dialog>
  )
}

function loadedTurns(queryClient: ReturnType<typeof useQueryClient>, caseId: string): CaseTurn[] {
  const cached = queryClient.getQueryData<InfiniteData<CaseTurnPage>>(caseTurnsKey(caseId))
  return cached?.pages.flatMap((page) => page.items) ?? []
}

/**
 * Every turn of the case: the loaded ones from the conversation's cache, the others read
 * here in pages of 50 (into this query only, so the conversation's paging is untouched).
 */
function useAllTurns(detail: CaseDetail) {
  const client = useApiClient()
  const queryClient = useQueryClient()
  const caseId = detail.case_id
  return useQuery({
    queryKey: ['case-export', caseId, detail.version],
    gcTime: 0,
    retry: false,
    queryFn: async ({ signal }) => {
      const byTurn = new Map(loadedTurns(queryClient, caseId).map((turn) => [turn.turn, turn]))
      for (const range of missingRanges([...byTurn.keys()], detail.turns)) {
        for (let offset = range.start; offset < range.end; offset += EXPORT_PAGE_SIZE) {
          const page = await unwrap(
            client.GET('/admin/cases/{case_id}/turns', {
              params: {
                path: { case_id: caseId },
                query: { offset, limit: Math.min(EXPORT_PAGE_SIZE, range.end - offset) },
              },
              signal,
            }),
          )
          for (const turn of page.items) byTurn.set(turn.turn, turn)
        }
      }
      return [...byTurn.values()].sort((a, b) => a.turn - b.turn)
    },
  })
}

function ExportBody({ detail }: { detail: CaseDetail }) {
  const { t } = useTranslation('chat')
  const { language } = useLanguage()
  const queryClient = useQueryClient()
  const [format, setFormat] = useState<ExportFormat>('markdown')
  // One time for the preview and the file.
  const [now] = useState(() => new Date())
  const [missing] = useState(() => {
    const loaded = loadedTurns(queryClient, detail.case_id).map((turn) => turn.turn)
    return missingRanges(loaded, detail.turns).reduce((sum, r) => sum + r.end - r.start, 0)
  })
  const turns = useAllTurns(detail)
  const content = turns.data
    ? format === 'json'
      ? exportJson(detail, turns.data, now)
      : exportMarkdown(detail, turns.data, now, language)
    : null

  return (
    <>
      <div role="group" aria-label={t('exportDialog.format')} className="flex gap-2">
        {(['markdown', 'json'] as const).map((value) => (
          <Button
            key={value}
            variant={format === value ? 'default' : 'outline'}
            size="sm"
            aria-pressed={format === value}
            onClick={() => {
              setFormat(value)
            }}
          >
            {value === 'markdown' ? 'Markdown' : 'JSON'}
          </Button>
        ))}
      </div>
      {turns.isError ? (
        <LoadError
          error={turns.error}
          onRetry={() => {
            void turns.refetch()
          }}
        />
      ) : content === null ? (
        <p role="status" className="text-muted-foreground text-sm">
          {missing > 0
            ? t('exportDialog.fetching', { count: missing })
            : t('exportDialog.preparing')}
        </p>
      ) : (
        <pre
          aria-label={t('exportDialog.preview')}
          tabIndex={0}
          className="bg-secondary max-h-[50vh] overflow-auto rounded-md p-3 font-mono text-[12px] break-words whitespace-pre-wrap"
        >
          {content}
        </pre>
      )}
      <DialogFooter>
        <Button
          disabled={content === null}
          onClick={() => {
            if (content === null) return
            downloadFile(
              exportFileName(detail, format, now),
              content,
              format === 'json' ? 'application/json' : 'text/markdown;charset=utf-8',
            )
          }}
        >
          <Download aria-hidden="true" />
          {t('exportDialog.download')}
        </Button>
      </DialogFooter>
    </>
  )
}

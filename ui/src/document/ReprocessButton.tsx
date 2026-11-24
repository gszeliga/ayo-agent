import { ChevronDown, RefreshCw } from 'lucide-react'
import { useTranslation } from 'react-i18next'
import { toast } from 'sonner'

import { ApiError, describeError } from '@/api/errors'
import { Button } from '@/components/ui/button'
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu'
import { useConnection } from '@/connection/context'
import { reprocessProviderFailed } from '@/documents/bulkReprocess'
import { useReprocess } from '@/documents/mutations'
import { useLanguage } from '@/layout/languageContext'

/** Reprocess (skipped when up to date), with Force in the menu. */
export function ReprocessButton({ docId, onGone }: { docId: string; onGone: () => void }) {
  const { t } = useTranslation('document')
  const { language } = useLanguage()
  const reprocess = useReprocess(docId)
  const { connection } = useConnection()

  function run(force: boolean) {
    reprocess.mutate(force, {
      onSuccess: (result) => {
        if (result.status === 'up_to_date') {
          toast.success(t('reprocess.upToDate'), { description: t('reprocess.upToDateHint') })
        } else {
          toast.success(t('reprocess.done', { count: result.chunk_count ?? 0 }))
        }
      },
      onError: (error) => {
        if (error instanceof ApiError && error.status === 404) {
          onGone()
        } else if (error instanceof ApiError && error.status === 409) {
          toast.error(t('reprocess.changed'), {
            action: {
              label: t('retry', { ns: 'common' }),
              onClick: () => {
                run(force)
              },
            },
          })
        } else if (error instanceof ApiError && error.status === 502) {
          toast.error(reprocessProviderFailed(language))
        } else {
          toast.error(describeError(error, connection?.baseUrl ?? '', language))
        }
      },
    })
  }

  const busy = reprocess.isPending
  return (
    <div className="flex">
      <Button
        variant="outline"
        className="rounded-r-none"
        disabled={busy}
        onClick={() => {
          run(false)
        }}
      >
        <RefreshCw aria-hidden="true" className={busy ? 'animate-spin' : undefined} />
        {busy ? t('reprocess.busy') : t('reprocess.button')}
      </Button>
      <DropdownMenu>
        <DropdownMenuTrigger asChild>
          <Button
            variant="outline"
            size="icon"
            className="-ml-px rounded-l-none"
            disabled={busy}
            aria-label={t('reprocess.more')}
          >
            <ChevronDown aria-hidden="true" />
          </Button>
        </DropdownMenuTrigger>
        <DropdownMenuContent align="end" className="w-72">
          <DropdownMenuItem
            onSelect={() => {
              run(true)
            }}
          >
            <div>
              <div className="font-medium">{t('reprocess.force')}</div>
              <div className="text-muted-foreground text-xs">{t('reprocess.forceHint')}</div>
            </div>
          </DropdownMenuItem>
        </DropdownMenuContent>
      </DropdownMenu>
    </div>
  )
}

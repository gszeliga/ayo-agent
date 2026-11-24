import { useTranslation } from 'react-i18next'
import { Link } from 'react-router'

import type { components } from '@/api/schema'
import { Badge } from '@/components/ui/badge'
import { formatUtc, relativeTime } from '@/lib/format'
import { useLanguage } from '@/layout/languageContext'
import { cn } from '@/lib/utils'
import { chatCasePath } from '@/paths'

type CaseListItem = components['schemas']['CaseListItem']

/** One case in the list: a link that opens it. */
export function CaseRow({ item, selected }: { item: CaseListItem; selected: boolean }) {
  const { t } = useTranslation('chat')
  const { language } = useLanguage()
  const closed = item.closed_at !== null
  return (
    <Link
      to={chatCasePath(item.case_id)}
      aria-current={selected ? 'page' : undefined}
      className={cn(
        'hover:bg-accent block rounded-md border border-transparent px-3 py-2.5',
        selected && 'border-border bg-secondary',
      )}
    >
      <div className="flex items-start justify-between gap-2">
        <span
          className={cn(
            'line-clamp-2 font-medium',
            item.title === null && 'text-muted-foreground italic',
          )}
        >
          {item.title ?? t('untitled')}
        </span>
        <Badge variant={closed ? 'outline' : 'secondary'} className="mt-0.5">
          {t(`phase.${item.phase}`)}
        </Badge>
      </div>
      <div className="text-muted-foreground mt-1 flex flex-wrap items-center gap-x-2 gap-y-1 text-xs">
        <span>{item.tenant}</span>
        <span aria-hidden="true">·</span>
        <span>{t('turns', { count: item.turns })}</span>
        {item.pending_actions > 0 && (
          <>
            <span aria-hidden="true">·</span>
            <span>{t('row.pending', { count: item.pending_actions })}</span>
          </>
        )}
        {item.overdue_actions > 0 && (
          <Badge variant="warning">{t('row.overdue', { count: item.overdue_actions })}</Badge>
        )}
        {item.web_session_id === null && <Badge variant="outline">{t('row.otherChannel')}</Badge>}
        <span className="ml-auto" title={formatUtc(item.updated_at)}>
          <span className="sr-only">{t('row.updated')}</span>
          {relativeTime(item.updated_at, language)}
        </span>
      </div>
    </Link>
  )
}

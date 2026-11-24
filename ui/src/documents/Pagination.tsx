import { useTranslation } from 'react-i18next'

import { Button } from '@/components/ui/button'

import { lastPage, PAGE_SIZE } from './listParams'

export function Pagination({
  page,
  total,
  shown,
  onPage,
}: {
  page: number
  total: number
  shown: number
  onPage: (page: number) => void
}) {
  const { t } = useTranslation('documents')
  const from = (page - 1) * PAGE_SIZE + 1
  return (
    <nav aria-label={t('pagination.label')} className="flex items-center justify-between gap-4">
      <p className="text-muted-foreground tabular-nums">
        {shown > 0 ? t('pagination.range', { from, to: from + shown - 1, total }) : ''}
      </p>
      <div className="flex gap-2">
        <Button
          variant="outline"
          disabled={page <= 1}
          onClick={() => {
            onPage(page - 1)
          }}
        >
          {t('pagination.previous')}
        </Button>
        <Button
          variant="outline"
          disabled={page >= lastPage(total)}
          onClick={() => {
            onPage(page + 1)
          }}
        >
          {t('pagination.next')}
        </Button>
      </div>
    </nav>
  )
}

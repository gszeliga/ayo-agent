import { RefreshCw, Trash2, X } from 'lucide-react'
import { useTranslation } from 'react-i18next'

import { Button } from '@/components/ui/button'

export function SelectionBar({
  count,
  offPage,
  onClear,
  onReprocess,
  onDelete,
}: {
  count: number
  /** How many of them are on other pages. */
  offPage: number
  onClear: () => void
  onReprocess: () => void
  onDelete: () => void
}) {
  const { t } = useTranslation('documents')
  return (
    <div
      role="region"
      aria-label={t('selection.label')}
      className="border-primary bg-primary/5 flex flex-wrap items-center gap-3 rounded-lg border py-1.5 pr-1.5 pl-4"
    >
      <p className="flex-1 font-medium">
        {t('selection.count', { count })}
        {offPage > 0 && (
          <span className="text-muted-foreground font-normal">
            {' '}
            {t('selection.offPage', { count: offPage })}
          </span>
        )}
      </p>
      <Button variant="ghost" onClick={onClear}>
        <X aria-hidden="true" />
        {t('selection.clear')}
      </Button>
      <Button variant="outline" onClick={onReprocess}>
        <RefreshCw aria-hidden="true" />
        {t('selection.reprocess')}
      </Button>
      <Button variant="destructive" onClick={onDelete}>
        <Trash2 aria-hidden="true" />
        {t('selection.delete')}
      </Button>
    </div>
  )
}

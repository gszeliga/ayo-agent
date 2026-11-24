import { useTranslation } from 'react-i18next'
import { Link } from 'react-router'

import { EmptyState } from '@/components/StateMessage'
import { Button } from '@/components/ui/button'
import { useDocumentTitle } from '@/hooks/useDocumentTitle'

export function NotFoundPage() {
  const { t } = useTranslation()
  useDocumentTitle(t('notFound.title'))
  return (
    <EmptyState
      as="h1"
      title={t('notFound.title')}
      description={t('notFound.description')}
      className="mx-auto mt-8 max-w-xl"
      action={
        <Button asChild variant="outline">
          <Link to="/documents">{t('notFound.goToDocuments')}</Link>
        </Button>
      }
    />
  )
}

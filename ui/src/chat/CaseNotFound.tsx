import { useTranslation } from 'react-i18next'
import { Link } from 'react-router'

import { EmptyState } from '@/components/StateMessage'
import { Button } from '@/components/ui/button'
import { ROUTES } from '@/paths'

/** An unknown or malformed case id: deleted, or the link is wrong. */
export function CaseNotFound() {
  const { t } = useTranslation('chat')
  return (
    <EmptyState
      as="h1"
      title={t('notFound.title')}
      description={t('notFound.description')}
      className="mx-auto mt-10 max-w-xl"
      action={
        <Button asChild>
          <Link to={ROUTES.chat}>{t('notFound.back')}</Link>
        </Button>
      }
    />
  )
}

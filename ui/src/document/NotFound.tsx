import { useTranslation } from 'react-i18next'
import { Link } from 'react-router'

import { EmptyState } from '@/components/StateMessage'
import { Button } from '@/components/ui/button'
import { useDocumentTitle } from '@/hooks/useDocumentTitle'

import type { BackLink } from './params'

export function DocumentNotFound({ back }: { back: BackLink }) {
  const { t } = useTranslation('document')
  useDocumentTitle(t('notFound.pageTitle'))
  return (
    <EmptyState
      as="h1"
      title={t('notFound.title')}
      description={t('notFound.description')}
      className="mx-auto mt-8 max-w-xl"
      action={
        <Button asChild>
          <Link to={back.to}>{t(`backTo.${back.target}`)}</Link>
        </Button>
      }
    />
  )
}

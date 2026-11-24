import { Lock } from 'lucide-react'
import { useTranslation } from 'react-i18next'

import type { ReadOnlyReason } from './readOnly'

export function ReadOnlyNotice({ reason }: { reason: ReadOnlyReason }) {
  const { t } = useTranslation('chat')
  return (
    <p
      role="note"
      className="bg-muted text-muted-foreground flex items-center gap-2 rounded-md px-3 py-2 text-[13px]"
    >
      <Lock aria-hidden="true" className="size-4 flex-none" />
      {t(`readOnly.${reason}`)}
    </p>
  )
}

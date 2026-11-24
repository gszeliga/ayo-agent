import { Trans, useTranslation } from 'react-i18next'

import type { Phase } from './phases'

/** A turn that changed phase: a quiet line after its reply. */
export function PhaseMarker({ from, to }: { from: Phase; to: Phase }) {
  const { t } = useTranslation('chat')
  return (
    <div className="text-muted-foreground flex items-center gap-3 text-xs">
      <span aria-hidden="true" className="bg-border h-px flex-1" />
      <span>
        <Trans
          t={t}
          i18nKey="phaseMarker"
          values={{ from: t(`phase.${from}`) }}
          components={{
            to: <strong className="text-foreground font-medium">{t(`phase.${to}`)}</strong>,
          }}
        />
      </span>
      <span aria-hidden="true" className="bg-border h-px flex-1" />
    </div>
  )
}

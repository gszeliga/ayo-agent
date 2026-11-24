import { Trans, useTranslation } from 'react-i18next'

import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from '@/components/ui/alert-dialog'

import type { useCopilotSettings } from '@/settings/queries'

interface Props {
  open: boolean
  onOpenChange: (open: boolean) => void
  /** A summary exists: generating replaces it. */
  replacing: boolean
  copilot: ReturnType<typeof useCopilotSettings>
  onGenerate: () => void
}

/** Asked before every summary: it is a real, billed model call (decision 22). */
export function GenerateSummaryDialog({
  open,
  onOpenChange,
  replacing,
  copilot,
  onGenerate,
}: Props) {
  const { t } = useTranslation('chat')
  const settings = copilot.data
  const model = settings ? (
    <code className="text-foreground font-mono break-all">{settings.summary_model}</code>
  ) : copilot.isPending ? (
    <span>{t('generateDialog.modelPending')}</span>
  ) : (
    <span>
      <Trans
        t={t}
        i18nKey="generateDialog.modelUnknown"
        components={{ code: <code className="font-mono" /> }}
      />
    </span>
  )
  return (
    <AlertDialog open={open} onOpenChange={onOpenChange}>
      <AlertDialogContent>
        <AlertDialogHeader>
          <AlertDialogTitle>
            {replacing ? t('generateDialog.titleReplace') : t('generateDialog.titleNew')}
          </AlertDialogTitle>
          <AlertDialogDescription asChild>
            <div className="space-y-2">
              <p>
                <Trans t={t} i18nKey="generateDialog.body" components={{ b: <strong />, model }} />
              </p>
              {replacing && <p>{t('generateDialog.replaces')}</p>}
              {settings && !settings.configured && (
                <p className="text-warning">{t('generateDialog.noKey')}</p>
              )}
            </div>
          </AlertDialogDescription>
        </AlertDialogHeader>
        <AlertDialogFooter>
          <AlertDialogCancel>{t('generateDialog.cancel')}</AlertDialogCancel>
          <AlertDialogAction onClick={onGenerate}>
            {replacing ? t('generateDialog.confirmReplace') : t('generateDialog.confirmNew')}
          </AlertDialogAction>
        </AlertDialogFooter>
      </AlertDialogContent>
    </AlertDialog>
  )
}

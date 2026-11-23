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
  const settings = copilot.data
  return (
    <AlertDialog open={open} onOpenChange={onOpenChange}>
      <AlertDialogContent>
        <AlertDialogHeader>
          <AlertDialogTitle>
            {replacing ? 'Regenerate the AI summary?' : 'Generate an AI summary?'}
          </AlertDialogTitle>
          <AlertDialogDescription asChild>
            <div className="space-y-2">
              <p>
                This makes one <strong>billed</strong> call to{' '}
                {settings ? (
                  <code className="text-foreground font-mono break-all">
                    {settings.summary_model}
                  </code>
                ) : copilot.isPending ? (
                  'the summary model'
                ) : (
                  <>
                    the summary model (<code className="font-mono">SUMMARY_MODEL</code>, else{' '}
                    <code className="font-mono">LLM_MODEL</code>: the settings could not be read)
                  </>
                )}{' '}
                through OpenRouter, with the case record and its latest messages.
              </p>
              {replacing && <p>It replaces the current summary.</p>}
              {settings && !settings.configured && (
                <p className="text-warning">
                  No model provider key is configured: the API will refuse it without a call.
                </p>
              )}
            </div>
          </AlertDialogDescription>
        </AlertDialogHeader>
        <AlertDialogFooter>
          <AlertDialogCancel>Cancel</AlertDialogCancel>
          <AlertDialogAction onClick={onGenerate}>
            {replacing ? 'Regenerate' : 'Generate'}
          </AlertDialogAction>
        </AlertDialogFooter>
      </AlertDialogContent>
    </AlertDialog>
  )
}

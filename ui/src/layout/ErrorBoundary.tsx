import { Component, type ErrorInfo, type ReactNode } from 'react'
import { useTranslation } from 'react-i18next'

import { Button } from '@/components/ui/button'
import { EmptyState } from '@/components/StateMessage'
import { isChunkLoadError } from '@/lib/chunkError'

interface State {
  error: unknown
}

/**
 * Catches a crash while rendering, instead of a blank page. Nothing is sent anywhere (there
 * is no telemetry); the error goes to the console. `resetKey` (the path) clears it, so
 * navigating away recovers.
 */
export class ErrorBoundary extends Component<
  { children: ReactNode; resetKey: string },
  State & { resetKey: string }
> {
  constructor(props: { children: ReactNode; resetKey: string }) {
    super(props)
    this.state = { error: null, resetKey: props.resetKey }
  }

  static getDerivedStateFromError(error: unknown): Partial<State> {
    return { error }
  }

  static getDerivedStateFromProps(
    props: { resetKey: string },
    state: State & { resetKey: string },
  ): Partial<State & { resetKey: string }> | null {
    return props.resetKey === state.resetKey ? null : { error: null, resetKey: props.resetKey }
  }

  componentDidCatch(error: unknown, info: ErrorInfo): void {
    console.error('UI crashed', error, info.componentStack)
  }

  render(): ReactNode {
    if (this.state.error === null) return this.props.children
    return <CrashMessage newVersion={isChunkLoadError(this.state.error)} />
  }
}

/** What a crash shows: a function component, so it can use the translations. */
function CrashMessage({ newVersion }: { newVersion: boolean }) {
  const { t } = useTranslation()
  const reload = (
    <Button
      onClick={() => {
        window.location.reload()
      }}
    >
      {t('crash.reload')}
    </Button>
  )
  if (newVersion) {
    return (
      <EmptyState
        as="h1"
        title={t('crash.newVersionTitle')}
        description={t('crash.newVersionDescription')}
        action={reload}
      />
    )
  }
  return (
    <EmptyState
      as="h1"
      title={t('crash.title')}
      description={t('crash.description')}
      action={
        <>
          {reload}
          <Button asChild variant="outline">
            <a href="/documents">{t('crash.backToDocuments')}</a>
          </Button>
        </>
      }
    />
  )
}

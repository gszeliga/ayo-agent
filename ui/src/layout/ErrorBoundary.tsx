import { Component, type ErrorInfo, type ReactNode } from 'react'

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
    const reload = (
      <Button
        onClick={() => {
          window.location.reload()
        }}
      >
        Reload
      </Button>
    )
    if (isChunkLoadError(this.state.error)) {
      return (
        <EmptyState
          as="h1"
          title="A new version of this page is available"
          description="Reload to get it."
          action={reload}
        />
      )
    }
    return (
      <EmptyState
        as="h1"
        title="Something went wrong"
        description="This page failed to show. Reloading usually helps; if not, the details are in the browser console."
        action={
          <>
            {reload}
            <Button asChild variant="outline">
              <a href="/documents">Back to documents</a>
            </Button>
          </>
        }
      />
    )
  }
}

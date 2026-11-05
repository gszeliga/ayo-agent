import { useCallback, useMemo, useState, type ReactNode } from 'react'

import { createApiClient } from '@/api/client'

import { ConnectionContext, type ConnectionState } from './context'
import { clearConnection, loadConnection, saveConnection, type Connection } from './storage'

export const KEY_REJECTED = 'Your key was rejected. Connect again with a valid key.'

export function ConnectionProvider({ children }: { children: ReactNode }) {
  const [connection, setConnection] = useState<Connection | null>(() => loadConnection())
  const [notice, setNotice] = useState<string | null>(null)

  const connect = useCallback((next: Connection) => {
    saveConnection(next)
    setNotice(null)
    setConnection(next)
  }, [])

  const disconnect = useCallback((reason?: string) => {
    clearConnection()
    setNotice(reason ?? null)
    setConnection(null)
  }, [])

  const client = useMemo(
    () =>
      connection
        ? createApiClient(connection.baseUrl, connection.apiKey, {
            onUnauthorized: () => {
              disconnect(KEY_REJECTED)
            },
          })
        : null,
    [connection, disconnect],
  )

  const state = useMemo<ConnectionState>(
    () => ({ connection, client, notice, connect, disconnect }),
    [connection, client, notice, connect, disconnect],
  )
  return <ConnectionContext value={state}>{children}</ConnectionContext>
}

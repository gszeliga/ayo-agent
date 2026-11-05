import { useQueryClient } from '@tanstack/react-query'
import { useCallback, useMemo, useState, type ReactNode } from 'react'

import { createApiClient } from '@/api/client'

import { ConnectionContext, type ConnectionState } from './context'
import { clearConnection, loadConnection, saveConnection, type Connection } from './storage'

export const KEY_REJECTED = 'Your key was rejected. Connect again with a valid key.'

export function ConnectionProvider({ children }: { children: ReactNode }) {
  const [connection, setConnection] = useState<Connection | null>(() => loadConnection())
  const [notice, setNotice] = useState<string | null>(null)
  const queryClient = useQueryClient()

  // Cached data belongs to one API and key: dropped whenever the connection changes.
  const connect = useCallback(
    (next: Connection) => {
      queryClient.clear()
      saveConnection(next)
      setNotice(null)
      setConnection(next)
    },
    [queryClient],
  )

  const disconnect = useCallback(
    (reason?: string) => {
      queryClient.clear()
      clearConnection()
      setNotice(reason ?? null)
      setConnection(null)
    },
    [queryClient],
  )

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

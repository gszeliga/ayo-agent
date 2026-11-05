import { createContext, useContext } from 'react'

import type { ApiClient } from '@/api/client'

import type { Connection } from './storage'

export interface ConnectionState {
  connection: Connection | null
  /** The client for the current connection; null when disconnected. */
  client: ApiClient | null
  /** Why the last connection ended, when it was not the user's choice (a rejected key). */
  notice: string | null
  connect: (connection: Connection) => void
  disconnect: (notice?: string) => void
}

export const ConnectionContext = createContext<ConnectionState | null>(null)

export function useConnection(): ConnectionState {
  const state = useContext(ConnectionContext)
  if (state === null) throw new Error('useConnection needs a <ConnectionProvider>')
  return state
}

/** The client, for pages behind the guard (always connected there). */
export function useApiClient(): ApiClient {
  const { client } = useConnection()
  if (client === null) throw new Error('useApiClient needs a connection (use it behind the guard)')
  return client
}

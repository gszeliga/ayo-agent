import createClient, { type Client } from 'openapi-fetch'

import { ApiError } from './errors'
import type { paths } from './schema'

export type ApiClient = Client<paths>

export interface ClientOptions {
  /** Called on every `401`: the key was rejected (or changed on the server). */
  onUnauthorized?: () => void
  /** For tests; defaults to the global `fetch` at call time (so MSW can intercept it). */
  fetch?: typeof globalThis.fetch
}

/** A typed client for one API base URL; every request carries the key. */
export function createApiClient(
  baseUrl: string,
  apiKey: string,
  { onUnauthorized, fetch }: ClientOptions = {},
): ApiClient {
  const client = createClient<paths>({
    baseUrl,
    fetch: fetch ?? ((request: Request) => globalThis.fetch(request)),
  })
  client.use({
    onRequest({ request }) {
      request.headers.set('X-API-Key', apiKey)
      return request
    },
    onResponse({ response }) {
      if (response.status === 401) onUnauthorized?.()
    },
  })
  return client
}

interface FetchResult<T> {
  data?: T
  error?: unknown
  response: Response
}

/** The data of a call, or an `ApiError`: what TanStack Query wants from a query function. */
export async function unwrap<T>(call: Promise<FetchResult<T>>): Promise<T> {
  let result: FetchResult<T>
  try {
    result = await call
  } catch (cause) {
    throw ApiError.network(cause)
  }
  if (result.error !== undefined || !result.response.ok) {
    throw ApiError.fromResponse(result.response.status, result.error)
  }
  return result.data as T
}

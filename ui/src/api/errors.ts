import type { components } from './schema'

export type ErrorItem = components['schemas']['ErrorItem']

/** Shown when the API answered, but not with its own error format (a proxy's HTML page). */
const UNEXPECTED_TYPE = 'unexpected_response'

function isErrorItem(value: unknown): value is ErrorItem {
  if (typeof value !== 'object' || value === null) return false
  const item = value as Record<string, unknown>
  return typeof item.type === 'string' && typeof item.msg === 'string' && Array.isArray(item.loc)
}

/**
 * The one error every screen handles. `status` is null when the API could not be reached
 * (network down, wrong URL, or a CORS refusal: browsers report them all the same way).
 */
export class ApiError extends Error {
  readonly status: number | null
  readonly items: ErrorItem[]

  constructor(status: number | null, items: ErrorItem[], options?: { cause?: unknown }) {
    super(items[0]?.msg ?? 'request failed', options)
    this.name = 'ApiError'
    this.status = status
    this.items = items
  }

  /** The API's answer, parsed: `{"detail": [{type, loc, msg}, ...]}` or anything else. */
  static fromResponse(status: number, body: unknown): ApiError {
    const detail = (body as { detail?: unknown } | null)?.detail
    if (Array.isArray(detail) && detail.length > 0 && detail.every(isErrorItem)) {
      return new ApiError(status, detail)
    }
    return new ApiError(status, [
      { type: UNEXPECTED_TYPE, loc: [], msg: `The API answered HTTP ${String(status)}` },
    ])
  }

  static network(cause: unknown): ApiError {
    return new ApiError(
      null,
      [{ type: 'network_error', loc: [], msg: 'The API could not be reached' }],
      {
        cause,
      },
    )
  }

  get isNetworkError(): boolean {
    return this.status === null
  }

  /** The first item's machine-readable code, e.g. `document_not_found`. */
  get type(): string | undefined {
    return this.items[0]?.type
  }

  /** Messages by field: the last string in each item's `loc` (`["body", "title"]` -> `title`). */
  fieldErrors(): Record<string, string> {
    const fields: Record<string, string> = {}
    for (const item of this.items) {
      const field = item.loc.findLast((part): part is string => typeof part === 'string')
      if (field !== undefined && !(field in fields)) fields[field] = item.msg
    }
    return fields
  }
}

/** What to tell the user about a failed call. */
export function describeError(error: Error, baseUrl: string): string {
  if (error instanceof ApiError && error.isNetworkError) {
    return `Can't reach the API at ${baseUrl}. Check the URL and that the API is running.`
  }
  return error.message
}

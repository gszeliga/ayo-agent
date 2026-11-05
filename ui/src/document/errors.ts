import { ApiError } from '@/api/errors'

/** A 404 from any of the document's endpoints: it was deleted (or never existed). */
export function isNotFound(error: unknown): boolean {
  return error instanceof ApiError && error.status === 404
}

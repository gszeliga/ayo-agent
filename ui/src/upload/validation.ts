import { formatBytes } from '@/lib/format'

import { TENANT_PATTERN } from '@/documents/listParams'

export const TENANT_HINT = 'Lowercase letters, digits and hyphens, 2–63 characters.'

export function tenantError(tenant: string): string | null {
  if (!tenant) return 'Enter a tenant.'
  return TENANT_PATTERN.test(tenant) ? null : TENANT_HINT
}

/**
 * What the API would refuse before reading the content (its encoding and whether anything
 * is indexable are left to it). `maxBytes` is unknown when the settings could not be read;
 * the API's 413 still applies then.
 */
export function fileError(file: File, maxBytes: number | undefined): string | null {
  if (!file.name.toLowerCase().endsWith('.md')) return 'Choose a Markdown file (.md).'
  if (file.size === 0) return 'The file is empty.'
  if (maxBytes !== undefined && file.size > maxBytes) return tooLarge(maxBytes)
  return null
}

export function tooLarge(maxBytes: number | undefined): string {
  return maxBytes === undefined
    ? 'The file is larger than the upload limit.'
    : `Larger than the ${formatBytes(maxBytes)} limit.`
}

/**
 * The `source_key` the API will use, as its `normalize_source_key` does: the given one or
 * the file name, NFC-normalized, reduced to its last path component, trimmed.
 */
export function effectiveSourceKey(sourceKey: string, fileName: string): string {
  const name = (sourceKey.trim() || fileName).normalize('NFC')
  return (name.split(/[/\\]/).at(-1) ?? '').trim()
}

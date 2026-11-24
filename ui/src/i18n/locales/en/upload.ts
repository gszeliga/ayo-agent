/** The upload dialog, from the list (upload) and the document page (replace). */
export const upload = {
  uploadTitle: 'Upload a document',
  replaceTitle: 'Replace document',
  uploadDescription: 'A Markdown file is split into chunks along its headings and embedded.',
  replaceDescription: 'Replaces the content of {{name}}. Chunks are rebuilt.',
  providerDown: 'The embedding provider is down: uploads will fail until it is back.',
  // The API's own error text, as received, in the parentheses.
  providerDownWithError:
    'The embedding provider is down: uploads will fail until it is back ({{error}}).',
  file: {
    label: 'Markdown file',
    // <choose> is the emphasised part.
    prompt: '<choose>Choose a file</choose> or drop it here',
    format: 'Markdown (.md), UTF-8',
    remove: 'Remove file',
  },
  tenant: {
    label: 'Tenant',
    hint: 'Lowercase letters, digits and hyphens, 2–63 characters.',
  },
  title: {
    label: 'Title (optional)',
    placeholder: 'From the first # heading, else the file name',
  },
  advanced: 'Advanced',
  sourceKey: {
    label: 'Source key',
    hint: 'Identifies the document within the tenant; uploading the same one again replaces it.',
    placeholder: 'The file name',
  },
  force: { label: 'Force reindex', hint: 'Even if nothing changed.' },
  existing:
    'A document with this name already exists in {{tenant}}: uploading replaces it ({{name}}, updated {{when}}).',
  problem: {
    fileMissing: 'Choose a Markdown file.',
    notMarkdown: 'Choose a Markdown file (.md).',
    empty: 'The file is empty.',
    tooLarge: 'Larger than the {{limit}} limit.',
    tooLargeUnknown: 'The file is larger than the upload limit.',
    tenantMissing: 'Enter a tenant.',
    tenantInvalid: 'Lowercase letters, digits and hyphens, 2–63 characters.',
    providerFailed:
      'The embedding provider failed after retries. Nothing was stored; try again later.',
    cancelled:
      'Upload cancelled. If the API had already received the file it may still index it: check the list in a moment.',
  },
  cancel: 'Cancel',
  upload: 'Upload',
  replace: 'Replace',
  busy: 'Uploading and indexing…',
  toast: {
    upToDate: 'Already up to date: nothing changed.',
    upToDateHint: 'Use Force reindex to rebuild it anyway.',
    indexed: 'Indexed {{name}}: {{chunks}}',
    replaced: 'Replaced {{name}}: {{chunks}}',
    chunks_one: '{{count}} chunk',
    chunks_other: '{{count}} chunks',
  },
}

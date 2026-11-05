/** A lazy chunk that is gone: typically the UI was deployed again since this page loaded. */
export function isChunkLoadError(error: unknown): boolean {
  if (!(error instanceof Error)) return false
  return (
    /dynamically imported module|Importing a module script failed|module script/i.test(
      error.message,
    ) || error.name === 'ChunkLoadError'
  )
}

/** Saves `content` as a file in the browser (a Blob and an object URL): nothing is uploaded. */
export function downloadFile(name: string, content: string, type: string): void {
  const url = URL.createObjectURL(new Blob([content], { type }))
  const link = document.createElement('a')
  link.href = url
  link.download = name
  link.rel = 'noopener'
  document.body.append(link)
  link.click()
  link.remove()
  // After the click has been handled: some browsers read the URL asynchronously.
  setTimeout(() => {
    URL.revokeObjectURL(url)
  }, 0)
}

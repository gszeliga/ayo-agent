import { lazy, Suspense, useState, type ComponentProps } from 'react'

// The dialog and its form controls are loaded on first open: most visits never upload.
const UploadDialog = lazy(() =>
  import('./UploadDialog').then((module) => ({ default: module.UploadDialog })),
)

type Props = ComponentProps<typeof UploadDialog>

/** UploadDialog, loaded when first opened and kept mounted after (so it can animate out). */
export function LazyUploadDialog(props: Props) {
  const [loaded, setLoaded] = useState(props.open)
  if (props.open && !loaded) setLoaded(true)
  if (!loaded) return null
  return (
    <Suspense fallback={null}>
      <UploadDialog {...props} />
    </Suspense>
  )
}

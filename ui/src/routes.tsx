import { lazy, Suspense } from 'react'
import { Navigate, Route, Routes } from 'react-router'

import { Skeleton } from '@/components/ui/skeleton'
import { RequireConnection } from '@/connection/RequireConnection'
import { DocumentsPage } from '@/documents/DocumentsPage'
import { AppShell } from '@/layout/AppShell'
import { ConnectPage } from '@/pages/ConnectPage'
import { NotFoundPage } from '@/pages/NotFoundPage'
import { Placeholder } from '@/pages/Placeholder'
import { ROUTES } from '@/paths'

// The detail page (Markdown, tabs, the write actions and their dialogs) loads when a
// document is first opened, keeping the main bundle to the shell and the list.
const DocumentPage = lazy(() =>
  import('@/document/DocumentPage').then((module) => ({ default: module.DocumentPage })),
)

export function AppRoutes() {
  return (
    <Routes>
      <Route path={ROUTES.connect} element={<ConnectPage />} />
      <Route element={<RequireConnection />}>
        <Route element={<AppShell />}>
          <Route index element={<Navigate to={ROUTES.documents} replace />} />
          <Route path={ROUTES.documents} element={<DocumentsPage />} />
          <Route
            path={ROUTES.document}
            element={
              <Suspense fallback={<Skeleton aria-label="Loading document" className="h-40" />}>
                <DocumentPage />
              </Suspense>
            }
          />
          <Route
            path={ROUTES.settings}
            element={<Placeholder title="Indexing settings" step="U8" />}
          />
          <Route path="*" element={<NotFoundPage />} />
        </Route>
      </Route>
    </Routes>
  )
}

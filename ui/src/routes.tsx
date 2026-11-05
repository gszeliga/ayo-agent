import { Navigate, Route, Routes } from 'react-router'

import { RequireConnection } from '@/connection/RequireConnection'
import { DocumentsPage } from '@/documents/DocumentsPage'
import { AppShell } from '@/layout/AppShell'
import { ConnectPage } from '@/pages/ConnectPage'
import { NotFoundPage } from '@/pages/NotFoundPage'
import { Placeholder } from '@/pages/Placeholder'
import { ROUTES } from '@/paths'

export function AppRoutes() {
  return (
    <Routes>
      <Route path={ROUTES.connect} element={<ConnectPage />} />
      <Route element={<RequireConnection />}>
        <Route element={<AppShell />}>
          <Route index element={<Navigate to={ROUTES.documents} replace />} />
          <Route path={ROUTES.documents} element={<DocumentsPage />} />
          <Route path={ROUTES.document} element={<Placeholder title="Document" step="U5" />} />
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

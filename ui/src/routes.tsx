import { lazy, Suspense } from 'react'
import { Navigate, Route, Routes } from 'react-router'

import { Skeleton } from '@/components/ui/skeleton'
import { RequireConnection } from '@/connection/RequireConnection'
import { DocumentsPage } from '@/documents/DocumentsPage'
import { AppShell } from '@/layout/AppShell'
import { ConnectPage } from '@/pages/ConnectPage'
import { NotFoundPage } from '@/pages/NotFoundPage'
import { ROUTES } from '@/paths'

// The detail page (Markdown, tabs, the write actions and their dialogs) loads when a
// document is first opened, keeping the main bundle to the shell and the list.
const DocumentPage = lazy(() =>
  import('@/document/DocumentPage').then((module) => ({ default: module.DocumentPage })),
)
// Likewise the settings page: visited rarely.
const SettingsPage = lazy(() =>
  import('@/settings/SettingsPage').then((module) => ({ default: module.SettingsPage })),
)
// And the test search page: a diagnosis tool.
const SearchPage = lazy(() =>
  import('@/search/SearchPage').then((module) => ({ default: module.SearchPage })),
)
// And the test chat: the cases list, a case's conversation and its inspector.
const ChatPage = lazy(() =>
  import('@/chat/ChatPage').then((module) => ({ default: module.ChatPage })),
)
const NoCaseSelected = lazy(() =>
  import('@/chat/ChatPage').then((module) => ({ default: module.NoCaseSelected })),
)
const NewConversation = lazy(() =>
  import('@/chat/NewConversation').then((module) => ({ default: module.NewConversation })),
)
const CaseView = lazy(() =>
  import('@/chat/CaseView').then((module) => ({ default: module.CaseView })),
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
            element={
              <Suspense fallback={<Skeleton aria-label="Loading settings" className="h-40" />}>
                <SettingsPage />
              </Suspense>
            }
          />
          <Route
            path={ROUTES.search}
            element={
              <Suspense fallback={<Skeleton aria-label="Loading search" className="h-40" />}>
                <SearchPage />
              </Suspense>
            }
          />
          <Route
            path={ROUTES.chat}
            element={
              <Suspense fallback={<Skeleton aria-label="Loading chat" className="h-40" />}>
                <ChatPage />
              </Suspense>
            }
          >
            <Route index element={<NoCaseSelected />} />
            <Route path={ROUTES.chatNew} element={<NewConversation />} />
            <Route path={ROUTES.chatCase} element={<CaseView />} />
          </Route>
          <Route path="*" element={<NotFoundPage />} />
        </Route>
      </Route>
    </Routes>
  )
}

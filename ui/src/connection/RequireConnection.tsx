import { Navigate, Outlet, useLocation } from 'react-router'

import { useConnection } from './context'

/** Routes behind it need a connection; without one, go to /connect and come back after. */
export function RequireConnection() {
  const { connection } = useConnection()
  const location = useLocation()
  if (connection === null) {
    const next = location.pathname + location.search
    return <Navigate to={`/connect?next=${encodeURIComponent(next)}`} replace />
  }
  return <Outlet />
}

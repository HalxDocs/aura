import { Navigate, Outlet } from 'react-router-dom'
import { useAuth } from '@/contexts/AuthContext'
import type { ReactNode } from 'react'

interface ProtectedRouteProps {
  /** Direct content (element form), or omit to use <Outlet/> (layout form). */
  children?: ReactNode
  requireAdmin?: boolean
  requireRole?: 'recruiter' | 'candidate'
}

export function ProtectedRoute({ children, requireAdmin = false, requireRole }: ProtectedRouteProps) {
  const { user, loading } = useAuth()

  if (loading) {
    return (
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', height: '100vh' }}>
        <p>Loading...</p>
      </div>
    )
  }

  if (!user) {
    return <Navigate to="/" replace />
  }

  if (requireAdmin && user.role !== 'admin') {
    return <Navigate to="/" replace />
  }

  // Roles are exclusive and live on the account. Recruiters pass recruiter
  // routes only (admins too — mirrors require_recruiter on the backend);
  // candidates (and the not-yet-picked "" state, mirroring
  // require_candidate) pass candidate routes. Users who have not picked a
  // role yet are sent to the picker from a recruiter route.
  const canRecruit = user.role === 'recruiter' || user.role === 'admin'
  const isCandidateSide = user.role === '' || user.role === 'candidate' || user.role === 'admin'
  const allowed = requireRole === 'recruiter' ? canRecruit : isCandidateSide
  if (requireRole && !allowed) {
    const target = user.role === '' ? '/choose-role' : '/'
    return <Navigate to={target} replace />
  }

  // Layout form (no children): the gate renders its matched child routes.
  return <>{children ?? <Outlet />}</>
}

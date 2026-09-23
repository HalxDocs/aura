import { Link } from 'react-router-dom'
import { useAuth } from '@/contexts/AuthContext'
import { initials } from '@/lib/dashboard-utils'
import '@/styles/aura-header.css'

export type HeaderLink =
  | 'dashboard'
  | 'new-interview'
  | 'my-interviews'
  | 'recruiter'
  | 'admin'
  | 'profile'

interface AppHeaderProps {
  /** Link rendered as active (bottom accent underline). */
  active?: HeaderLink
  /** Hide the link row (pages with their own in-content navigation). */
  hideLinks?: boolean
}

/**
 * Shared dashboard header: brand, role-appropriate links, and the user chip.
 * Roles are exclusive and live on the account, so the links derive from
 * user.role — no client-side mode state. Switching happens through the role
 * picker (/choose-role?switch=1), where the server enforces the usage locks.
 */
export function AppHeader({ active, hideLinks }: AppHeaderProps) {
  const { user, logout } = useAuth()

  const isAdmin = user?.role === 'admin'
  const isRecruiter = user?.role === 'recruiter' || isAdmin

  return (
    <nav className="nav aura-app-header" aria-label="Primary">
      <div className="nav-row">
        <Link to="/" className="brand" aria-label="Aura home">
          <span className="mark" aria-hidden="true"></span><span>Aura</span>
        </Link>
        {!hideLinks && (
          <div className="nav-links">
            {isRecruiter ? (
              <Link to="/recruiter" className={active === 'recruiter' ? 'active' : undefined}>Recruiter</Link>
            ) : (
              <>
                <Link to="/dashboard" className={active === 'dashboard' ? 'active' : undefined}>Dashboard</Link>
                <Link to="/interview" className={active === 'new-interview' ? 'active' : undefined}>New interview</Link>
                <Link to="/my-interviews" className={active === 'my-interviews' ? 'active' : undefined}>My interviews</Link>
              </>
            )}
            {isAdmin && (
              <Link to="/admin" className={active === 'admin' ? 'active' : undefined}>Admin</Link>
            )}
            {!isAdmin && user && (
              // Server-enforced usage locks decide whether switching is
              // actually allowed; the link is just the doorway to the picker.
              <Link to="/choose-role?switch=1">Switch role</Link>
            )}
            <Link
              to={isRecruiter ? '/profile/recruiter' : '/profile/candidate'}
              className={active === 'profile' ? 'active' : undefined}
            >
              Profile
            </Link>
          </div>
        )}
        <div className="nav-cta">
          {user?.role === '' && <Link to="/choose-role">Choose role</Link>}
          {user ? (
            <>
              <span className="user-chip">
                <span className="avatar" aria-hidden="true">{initials(user.name || user.email)}</span>
                <span className="name">{user.name || user.email}</span>
              </span>
              <button className="btn btn-ghost btn-sm" onClick={logout}>Sign out</button>
            </>
          ) : (
            <Link to="/login" className="btn btn-primary btn-sm">Sign in</Link>
          )}
        </div>
      </div>
    </nav>
  )
}

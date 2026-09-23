import { Link, useNavigate } from 'react-router-dom'
import { useAuth, type Mode } from '@/contexts/AuthContext'
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
 * Shared dashboard header: brand, mode-aware links, the candidate/recruiter
 * mode switcher, and the user chip. Every dashboard-style page used to copy
 * this markup; mode switching (Upwork-style) is client-side — setMode flips
 * localStorage + context state and routes to that mode's home, no API call.
 */
export function AppHeader({ active, hideLinks }: AppHeaderProps) {
  const { user, mode, setMode, logout } = useAuth()
  const navigate = useNavigate()

  const isAdmin = user?.role === 'admin'
  // Dual roles: admin, or anyone holding the one-way is_recruiter grant.
  const canRecruit = isAdmin || user?.role === 'recruiter' || !!user?.is_recruiter

  const switchTo = (next: Mode) => {
    if (next === mode) return
    setMode(next)
    navigate(next === 'recruiter' ? '/recruiter' : '/dashboard')
  }

  return (
    <nav className="nav aura-app-header" aria-label="Primary">
      <div className="nav-row">
        <Link to="/" className="brand" aria-label="Aura home">
          <span className="mark" aria-hidden="true"></span><span>Aura</span>
        </Link>
        {!hideLinks && (
          <div className="nav-links">
            <Link to="/dashboard" className={active === 'dashboard' ? 'active' : undefined}>Dashboard</Link>
            <Link to="/interview" className={active === 'new-interview' ? 'active' : undefined}>New interview</Link>
            <Link to="/my-interviews" className={active === 'my-interviews' ? 'active' : undefined}>My interviews</Link>
            {canRecruit ? (
              <Link to="/recruiter" className={active === 'recruiter' ? 'active' : undefined}>Recruiter</Link>
            ) : (
              // Flag-less candidates: the grant path still exists (Landing's
              // "Switch role"), but only reachable from there — keep an
              // affordance in every dashboard header too.
              user?.role === 'candidate' && (
                <Link to="/choose-role?switch=1">Become a recruiter</Link>
              )
            )}
            {isAdmin && (
              <Link to="/admin" className={active === 'admin' ? 'active' : undefined}>Admin</Link>
            )}
            <Link
              to={mode === 'recruiter' ? '/profile/recruiter' : '/profile/candidate'}
              className={active === 'profile' ? 'active' : undefined}
            >
              Profile
            </Link>
          </div>
        )}
        <div className="nav-cta">
          {/* Toggle buttons, not tabs: there is no tabpanel for tab semantics. */}
          {canRecruit && (
            <div className="nav-mode" role="group" aria-label="Active role">
              <button
                type="button"
                aria-pressed={mode === 'candidate'}
                className={mode === 'candidate' ? 'active' : undefined}
                onClick={() => switchTo('candidate')}
              >
                Candidate
              </button>
              <button
                type="button"
                aria-pressed={mode === 'recruiter'}
                className={mode === 'recruiter' ? 'active' : undefined}
                onClick={() => switchTo('recruiter')}
              >
                Recruiter
              </button>
            </div>
          )}
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

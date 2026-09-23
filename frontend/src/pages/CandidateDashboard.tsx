import { useEffect, useState } from 'react'
import axios from 'axios'
import { Link, useNavigate } from 'react-router-dom'
import {
  getCandidateProfile,
  listMySessions,
  startInterviewFromProfile,
  apiErrorMessage,
  type CandidateProfile,
  type SessionSummary,
} from '@/api/client'
import { PageShell } from '@/components/layout/PageShell'
import { recPill, statusPill, formatDate } from '@/lib/dashboard-utils'
import { useAuth } from '@/contexts/AuthContext'
import { Toaster } from '@/components/ui/toaster'
import { useToast } from '@/hooks/use-toast'
import { usePageMeta } from '@/hooks/use-page-meta'

/**
 * Candidate home: the post-login landing point (Landing redirects here).
 * The recruiter side has RecruiterDashboard; this is the candidate counterpart
 * — greeting, where-you-stand stats, the most recent sessions, and the
 * one-click start that a stored resume enables.
 */
export function CandidateDashboard() {
  usePageMeta("Dashboard — Aura")
  const { user } = useAuth()
  const navigate = useNavigate()
  const { toast } = useToast()
  const [profile, setProfile] = useState<CandidateProfile | null>(null)
  const [sessions, setSessions] = useState<SessionSummary[] | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [starting, setStarting] = useState(false)

  useEffect(() => {
    let cancelled = false
    // Both loads are optional-ish: a missing profile just means no
    // completeness stat and no one-click start.
    getCandidateProfile()
      .then(p => { if (!cancelled) setProfile(p) })
      .catch(() => { /* leave profile null */ })
    listMySessions()
      .then(data => { if (!cancelled) setSessions(data) })
      .catch(err => {
        if (cancelled) return
        if (err?.response?.status === 401 || err?.response?.status === 403) {
          navigate('/', { replace: true })
          return
        }
        setError(apiErrorMessage(err, 'Failed to load your interviews.'))
      })
    return () => { cancelled = true }
  }, [navigate])

  const completed = (sessions ?? []).filter(s => s.status === 'completed')
  const scored = completed.filter(s => s.overall_score !== null)
  const latestScored = scored[0]
  const recent = (sessions ?? []).slice(0, 5)

  // Same 0–100% completeness signal the profile page implies: headline +
  // skills + one experience entry are the minimum a useful interview needs.
  const profileFields = profile
    ? [
        profile.headline.trim(),
        profile.skills.length > 0 ? 'x' : '',
        profile.experience.length > 0 ? 'x' : '',
        profile.summary.trim(),
        profile.location.trim(),
      ]
    : []
  const filled = profileFields.filter(v => v).length
  const completeness = profile ? Math.round((filled / profileFields.length) * 100) : 0

  const startInterview = async () => {
    setStarting(true)
    try {
      const data = await startInterviewFromProfile()
      navigate(`/interview?session=${data.session_id}`, { replace: true })
    } catch (err) {
      const notFound = axios.isAxiosError(err) && err.response?.status === 404
      toast({
        title: 'Could not start',
        description: notFound
          ? 'No resume on your profile yet — add one on the profile page.'
          : apiErrorMessage(err, 'Could not start an interview from your saved resume.'),
        variant: 'destructive',
      })
      setStarting(false)
    }
  }

  const firstName = (user?.name || '').split(' ')[0]

  return (
    <PageShell active="dashboard" footer={false}>
      <div className="aura-dashboard-page">
        <div className="container">
          <header className="page-head">
            <span className="page-eyebrow"><span className="lit">Candidate</span>· Dashboard</span>
            <h1 className="page-h1">
              {firstName ? <>Welcome back, <em>{firstName}</em>.</> : <>Your <em>practice space.</em></>}
            </h1>
            <p className="lede">
              Run mock interviews against your resume and keep an eye on your progress — recruiters
              never see this side.
            </p>
            <div style={{ display: 'flex', gap: 12, flexWrap: 'wrap', marginTop: 18 }}>
              {profile?.resume_stored ? (
                <button className="btn btn-primary" onClick={startInterview} disabled={starting}>
                  {starting
                    ? <><span className="spinner" /> Preparing…</>
                    : <>Start a new interview<svg className="arrow" viewBox="0 0 16 16" fill="none" aria-hidden="true"><path d="M3 8h10m-4-4 4 4-4 4" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round"/></svg></>}
                </button>
              ) : (
                <Link to="/interview" className="btn btn-primary">
                  Start a new interview<svg className="arrow" viewBox="0 0 16 16" fill="none" aria-hidden="true"><path d="M3 8h10m-4-4 4 4-4 4" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round"/></svg>
                </Link>
              )}
              <Link to="/profile/candidate" className="btn btn-ghost">Update profile</Link>
            </div>
          </header>

          {error && <div className="error-banner" role="alert">{error}</div>}

          <div className="stats-bar" role="group" aria-label="Your statistics">
            <div className="stat-card">
              <div className="stat-label">Interviews</div>
              <div className="stat-value">{sessions ? sessions.length : '—'}</div>
              <div className="stat-foot">{completed.length} completed</div>
            </div>
            <div className="stat-card">
              <div className="stat-label">Latest score</div>
              <div className="stat-value">{latestScored ? latestScored.overall_score : '—'}</div>
              <div className="stat-foot">
                {latestScored?.recommendation ?? 'No scored interviews yet'}
              </div>
            </div>
            <div className="stat-card">
              <div className="stat-label">Profile</div>
              <div className="stat-value">{profile ? `${completeness}%` : '—'}</div>
              <div className="stat-foot">
                {profile
                  ? completeness < 100
                    ? 'Complete it for sharper questions'
                    : 'Ready — one-click starts enabled'
                  : 'Set up your profile'}
              </div>
            </div>
          </div>

          <section aria-label="Recent interviews">
            <div className="section-head" style={{ display: 'flex', alignItems: 'baseline', justifyContent: 'space-between', gap: 16 }}>
              <h2 className="section-title" style={{ margin: 0 }}>Recent interviews</h2>
              {(sessions?.length ?? 0) > 0 && (
                <Link to="/my-interviews" className="back-link">View all →</Link>
              )}
            </div>

            {sessions === null && !error ? (
              <div className="card">
                <div className="loading-state" role="status" aria-live="polite" style={{ minHeight: 240 }}>
                  <div className="spinner" aria-hidden="true"></div>
                  <span>Loading your interviews…</span>
                </div>
              </div>
            ) : recent.length === 0 ? (
              <div className="card">
                <div className="empty">
                  <h3>No interviews yet</h3>
                  <p>Upload your resume and run your first mock interview — it takes about 10 minutes.</p>
                  <div className="empty-cta">
                    <Link to="/interview" className="btn btn-primary">Start your first interview</Link>
                  </div>
                </div>
              </div>
            ) : (
              <div className="card table-scroll">
                <table className="table">
                  <thead>
                    <tr>
                      <th scope="col">Date</th>
                      <th scope="col">Candidate</th>
                      <th scope="col">Score</th>
                      <th scope="col">Recommendation</th>
                      <th scope="col">Status</th>
                      <th scope="col" style={{ textAlign: 'right' }}>Actions</th>
                    </tr>
                  </thead>
                  <tbody>
                    {recent.map(s => {
                      const rec = recPill(s.recommendation)
                      const status = statusPill(s.status)
                      const canView = s.status === 'completed'
                      return (
                        <tr key={s.session_id} onClick={() => canView && navigate(`/my-interviews/${s.session_id}`)}>
                          <td className="num">{formatDate(s.created_at)}</td>
                          <td>{s.candidate_name}</td>
                          <td className="num">{s.overall_score ?? <span className="muted">—</span>}</td>
                          <td><span className={rec.cls}><span className="dot"></span>{rec.text}</span></td>
                          <td><span className={status.cls}><span className="dot"></span>{status.text}</span></td>
                          <td style={{ textAlign: 'right' }}>
                            {canView ? (
                              <Link
                                to={`/my-interviews/${s.session_id}`}
                                className="btn btn-ghost btn-sm"
                                onClick={e => e.stopPropagation()}
                              >
                                View
                              </Link>
                            ) : (
                              <span className="muted">—</span>
                            )}
                          </td>
                        </tr>
                      )
                    })}
                  </tbody>
                </table>
              </div>
            )}
          </section>
        </div>
      </div>
      <Toaster />
    </PageShell>
  )
}

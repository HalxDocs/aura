import { useEffect, useState } from 'react'
import { Link, Navigate, useNavigate, useParams } from 'react-router-dom'
import { apiErrorMessage, getInvitePreview, startInvite, getToken, type InvitePreview as InvitePreviewData, type InterviewPlan } from '@/api/client'
import { useAuth } from '@/contexts/AuthContext'
import { InterviewAgent } from '@/components/voice/InterviewAgent'
import { Toaster } from '@/components/ui/toaster'
import { useToast } from '@/hooks/use-toast'
import { initials, formatDateTime, isExpired } from '@/lib/dashboard-utils'
import '@/styles/aura-pre.css'
import { usePageMeta } from '@/hooks/use-page-meta';

type Step = 'PREVIEW' | 'INTERVIEW'

export function InviteInterview() {
  usePageMeta("Interview invitation — Aura", { noindex: true })
  const { token } = useParams<{ token: string }>()
  const { user, login } = useAuth()
  const navigate = useNavigate()
  const { toast } = useToast()

  const [preview, setPreview] = useState<InvitePreviewData | null>(null)
  const [plan, setPlan] = useState<InterviewPlan | null>(null)
  const [sessionId, setSessionId] = useState<string | null>(null)
  const [livekitToken, setLivekitToken] = useState<string | null>(null)
  const [step, setStep] = useState<Step>('PREVIEW')
  const [loading, setLoading] = useState(true)
  const [starting, setStarting] = useState(false)
  const [error, setError] = useState<string | null>(null)
  // Bumped by the expiry timer below; without it a preview loaded before
  // expiry keeps saying "This link expires …" until some other re-render.
  const [, setExpiryTick] = useState(0)

  // Remember where to come back to after sign-in / role picking
  useEffect(() => {
    if (!user || user.role === '') {
      if (token) sessionStorage.setItem('aura_return_to', `/invite/${token}`)
    }
  }, [user, token])

  useEffect(() => {
    if (!user || !token) {
      // eslint-disable-next-line react-hooks/set-state-in-effect
      setLoading(false)
      return
    }
    let cancelled = false
    setLoading(true)
    getInvitePreview(token)
      .then(data => { if (!cancelled) setPreview(data) })
      .catch(err => {
        if (cancelled) return
        setError(apiErrorMessage(err, 'This invite link is not available.'))
      })
      .finally(() => { if (!cancelled) setLoading(false) })
    return () => { cancelled = true }
  }, [user, token])

  // A preview loaded before expiry never refetches on its own; flip the expiry
  // copy and disable Start the moment the deadline passes. Beyond setTimeout's
  // ~24.8-day ceiling (links can run 30 days) just skip the timer — a start
  // click still fails with the server's 410 toast.
  useEffect(() => {
    const ms = preview?.expires_at ? new Date(preview.expires_at).getTime() - Date.now() : 0
    if (ms <= 0 || ms > 2 ** 31 - 1) return
    const timer = setTimeout(() => setExpiryTick(t => t + 1), ms + 1000)
    return () => clearTimeout(timer)
  }, [preview])

  const begin = async () => {
    if (!token || !preview) return
    setStarting(true)
    setError(null)
    try {
      const started = await startInvite(token)
      const t = await getToken(started.session_id)
      setSessionId(started.session_id)
      setPlan(started.plan)
      setLivekitToken(t)
      setStep('INTERVIEW')
    } catch (err) {
      toast({
        title: 'Could not start the interview',
        description: apiErrorMessage(err, 'Please try again in a moment.'),
        variant: 'destructive',
      })
    } finally {
      setStarting(false)
    }
  }

  // ---- Not signed in: invite preview teaser + login buttons ----
  if (!user) {
    return (
      <div className="aura-pre-page">
        <div className="page-ambient" aria-hidden="true"></div>
        <div className="grid-mesh" aria-hidden="true"></div>
        <main className="container" style={{ maxWidth: 640, paddingTop: 60 }}>
          <span className="eyebrow"><span className="dot" aria-hidden="true"></span>Interview invitation</span>
          <h1 className="h1">Sign in to <em>begin.</em></h1>
          <p className="lede">
            You've been invited to a voice interview. Sign in with your account — your answers
            and report stay private between you and the recruiter.
          </p>
          <article className="card">
            <div className="card-body">
              <div className="btn-row">
                <button className="btn btn-primary" onClick={() => login('google')}>Continue with Google</button>
                <button className="btn btn-ghost" onClick={() => login('github')} style={{ marginLeft: 8 }}>Continue with GitHub</button>
              </div>
              <p style={{ marginTop: 14, fontSize: 12, opacity: 0.6 }}>
                You'll return to this invite automatically after signing in.
              </p>
            </div>
          </article>
        </main>
        <Toaster />
      </div>
    )
  }

  // ---- Signed in but no role chosen yet ----
  if (user.role === '') {
    return <Navigate to="/choose-role" replace />
  }

  // ---- Live interview ----
  if (step === 'INTERVIEW' && livekitToken && sessionId && plan) {
    return (
      <InterviewAgent
        token={livekitToken}
        sessionId={sessionId}
        candidateName={plan.candidate_name}
        recordAudio
        onInterviewEnd={() => navigate(`/my-interviews/${sessionId}`, { replace: true })}
      />
    )
  }

  // ---- Preview ----
  const body = () => {
    if (loading) {
      return (
        <div className="loading-state" role="status" aria-live="polite" style={{ paddingTop: 40 }}>
          <div className="spinner" aria-hidden="true"></div>
          <span>Loading your invitation…</span>
        </div>
      )
    }
    if (error || !preview) {
      return (
        <div className="card" style={{ marginTop: 24 }}>
          <div className="empty">
            <h3>Invite unavailable</h3>
            <p>{error || 'This invite link is not valid.'}</p>
            <div className="empty-cta">
              <Link to="/" className="btn btn-primary">Go home</Link>
            </div>
          </div>
        </div>
      )
    }
    return (
      <>
        <article className="card" style={{ marginTop: 24 }}>
          <div className="card-body">
            <div className="preview-head">
              <div className="avatar">{initials(preview.recruiter_name || 'R')}</div>
              <div>
                <h2 className="name" style={{ margin: 0 }}>{preview.title}</h2>
                <div className="sub">
                  Voice interview with {preview.recruiter_name}
                  {preview.recruiter_company ? ` · ${preview.recruiter_company}` : ''}
                  {' '}· {preview.questions.length} questions
                </div>
              </div>
            </div>

            {preview.context && (
              <>
                <div className="hr" />
                <div className="label-row">About this role</div>
                <p style={{ margin: '8px 0 0', opacity: 0.8, fontSize: 14, lineHeight: 1.6 }}>{preview.context}</p>
              </>
            )}

            <div className="hr" />
            <div className="label-row">You'll be asked</div>
            <ol style={{ margin: '10px 0 0', paddingLeft: 20, lineHeight: 2 }}>
              {preview.questions.map((q, i) => <li key={i}>{q}</li>)}
            </ol>

            {preview.expires_at && (
              <p style={{ marginTop: 12, fontSize: 12, opacity: isExpired(preview.expires_at) ? 0.85 : 0.6 }}>
                {isExpired(preview.expires_at)
                  ? 'This link has expired — ask your recruiter for a fresh one.'
                  : `This link expires ${formatDateTime(preview.expires_at)}.`}
              </p>
            )}

            <div className="btn-row" style={{ marginTop: 22 }}>
              <button
                className="btn btn-primary"
                onClick={begin}
                disabled={starting || isExpired(preview.expires_at)}
              >
                {starting ? <><span className="spinner" /> Preparing…</> : (
                  <>
                    Start voice interview
                    <svg width="14" height="14" viewBox="0 0 16 16" fill="none">
                      <path d="M3 8h10m-4-4 4 4-4 4" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round"/>
                    </svg>
                  </>
                )}
              </button>
            </div>
            <p style={{ marginTop: 12, fontSize: 12, opacity: 0.6 }}>
              Your microphone is recorded so the recruiter can review the conversation. Everything stays private to your report.
            </p>
          </div>
        </article>
      </>
    )
  }

  return (
    <div className="aura-pre-page">
      <div className="page-ambient" aria-hidden="true"></div>
      <div className="grid-mesh" aria-hidden="true"></div>
      <main className="container" style={{ maxWidth: 760 }}>
        <span className="eyebrow"><span className="dot" aria-hidden="true"></span>Interview invitation</span>
        <h1 className="h1">Ready when <em>you are.</em></h1>
        {body()}
      </main>
      <Toaster />
    </div>
  )
}

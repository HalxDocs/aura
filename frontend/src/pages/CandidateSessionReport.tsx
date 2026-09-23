import { useEffect, useState } from 'react'
import type { KeyboardEvent } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'
import { getMySessionDetail, type SessionDetail, type TranscriptEntryRead } from '@/api/client'
import { ReportView } from '@/components/interview/ReportView'
import { PageShell } from '@/components/layout/PageShell'
import '@/styles/aura-dashboard.css'
import { usePageMeta } from '@/hooks/use-page-meta';

// WAI-ARIA tabs pattern: click activates, arrow keys/Home/End move both focus
// and selection (selection follows focus), and only the active tab is in the
// tab order (roving tabindex).
const TABS = [
  { key: 'report', label: 'Report' },
  { key: 'transcript', label: 'Transcript' },
] as const

export function CandidateSessionReport() {
  usePageMeta("Interview report — Aura")
  const navigate = useNavigate()
  const { sessionId } = useParams<{ sessionId: string }>()
  const [data, setData] = useState<SessionDetail | null>(null)
  const [tab, setTab] = useState<'report' | 'transcript'>('report')
  const [error, setError] = useState<string | null>(null)

  function onTablistKeyDown(e: KeyboardEvent<HTMLDivElement>) {
    const idx = TABS.findIndex(t => t.key === tab)
    let next: number
    if (e.key === 'ArrowRight' || e.key === 'ArrowDown') next = (idx + 1) % TABS.length
    else if (e.key === 'ArrowLeft' || e.key === 'ArrowUp') next = (idx + TABS.length - 1) % TABS.length
    else if (e.key === 'Home') next = 0
    else if (e.key === 'End') next = TABS.length - 1
    else return
    e.preventDefault()
    setTab(TABS[next].key)
    document.getElementById(`tab-${TABS[next].key}`)?.focus()
  }

  useEffect(() => {
    if (!sessionId) return
    let cancelled = false
    // eslint-disable-next-line react-hooks/set-state-in-effect
    setData(null)
    setError(null)
    getMySessionDetail(sessionId)
      .then(r => { if (!cancelled) setData(r) })
      .catch(err => {
        if (cancelled) return
        console.error('Failed to load session report:', {
          sessionId,
          status: err?.response?.status,
          message: err?.message
        })
        if (err?.response?.status === 401 || err?.response?.status === 403) {
          navigate('/', { replace: true })
          return
        }
        if (err?.response?.status === 404) {
          setError('This report is not available yet.')
          return
        }
        setError('Failed to load the report. Please try again.')
      })
    return () => { cancelled = true }
  }, [sessionId, navigate])

  if (error) {
    return (
      <PageShell hideLinks>
        <div className="container">
          <div className="page-head">
            <span className="page-eyebrow"><span className="lit">Report</span></span>
            <h1 className="page-h1">Report not available</h1>
          </div>
          <div className="error-banner" role="alert">{error}</div>
          <Link to="/my-interviews" className="btn btn-ghost" style={{ marginTop: 12 }}>
            ← Back to my interviews
          </Link>
        </div>
      </PageShell>
    )
  }

  if (!data) {
    return (
      <PageShell hideLinks>
        <div className="container">
          <div className="loading-state" role="status" aria-live="polite">
            <div className="spinner" aria-hidden="true"></div>
            <span>Loading report…</span>
          </div>
        </div>
      </PageShell>
    )
  }

  return (
    <PageShell active="my-interviews">
      <div className="container">
        {/* The page's <h1>: ReportView below is embedded with headingLevel="h2"
            and the tabpanels carry their own <h2>s, so every tab state keeps
            exactly one heading level per page (axe page-has-heading-one). */}
        <h1 className="sr-only">Interview report</h1>
        <Link to="/my-interviews" className="back-link">
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
            <polyline points="15 18 9 12 15 6"/>
          </svg>
          Back to my interviews
        </Link>

        <div className="filter-bar" style={{ marginBottom: 20 }}>
          <div role="tablist" aria-label="Interview artifacts" style={{ display: 'flex', gap: 12 }} onKeyDown={onTablistKeyDown}>
            {TABS.map(t => (
              <button
                key={t.key}
                className={`btn ${tab === t.key ? 'btn-primary' : 'btn-ghost'}`}
                role="tab"
                id={`tab-${t.key}`}
                aria-selected={tab === t.key}
                aria-controls={`${t.key}-panel`}
                tabIndex={tab === t.key ? 0 : -1}
                onClick={() => setTab(t.key)}
              >{t.label}</button>
            ))}
          </div>
        </div>
        {tab === 'report' && data.report ? (
          <div role="tabpanel" id="report-panel" aria-labelledby="tab-report">
            <ReportView
              report={data.report}
              sessionId={sessionId!}
              onDone={() => navigate('/my-interviews')}
              doneLabel="Back to my interviews"
              completedAt={data.completed_at}
              headingLevel="h2"
            />
          </div>
        ) : tab === 'report' ? (
          <div role="tabpanel" id="report-panel" aria-labelledby="tab-report" className="card">
            <div className="empty">
              <h2 className="section-title">Report</h2>
              <h3>Report not ready</h3>
              <p>The report will appear once the interview is complete.</p>
            </div>
          </div>
        ) : data.transcript && data.transcript.length > 0 ? (
          <div role="tabpanel" id="transcript-panel" aria-labelledby="tab-transcript" className="card">
            <h2 className="section-title">Transcript</h2>
            <div className="transcript" role="log" aria-label="Interview transcript">
              {data.transcript.map((entry: TranscriptEntryRead, index: number) => (
                <div key={index} className={`transcript-line ${entry.speaker === 'Interviewer' ? 'assistant' : ''}`}>
                  <span className="who">{entry.speaker} · {formatTimestamp(entry.timestamp_s)}</span>
                  <span className="text">{entry.text}</span>
                </div>
              ))}
            </div>
          </div>
        ) : (
          <div role="tabpanel" id="transcript-panel" aria-labelledby="tab-transcript" className="card">
            <div className="empty">
              <h2 className="section-title">Transcript</h2>
              <h3>No transcript available</h3>
              <p>The transcript will appear after the interview concludes.</p>
            </div>
          </div>
        )}
      </div>
    </PageShell>
  )
}

function formatTimestamp(seconds: number): string {
  const minutes = Math.floor(seconds / 60)
  const remainder = Math.floor(seconds % 60)
  return `${String(minutes).padStart(2, '0')}:${String(remainder).padStart(2, '0')}`
}

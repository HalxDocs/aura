import { Link } from 'react-router-dom'
import { PageShell } from '@/components/layout/PageShell'
import '@/styles/aura-dashboard.css'
import { usePageMeta } from '@/hooks/use-page-meta';

/** Full-page 404 for any unmatched URL. Reuses the dashboard design system. */
export function NotFound() {
  usePageMeta("Page not found — Aura", { noindex: true })
  return (
    <PageShell>
      <div className="container" style={{ paddingTop: 96, paddingBottom: 96 }}>
        <div style={{ maxWidth: 560, margin: '0 auto', textAlign: 'center' }}>
          <span
            className="page-eyebrow"
            style={{ justifyContent: 'center', display: 'flex' }}
          >
            <span className="lit">Error 404</span>· Page not found
          </span>
          <h1
            className="page-h1"
            style={{ fontSize: 'clamp(56px, 10vw, 96px)', lineHeight: 1, margin: '12px 0 8px' }}
          >
            4<em>0</em>4
          </h1>
          <p className="lede" style={{ marginBottom: 32 }}>
            The page you're looking for doesn't exist, was moved, or you may have
            followed a broken link.
          </p>
          <div style={{ display: 'flex', gap: 12, justifyContent: 'center', flexWrap: 'wrap' }}>
            <Link to="/" className="btn btn-primary">
              Back to home
            </Link>
            <Link to="/my-interviews" className="btn btn-ghost">
              My interviews
            </Link>
          </div>
        </div>
      </div>
    </PageShell>
  )
}

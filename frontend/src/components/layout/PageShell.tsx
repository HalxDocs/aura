import { Link } from 'react-router-dom'
import { AppHeader, type HeaderLink } from './AppHeader'

/**
 * Shared app-page shell: one ambient backdrop, one header, one footer.
 *
 * Before this existed every page rendered its own root div + ambient layers +
 * header — and ReportView shipped a second branded nav inside pages that
 * already had one — which is how the app accumulated doubled headers and
 * stray marketing chrome. Pages now render their content inside this shell;
 * page sheets style only their content.
 *
 * `active`/`hideLinks` pass through to AppHeader. `hideLinks` doubles as the
 * "minimal header" variant (brand + user + Sign out) used by flow pages where
 * the links row would invite navigating away mid-flow.
 */
export function PageShell({
  children,
  active,
  hideLinks,
  footer = true,
}: {
  children: React.ReactNode
  active?: HeaderLink
  hideLinks?: boolean
  footer?: boolean
}) {
  return (
    <div className="aura-page">
      <div className="page-ambient" aria-hidden="true"></div>
      <div className="grid-mesh" aria-hidden="true"></div>

      <AppHeader active={active} hideLinks={hideLinks} />

      <main>{children}</main>

      {footer && (
        <footer className="aura-page-footer">
          <span>© 2026 Aura · Built on LiveKit &amp; Pydantic AI</span>
          <span>
            <Link to="/">Landing</Link>
          </span>
        </footer>
      )}
    </div>
  )
}

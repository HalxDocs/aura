import { useState, type CSSProperties } from "react";
import { downloadArtifact } from "@/api/client";
import { recPill } from "@/lib/dashboard-utils";
import "@/styles/aura-report.css";

interface ReportViewProps {
  report: { candidate_name: string; overall_score: number; recommendation: string; summary: string; strengths: string[]; weaknesses: string[]; section_grades: { section_name: string; score: number; comments: string }[] };
  sessionId: string;
  /** Called by the single exit button; the host page decides the destination. */
  onDone: () => void;
  /** Exit-button label — must describe where onDone actually goes. */
  doneLabel?: string;
  /** Real completion timestamp from the session; shown in the page head. */
  completedAt?: string | null;
  recruiterActions?: React.ReactNode;
  headingLevel?: "h1" | "h2";
}

/**
 * The interview report document. Page chrome (header, ambient backdrop,
 * footer) belongs to the host page's PageShell — this component used to ship
 * its own sticky nav and brand footer, which stacked a second header onto
 * every page that embedded it.
 */
export function ReportView({ report, sessionId, onDone, doneLabel = "Back", completedAt, recruiterActions, headingLevel = "h1" }: ReportViewProps) {
  const HeadingTag = headingLevel;
  const [downloading, setDownloading] = useState<'pdf' | 'transcript' | null>(null);
  const [downloadError, setDownloadError] = useState<string | null>(null);

  const initials = report.candidate_name.split(" ").map(s => s[0]).slice(0, 2).join("").toUpperCase() || "C";
  const rec = recPill(report.recommendation as never);
  const overallPct = Math.max(0, Math.min(100, report.overall_score));
  const reportDate = completedAt
    ? new Date(completedAt).toLocaleDateString(undefined, { year: "numeric", month: "short", day: "numeric" })
    : null;

  // Downloads go through the backend artifacts (GET /download/{id}/{type}):
  // the PDF is the server-rendered report document, shared with what gets
  // archived to MinIO — the previous html2canvas screenshot export sliced the
  // dark dashboard into pages and cut through text mid-line.
  async function handleDownload(fileType: 'pdf' | 'transcript') {
    setDownloadError(null);
    setDownloading(fileType);
    try {
      await downloadArtifact(sessionId, fileType, report.candidate_name);
    } catch {
      setDownloadError(`Could not download the ${fileType === 'pdf' ? 'PDF report' : 'transcript'}. Please try again.`);
    } finally {
      setDownloading(null);
    }
  }

  return (
    <div className="aura-report-page">
      {downloadError && (
        <div className="download-error" role="alert" style={{ position: "relative", zIndex: 10, margin: "12px auto 0", maxWidth: 1200 }}>{downloadError}</div>
      )}

      <div>
        <section className="container" aria-label="Interview report">
          {/* Page head: the one download control lives here. The old layout
              scattered five (three dropdowns sharing one open state — they all
              opened at once — plus host-page buttons). */}
          <header className="page-head">
            <div>
              <span className="page-eyebrow">
                <span className="lit">Interview Report</span>
                <span>·</span>
                <span>{reportDate ?? "In progress"}</span>
              </span>
              <HeadingTag className="page-h1">Interview <em>Result</em></HeadingTag>
            </div>
            <div className="page-head-actions">
              <button className="btn btn-ghost" type="button" onClick={() => handleDownload('pdf')} disabled={downloading !== null}>
                <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
                  <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/>
                  <polyline points="7 10 12 15 17 10"/>
                  <line x1="12" y1="15" x2="12" y2="3"/>
                </svg>
                {downloading === 'pdf' ? "Preparing…" : "Download PDF"}
              </button>
              <button className="btn btn-ghost" type="button" onClick={() => handleDownload('transcript')} disabled={downloading !== null}>
                {downloading === 'transcript' ? "Preparing…" : "Transcript"}
              </button>
            </div>
          </header>

          {/* Hero: candidate identity + score ring */}
          <section className="hero" aria-label="Candidate summary">
            <article className="card glow card-pad">
              <div className="candidate-head">
                <div className="avatar" aria-hidden="true">{initials}</div>
                <div className="candidate-id">
                  <h2 className="candidate-name">{report.candidate_name}</h2>
                  <div className="candidate-role">Candidate · Voice interview · Aura</div>
                </div>
              </div>

              <div className="meta-row" role="group" aria-label="Interview metadata">
                <div className="meta-cell">
                  <div className="meta-label">Date</div>
                  <div className="meta-value">{reportDate ?? "—"}</div>
                </div>
                <div className="meta-cell">
                  <div className="meta-label">Modality</div>
                  <div className="meta-value">Voice</div>
                </div>
                <div className="meta-cell">
                  <div className="meta-label">Agent</div>
                  <div className="meta-value">Aura</div>
                </div>
              </div>

              <div className="summary-block">
                <div className="summary-eyebrow">Overall performance summary</div>
                <p>{report.summary}</p>
              </div>
            </article>

            <article className="card glow score-card">
              <div className="score-card-head">
                <h3>Overall Score</h3>
                <span className={rec.cls}><span className="dot"></span>{rec.text}</span>
              </div>

              <div className="score-ring-wrap" aria-hidden="true">
                <div className="score-ring" style={{ "--p": overallPct } as CSSProperties}></div>
                <div className="score-center">
                  <div className="score-num">{report.overall_score}<span className="denom">/100</span></div>
                  <div className="score-band">{rec.text}</div>
                </div>
              </div>
            </article>
          </section>

          {/* Strengths / Areas for improvement */}
          <section className="section" aria-label="Strengths and watch-outs">
            <div className="two-col">
              <article className="card card-pad-tight">
                <div className="insight-head s">
                  <span className="icon-pip" aria-hidden="true">
                    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
                      <polyline points="20 6 9 17 4 12"/>
                    </svg>
                  </span>
                  <h3>Key strengths</h3>
                </div>
                <ul className="insight-list">
                  {report.strengths.map((s, i) => <li key={i}>{s}</li>)}
                </ul>
              </article>

              <article className="card card-pad-tight">
                <div className="insight-head w">
                  <span className="icon-pip" aria-hidden="true">
                    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
                      <circle cx="12" cy="12" r="9"/>
                      <line x1="12" y1="8" x2="12" y2="12"/>
                      <line x1="12" y1="16" x2="12.01" y2="16"/>
                    </svg>
                  </span>
                  <h3>Areas for improvement</h3>
                </div>
                <ul className="insight-list">
                  {report.weaknesses.map((w, i) => <li key={i}>{w}</li>)}
                </ul>
              </article>
            </div>
          </section>

          {/* Section breakdown */}
          <section className="section" aria-label="Section breakdown">
            <div className="section-head">
              <h2 className="section-title">Section breakdown</h2>
              <span className="section-sub">{report.section_grades.length} dimensions</span>
            </div>

            <article className="card">
              <div className="rubric">
                {report.section_grades.map((g, i) => {
                  const pct = Math.max(0, Math.min(100, g.score * 10));
                  return (
                    <div key={i} className="rubric-row">
                      <div className="rubric-name">
                        <span className="n">{g.section_name}</span>
                      </div>
                      <p className="rubric-evidence">{g.comments}</p>
                      <div className="rubric-meter">
                        <div className="rubric-meter-head">
                          <span className="score">{g.score}<span className="denom"> / 10</span></span>
                        </div>
                        <div className="meter" aria-hidden="true">
                          <i style={{ "--w": `${pct}%` } as CSSProperties}></i>
                        </div>
                        <div className="meter-foot">
                          <span>0</span><span>10</span>
                        </div>
                      </div>
                    </div>
                  );
                })}
              </div>
            </article>
          </section>

          {/* Action bar: exit (label = destination) + recruiter artifacts. The
              old "Back to Aura" / "New interview" labels described pages the
              button did not go to. */}
          <section className="action-bar" aria-label="Report actions">
            <div className="action-meta">
              <span>Generated by Aura</span>
              <span className="sep"></span>
              <span>{reportDate ?? "—"}</span>
              {recruiterActions && (
                <span className="recruiter-actions" style={{ marginLeft: 12, display: 'inline-flex', gap: 8, alignItems: 'center' }}>
                  {recruiterActions}
                </span>
              )}
            </div>
            <div className="action-set">
              <button className="btn btn-ghost" type="button" onClick={onDone}>
                <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
                  <line x1="19" y1="12" x2="5" y2="12"/>
                  <polyline points="12 19 5 12 12 5"/>
                </svg>
                {doneLabel}
              </button>
            </div>
          </section>
        </section>
      </div>
    </div>
  );
}

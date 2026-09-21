// Appended after vendor/axe.min.js (piped together via `eval --stdin`).
// Runs axe asynchronously and parks the result on window for a follow-up read.
;(function () {
  if (!window.axe) {
    window.__axeDone = true;
    window.__axeResult = { error: "axe not loaded" };
    return;
  }
  const summarize = (v) => ({
    id: v.id,
    impact: v.impact,
    help: v.help,
    tags: (v.tags || []).filter((t) => t.startsWith("wcag") || t === "best-practice" || t === "cat.forms" || t === "cat.name-role-value"),
    nodes: v.nodes.slice(0, 10).map((n) => ({
      target: (n.target || []).join(" "),
      html: (n.html || "").slice(0, 150),
      failure: (n.failureSummary || "").slice(0, 200),
    })),
    nodeCount: v.nodes.length,
  });
  window.axe
    .run(document, { resultTypes: ["violations", "incomplete"] })
    .then((r) => {
      window.__axeResult = {
        tool: "axe-core " + (window.axe.version || "4.x"),
        violations: r.violations.map(summarize),
        incomplete: r.incomplete.map(summarize),
        passes: r.passes.length,
      };
      window.__axeDone = true;
    })
    .catch((e) => {
      window.__axeResult = { error: String(e) };
      window.__axeDone = true;
    });
})();

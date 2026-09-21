// Page integrity + SEO/meta + performance extraction. Returns one JSON string.
(() => {
  const pick = (sel, attr) => {
    const el = document.querySelector(sel);
    return el ? el.getAttribute(attr || "content") : null;
  };
  const headings = Array.from(document.querySelectorAll("h1,h2,h3,h4,h5,h6")).map(
    (h) => h.tagName + ": " + (h.textContent || "").trim().slice(0, 80)
  );
  const links = Array.from(document.querySelectorAll("a[href]"))
    .map((a) => a.getAttribute("href"))
    .filter(Boolean);
  const buttons = Array.from(
    document.querySelectorAll('button,[role="button"],input[type="submit"]')
  ).map((b) => ({
    text: ((b.innerText || b.value || "") + "").trim().slice(0, 60),
    aria: b.getAttribute("aria-label"),
  }));
  const inputs = Array.from(document.querySelectorAll("input,select,textarea")).map((i) => ({
    type: i.type || null,
    name: i.name || i.id || null,
    hasLabel:
      (i.labels && i.labels.length > 0) ||
      !!i.getAttribute("aria-label") ||
      !!i.getAttribute("aria-labelledby") ||
      i.type === "hidden",
  }));
  const nav = performance.getEntriesByType("navigation")[0];
  const res = performance.getEntriesByType("resource");
  const round = (x) => (x == null ? null : Math.round(x));
  return JSON.stringify({
    title: document.title,
    lang: document.documentElement.lang || null,
    metaDescription: pick('meta[name="description"]'),
    viewport: pick('meta[name="viewport"]'),
    charset: document.characterSet,
    canonical: pick('link[rel="canonical"]', "href"),
    og: {
      title: pick('meta[property="og:title"]'),
      description: pick('meta[property="og:description"]'),
      image: pick('meta[property="og:image"]'),
    },
    favicon: !!document.querySelector('link[rel*="icon"]'),
    h1Count: document.querySelectorAll("h1").length,
    headings: headings.slice(0, 25),
    imgCount: document.images.length,
    imgNoAlt: Array.from(document.images).filter((i) => i.getAttribute("alt") === null).length,
    buttonsCount: buttons.length,
    buttonsUnnamed: buttons.filter((b) => !b.text && !b.aria).length,
    inputsCount: inputs.length,
    inputsNoLabel: inputs.filter((i) => !i.hasLabel).length,
    linkCount: links.length,
    links: Array.from(new Set(links)).slice(0, 80),
    domNodes: document.getElementsByTagName("*").length,
    bodyTextLen: ((document.body && document.body.innerText) || "").trim().length,
    perf: {
      ttfb: nav ? round(nav.responseStart - nav.startTime) : null,
      domContentLoaded: nav ? round(nav.domContentLoadedEventEnd - nav.startTime) : null,
      load: nav ? round(nav.loadEventEnd - nav.startTime) : null,
      requests: res.length,
      transferKB: Math.round(res.reduce((s, r) => s + (r.transferSize || 0), 0) / 1024),
      slowest: res
        .slice()
        .sort((a, b) => b.duration - a.duration)
        .slice(0, 5)
        .map((r) => ({
          name: r.name.split("?")[0].slice(-80),
          ms: Math.round(r.duration),
          kb: Math.round((r.transferSize || 0) / 1024),
        })),
    },
  });
})()

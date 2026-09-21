import { useEffect } from 'react';

/**
 * Per-route document metadata: tab title, meta description, og:title /
 * og:description, optional canonical URL and optional robots noindex.
 *
 * The SPA ships one static index.html, so without this every route shares the
 * landing's title/description (flagged by the web audit). Cleanup restores the
 * index.html defaults so navigating back to the landing is unchanged.
 */

const DEFAULT_TITLE = 'Aura — AI Interviewer';
const DEFAULT_DESCRIPTION =
  'Aura is an AI interviewer agent. Real-time voice interviews that probe deeper, evaluate fairer, and report faster.';

function upsertMeta(attr: 'name' | 'property', key: string, value: string | null) {
  const selector = `meta[${attr}="${key}"]`;
  let el = document.head.querySelector<HTMLMetaElement>(selector);
  if (value === null) {
    el?.remove();
    return;
  }
  if (!el) {
    el = document.createElement('meta');
    el.setAttribute(attr, key);
    document.head.appendChild(el);
  }
  el.setAttribute('content', value);
}

export function usePageMeta(
  title: string,
  opts: { description?: string; canonical?: string; noindex?: boolean } = {},
) {
  const { description, canonical, noindex } = opts;
  useEffect(() => {
    document.title = title;
    upsertMeta('name', 'description', description ?? DEFAULT_DESCRIPTION);
    upsertMeta('property', 'og:title', title);
    upsertMeta('property', 'og:description', description ?? DEFAULT_DESCRIPTION);

    if (canonical) {
      let link = document.head.querySelector<HTMLLinkElement>('link[rel="canonical"]');
      if (!link) {
        link = document.createElement('link');
        link.rel = 'canonical';
        document.head.appendChild(link);
      }
      link.href = canonical;
    }

    if (noindex) upsertMeta('name', 'robots', 'noindex');

    return () => {
      document.title = DEFAULT_TITLE;
      upsertMeta('name', 'description', DEFAULT_DESCRIPTION);
      upsertMeta('property', 'og:title', DEFAULT_TITLE);
      upsertMeta('property', 'og:description', DEFAULT_DESCRIPTION);
      if (canonical) document.head.querySelector('link[rel="canonical"]')?.remove();
      if (noindex) upsertMeta('name', 'robots', null);
    };
  }, [title, description, canonical, noindex]);
}

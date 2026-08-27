export type AkteKind = 'worker' | 'client';

export function akteHref(kind: AkteKind, id?: string | null) {
  if (!id) return '#';
  const url = new URL(window.location.href);
  url.searchParams.set('view', 'akte');
  url.searchParams.set('akte_kind', kind);
  url.searchParams.set('akte_id', String(id));
  url.searchParams.delete('people_kind');
  return `${url.pathname}${url.search}`;
}

export function openAkte(kind: AkteKind, id?: string | null) {
  if (!id) return;
  const href = akteHref(kind, id);
  window.history.pushState({ view: 'akte', akte_kind: kind, akte_id: String(id) }, '', href);
  window.dispatchEvent(new PopStateEvent('popstate'));
}

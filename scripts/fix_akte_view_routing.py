from pathlib import Path

p=Path('frontend/src/App.tsx')
s=p.read_text()
s=s.replace("  const initialView = (() => { const value = new URLSearchParams(window.location.search).get('view') as View | null; return value || 'dashboard'; })();\n  const [view, setView] = useState<View>(initialView);", "  const [view, setView] = useState<View>('dashboard');")
s=s.replace("    const syncView = () => { const value = new URLSearchParams(window.location.search).get('view') as View | null; setView(value || 'dashboard'); };\n    window.addEventListener('popstate', syncView);\n    return () => { window.removeEventListener('auth-lost', lost); window.removeEventListener('popstate', syncView); };", "    return () => window.removeEventListener('auth-lost', lost);")
old="""  const navigateTo = (next: View) => {
    setView(next);
    setMobileMenuOpen(false);
    const url = new URL(window.location.href);
    url.searchParams.set('view', next);
    if (next !== 'akte') { url.searchParams.delete('akte_kind'); url.searchParams.delete('akte_id'); }
    window.history.pushState({ view: next }, '', `${url.pathname}${url.search}${url.hash}`);
    window.requestAnimationFrame(() => window.scrollTo({ top: 0, behavior: 'smooth' }));
  };
"""
new="""  const navigateTo = (next: View) => {
    setView(next);
    setMobileMenuOpen(false);
    window.requestAnimationFrame(() => window.scrollTo({ top: 0, behavior: 'smooth' }));
  };
"""
if old not in s: raise SystemExit('App navigate marker not found')
s=s.replace(old,new,1)
p.write_text(s)

p=Path('frontend/src/viewRouting.ts')
s=p.read_text()
s=s.replace("  | 'operations';", "  | 'operations'\n  | 'akte';",1)
for role in ('admin','manager','worker','client'):
    marker="    'operations',\n  ])," if role!='client' else "    'messages',\n  ]),"
# Insert Akte into all role sets using stable role-specific last entries.
s=s.replace("    'operations',\n  ]),\n  manager:", "    'operations',\n    'akte',\n  ]),\n  manager:",1)
s=s.replace("    'operations',\n  ]),\n  worker:", "    'operations',\n    'akte',\n  ]),\n  worker:",1)
s=s.replace("    'ranking',\n  ]),\n  client:", "    'ranking',\n    'akte',\n  ]),\n  client:",1)
s=s.replace("    'messages',\n  ]),\n};", "    'messages',\n    'akte',\n  ]),\n};",1)
s=s.replace("  'operations',\n]);", "  'operations',\n  'akte',\n]);",1)
old="""function canonicalUrl(view: View) {
  const url = new URL(window.location.href);
  if (view === 'dashboard') url.searchParams.delete('view');
  else url.searchParams.set('view', view);
  return `${url.pathname}${url.search}${url.hash}`;
}
"""
new="""function canonicalUrl(view: View) {
  const url = new URL(window.location.href);
  if (view === 'dashboard') url.searchParams.delete('view');
  else url.searchParams.set('view', view);
  if (view !== 'akte') {
    url.searchParams.delete('akte_kind');
    url.searchParams.delete('akte_id');
  }
  return `${url.pathname}${url.search}${url.hash}`;
}
"""
if old not in s: raise SystemExit('viewRouting canonical marker not found')
s=s.replace(old,new,1)
p.write_text(s)

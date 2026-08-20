import { defineConfig, type Plugin } from 'vite';
import react from '@vitejs/plugin-react';
import { VitePWA } from 'vite-plugin-pwa';

const lazyAppFeatures = new Set([
  'Operations',
  'ScheduleV2',
  'AttendanceV3',
  'EmployeeHome',
  'PortalAccessPanel',
  'AdminHomeV4',
  'GlobalSearch',
  'DocumentCenterV5',
]);

/**
 * App.tsx is still a large legacy shell. Keep the source stable while making
 * two surgical build/dev transforms:
 * 1) wire its existing view state to the isolated browser-history hook;
 * 2) replace only heavy feature imports with lazy Suspense wrappers.
 */
function appShellTransforms(): Plugin {
  const prefix = '\0lazy-app-feature:';
  const viewStateMarker = "const [view, setView] = useState<View>('dashboard');";

  return {
    name: 'app-shell-transforms',
    enforce: 'pre',
    transform(code, id) {
      const normalizedId = id.replace(/\\/g, '/').split('?')[0];
      if (!normalizedId.endsWith('/src/App.tsx')) return null;
      if (!code.includes(viewStateMarker)) {
        this.error('App view-state marker changed; update app-shell-transforms before building.');
      }

      return {
        code: `import { useViewRouting } from './viewRouting';\n${code.replace(
          viewStateMarker,
          'const [view, setView] = useViewRouting(user?.role);',
        )}`,
        map: null,
      };
    },
    resolveId(source, importer) {
      const normalizedImporter = importer?.replace(/\\/g, '/').split('?')[0];
      if (!normalizedImporter?.endsWith('/src/App.tsx') || !source.startsWith('./')) return null;

      const feature = source.slice(2);
      return lazyAppFeatures.has(feature) ? `${prefix}${feature}` : null;
    },
    load(id) {
      if (!id.startsWith(prefix)) return null;
      const feature = id.slice(prefix.length);
      const modulePath = `/src/${feature}.tsx`;

      return `
        import React, { lazy, Suspense } from 'react';
        const Feature = lazy(() => import(${JSON.stringify(modulePath)}));
        export default function LazyAppFeature(props) {
          const fallback = React.createElement(
            'div',
            { className: 'loader', role: 'status', 'aria-live': 'polite' },
            React.createElement('p', null, 'Daten werden geladen …'),
          );
          return React.createElement(
            Suspense,
            { fallback },
            React.createElement(Feature, props),
          );
        }
      `;
    },
  };
}

/**
 * Production-only UI cleanup for legacy migration residue that is still stored
 * for audit purposes. We keep historical data in the backend but do not expose
 * internal WIW/sync identifiers in the day-to-day mobile UI.
 */
function productionUiPolish(): Plugin {
  const replaceRequired = (
    context: { error: (message: string) => never },
    code: string,
    from: string,
    to: string,
    label: string,
  ) => {
    if (!code.includes(from)) context.error(`Production UI marker changed: ${label}`);
    return code.replace(from, to);
  };

  return {
    name: 'production-ui-polish',
    enforce: 'pre',
    transform(code, id) {
      const normalizedId = id.replace(/\\/g, '/').split('?')[0];

      if (normalizedId.endsWith('/src/App.tsx')) {
        let next = code;
        next = replaceRequired(
          this,
          next,
          "const dateOnly = (input?: string) => (input ? new Date(input).toLocaleDateString('de-DE') : '–');",
          "const dateOnly = (input?: string) => (input ? new Date(input).toLocaleDateString('de-DE') : '–');\nconst cleanLegacyContractTitle = (title?: string) => String(title || '').replace(/\\s+LOCAL-WIW-[A-Z0-9-]+/gi, '').trim();",
          'legacy contract title helper',
        );
        next = replaceRequired(
          this,
          next,
          '    setWorkers(unpack(workerData));',
          "    setWorkers(unpack(workerData).filter((worker: any) => !String(worker.user_detail?.email || '').toLowerCase().endsWith('@sync.invalid')));",
          'people synthetic-worker filter',
        );
        next = next.split("{worker.user_detail?.name?.[0] || 'M'}").join("{worker.user_detail?.name?.[0]?.toUpperCase() || 'M'}");
        next = next.split('{position.name}').join("{position.name === 'WIW Einsatz' ? 'Einsatz' : position.name}");
        next = replaceRequired(
          this,
          next,
          '<b>{contract.title}</b>',
          '<b>{cleanLegacyContractTitle(contract.title)}</b>',
          'contract title display',
        );
        next = replaceRequired(
          this,
          next,
          '<IonBadge>{user.role}</IonBadge>',
          "<IonBadge>{user.role === 'admin' ? 'Administrator' : user.role === 'manager' ? 'Management' : user.role === 'worker' ? 'Mitarbeiter' : 'Kunde'}</IonBadge>",
          'profile role label',
        );
        next = replaceRequired(
          this,
          next,
          `  const navigateTo = (next: View) => {\n    setView(next);\n    setMobileMenuOpen(false);\n    window.requestAnimationFrame(() => window.scrollTo({ top: 0, behavior: 'smooth' }));\n  };`,
          `  const navigateTo = (next: View) => {\n    setView(next);\n    setMobileMenuOpen(false);\n    window.requestAnimationFrame(() => {\n      const content = document.querySelector('ion-content.app-content') as any;\n      if (content?.scrollToTop) void content.scrollToTop(0);\n      else window.scrollTo({ top: 0, behavior: 'auto' });\n    });\n  };`,
          'Ionic scroll reset',
        );
        return { code: next, map: null };
      }

      if (normalizedId.endsWith('/src/PremiumOperations.tsx')) {
        let next = code;
        const replacements: Array<[string, string]> = [
          ['WIW PREMIUM PARITY', 'A+ WORKFORCE PRO'],
          ['Premium Workforce Steuerung', 'Erweiterte Workforce-Steuerung'],
          ['Auto Scheduling', 'Automatische Dienstplanung'],
          ['Labor Sharing zwischen Einsatzorten', 'Standortübergreifender Personaleinsatz'],
          ['Task Lists & Custom Reports', 'Aufgabenlisten & individuelle Berichte'],
          ['Task List erstellen', 'Aufgabenliste erstellen'],
          ['API, Webhooks & Enterprise SSO', 'API, Webhooks & Unternehmens-SSO'],
        ];
        for (const [from, to] of replacements) next = next.split(from).join(to);
        return { code: next, map: null };
      }

      if (normalizedId.endsWith('/src/Operations.tsx')) {
        let next = code;
        next = next.replace("    ['When I Work', data.wiw_configured],\n", '');

        const wiwPanel = /<section className="operations-panel" data-testid="wiw-integration-panel">[\s\S]*?<\/section>\s*(?=<section className="operations-panel" data-testid="document-catalog-panel">)/;
        if (!wiwPanel.test(next)) this.error('Production UI marker changed: WIW migration panel');
        next = next.replace(
          wiwPanel,
          `<section className="operations-panel" data-testid="native-data-source-panel">\n              <div className="operations-head"><div><h3>A+ Workforce Datenbasis</h3><p>Schichten, Einsatzorte und Arbeitszeiten werden direkt in A+ Workforce geführt.</p></div><IonBadge color="success">Aktiv</IonBadge></div>\n              <div className="operations-note">Historische Importkennungen bleiben ausschließlich für Migration und Audit gespeichert und werden im operativen Alltag nicht mehr angezeigt.</div>\n            </section>\n            `,
        );
        next = next.split('OpenShifts in WIW erzeugen').join('OpenShifts direkt in A+ Workforce erzeugen');
        next = next.split('WIW-Schichten wurden in Vertragspakete übernommen.').join('Schichten wurden in Vertragspakete übernommen.');
        next = next.split('WIW-Pakete aktualisieren').join('Vertragspakete aktualisieren');
        return { code: next, map: null };
      }

      return null;
    },
  };
}

export default defineConfig({
  plugins: [
    appShellTransforms(),
    productionUiPolish(),
    react(),
    VitePWA({
      // Temporarily retire the service worker. Existing mobile clients can keep an
      // old Workbox navigation fallback alive and serve the SPA for /api/oauth
      // navigations. selfDestroying publishes a replacement worker that removes
      // the old registration/caches and reloads controlled clients.
      selfDestroying: true,
      injectRegister: false,
      includeAssets: ['favicon.svg'],
      manifest: {
        name: 'A+ Solution Workforce',
        short_name: 'A+ Solution',
        description: 'Personal, Einsätze, Zeiten und Verträge.',
        theme_color: '#0b1f4d',
        background_color: '#f4f7fb',
        display: 'standalone',
        lang: 'de',
        icons: [
          { src: '/icon-192.png', sizes: '192x192', type: 'image/png' },
          { src: '/icon-512.png', sizes: '512x512', type: 'image/png' },
        ],
      },
    }),
  ],
  build: {
    rollupOptions: {
      output: {
        manualChunks(id) {
          if (id.includes('/node_modules/react/') || id.includes('/node_modules/react-dom/')) {
            return 'react-vendor';
          }
          if (id.includes('/node_modules/@ionic/')) return 'ionic-vendor';
          if (id.includes('/node_modules/ionicons/')) return 'icons-vendor';
          return undefined;
        },
      },
    },
  },
  server: { port: 8080 },
});

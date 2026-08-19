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
 * Operations is another large legacy surface. Keep the source stable, remove
 * WIW from the live workflow and mount the native Premium parity control panel
 * for admins/managers/workers before the existing notification feed.
 */
function nativeWorkforceCutoverTransforms(): Plugin {
  const replacements: Array<[string, string]> = [
    ["    ['When I Work', data.wiw_configured],\n", ''],
    ['OpenShifts wurden in When I Work erstellt.', 'OpenShifts wurden direkt in A+ Workforce erstellt.'],
    ['WIW-Schichten wurden in Vertragspakete übernommen.', 'Lokale Schichten wurden in Vertragspakete übernommen.'],
    ['Deutschen Auftragstext analysieren, OpenShifts in WIW erzeugen und Kundenvertrag vorbereiten.', 'Deutschen Auftragstext analysieren, OpenShifts direkt in A+ Workforce erzeugen und Kundenvertrag vorbereiten.'],
    ['Aus WIW synchronisieren', 'Aus Zeiterfassung berechnen'],
    ['Manuelle Auszahlungen und Korrekturen bleiben bei jeder WIW-Synchronisierung erhalten.', 'Manuelle Auszahlungen und Korrekturen bleiben bei jeder Neuberechnung erhalten.'],
  ];
  const wiwPanel = /<section className="operations-panel" data-testid="wiw-integration-panel">[\s\S]*?<\/section>\s*(?=<section className="operations-panel" data-testid="document-catalog-panel">)/;
  const nativePanel = `<section className="operations-panel" data-testid="native-data-source-panel">
              <div className="operations-head"><div><h3>A+ Workforce Datenbasis</h3><p>Schichten, Besetzungen und Arbeitszeiten werden direkt in dieser App geführt.</p></div><IonBadge color="success">Aktiv</IonBadge></div>
              <div className="operations-note">When I Work ist kein Bestandteil des laufenden Betriebs mehr. Historische WIW-IDs bleiben nur für Migration und Audit erhalten.</div>
            </section>
            `;
  const notificationsMarker = '<Notifications rows={data.notifications || []} readAll={readAll} />';

  return {
    name: 'native-workforce-cutover-transforms',
    enforce: 'pre',
    transform(code, id) {
      const normalizedId = id.replace(/\\/g, '/').split('?')[0];
      if (!normalizedId.endsWith('/src/Operations.tsx')) return null;
      let next = code;
      for (const [from, to] of replacements) {
        if (!next.includes(from)) this.error(`Operations cutover marker changed: ${from}`);
        next = next.replace(from, to);
      }
      if (!wiwPanel.test(next)) this.error('Operations WIW panel marker changed; update cutover transform.');
      next = next.replace(wiwPanel, nativePanel);
      if (!next.includes(notificationsMarker)) this.error('Operations notifications marker changed; update Premium mount.');
      next = next.replace(notificationsMarker, `<PremiumOperations user={user} />\n      ${notificationsMarker}`);
      next = `import PremiumOperations from './PremiumOperations';\n${next}`;
      return { code: next, map: null };
    },
  };
}

export default defineConfig({
  plugins: [
    appShellTransforms(),
    nativeWorkforceCutoverTransforms(),
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

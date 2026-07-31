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
 * App.tsx is still a large legacy shell. Intercept only its feature imports and
 * replace them with tiny Suspense wrappers so Rollup can emit true route/role
 * chunks without rewriting the monolith in one risky change.
 */
function lazyAppFeatureChunks(): Plugin {
  const prefix = '\0lazy-app-feature:';

  return {
    name: 'lazy-app-feature-chunks',
    enforce: 'pre',
    resolveId(source, importer) {
      const normalizedImporter = importer?.replace(/\\/g, '/');
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

export default defineConfig({
  plugins: [
    lazyAppFeatureChunks(),
    react(),
    VitePWA({
      registerType: 'autoUpdate',
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

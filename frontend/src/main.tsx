import React from 'react';
import ReactDOM from 'react-dom/client';
import { setupIonicReact } from '@ionic/react';
import '@ionic/react/css/core.css';
import '@ionic/react/css/normalize.css';
import '@ionic/react/css/structure.css';
import '@ionic/react/css/typography.css';
import '@ionic/react/css/padding.css';
import './theme.css';
import './brand-refresh.css';
import App from './App';
import StoreComplianceLinks from './StoreComplianceLinks';
import StoreLegalPage, { legalPageFromPath } from './StoreLegalPages';

setupIonicReact({ mode: 'md' });

const legalPage = legalPageFromPath(window.location.pathname);

ReactDOM.createRoot(document.getElementById('root')!).render(
  <React.StrictMode>
    {legalPage ? (
      <StoreLegalPage page={legalPage} />
    ) : (
      <>
        <App />
        <StoreComplianceLinks />
      </>
    )}
  </React.StrictMode>,
);

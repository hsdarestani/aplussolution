import React from 'react';
import ReactDOM from 'react-dom/client';
import { setupIonicReact } from '@ionic/react';
import '@ionic/react/css/core.css';
import '@ionic/react/css/normalize.css';
import '@ionic/react/css/structure.css';
import '@ionic/react/css/typography.css';
import '@ionic/react/css/padding.css';
import './theme.css';
import './forecast-tools.css';
import App from './App';
import CommunicationsDock from './CommunicationsDock';
import SelfServiceDockMount from './SelfServiceDockMount';
import ReportingDock from './ReportingDock';
import AttendanceFinalDock from './AttendanceFinalDock';
import StoreComplianceLinks from './StoreComplianceLinks';
import StoreLegalPage, { legalPageFromPath } from './StoreLegalPages';
import TimeClockTerminal from './TimeClockTerminal';

setupIonicReact({ mode: 'md' });

const legalPage = legalPageFromPath(window.location.pathname);
const terminalPage = /^\/terminal\/[^/]+\/?$/.test(window.location.pathname);

ReactDOM.createRoot(document.getElementById('root')!).render(
  <React.StrictMode>
    {terminalPage ? (
      <TimeClockTerminal />
    ) : legalPage ? (
      <StoreLegalPage page={legalPage} />
    ) : (
      <>
        <App />
        <CommunicationsDock />
        <SelfServiceDockMount />
        <ReportingDock />
        <AttendanceFinalDock />
        <StoreComplianceLinks />
      </>
    )}
  </React.StrictMode>,
);
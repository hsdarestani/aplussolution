from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
app_path = ROOT / 'frontend/src/App.tsx'
theme_path = ROOT / 'frontend/src/theme.css'
operations_path = ROOT / 'frontend/src/operations.css'

app = app_path.read_text()

if 'mobile-first-app-shell-v1' in app:
    raise SystemExit('Mobile redesign already applied')

app = app.replace(
"""  addOutline,
  briefcaseOutline,""",
"""  addOutline,
  appsOutline,
  briefcaseOutline,""",
1,
)

old_header = """function Header({ title }: { title: string }) {
  return (
    <IonHeader>
      <IonToolbar>
        <IonTitle>{title}</IonTitle>
      </IonToolbar>
    </IonHeader>
  );
}"""
new_header = """function Header({ title, appShell = false }: { title: string; appShell?: boolean }) {
  return (
    <IonHeader className={appShell ? 'app-header' : ''}>
      <IonToolbar>
        <IonTitle>{title}</IonTitle>
      </IonToolbar>
    </IonHeader>
  );
}"""
if old_header not in app:
    raise SystemExit('Header block not found')
app = app.replace(old_header, new_header, 1)

app = app.replace(
"""  const [ready, setReady] = useState(false);
  const [view, setView] = useState<View>('dashboard');""",
"""  const [ready, setReady] = useState(false);
  const [view, setView] = useState<View>('dashboard');
  const [mobileMenuOpen, setMobileMenuOpen] = useState(false);""",
1,
)

old_setup = """  const items = nav[user.role] || nav.worker;
  let content: React.ReactNode = <Dashboard user={user} navigate={setView} />;"""
new_setup = """  const items = nav[user.role] || nav.worker;
  const primaryViews: View[] = ['dashboard', 'schedule', 'time', 'messages'];
  const mobilePrimaryItems = items.filter(([key]) => primaryViews.includes(key));
  const mobileMoreItems = items.filter(([key]) => !primaryViews.includes(key));
  const currentLabel = view === 'profile' ? 'Profil' : items.find(([key]) => key === view)?.[1] || 'A+ Solution';
  const roleLabel: Record<string, string> = {
    admin: 'Administration',
    manager: 'Management',
    worker: 'Mitarbeiter',
    client: 'Kundenportal',
  };
  const mobileLabels: Partial<Record<View, string>> = {
    dashboard: 'Start',
    schedule: 'Plan',
    time: 'Zeit',
    messages: 'Chat',
  };
  const navigateTo = (next: View) => {
    setView(next);
    setMobileMenuOpen(false);
    window.requestAnimationFrame(() => window.scrollTo({ top: 0, behavior: 'smooth' }));
  };

  let content: React.ReactNode = <Dashboard user={user} navigate={navigateTo} />;"""
if old_setup not in app:
    raise SystemExit('App setup block not found')
app = app.replace(old_setup, new_setup, 1)

old_return = """  return (
    <IonApp>
      <IonPage>
        <Header title=\"A+ Solution\" />
        <IonContent>
          <div className=\"app\">
            <aside>
              <div className=\"menu-logo\">
                A+<span>Solution</span>
              </div>
              <div className=\"user\">
                <div className=\"avatar\">{user.name[0]}</div>
                <div>
                  <b>{user.name}</b>
                  <small>{user.role}</small>
                </div>
              </div>
              <IonList lines=\"none\">
                {items.map((item) => (
                  <IonItem
                    button
                    detail={false}
                    key={item[0]}
                    className={view === item[0] ? 'active' : ''}
                    onClick={() => setView(item[0])}
                  >
                    <IonIcon slot=\"start\" icon={icons[item[0]]} />
                    <IonLabel>{item[1]}</IonLabel>
                  </IonItem>
                ))}
                <IonItem
                  button
                  detail={false}
                  className={view === 'profile' ? 'active' : ''}
                  onClick={() => setView('profile')}
                >
                  <IonIcon slot=\"start\" icon={peopleOutline} />
                  <IonLabel>Profil</IonLabel>
                </IonItem>
              </IonList>
              <IonButton fill=\"clear\" onClick={logout}>
                <IonIcon slot=\"start\" icon={exitOutline} />
                Abmelden
              </IonButton>
            </aside>
            <main>{content}</main>
          </div>
        </IonContent>
      </IonPage>
    </IonApp>
  );"""

new_return = """  return (
    <IonApp className=\"mobile-first-app-shell-v1\">
      <IonPage>
        <Header title=\"A+ Solution\" appShell />
        <IonContent className=\"app-content\">
          <div className=\"app\">
            <header className=\"mobile-appbar\">
              <button className=\"mobile-brand\" type=\"button\" onClick={() => navigateTo('dashboard')} aria-label=\"Zur Startseite\">
                <span>A+</span>
                <small>Solution</small>
              </button>
              <div className=\"mobile-page-title\">
                <small>{roleLabel[user.role] || user.role}</small>
                <strong>{currentLabel}</strong>
              </div>
              <button className=\"mobile-avatar\" type=\"button\" onClick={() => navigateTo('profile')} aria-label=\"Profil öffnen\">
                {user.name[0]}
              </button>
            </header>

            <aside>
              <div className=\"menu-logo\">
                A+<span>Solution</span>
              </div>
              <div className=\"user\">
                <div className=\"avatar\">{user.name[0]}</div>
                <div>
                  <b>{user.name}</b>
                  <small>{user.role}</small>
                </div>
              </div>
              <IonList lines=\"none\">
                {items.map((item) => (
                  <IonItem
                    button
                    detail={false}
                    key={item[0]}
                    className={view === item[0] ? 'active' : ''}
                    onClick={() => navigateTo(item[0])}
                  >
                    <IonIcon slot=\"start\" icon={icons[item[0]]} />
                    <IonLabel>{item[1]}</IonLabel>
                  </IonItem>
                ))}
                <IonItem
                  button
                  detail={false}
                  className={view === 'profile' ? 'active' : ''}
                  onClick={() => navigateTo('profile')}
                >
                  <IonIcon slot=\"start\" icon={peopleOutline} />
                  <IonLabel>Profil</IonLabel>
                </IonItem>
              </IonList>
              <IonButton fill=\"clear\" onClick={logout}>
                <IonIcon slot=\"start\" icon={exitOutline} />
                Abmelden
              </IonButton>
            </aside>

            <main className=\"app-main\">{content}</main>
          </div>
        </IonContent>

        <nav className=\"mobile-tabbar\" aria-label=\"Hauptnavigation\">
          {mobilePrimaryItems.map(([key, label]) => (
            <button
              type=\"button\"
              key={key}
              className={view === key ? 'active' : ''}
              onClick={() => navigateTo(key)}
              aria-current={view === key ? 'page' : undefined}
            >
              <IonIcon icon={icons[key]} />
              <span>{mobileLabels[key] || label}</span>
            </button>
          ))}
          <button
            type=\"button\"
            className={!primaryViews.includes(view) ? 'active' : ''}
            onClick={() => setMobileMenuOpen(true)}
            aria-label=\"Weitere Bereiche öffnen\"
          >
            <IonIcon icon={appsOutline} />
            <span>Mehr</span>
          </button>
        </nav>

        <IonModal
          isOpen={mobileMenuOpen}
          onDidDismiss={() => setMobileMenuOpen(false)}
          initialBreakpoint={0.72}
          breakpoints={[0, 0.72, 1]}
          className=\"mobile-menu-modal\"
        >
          <IonContent>
            <div className=\"mobile-menu-sheet\">
              <div className=\"mobile-menu-handle\" />
              <div className=\"mobile-menu-user\">
                <div className=\"avatar\">{user.name[0]}</div>
                <div>
                  <strong>{user.name}</strong>
                  <small>{user.email}</small>
                </div>
              </div>
              <div className=\"mobile-menu-heading\">
                <div>
                  <small>A+ WORKFORCE</small>
                  <h2>Weitere Bereiche</h2>
                </div>
                <button type=\"button\" onClick={() => setMobileMenuOpen(false)}>Fertig</button>
              </div>
              <div className=\"mobile-menu-grid\">
                {mobileMoreItems.map(([key, label]) => (
                  <button
                    type=\"button\"
                    key={key}
                    className={view === key ? 'active' : ''}
                    onClick={() => navigateTo(key)}
                  >
                    <span className=\"mobile-menu-icon\"><IonIcon icon={icons[key]} /></span>
                    <strong>{label}</strong>
                  </button>
                ))}
                <button type=\"button\" className={view === 'profile' ? 'active' : ''} onClick={() => navigateTo('profile')}>
                  <span className=\"mobile-menu-icon\"><IonIcon icon={peopleOutline} /></span>
                  <strong>Profil</strong>
                </button>
              </div>
              <button className=\"mobile-logout\" type=\"button\" onClick={logout}>
                <IonIcon icon={exitOutline} />
                Abmelden
              </button>
            </div>
          </IonContent>
        </IonModal>
      </IonPage>
    </IonApp>
  );"""
if old_return not in app:
    raise SystemExit('App return block not found')
app = app.replace(old_return, new_return, 1)
app_path.write_text(app)

mobile_css = r'''

/* mobile-first-app-shell-v1 */
.mobile-appbar,
.mobile-tabbar {
  display: none;
}

.mobile-menu-modal {
  --border-radius: 28px 28px 0 0;
}

@media (max-width: 900px) {
  html,
  body,
  #root,
  ion-app,
  ion-page {
    min-height: 100%;
    background: var(--bg);
  }

  body {
    overscroll-behavior-y: none;
  }

  .app-header {
    display: none;
  }

  .app-content {
    --background: var(--bg);
  }

  .app {
    display: block;
    min-height: 100dvh;
    padding-top: calc(68px + env(safe-area-inset-top));
    padding-bottom: calc(86px + env(safe-area-inset-bottom));
    background:
      radial-gradient(circle at 100% 0, rgba(21, 94, 239, .08), transparent 38%),
      var(--bg);
  }

  .app > aside {
    display: none;
  }

  .mobile-appbar {
    position: fixed;
    inset: 0 0 auto 0;
    z-index: 1000;
    height: calc(68px + env(safe-area-inset-top));
    padding: env(safe-area-inset-top) 16px 0;
    display: grid;
    grid-template-columns: 82px minmax(0, 1fr) 44px;
    align-items: center;
    gap: 10px;
    background: rgba(255, 255, 255, .93);
    border-bottom: 1px solid rgba(228, 231, 236, .85);
    backdrop-filter: blur(20px) saturate(160%);
    -webkit-backdrop-filter: blur(20px) saturate(160%);
    box-shadow: 0 8px 28px rgba(16, 24, 40, .06);
  }

  .mobile-brand,
  .mobile-avatar,
  .mobile-tabbar button,
  .mobile-menu-sheet button {
    font: inherit;
    -webkit-tap-highlight-color: transparent;
  }

  .mobile-brand {
    display: flex;
    align-items: baseline;
    gap: 4px;
    padding: 0;
    border: 0;
    background: transparent;
    color: var(--navy);
    text-align: left;
  }

  .mobile-brand span {
    font-size: 27px;
    line-height: 1;
    font-weight: 950;
    letter-spacing: -2px;
  }

  .mobile-brand small {
    font-size: 11px;
    font-weight: 800;
  }

  .mobile-page-title {
    min-width: 0;
    text-align: center;
  }

  .mobile-page-title small,
  .mobile-page-title strong {
    display: block;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }

  .mobile-page-title small {
    margin-bottom: 2px;
    color: var(--muted);
    font-size: 10px;
    font-weight: 700;
    letter-spacing: .04em;
    text-transform: uppercase;
  }

  .mobile-page-title strong {
    color: var(--ink);
    font-size: 15px;
  }

  .mobile-avatar {
    width: 42px;
    height: 42px;
    border: 0;
    border-radius: 15px;
    background: linear-gradient(145deg, #0b1f4d, #155eef);
    color: #fff;
    font-weight: 900;
    box-shadow: 0 8px 18px rgba(21, 94, 239, .24);
  }

  .mobile-tabbar {
    position: fixed;
    inset: auto 0 0 0;
    z-index: 1001;
    min-height: calc(72px + env(safe-area-inset-bottom));
    padding: 8px 8px calc(8px + env(safe-area-inset-bottom));
    display: grid;
    grid-template-columns: repeat(5, minmax(0, 1fr));
    gap: 3px;
    background: rgba(255, 255, 255, .96);
    border-top: 1px solid rgba(228, 231, 236, .9);
    box-shadow: 0 -10px 32px rgba(16, 24, 40, .09);
    backdrop-filter: blur(20px) saturate(160%);
    -webkit-backdrop-filter: blur(20px) saturate(160%);
  }

  .mobile-tabbar button {
    position: relative;
    min-width: 0;
    min-height: 54px;
    padding: 6px 2px;
    display: grid;
    place-items: center;
    align-content: center;
    gap: 3px;
    border: 0;
    border-radius: 16px;
    background: transparent;
    color: #7b8496;
  }

  .mobile-tabbar button ion-icon {
    font-size: 23px;
  }

  .mobile-tabbar button span {
    max-width: 100%;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
    font-size: 10px;
    font-weight: 700;
  }

  .mobile-tabbar button.active {
    color: #155eef;
    background: #edf3ff;
  }

  .mobile-tabbar button.active::before {
    content: '';
    position: absolute;
    top: 4px;
    width: 22px;
    height: 3px;
    border-radius: 999px;
    background: #155eef;
  }

  main,
  .app-main {
    width: 100%;
    max-width: 100%;
    padding: 16px;
    overflow: hidden;
  }

  .app-main > .title {
    margin: 4px 0 18px;
  }

  .title {
    gap: 14px;
  }

  .title h1 {
    font-size: clamp(24px, 7vw, 30px);
    line-height: 1.12;
  }

  .title p {
    font-size: 14px;
    line-height: 1.55;
  }

  .title > ion-button,
  .title > .button-group,
  .title > div:last-child:not(:first-child) {
    width: 100%;
  }

  .title > ion-button {
    margin: 0;
  }

  ion-button {
    min-height: 44px;
  }

  .hero {
    padding: 22px;
    border-radius: 24px;
    box-shadow: 0 18px 40px rgba(11, 31, 77, .18);
  }

  .hero h2 {
    font-size: 23px;
    line-height: 1.24;
  }

  .stats {
    grid-template-columns: repeat(2, minmax(0, 1fr));
    gap: 10px;
  }

  .stats ion-card {
    border: 1px solid rgba(228, 231, 236, .8);
    box-shadow: 0 10px 25px rgba(16, 24, 40, .06);
  }

  .stats ion-card-content {
    padding: 16px;
  }

  .panel,
  .worker-pool,
  .messenger,
  .rank-card,
  .shift-card {
    max-width: 100%;
    border-color: rgba(228, 231, 236, .82);
    box-shadow: 0 10px 28px rgba(16, 24, 40, .055);
  }

  .panel {
    padding: 16px;
    border-radius: 20px;
  }

  .section-head,
  .chat-head,
  .modal-head {
    gap: 12px;
  }

  .section-head:has(> ion-button),
  .section-head:has(> .button-group) {
    flex-wrap: wrap;
  }

  .row {
    min-height: 64px;
    padding: 14px 2px;
  }

  .row-actions,
  .button-group {
    gap: 7px;
  }

  .button-group ion-button,
  .row-actions ion-button {
    min-height: 42px;
  }

  .schedule-layout,
  .columns,
  .profile-grid,
  .messenger {
    grid-template-columns: minmax(0, 1fr);
  }

  .schedule-layout {
    gap: 12px;
  }

  .worker-pool {
    margin-inline: -16px;
    padding: 12px 16px;
    border-width: 1px 0;
    border-radius: 0;
    overflow-x: auto;
    scroll-snap-type: x proximity;
  }

  .worker-card {
    scroll-snap-align: start;
  }

  .conversation-list {
    scrollbar-width: none;
  }

  .conversation-list::-webkit-scrollbar,
  .worker-pool::-webkit-scrollbar {
    display: none;
  }

  .messenger {
    min-height: calc(100dvh - 190px);
    border-radius: 22px;
  }

  .chat-panel {
    min-height: 460px;
  }

  .message-compose {
    position: sticky;
    bottom: 0;
    padding-bottom: calc(14px + env(safe-area-inset-bottom));
  }

  .form-grid {
    gap: 12px;
  }

  ion-modal:not(.mobile-menu-modal) {
    --height: min(92dvh, 820px);
    --border-radius: 26px 26px 0 0;
    align-items: flex-end;
  }

  ion-modal:not(.mobile-menu-modal)::part(content) {
    border-radius: 26px 26px 0 0;
  }

  .modal-head {
    position: sticky;
    top: 0;
    z-index: 2;
    padding-top: 4px;
    background: #fff;
  }

  .mobile-menu-modal {
    --background: transparent;
    --box-shadow: 0 -20px 60px rgba(16, 24, 40, .2);
  }

  .mobile-menu-modal::part(content) {
    overflow: hidden;
    border-radius: 28px 28px 0 0;
  }

  .mobile-menu-modal ion-content {
    --background: #f6f8fc;
  }

  .mobile-menu-sheet {
    min-height: 100%;
    padding: 10px 16px calc(28px + env(safe-area-inset-bottom));
  }

  .mobile-menu-handle {
    width: 42px;
    height: 5px;
    margin: 0 auto 14px;
    border-radius: 99px;
    background: #cfd5df;
  }

  .mobile-menu-user {
    display: flex;
    align-items: center;
    gap: 12px;
    padding: 14px;
    margin-bottom: 14px;
    border: 1px solid #e5e9f0;
    border-radius: 20px;
    background: #fff;
    box-shadow: 0 8px 24px rgba(16, 24, 40, .05);
  }

  .mobile-menu-user > div:last-child {
    min-width: 0;
  }

  .mobile-menu-user strong,
  .mobile-menu-user small {
    display: block;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }

  .mobile-menu-user small {
    margin-top: 3px;
    color: var(--muted);
  }

  .mobile-menu-heading {
    display: flex;
    align-items: flex-end;
    justify-content: space-between;
    gap: 12px;
    margin: 18px 2px 12px;
  }

  .mobile-menu-heading small {
    color: #155eef;
    font-size: 10px;
    font-weight: 900;
    letter-spacing: .1em;
  }

  .mobile-menu-heading h2 {
    margin: 3px 0 0;
    font-size: 23px;
  }

  .mobile-menu-heading button {
    padding: 8px;
    border: 0;
    background: transparent;
    color: #155eef;
    font-weight: 800;
  }

  .mobile-menu-grid {
    display: grid;
    grid-template-columns: repeat(2, minmax(0, 1fr));
    gap: 10px;
  }

  .mobile-menu-grid > button {
    min-height: 112px;
    padding: 14px;
    display: flex;
    flex-direction: column;
    align-items: flex-start;
    justify-content: space-between;
    gap: 14px;
    border: 1px solid #e3e7ef;
    border-radius: 21px;
    background: #fff;
    color: var(--ink);
    text-align: left;
    box-shadow: 0 8px 24px rgba(16, 24, 40, .045);
  }

  .mobile-menu-grid > button.active {
    border-color: #9db9ff;
    background: #edf3ff;
    color: #155eef;
  }

  .mobile-menu-icon {
    width: 42px;
    height: 42px;
    display: grid;
    place-items: center;
    border-radius: 15px;
    background: #edf3ff;
    color: #155eef;
  }

  .mobile-menu-icon ion-icon {
    font-size: 23px;
  }

  .mobile-menu-grid strong {
    font-size: 14px;
    line-height: 1.25;
  }

  .mobile-logout {
    width: 100%;
    min-height: 50px;
    margin-top: 14px;
    display: flex;
    align-items: center;
    justify-content: center;
    gap: 9px;
    border: 1px solid #f1b8b3;
    border-radius: 17px;
    background: #fff6f5;
    color: #b42318;
    font-weight: 800;
  }
}

@media (max-width: 620px) {
  .login-grid {
    min-height: 100dvh;
    padding: calc(20px + env(safe-area-inset-top)) 18px calc(20px + env(safe-area-inset-bottom));
    align-content: center;
  }

  .brand .logo {
    font-size: 50px;
  }

  .brand h1 {
    margin: 12px 0 0;
    font-size: 31px;
    line-height: 1.08;
  }

  .login-card {
    padding: 22px;
    border-radius: 25px;
    box-shadow: 0 22px 55px rgba(0, 0, 0, .28);
  }

  .login-card h2 {
    font-size: 26px;
  }

  main,
  .app-main {
    padding: 14px;
  }

  .stats strong {
    font-size: 23px;
  }

  .panel {
    margin-top: 14px;
  }

  .empty {
    padding: 34px 16px;
  }

  .row .grow,
  .shift-card .grow {
    min-width: calc(100% - 66px);
  }

  .section-head,
  .operations-head {
    flex-wrap: wrap;
  }

  .section-head > ion-button,
  .operations-head > ion-button {
    width: 100%;
  }
}
'''

theme = theme_path.read_text()
if 'mobile-first-app-shell-v1' not in theme:
    theme_path.write_text(theme.rstrip() + mobile_css + '\n')

operations_css = r'''

/* mobile-first-app-shell-v1 */
@media (max-width: 900px) {
  .operations-grid.two {
    grid-template-columns: minmax(0, 1fr);
  }

  .operations-panel {
    border-color: rgba(228, 231, 236, .82);
    box-shadow: 0 10px 28px rgba(16, 24, 40, .055);
  }

  .operations-actions,
  .swap-actions {
    width: 100%;
  }

  .operations-actions ion-button,
  .swap-actions ion-button {
    flex: 1 1 145px;
    min-height: 44px;
  }

  .operations-modal {
    padding: 20px 16px calc(24px + env(safe-area-inset-bottom));
  }

  .operations-modal-head {
    position: sticky;
    top: 0;
    z-index: 3;
    padding: 4px 0 12px;
    background: #fff;
  }

  .operations-modal-actions {
    position: sticky;
    bottom: 0;
    z-index: 3;
    padding: 14px 0 calc(8px + env(safe-area-inset-bottom));
    background: #fff;
  }
}

@media (max-width: 620px) {
  .operations-stats {
    margin-inline: -14px;
    padding: 2px 14px 8px;
    display: flex;
    gap: 10px;
    overflow-x: auto;
    scroll-snap-type: x mandatory;
    scrollbar-width: none;
  }

  .operations-stats::-webkit-scrollbar {
    display: none;
  }

  .operations-stats ion-card {
    min-width: 152px;
    scroll-snap-align: start;
    box-shadow: 0 10px 25px rgba(16, 24, 40, .06);
  }

  .operations-panel {
    padding: 16px;
    border-radius: 20px;
  }

  .operations-head {
    gap: 10px;
  }

  .operations-head > div {
    min-width: 0;
  }

  .operations-head p {
    font-size: 13px;
    line-height: 1.5;
  }

  .operations-row {
    min-height: 64px;
    padding: 14px 2px;
  }

  .report-fields,
  .readiness-list,
  .client-summary,
  .working-time-setting {
    grid-template-columns: minmax(0, 1fr);
  }

  .readiness-item {
    min-height: 50px;
    background: #fbfcfe;
  }

  .folder-scroll {
    max-height: none;
  }

  .operations-form {
    gap: 12px;
  }

  .operations-modal-actions ion-button {
    flex: 1;
    margin: 0;
  }
}
'''

operations = operations_path.read_text()
if 'mobile-first-app-shell-v1' not in operations:
    operations_path.write_text(operations.rstrip() + operations_css + '\n')

print('Mobile-first app shell applied')

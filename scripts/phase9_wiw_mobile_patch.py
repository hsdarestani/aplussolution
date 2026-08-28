from pathlib import Path


def replace_once(path: str, old: str, new: str):
    file = Path(path)
    text = file.read_text(encoding='utf-8')
    if old not in text:
        raise SystemExit(f'missing expected marker in {path}: {old[:100]!r}')
    file.write_text(text.replace(old, new, 1), encoding='utf-8')


# Attendance: imported WIW rows are already in the database; do not hide all but the latest 30.
replace_once(
    'backend/core/attendance_views.py',
    "    history_qs = TimeEntry.objects.select_related('shift__position', 'worker__user').filter(\n        worker=worker,\n        clock_out__isnull=False,\n    ).order_by('-clock_in')[:30]\n",
    "    # Keep the complete closed history, including imported WIW rows. The mobile\n    # Pay Periods view derives its range from the oldest available entry.\n    history_qs = TimeEntry.objects.select_related('shift__position', 'worker__user').filter(\n        worker=worker,\n        clock_out__isnull=False,\n    ).order_by('-clock_in')\n",
)

# Global appearance is light by default and persisted locally.
replace_once(
    'frontend/src/main.tsx',
    "import './phase8-wiw-mobile.css';\n",
    "import './phase8-wiw-mobile.css';\nimport './wiw-mobile-light.css';\n",
)
replace_once(
    'frontend/src/main.tsx',
    "import { installLocationPicker } from './locationPicker';\n",
    "import { installLocationPicker } from './locationPicker';\nimport { installMobileAppearance } from './mobileAppearance';\n",
)
replace_once(
    'frontend/src/main.tsx',
    "installLocationPicker();\nsetupIonicReact({ mode: 'md' });\n",
    "installLocationPicker();\ninstallMobileAppearance();\nsetupIonicReact({ mode: 'md' });\n",
)

# App shell: expose active view to mobile CSS and render a full-screen WIW-style More screen.
replace_once(
    'frontend/src/App.tsx',
    "import Settings from './Settings';\n",
    "import Settings from './Settings';\nimport MobileMoreMenu from './MobileMoreMenu';\n",
)
replace_once(
    'frontend/src/App.tsx',
    '<IonApp className="mobile-first-app-shell-v1">',
    '<IonApp className="mobile-first-app-shell-v1" data-view={view}>',
)
replace_once(
    'frontend/src/App.tsx',
    "          initialBreakpoint={0.72}\n          breakpoints={[0, 0.72, 1]}\n",
    "          initialBreakpoint={1}\n          breakpoints={[0, 1]}\n",
)
replace_once(
    'frontend/src/App.tsx',
    "          <IonContent>\n            <div className=\"mobile-menu-sheet\">\n",
    "          <IonContent>\n            <MobileMoreMenu user={user} items={mobileMoreItems as [string,string][]} view={view} navigate={navigateTo} onLogout={logout} />\n            <div className=\"mobile-menu-sheet\">\n",
)

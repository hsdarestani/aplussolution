import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def test_phase2_production_script_has_valid_bash_syntax():
    script = ROOT / 'scripts' / 'production_wiw_phase2_resync.sh'
    result = subprocess.run(['bash', '-n', str(script)], capture_output=True, text=True, check=False)
    assert result.returncode == 0, result.stderr


def test_phase2_production_script_is_a_safe_noop_after_cutover():
    script = (ROOT / 'scripts' / 'production_wiw_phase2_resync.sh').read_text(encoding='utf-8')
    assert 'WIW reconciliation is retired' in script
    assert 'exit 0' in script
    assert 'reconcile_wiw_history' not in script
    assert 'pg_dump' not in script
    assert 'docker compose stop' not in script
    assert 'docker compose run' not in script


def test_phase2_retired_script_never_touches_existing_data_or_services():
    script = (ROOT / 'scripts' / 'production_wiw_phase2_resync.sh').read_text(encoding='utf-8')
    forbidden_writes = (
        'manage.py migrate',
        'manage.py shell',
        'docker compose exec',
        'docker compose up',
        'docker compose down',
        'docker compose restart',
        'DELETE FROM',
        'TRUNCATE',
    )
    assert all(token not in script for token in forbidden_writes)
    assert 'existing A+ data is preserved unchanged' in script


def test_phase2_workflow_is_manual_tombstone_only():
    workflow = (ROOT / '.github' / 'workflows' / 'wiw-phase2.yml').read_text(encoding='utf-8')
    assert 'workflow_dispatch:' in workflow
    assert 'workflow_run:' not in workflow
    assert 'push:' not in workflow
    assert 'schedule:' not in workflow
    assert 'production_wiw_phase2_resync.sh' not in workflow
    assert 'synchronization has been retired' in workflow

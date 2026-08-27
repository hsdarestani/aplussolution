import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def test_phase2_production_script_has_valid_bash_syntax():
    script = ROOT / 'scripts' / 'production_wiw_phase2_resync.sh'
    result = subprocess.run(['bash', '-n', str(script)], capture_output=True, text=True, check=False)
    assert result.returncode == 0, result.stderr


def test_phase2_production_script_uses_single_process_maintenance_mode_and_restores_services():
    script = (ROOT / 'scripts' / 'production_wiw_phase2_resync.sh').read_text(encoding='utf-8')
    assert 'docker compose stop backend celery celery-beat' in script
    assert 'trap resume_app_services EXIT' in script
    assert 'docker compose up -d backend celery celery-beat' in script
    assert 'docker compose run --rm --no-deps -T backend python manage.py reconcile_wiw_history --compact' in script
    assert 'docker compose exec -T backend python manage.py reconcile_wiw_history --compact' not in script
    assert 'WIW Phase 2 preflight OK' not in script


def test_phase2_completion_marker_is_written_only_after_public_health_check():
    script = (ROOT / 'scripts' / 'production_wiw_phase2_resync.sh').read_text(encoding='utf-8')
    health_index = script.index('https://solution.smarbiz.sbs/health/')
    marker_index = script.index('cat > "$DONE_MARKER"')
    assert health_index < marker_index


def test_phase2_workflow_runs_only_after_successful_main_deploy():
    workflow = (ROOT / '.github' / 'workflows' / 'wiw-phase2.yml').read_text(encoding='utf-8')
    assert 'workflow_run:' in workflow
    assert 'Validate and deploy production' in workflow
    assert "workflow_run.conclusion == 'success'" in workflow
    assert "workflow_run.head_branch == 'main'" in workflow
    assert 'production_wiw_phase2_resync.sh' in workflow

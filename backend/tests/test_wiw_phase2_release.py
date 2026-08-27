import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def test_phase2_production_script_has_valid_bash_syntax():
    script = ROOT / 'scripts' / 'production_wiw_phase2_resync.sh'
    result = subprocess.run(['bash', '-n', str(script)], capture_output=True, text=True, check=False)
    assert result.returncode == 0, result.stderr


def test_phase2_workflow_runs_only_after_successful_main_deploy():
    workflow = (ROOT / '.github' / 'workflows' / 'wiw-phase2.yml').read_text(encoding='utf-8')
    assert 'workflow_run:' in workflow
    assert 'Validate and deploy production' in workflow
    assert "workflow_run.conclusion == 'success'" in workflow
    assert "workflow_run.head_branch == 'main'" in workflow
    assert 'production_wiw_phase2_resync.sh' in workflow

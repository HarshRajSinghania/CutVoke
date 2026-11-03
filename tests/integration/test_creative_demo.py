"""Execute the published creative-loop example against real stdio and local FFmpeg."""
import json
import os
from pathlib import Path
import subprocess
import sys


def test_real_stdio_creative_loop(tmp_path):
    root=Path(__file__).resolve().parents[2]
    output=tmp_path/'creative-loop'
    result=subprocess.run([sys.executable,str(root/'skills/cutvoke-editor/scripts/creative_demo.py'),'--output',str(output)],
        cwd=root,env={**os.environ,'PYTHONPATH':str(root/'src')},capture_output=True,text=True,timeout=240)
    assert result.returncode==0,result.stdout+'\n'+result.stderr
    report=json.loads(result.stdout)
    assert report['creativeAcceptance']=='not_assessed' and report['technicalValidationOnly']
    assert report['idempotentReplay'] and report['oldEvidenceRejected'] and report['mediaPreserved']
    project_root=Path(report['output']).parent.parent
    assert project_root.is_relative_to(output)
    for name in ('plan-before','plan-after','review-before','review-after','repair','repair-preview'):
        assert (project_root/'notes'/f'{name}.json').is_file()
    review=json.loads((project_root/'notes/review-after.json').read_text())
    assert review['revision']==report['revision']
    assert any(e['inspection']=='pending' and e['kind']=='continuous-av' for e in review['evidence'])
    calls=json.loads((project_root/'calls.json').read_text())
    assert all(c['ok'] for c in calls)
    assert len([c for c in calls if c['tool']=='creative_workflow'])>=10
    assert abs(report['checks']['1']['audioPeakHz']-440)<5
    assert abs(report['checks']['6']['audioPeakHz']-880)<5

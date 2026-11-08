"""The v0.3.5 recovery remains bound to its draft, source, CI and upload host."""
import hashlib
import importlib.util
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location('recover_v035_fixture', ROOT / 'tools/release/recover_v035.py')
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)


def draft():
    return {'id': m.RELEASE_ID, 'tag_name': m.TAG, 'target_commitish': m.SOURCE,
            'prerelease': True, 'body': 'Original fixture notes'}


def test_accepts_exact_draft_identity_and_notes():
    release = draft()
    sha = hashlib.sha256(release['body'].encode()).hexdigest()
    assert m.validate_release(release, sha) is release


@pytest.mark.parametrize('field,value', [('id', 1), ('tag_name', 'v0.3.4'),
    ('target_commitish', 'a' * 40), ('prerelease', False), ('body', 'changed')])
def test_rejects_other_release_source_or_notes(field, value):
    release = draft()
    sha = hashlib.sha256(release['body'].encode()).hexdigest()
    release[field] = value
    with pytest.raises(RuntimeError):
        m.validate_release(release, sha)


@pytest.mark.parametrize('field,value', [('GITHUB_REPOSITORY', 'someone/else'),
    ('GITHUB_ACTIONS', 'false'), ('GITHUB_EVENT_NAME', 'push'), ('GITHUB_REF', 'refs/heads/main')])
def test_wrong_execution_context_stops_before_any_api(monkeypatch, field, value):
    for key, item in {'GITHUB_REPOSITORY': m.REPO, 'GITHUB_ACTIONS': 'true',
                     'GITHUB_EVENT_NAME': 'workflow_dispatch', 'GITHUB_REF': m.BRANCH}.items():
        monkeypatch.setenv(key, item)
    monkeypatch.setenv(field, value)
    monkeypatch.setattr(m, 'api', lambda *_: pytest.fail('unexpected API access'))
    with pytest.raises(RuntimeError, match='bound manual'):
        m.main()


def responses():
    result = {f'repos/{m.REPO}/branches/main': {'commit': {'sha': m.SOURCE}},
              f'repos/{m.REPO}/git/ref/tags/{m.TAG}': {'object': {'type': 'commit', 'sha': m.SOURCE}}}
    for workflow, run in m.RUNS.items():
        result[f'repos/{m.REPO}/actions/runs/{run}'] = {
            'head_sha': m.SOURCE, 'head_branch': 'main', 'event': 'push',
            'path': '.github/workflows/' + workflow, 'status': 'completed', 'conclusion': 'success'}
        result[f'repos/{m.REPO}/actions/runs/{run}/jobs?per_page=100'] = {'jobs': [
            {'name': name, 'status': 'completed', 'conclusion': 'success'} for name in sorted(m.JOBS[workflow])]}
    return result


def test_accepts_all_nine_same_source_jobs(monkeypatch):
    data = responses()
    monkeypatch.setattr(m, 'api', data.__getitem__)
    m.synchronized(full=True)


@pytest.mark.parametrize('failure', ['main', 'tag', 'source', 'missing-job', 'skipped-job'])
def test_changed_source_or_incomplete_ci_blocks_recovery(monkeypatch, failure):
    data = responses()
    run = m.RUNS['ci.yml']
    if failure == 'main':
        data[f'repos/{m.REPO}/branches/main']['commit']['sha'] = 'b' * 40
    elif failure == 'tag':
        data[f'repos/{m.REPO}/git/ref/tags/{m.TAG}']['object']['sha'] = 'b' * 40
    elif failure == 'source':
        data[f'repos/{m.REPO}/actions/runs/{run}']['head_sha'] = 'b' * 40
    elif failure == 'missing-job':
        data[f'repos/{m.REPO}/actions/runs/{run}/jobs?per_page=100']['jobs'].pop()
    else:
        data[f'repos/{m.REPO}/actions/runs/{run}/jobs?per_page=100']['jobs'][0]['conclusion'] = 'skipped'
    monkeypatch.setattr(m, 'api', data.__getitem__)
    with pytest.raises(RuntimeError):
        m.synchronized(full=True)


@pytest.mark.parametrize('url', ['https://example.com/upload',
    f'https://uploads.github.com/repos/{m.REPO}/releases/1/assets{{?name,label}}'])
def test_upload_rejects_other_hosts_and_release_ids(tmp_path, url):
    path = tmp_path / 'fixture.zip'
    path.write_bytes(b'original fixture')
    with pytest.raises(RuntimeError, match='upload URL'):
        m.upload({'upload_url': url}, path)

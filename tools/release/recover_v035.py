"""Resume only the verified v0.3.5 draft; never rebuild or replace assets."""
import hashlib
import json
import os
from pathlib import Path
import runpy
import shutil
import tempfile
import urllib.error
import urllib.parse
import urllib.request
import zipfile

ROOT = Path(__file__).resolve().parents[2]
HELPERS = runpy.run_path(str(ROOT / 'tools/release/publish_verified.py'))
api, require = HELPERS['api'], HELPERS['require']
digest, stream_digest = HELPERS['digest'], HELPERS['stream_digest']
download_artifact = HELPERS['download_artifact']
build_info, verify_info = HELPERS['build_info'], HELPERS['verify_info']
validate_assets = HELPERS['recovery_assets']
REPO = 'frankShan001/CutVoke'
RELEASE_ID = 438102457
TAG, VERSION = 'v0.3.5', '0.3.5'
SOURCE = 'c8cd8d53326fc1878b100dd3eefd6f6b7d4dfb5a'
BRANCH = 'refs/heads/release/v0.3.5-recovery'
MANIFEST_ARTIFACT = 13608439035
ORIGINAL_RUN = 42459649398
MANIFEST_ZIP_SHA = 'a22a28ed9799025dec6ba2a47b2affbb96a6049ef4f29c8a42a5f5e7a374b615'
MANIFEST_SHA = 'a34a69acee68fb84ffabfab051850da5c7d3962b7eba1ca8f5cfbec4f9dc2437'
SUMS_SHA = 'e967acf3364e281c00f0a541ab52e50a4219b7bccf5f0eaafc71549cbc3e5d3c'
BODY_SHA = '12fe8a8a1a691b248ffb8aebd943f184abe58122ede5293b406e43f4dc3a2694'
RUNS = {'ci.yml': 42456592754, 'windows-portable.yml': 42456592873,
        'unix-packages.yml': 42456592730}
JOBS = HELPERS['RECOVERY_JOBS']
OLD = {**HELPERS['RECOVERY_OLD'], 'v0.3.4': HELPERS['RECOVERY_ID']}


def validate_release(release, body_sha=BODY_SHA):
    require(release['id'] == RELEASE_ID and release['tag_name'] == TAG
            and release['target_commitish'] == SOURCE and release['prerelease'] is True,
            'Recovery release ID/tag/source mismatch')
    require(hashlib.sha256(release['body'].encode('utf-8')).hexdigest() == body_sha,
            'Recovery release notes changed')
    return release


def bound_release():
    return validate_release(api(f'repos/{REPO}/releases/{RELEASE_ID}'))


def synchronized(*, full=False):
    require(api(f'repos/{REPO}/branches/main')['commit']['sha'] == SOURCE,
            'main advanced; refusing recovery publication')
    ref = api(f'repos/{REPO}/git/ref/tags/{TAG}')['object']
    require(ref['type'] == 'commit' and ref['sha'] == SOURCE, 'Recovery tag changed')
    if full:
        for workflow, run_id in RUNS.items():
            run = api(f'repos/{REPO}/actions/runs/{run_id}')
            require(run['head_sha'] == SOURCE and run['head_branch'] == 'main'
                    and run['event'] == 'push' and run['path'] == '.github/workflows/' + workflow
                    and run['status'] == 'completed' and run['conclusion'] == 'success',
                    'Recovery workflow/source mismatch')
            jobs = api(f'repos/{REPO}/actions/runs/{run_id}/jobs?per_page=100')['jobs']
            require(len(jobs) == len(JOBS[workflow])
                    and {job['name'] for job in jobs} == JOBS[workflow]
                    and all(job['status'] == 'completed' and job['conclusion'] == 'success' for job in jobs),
                    'Recovery job missing, skipped or unsuccessful')


def historical_state():
    result = {}
    for tag, release_id in OLD.items():
        release = api(f'repos/{REPO}/releases/{release_id}')
        require(release['id'] == release_id and release['tag_name'] == tag
                and not release['draft'], 'Historical release identity changed')
        result[tag] = {'ref': api(f'repos/{REPO}/git/ref/tags/{tag}')['object'],
                       'source': release['target_commitish'], 'prerelease': release['prerelease'],
                       'body': hashlib.sha256(release['body'].encode('utf-8')).hexdigest(),
                       'assets': sorted((a['id'], a['name'], a['size'], a['digest'])
                                        for a in release['assets'])}
    return result


def upload(release, path):
    url = release['upload_url'].split('{', 1)[0]
    require(url == f'https://uploads.github.com/repos/{REPO}/releases/{RELEASE_ID}/assets',
            'Unexpected recovery upload URL')
    url += '?' + urllib.parse.urlencode({'name': path.name})
    with path.open('rb') as source:
        request = urllib.request.Request(url, method='POST', data=source, headers={
            'Authorization': 'Bearer ' + os.environ['GH_TOKEN'], 'User-Agent': 'CutVoke-release',
            'Content-Type': 'application/octet-stream', 'Content-Length': str(path.stat().st_size),
            'Accept': 'application/vnd.github+json', 'X-GitHub-Api-Version': '2022-11-28'})
        try:
            with urllib.request.build_opener(HELPERS['NoRedirect']()).open(request, timeout=180) as response:
                require(response.status == 201, 'Recovery upload not confirmed')
                return json.load(response)
        except urllib.error.HTTPError as error:
            raise RuntimeError(f'Recovery upload HTTP {error.code}; no replacement attempted') from None


def main():
    require(os.environ.get('GITHUB_REPOSITORY') == REPO
            and os.environ.get('GITHUB_ACTIONS') == 'true'
            and os.environ.get('GITHUB_EVENT_NAME') == 'workflow_dispatch'
            and os.environ.get('GITHUB_REF') == BRANCH,
            'Recovery requires the bound manual Actions branch run')
    release = bound_release()
    require(release['draft'], 'Draft already published; use public verification instead')
    synchronized(full=True)
    old = historical_state()
    output = ROOT / '.artifacts/release'
    output.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='resume-v035-', dir=output) as directory:
        work = Path(directory)
        artifact = api(f'repos/{REPO}/actions/artifacts/{MANIFEST_ARTIFACT}')
        require(artifact['name'] == 'release-verification' and not artifact['expired']
                and artifact['workflow_run']['id'] == ORIGINAL_RUN
                and artifact['workflow_run']['head_sha'] == SOURCE
                and artifact['digest'] == 'sha256:' + MANIFEST_ZIP_SHA,
                'Recovery manifest artifact mismatch')
        outer = work / 'manifest.zip'
        download_artifact(REPO, artifact, outer)
        with zipfile.ZipFile(outer) as archive:
            require(len(archive.namelist()) == 2
                    and set(archive.namelist()) == {'BUILD-INFO.json', 'SHA256SUMS'},
                    'Unexpected recovery manifest files')
            for name in archive.namelist():
                (output / name).write_bytes(archive.read(name))
        manifest_path, sums = output / 'BUILD-INFO.json', output / 'SHA256SUMS'
        require(digest(manifest_path) == MANIFEST_SHA and digest(sums) == SUMS_SHA,
                'Recovery manifest/checksums changed')
        manifest = json.loads(manifest_path.read_text('utf-8'))
        checks = {key: f'https://github.com/{REPO}/actions/runs/{value}' for key, value in RUNS.items()}
        require(manifest['version'] == VERSION and manifest['tag'] == TAG
                and manifest['commit'] == SOURCE and manifest['prerelease'] is True
                and manifest['checks'] == checks and len(manifest['assets']) == 4,
                'Recovery manifest binding mismatch')
        require(sums.read_text('ascii') == ''.join(f'{a["sha256"]}  {a["name"]}\n' for a in manifest['assets']),
                'Recovery checksum entries mismatch')
        expected = {p.name: (p.stat().st_size, 'sha256:' + digest(p)) for p in (manifest_path, sums)}
        paths = []
        for (platform, (workflow, artifact_name, suffix)), item in zip(HELPERS['PACKAGES'].items(), manifest['assets']):
            filename = f'CutVoke-{VERSION}-{platform}{suffix}'
            require(item['name'] == filename and item['run'] == checks[workflow], 'Recovery package run/name mismatch')
            artifact = api(f'repos/{REPO}/actions/artifacts/{item["artifactId"]}')
            require(artifact['name'] == artifact_name and not artifact['expired']
                    and artifact['workflow_run']['head_sha'] == SOURCE
                    and artifact['workflow_run']['id'] == RUNS[workflow],
                    'Recovery package artifact source mismatch')
            outer = work / (platform + '.zip')
            download_artifact(REPO, artifact, outer)
            path = work / filename
            with zipfile.ZipFile(outer) as archive:
                require(archive.namelist().count(filename) == 1, 'Recovery archive filename mismatch')
                info = json.loads(archive.read('download-info.json'))
                verify_info(info, VERSION, SOURCE, platform)
                require(info['filename'] == filename and info['runUrl'] == checks[workflow]
                        and info['bytes'] == item['bytes'] and info['sha256'] == item['sha256'],
                        'Recovery package metadata mismatch')
                with archive.open(filename) as source, path.open('xb') as target:
                    shutil.copyfileobj(source, target, 1024 * 1024)
            expected[filename] = (item['bytes'], 'sha256:' + item['sha256'])
            require((path.stat().st_size, 'sha256:' + digest(path)) == expected[filename],
                    'Recovery package digest mismatch')
            verify_info(build_info(path), VERSION, SOURCE, platform)
            paths.append(path)
            outer.unlink()
        initial = validate_assets(release, expected)
        initial_ids = {name: asset['id'] for name, asset in initial.items()}
        # Inspect all four archives before the first write. Reuse only matching
        # uploaded assets; neither an old release nor an asset is replaced.
        for path in paths + [manifest_path, sums]:
            synchronized()
            current = bound_release()
            require(current['draft'], 'Draft state changed during upload')
            existing = validate_assets(current, expected)
            require(all(existing.get(name, {}).get('id') == value for name, value in initial_ids.items()),
                    'Existing asset ID changed')
            if path.name not in existing:
                print('Uploading verified', path.name, flush=True)
                asset = upload(current, path)
                require(asset['name'] == path.name and asset['state'] == 'uploaded'
                        and (asset['size'], asset['digest']) == expected[path.name], 'Upload digest mismatch')
        current = bound_release()
        require(current['draft'], 'Draft state changed before publication')
        validate_assets(current, expected, complete=True)
        synchronized(full=True)
        require(historical_state() == old, 'Historical releases changed')
        HELPERS['gh']('api', '--method', 'PATCH', f'repos/{REPO}/releases/{RELEASE_ID}',
                      '-F', 'draft=false', '-F', 'prerelease=true')
        published = bound_release()
        require(not published['draft'], 'Publication not confirmed')
        assets = validate_assets(published, expected, complete=True)
        downloads = []
        for name, asset in assets.items():
            url = f'https://github.com/{REPO}/releases/download/{TAG}/{name}'
            require(asset['browser_download_url'] == url, 'Public URL mismatch')
            with urllib.request.urlopen(url, timeout=180) as stream:
                require('sha256:' + stream_digest(stream) == expected[name][1], 'Public download digest mismatch')
            downloads.append({'name': name, 'bytes': expected[name][0], 'sha256': expected[name][1][7:], 'url': url})
        require(historical_state() == old, 'Historical releases changed after publication')
        report = {'passed': True, 'releaseId': RELEASE_ID, 'tag': TAG, 'source': SOURCE,
                  'recoveryToolCommit': os.environ.get('GITHUB_SHA'), 'checks': checks,
                  'verifiedPublicDownloads': downloads, 'preservedAssetIds': initial_ids,
                  'oldReleasesUnchanged': True}
        (output / 'recovery-verification.json').write_text(json.dumps(report, indent=2) + '\n')
        print(f'Published and verified six public files at {published["html_url"]}', flush=True)
        with Path(os.environ['GITHUB_STEP_SUMMARY']).open('a') as summary:
            summary.write(f'Recovered release {RELEASE_ID}; source `{SOURCE}`; six public downloads verified.\n')


if __name__ == '__main__':
    main()

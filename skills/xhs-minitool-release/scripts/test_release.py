"""Behavioral self-checks in a new explicitly chosen workspace; stdlib only."""
import argparse
import json
from pathlib import Path
import subprocess
import sys
sys.dont_write_bytecode = True
from package_release import package


def run(work, project=None, channel=None):
    work.mkdir(parents=True, exist_ok=False)
    source = work / 'fixture'
    (source / 'assets').mkdir(parents=True)
    (source / 'index.html').write_text('''<!doctype html><html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover"><link rel="stylesheet" href="./assets/style.css"></head><body><main id="menu"><button id="start">开始</button></main><section id="workspace" hidden><p>可用工作区</p><button id="back">返回</button></section><div id="loading">正在加载</div><script src="./assets/app.js"></script></body></html>''', encoding='utf-8')
    (source / 'assets' / 'style.css').write_text('''[hidden]{display:none!important}body{margin:0;padding:120px 16px 16px}button{height:48px;min-width:100px}#loading{position:fixed;inset:0;background:white;z-index:99}''', encoding='utf-8')
    app = '''document.querySelector('#start').addEventListener('click',function(){document.querySelector('#menu').hidden=true;document.querySelector('#workspace').hidden=false;});document.querySelector('#back').addEventListener('click',function(){document.querySelector('#workspace').hidden=true;document.querySelector('#menu').hidden=false;});document.querySelector('#loading').remove();'''
    (source / 'assets' / 'app.js').write_text(app, encoding='utf-8')
    (source / 'assets' / '数据.json').write_text('{"ready":true}', encoding='utf-8')
    checks = []

    def build(label, overrides=None):
        return package(source, work / (label + '.zip'), work / (label + '-extract'),
                       work / (label + '.json'), overrides)

    good = build('good')
    assert not good['errors'] and good['fileCount'] == 4
    assert (work / 'good-extract' / 'assets' / '数据.json').read_text(encoding='utf-8') == '{"ready":true}'
    assert good['zipSha256'] == build('identical')['zipSha256']
    checks.append('root entry, Unicode paths, ZIP/extraction hashes, deterministic bytes')
    try:
        build('good')
        raise AssertionError('Overwrite was accepted')
    except ValueError:
        pass
    checks.append('old ZIP/report/extraction preserved')
    for label, text, rule in [
        ('missing', '<img src="missing.png">', 'MISSING_RESOURCE'),
        ('absolute', '<img src="/assets/a.png">', 'NON_RELATIVE_RESOURCE'),
        ('external', '<img src="https://example.invalid/a.png">', 'NON_RELATIVE_RESOURCE'),
        ('traversal', '<img src="../outside.png">', 'MISSING_RESOURCE'),
        ('inline', '<script>alert(1)</script>', 'INLINE_SCRIPT'),
        ('module', '<script type="module" src="./assets/app.js"></script>', 'MODULE_ENTRY'),
        ('event', '<button onclick="x()">x</button>', 'INLINE_EVENT'),
        ('case', '<script src="./assets/APP.js"></script>', 'RESOURCE_CASE_MISMATCH' if sys.platform == 'win32' else 'MISSING_RESOURCE'),
    ]:
        original = (source / 'index.html').read_text(encoding='utf-8')
        (source / 'index.html').write_text(original + text, encoding='utf-8')
        bad = build(label)
        assert any(e['rule'] == rule for e in bad['errors']), (label, bad)
        assert not (work / (label + '.zip')).exists()
        (source / 'index.html').write_text(original, encoding='utf-8')
        checks.append('reject ' + label)
    extra = source / 'other.html'
    extra.write_text('<p>extra</p>', encoding='utf-8')
    assert any(e['rule'] == 'ROOT_ENTRY' for e in build('extra-html')['errors'])
    extra.unlink()
    assert any(e['rule'] == 'ZIP_LIMIT' for e in build('limit', {'zipMaxBytes': 10})['errors'])
    (source / 'assets' / 'app.js').write_text(app + '\n// fetch("not executable");', encoding='utf-8')
    assert any(e['rule'] == 'NETWORK' for e in build('heuristic')['manualReviewRequired'])
    assert any(e['rule'] == 'DEBUG_PATTERN' for e in build('debug', {'debugPatterns': ['not executable']})['errors'])
    checks.extend(['reject multiple HTML', 'enforce ZIP limit', 'surface heuristic review', 'reject configured debug symbol'])
    (source / 'assets' / 'app.js').write_text(app, encoding='utf-8')
    config = {'ready': '#menu', 'timeoutMs': 2500,
              'steps': [{'tap': '#start', 'visible': '#workspace'}, {'tap': '#back', 'visible': '#menu'}],
              'viewports': [{'width': 390, 'height': 844, 'safeArea': {'top': 60, 'bottom': 34},
                             'nativeButtons': [{'top': 60, 'right': 8, 'width': 44, 'height': 44}]},
                            {'width': 844, 'height': 390}]}
    config_file = work / 'flow.json'
    config_file.write_text(json.dumps(config), encoding='utf-8')
    if project:
        smoke = Path(__file__).with_name('smoke_release.mjs')

        def smoke_run(root, name, expected):
            command = ['node', str(smoke), '--root', str(root), '--project', str(project),
                       '--config', str(config_file), '--out', str(work / name),
                       '--package-report', str(work / (root.name.removesuffix('-extract') + '.json'))]
            if channel:
                command.extend(['--channel', channel])
            result = subprocess.run(command, capture_output=True, text=True, encoding='utf-8')
            assert (result.returncode == 0) == expected, result.stdout + result.stderr
            return json.loads((work / name / 'report.json').read_text(encoding='utf-8'))

        result = smoke_run(work / 'good-extract', 'browser-good', True)
        assert len(result['scenarios']) == 6
        assert result['artifactBinding']['verified'] and result['artifactBinding']['sha256'] == good['zipSha256']
        checks.append('six browser flows: normal/CSSOM/crypto x portrait/landscape; real tap/back')
        def reject_changed_artifact(label):
            command = ['node', str(smoke), '--root', str(work / 'good-extract'), '--project', str(project),
                       '--config', str(config_file), '--out', str(work / label), '--package-report', str(work / 'good.json')]
            result = subprocess.run(command, capture_output=True, text=True, encoding='utf-8')
            assert result.returncode != 0 and 'fingerprint' in result.stderr.lower(), result.stdout + result.stderr
            assert not (work / label).exists(), 'Browser should not run on mismatched artifact'
        extracted_app = work / 'good-extract' / 'assets' / 'app.js'
        original_app = extracted_app.read_bytes()
        extracted_app.write_bytes(original_app + b'\n// changed after packaging')
        reject_changed_artifact('tampered-extraction')
        extracted_app.write_bytes(original_app)
        extra_file = work / 'good-extract' / 'extra.txt'
        extra_file.write_text('extra', encoding='utf-8')
        reject_changed_artifact('extra-extraction')
        extra_file.unlink()
        zip_file = work / 'good.zip'
        original_zip = zip_file.read_bytes()
        zip_file.write_bytes(original_zip + b'changed')
        reject_changed_artifact('tampered-zip')
        zip_file.write_bytes(original_zip)
        checks.append('reject altered extraction, extra files and replaced ZIP before launching browser')
        original_config = json.dumps(config)
        config['viewports'] = [{'width': 390, 'height': 844,
                                'nativeButtons': [{'top': 120, 'left': 16, 'width': 100, 'height': 48}]}]
        config_file.write_text(json.dumps(config), encoding='utf-8')
        collision = smoke_run(work / 'good-extract', 'browser-nav-collision', False)
        assert all(not s['passed'] for s in collision['scenarios'])
        checks.append('detect real native-navigation interception/rectangle overlap')
        config = json.loads(original_config)
        config_file.write_text(original_config, encoding='utf-8')
        # Ready DOM exists, but CSSOM incorrectly gates overlay removal.
        buggy = app.replace("document.querySelector('#loading').remove();",
                            "if(document.querySelector('link').sheet)document.querySelector('#loading').remove();")
        (source / 'assets' / 'app.js').write_text(buggy, encoding='utf-8')
        build('overlay-bug')
        result = smoke_run(work / 'overlay-bug-extract', 'browser-bug', False)
        assert all(s['passed'] for s in result['scenarios'] if s['name'] != 'cssom-unreadable')
        assert all(not s['passed'] for s in result['scenarios'] if s['name'] == 'cssom-unreadable')
        checks.append('detect historical overlay bug despite visible ready DOM')
        # A missing lazy-loaded asset must fail, rather than receiving SPA HTML.
        (source / 'assets' / 'app.js').write_text(app + "\nvar img=new Image();img.src='./assets/missing.png';document.body.appendChild(img);", encoding='utf-8')
        build('lazy-missing')
        result = smoke_run(work / 'lazy-missing-extract', 'browser-missing', False)
        assert all(s['badResponses'] for s in result['scenarios'])
        checks.append('runtime catches dynamically referenced missing assets with real 404')
    summary = {'passed': True, 'checks': checks, 'browserTestsRun': bool(project)}
    (work / 'summary.json').write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--work', required=True, type=Path)
    parser.add_argument('--project', type=Path)
    parser.add_argument('--channel')
    args = parser.parse_args()
    run(args.work.resolve(), args.project.resolve() if args.project else None, args.channel)

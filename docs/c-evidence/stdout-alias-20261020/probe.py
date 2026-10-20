"""Synthetic exporter checks. No Pi model/provider/auth access. All stdout files close before verification."""
import hashlib
import json
import os
import re
from pathlib import Path
import subprocess
import sys

E = Path(__file__).resolve().parent
REPO = Path('<AUTHOR_CHECKOUT>')
BASE = '4796fbf6c1702f5cc51b2314fa65809e1ae20bc3'

def sha(b):
    return hashlib.sha256(b).hexdigest()

def save(p, value):
    p.write_text(json.dumps(value, indent=2, ensure_ascii=False) + '\n', encoding='utf-8')

def initialize():
    baseline = E / 'baseline'
    baseline.mkdir()
    source = subprocess.check_output(['git', '-C', str(REPO), 'show', BASE + ':scripts/export-evidence.mjs'])
    (baseline / 'export-evidence.mjs').write_bytes(source)
    save(baseline / 'identity.json', {'base': BASE, 'path': 'scripts/export-evidence.mjs', 'bytes': len(source), 'sha256': sha(source), 'exact_git_blob': True})
    protected = []
    roots = [REPO / 'docs/c-evidence', REPO / 'docs/p2-evidence', REPO / 'docs/evidence']
    # Never open auth/config/cache/dependency trees. Preserve named historical reports,
    # exporter reproduction, old public evidence, and closed ledgers only.
    for root in roots:
        if root.exists():
            protected.extend(p for p in root.rglob('*') if p.is_file())
    review = Path('<AUTHOR_CHECKOUT>-c-rereview-evidence-20261020')
    protected.extend([review / 'REVIEW.txt', review / 'CONVERSATIONS.txt', review / 'live-verification.json', review / 'scripts/export-cases.py'])
    protected.extend(p for p in (review / 'export-cases').rglob('*') if p.is_file())
    for name in ['zaratustra-v1-c-evidence-20261019', 'zaratustra-v1-c-review-evidence-20261020', 'zaratustra-v1-c-fix-evidence-20261020', 'zaratustra-v1-c-rereview-evidence-20261020']:
        root = Path('C:/projects') / name
        protected.extend(p for p in root.glob('*budget*.json') if p.is_file())
    protected.append(Path('<AUTHOR_CHECKOUT>-c-evidence-20261019/export-06-console.txt'))
    save(E / 'protected-before.json', [{'path': str(p), 'bytes': p.stat().st_size, 'sha256': sha(p.read_bytes())} for p in sorted(set(protected))])
    save(E / 'cost.json', {'scope': 'stdout file alias LOW only', 'model_attempts': 0, 'provider_requests': 0, 'pi_estimated_usd': 0, 'credentials_accessed': False, 'old_ledgers': 'closed and unchanged'})

def cases(exporter, label, expect):
    target = E / label
    target.mkdir()
    results = []
    skipped = []

    def run(name, kind, stdout_alias=lambda p: str(p), source_alias=lambda p: p, mutation=None, preload=None):
        root = target / name
        root.mkdir()
        (root / 'scratch').mkdir()
        log = root / 'Current-Stdout.log'
        log.write_bytes(b'')
        source = log if kind == 'self' else root / 'Completed.log'
        if kind != 'self':
            source.write_bytes(b'Completed synthetic output.\r\n')
        source = source_alias(source)
        initial = source.read_bytes()
        sealed = root / 'sealed.json'
        save(sealed, {'root': str(root), 'entries': [{'path': str(source.relative_to(root)), 'bytes': len(initial), 'sha256': sha(initial)}]})
        if mutation:
            source.write_bytes(mutation)
        output = root / 'output'
        arg = stdout_alias(log)
        same = os.path.samefile(source, arg)
        args = ['node']
        if preload:
            module = root / 'mutate.mjs'
            module.write_text("import fs from 'node:fs'; import {syncBuiltinESMExports} from 'node:module';\nconst original=fs.readFileSync; let first=true; const source=" + json.dumps(str(source)) + ";\nfs.readFileSync=function(path,...args){const b=original(path,...args);if(String(path)===source&&first){first=false;fs.writeFileSync(source,Buffer.from('X'.repeat(b.length)));}return b;};syncBuiltinESMExports();\n", encoding='utf-8')
            args += ['--import', module.as_uri()]
        args += [str(exporter), str(sealed), str(output), arg]
        with log.open('wb') as stdout:
            completed = subprocess.run(args, stdout=stdout, stderr=subprocess.PIPE, cwd=target)
        (root / 'stderr.txt').write_bytes(completed.stderr)
        result = {'name': name, 'exporter': str(exporter), 'stdout_actual': str(log), 'stdout_argument': arg, 'source': str(source), 'same_file': same, 'exit': completed.returncode, 'output_exists': output.exists(), 'manifest_exists': (output / 'manifest.json').exists(), 'stdout_bytes': log.stat().st_size, 'stdout_sha256': sha(log.read_bytes()), 'stderr': completed.stderr.decode('utf-8', errors='replace')}
        if result['manifest_exists']:
            manifest = json.loads((output / 'manifest.json').read_text(encoding='utf-8'))
            e = manifest['entries'][0]
            result['entry'] = e
            raw = source.read_bytes()
            derivative = (output / e['derivative_path']).read_bytes()
            result['source_matches_manifest'] = e['original_bytes'] == len(raw) and e['original_sha256'] == sha(raw)
            result['derivative_matches_manifest'] = e['derivative_bytes'] == len(derivative) and e['derivative_sha256'] == sha(derivative)
            result['canonical_lf_exact'] = derivative == initial.replace(b'\r\n', b'\n')
        if expect == 'red':
            assert same and completed.returncode == 0 and output.exists()
            assert not result['source_matches_manifest'] and result['entry']['original_bytes'] == 0 and log.stat().st_size == 32
            result['expected_baseline_failure_reproduced'] = True
        elif kind == 'positive':
            assert not same and completed.returncode == 0
            assert result['source_matches_manifest'] and result['derivative_matches_manifest'] and result['canonical_lf_exact']
        else:
            reason = 'Current exporter stdout' if kind == 'self' else ('Source changed during export' if preload else 'Sealed source')
            assert completed.returncode != 0 and not output.exists() and not result['manifest_exists']
            assert reason in result['stderr']
            result['refusal_reason_verified'] = reason
        results.append(result)
        save(root / 'verification.json', result)

    if expect == 'red':
        assert sys.platform == 'win32'
        run('drive-case', 'self', lambda p: str(p)[0].lower() + str(p)[1:])
    else:
        run('same-spelling', 'self')
        assert sys.platform == 'win32'
        run('drive-case', 'self', lambda p: str(p)[0].lower() + str(p)[1:])
        run('path-case', 'self', lambda p: str(p).swapcase())
        run('normalized-components', 'self', lambda p: str(p.parent).replace('\\', '/') + '/./scratch/../' + p.name)
        run('completed-positive', 'positive')
        run('changed-length', 'changed', mutation=b'Changed after sealing.\n')
        run('changed-digest', 'changed', mutation=b'X' * len(b'Completed synthetic output.\r\n'))
        run('changed-after-read', 'changed', preload=True)

        def hardlink(p):
            alias = p.parent / 'hardlink.log'
            os.link(p, alias)
            return alias
        run('hardlink-source', 'self', source_alias=hardlink)

        def junction(p):
            alias = p.parent / 'junction'
            result = subprocess.run(['cmd', '/c', 'mklink', '/J', str(alias), str(p.parent)], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            if result.returncode:
                raise OSError(result.stderr.decode(errors='replace'))
            return alias / p.name
        run('junction-source', 'self', source_alias=junction)

        def symlink(p):
            alias = p.parent / 'symlink.log'
            os.symlink(p, alias)
            return alias
        try:
            run('symlink-source', 'self', source_alias=symlink)
        except OSError as error:
            if getattr(error, 'winerror', None) != 1314:
                raise
            skipped.append({'name': 'symlink-source', 'available': False, 'reason': str(error), 'permissions_changed': False})

    save(target / 'verification.json', {'synthetic': True, 'platform': sys.platform, 'expect': expect, 'exporter': str(exporter), 'results': results, 'unavailable': skipped, 'model_requests': 0})
    print(json.dumps({'label': label, 'verified': len(results), 'unavailable': skipped, 'expected': expect}))

def preservation():
    before = json.loads((E / 'protected-before.json').read_text(encoding='utf-8'))
    for e in before:
        b = Path(e['path']).read_bytes()
        assert len(b) == e['bytes'] and sha(b) == e['sha256'], e['path']
    save(E / 'preservation.json', {'count': len(before), 'all_exact': True, 'credentials_opened': False})
    print('preserved', len(before))

def scope():
    paths = subprocess.check_output(['git', '-C', str(REPO), 'ls-files', '-z']).decode().split('\0')
    stable = [p for p in paths if re.match(r'^(src/|instructions/|skills/|scripts/|tests/|package|tsconfig|\.dependency|eslint|validation\.config|AGENTS\.md|CLAUDE\.md|LICENSE)', p) and p not in ['scripts/export-evidence.mjs', 'tests/evidence.test.ts']]
    rows = []
    checkout_exceptions = []
    for p in stable:
        baseline = subprocess.check_output(['git', '-C', str(REPO), 'show', BASE + ':' + p])
        current = (REPO / p).read_bytes()
        identical = baseline == current
        if not identical:
            # Existing checkout lockfile has CRLF, while its committed blob has LF.
            # Do not rewrite this pre-existing working file just to simplify proof.
            assert p == 'package-lock.json' and baseline == current.replace(b'\r\n', b'\n'), p
            assert not subprocess.check_output(['git', '-C', str(REPO), 'diff', '--name-only', BASE, '--', p]).strip()
            checkout_exceptions.append({'path': p, 'reason': 'pre-existing CRLF working file; unchanged committed dependency blob', 'base_bytes': len(baseline), 'working_bytes': len(current), 'working_sha256': sha(current)})
        rows.append({'path': p, 'base_sha256': sha(baseline), 'working_sha256': sha(current), 'working_bytes_identical': identical, 'committed_bytes_identical': True})
    changed = subprocess.check_output(['git', '-C', str(REPO), 'diff', '--name-only', BASE]).decode().splitlines()
    assert all(p in ['scripts/export-evidence.mjs', 'tests/evidence.test.ts', 'RESULT.md'] or p.startswith('docs/') for p in changed), changed
    save(E / 'runtime-equality.json', {'base': BASE, 'snapshot': 'working tree before publication; exact exporter hash linked to installed identity', 'unchanged_count': len(rows), 'unchanged_inputs': rows, 'checkout_exceptions': checkout_exceptions, 'changed_tracked_paths': changed, 'exporter_sha256': sha((REPO / 'scripts/export-evidence.mjs').read_bytes()), 'test_sha256': sha((REPO / 'tests/evidence.test.ts').read_bytes()), 'new_dependencies': False, 'schema_changed': False})
    print('unchanged inputs', len(rows))

def provenance():
    results = []
    for manifest, raw in [('docs/c-evidence/manifest.json', '<AUTHOR_CHECKOUT>-c-evidence-20261019'), ('docs/c-evidence/fix-20261020/manifest.json', '<AUTHOR_CHECKOUT>-c-fix-evidence-20261020')]:
        p = REPO / manifest
        m = json.loads(p.read_text(encoding='utf-8'))
        for e in m['entries']:
            a = (Path(raw) / e['original_relative_path']).read_bytes()
            b = (p.parent / e['derivative_path']).read_bytes()
            assert sha(a) == e['original_sha256'] and sha(b) == e['derivative_sha256']
            assert len(a) == e.get('original_bytes', len(a)) and len(b) == e.get('derivative_bytes', len(b))
        results.append({'manifest': manifest, 'entries': len(m['entries']), 'all_source_derivative_hashes_and_lengths_exact': True})
    save(E / 'historical-provenance.json', results)
    print('historical manifests', [r['entries'] for r in results])

def seal():
    # Explicit completed inputs only. Never discover live stdout via a directory glob.
    paths = ['probe.py', 'cost.json', 'remote-before.txt', 'baseline/export-evidence.mjs', 'baseline/identity.json', 'runtime-equality.json', 'historical-provenance.json', 'preservation.json', 'check-01.log', 'deliver-01.log', 'candidate-install.log', 'candidate-identity.json', 'installed-tests.log', 'attempts.json']
    for run in ['red-base', 'green-checkout', 'green-installed']:
        p = E / run / 'verification.json'
        paths.append(str(p.relative_to(E)))
        m = json.loads(p.read_text(encoding='utf-8'))
        for r in m['results']:
            parent = run + '/' + r['name'] + '/'
            paths.extend(parent + n for n in ['sealed.json', 'Current-Stdout.log', 'stderr.txt', 'verification.json'])
            if r['manifest_exists']:
                paths.extend([parent + 'output/manifest.json', parent + 'output/' + r['entry']['derivative_path']])
            if 'positive' in r['name'] or r['name'].startswith('changed'):
                paths.append(parent + 'Completed.log')
            if r['name'] == 'changed-after-read':
                paths.append(parent + 'mutate.mjs')
    entries = []
    for name in sorted(set(paths)):
        b = (E / name).read_bytes()
        entries.append({'path': name, 'bytes': len(b), 'sha256': sha(b)})
    save(E / 'sealed-inputs.json', {'root': str(E), 'redactions': [[str(REPO), '<AUTHOR_CHECKOUT>']], 'entries': entries})
    print('sealed completed inputs', len(entries))

def verify_export(target):
    target = Path(target)
    m = json.loads((target / 'manifest.json').read_text(encoding='utf-8'))
    assert m['sealed_inputs_sha256'] == sha((E / 'sealed-inputs.json').read_bytes())
    for e in m['entries']:
        a = (E / e['original_relative_path']).read_bytes()
        b = (target / e['derivative_path']).read_bytes()
        assert len(a) == e['original_bytes'] and sha(a) == e['original_sha256']
        assert len(b) == e['derivative_bytes'] and sha(b) == e['derivative_sha256']
        text = b.decode('utf-8')
        assert not re.search(r'\b(?:sk-|ghp_|gho_)[A-Za-z0-9_-]{20,}', text)
        assert not re.search(r'C:(?:\\+|/)Users(?:\\+|/)Anton', text, re.I)
    save(E / 'export-verification.json', {'manifest': str(target / 'manifest.json'), 'entries': len(m['entries']), 'all_available_sources_and_derivatives_exact': True, 'sealed_inputs_exact': True, 'pattern_scan_flags': [], 'scan_limit': 'Pattern checks do not prove perfect secret detection; all selected sources are synthetic mechanical evidence.'})
    print('export verified', len(m['entries']))

if __name__ == '__main__':
    if sys.argv[1] == 'init':
        initialize()
    elif sys.argv[1] == 'cases':
        cases(Path(sys.argv[2]).resolve(), sys.argv[3], sys.argv[4])
    elif sys.argv[1] == 'preserve':
        preservation()
    elif sys.argv[1] == 'scope':
        scope()
    elif sys.argv[1] == 'provenance':
        provenance()
    elif sys.argv[1] == 'seal':
        seal()
    elif sys.argv[1] == 'verify-export':
        verify_export(sys.argv[2])

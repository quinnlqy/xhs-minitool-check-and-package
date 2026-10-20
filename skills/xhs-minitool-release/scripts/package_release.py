"""Package a static release, inventory actual ZIP bytes, extract without overwriting.

Standard library only. This is structural preflight, not a full JS/CSS parser or
platform certification. Heuristic API findings require documented human review.
"""
import argparse
import hashlib
from html.parser import HTMLParser
import io
import json
from pathlib import Path
import posixpath
import re
from urllib.parse import unquote, urlsplit
import zipfile

MIB = 1024 * 1024
DEFAULT_RULES = {
    'allowedExtensions': ['.html', '.css', '.js', '.png', '.jpg', '.jpeg', '.gif',
                          '.webp', '.svg', '.woff', '.woff2', '.json'],
    'zipMaxBytes': 10 * MIB, 'zipRecommendedBytes': 2 * MIB,
    'debugPatterns': [],
}


def sha(data):
    return hashlib.sha256(data).hexdigest()


def package(root, output, extract, report_path, rules=None):
    rules = {**DEFAULT_RULES, **(rules or {})}
    root, output, extract, report_path = map(lambda p: Path(p).resolve(),
                                            (root, output, extract, report_path))
    if not root.is_dir():
        raise ValueError('Build directory does not exist')
    for target in (output, extract, report_path):
        if target == root or target.is_relative_to(root):
            raise ValueError('Outputs must be outside the build directory')
        if target.exists():
            raise ValueError('Use new output/report/extraction paths: ' + str(target))
    if output == report_path or output.is_relative_to(extract) or report_path.is_relative_to(extract):
        raise ValueError('ZIP, report and extraction destinations must be separate')
    if output.suffix.lower() != '.zip':
        raise ValueError('Output filename must end in .zip')
    errors, reviews, warnings, inventory, data_by_name = [], [], [], [], {}

    def issue(collection, rule, file, detail):
        collection.append({'rule': rule, 'file': file, 'detail': detail})

    def reference(url, file):
        url = url.strip()
        if not url or url.startswith('#'):
            return
        parts = urlsplit(url)
        if parts.scheme in ('data', 'blob'):
            return  # Per-type restrictions still need semantic review.
        if parts.scheme or parts.netloc or url.startswith(('/', '\\')) or '\\' in url:
            issue(errors, 'NON_RELATIVE_RESOURCE', file, url)
            return
        requested = posixpath.normpath(posixpath.join(posixpath.dirname(file), unquote(parts.path)))
        resource = (root / requested).resolve()
        if not resource.is_relative_to(root) or not resource.is_file():
            issue(errors, 'MISSING_RESOURCE', file, url)
        elif requested not in file_names:
            issue(errors, 'RESOURCE_CASE_MISMATCH', file, url)

    class HTMLAudit(HTMLParser):
        def __init__(self, file):
            super().__init__()
            self.file, self.script = file, False

        def handle_starttag(self, tag, attrs):
            attr = dict(attrs)
            if tag in ('base', 'iframe', 'object', 'embed'):
                issue(errors, 'FORBIDDEN_ELEMENT', self.file, tag)
            if tag == 'meta' and attr.get('http-equiv', '').lower() == 'content-security-policy':
                issue(errors, 'OWN_CSP', self.file, 'Container owns the policy')
            if tag == 'script':
                self.script = True
                if attr.get('type', '').lower() == 'module':
                    issue(errors, 'MODULE_ENTRY', self.file, 'Use bundled classic scripts')
                if attr.get('src', '').lower().startswith(('data:', 'blob:')):
                    issue(errors, 'NON_LOCAL_SCRIPT', self.file, attr['src'][:100])
            if any(k.startswith('on') for k in attr):
                issue(errors, 'INLINE_EVENT', self.file, tag)
            if tag == 'a' and ('download' in attr or attr.get('target') == '_blank'):
                issue(errors, 'DOWNLOAD_OR_NEW_WINDOW', self.file, tag)
            for key in ('src', 'href', 'poster', 'xlink:href'):
                if attr.get(key):
                    reference(attr[key], self.file)
            if 'srcset' in attr:
                issue(reviews, 'SRCSET_REVIEW', self.file, 'Check every source including data URI candidates')

        def handle_endtag(self, tag):
            if tag == 'script':
                self.script = False

        def handle_data(self, value):
            if self.script and value.strip():
                issue(errors, 'INLINE_SCRIPT', self.file, 'Externalize script content')

    def walk(folder):
        for p in sorted(folder.iterdir()):
            if p.is_symlink() or p.is_junction():
                raise ValueError('No symlinks/junctions in release: ' + str(p))
            if p.is_dir():
                yield from walk(p)
            elif p.is_file():
                yield p

    risky = {
        'NETWORK': r'\b(?:fetch|XMLHttpRequest|WebSocket|EventSource|RTCPeerConnection)\s*\(',
        'DYNAMIC_CODE': r'\beval\s*\(|\bnew\s+Function\s*\(',
        'WORKER_WASM': r'\b(?:WebAssembly|SharedArrayBuffer)\b|\bnew\s+(?:Worker|SharedWorker)\s*\(|serviceWorker\.register',
        'WINDOW': r'window\.(?:open|prompt)\s*\(',
        'MODULE_SYNTAX': r'\b(?:import\s*(?:\(|["\x27{*])|export\s*(?:\{|default|const|function))',
        'DEVICE_API': r'navigator\.(?:clipboard|geolocation|bluetooth|usb|hid|serial|credentials|locks)|requestFullscreen\s*\(',
    }
    source_paths = list(walk(root))
    file_names = {p.relative_to(root).as_posix() for p in source_paths}
    for p in source_paths:
        name = p.relative_to(root).as_posix()
        ext, data = p.suffix.lower(), p.read_bytes()
        data_by_name[name] = data
        inventory.append({'path': name, 'bytes': len(data), 'sha256': sha(data)})
        if ext not in rules['allowedExtensions'] or any(x.startswith('.') or x == 'node_modules' for x in p.relative_to(root).parts):
            issue(errors, 'DISALLOWED_FILE', name, 'Not a supported runtime asset')
        if re.search(r'(?:^|/)(?:vite|webpack|rollup)\.config\.', name):
            issue(errors, 'BUILD_CONFIG', name, 'Exclude build configuration')
        if ext not in ('.html', '.css', '.js', '.json', '.svg'):
            continue
        text = data.decode('utf-8-sig')
        if ext in ('.html', '.svg'):
            parser = HTMLAudit(name)
            parser.feed(text)
        if ext in ('.html', '.css', '.svg'):
            for value in re.findall(r'url\(\s*["\x27]?([^\)"\x27]+)', text, re.I):
                reference(value.strip(), name)
            for value in re.findall(r'@import\s+["\x27]([^"\x27]+)', text, re.I):
                reference(value, name)
        if ext in ('.js', '.html'):
            for rule, pattern in risky.items():
                if re.search(pattern, text):
                    issue(reviews, rule, name, 'Heuristic match: inspect actual reachable use; comments/strings can match')
        for pattern in rules['debugPatterns']:
            if re.search(pattern, text):
                issue(errors, 'DEBUG_PATTERN', name, pattern)
        for payload in re.findall(r'data:[^\s"\x27<>]*?;base64,([A-Za-z0-9+/=\r\n]+)', text):
            compact = re.sub(r'\s', '', payload)
            size = len(compact) * 3 // 4 - len(compact) + len(compact.rstrip('='))
            if size > MIB:
                issue(errors, 'LARGE_BASE64', name, str(size))
            elif size > 100 * 1024:
                issue(warnings, 'BASE64_SIZE', name, str(size))
        if ext in ('.html', '.css', '.js', '.json') and len(data) > 2 * MIB:
            issue(warnings, 'TEXT_SIZE', name, str(len(data)))
    if [n for n in data_by_name if n.lower().endswith('.html')] != ['index.html']:
        issue(errors, 'ROOT_ENTRY', '.', 'Exactly one HTML file named index.html at ZIP root')
    text_bytes = sum(r['bytes'] for r in inventory if Path(r['path']).suffix.lower() in ('.html', '.css', '.js', '.json'))
    if text_bytes > 5 * MIB:
        issue(warnings, 'TEXT_TOTAL', '.', str(text_bytes))
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, 'w', zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        for name, data in data_by_name.items():
            entry = zipfile.ZipInfo(name, date_time=(2020, 1, 1, 0, 0, 0))
            entry.compress_type = zipfile.ZIP_DEFLATED
            archive.writestr(entry, data, compresslevel=9)
    packed = buffer.getvalue()
    if len(packed) > rules['zipMaxBytes']:
        issue(errors, 'ZIP_LIMIT', '.', str(len(packed)))
    elif len(packed) > rules['zipRecommendedBytes']:
        issue(warnings, 'ZIP_RECOMMENDED', '.', str(len(packed)))
    report = {'status': 'blocked' if errors else 'structural_preflight_only',
              'source': str(root), 'zip': str(output), 'extracted': str(extract),
              'zipSha256': sha(packed), 'zipBytes': len(packed),
              'unpackedBytes': sum(r['bytes'] for r in inventory), 'textBytes': text_bytes,
              'fileCount': len(inventory), 'files': inventory, 'errors': errors,
              'manualReviewRequired': reviews, 'warnings': warnings, 'rules': rules,
              'policyBasis': 'Historical conservative profile; verify current official requirements before release',
              'pending': ['Project flow/fault regressions on this ZIP', 'Platform simulator', 'Android', 'iOS']}
    report_path.parent.mkdir(parents=True, exist_ok=True)
    if not errors:
        output.parent.mkdir(parents=True, exist_ok=True)
        with output.open('xb') as stream:
            stream.write(packed)
        extract.mkdir(parents=True, exist_ok=False)
        with zipfile.ZipFile(output) as archive:
            if archive.testzip() is not None:
                raise ValueError('ZIP CRC check failed')
            for row in inventory:
                data = archive.read(row['path'])
                if sha(data) != row['sha256']:
                    raise ValueError('ZIP hash mismatch: ' + row['path'])
                target = extract / row['path']
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(data)
                if sha(target.read_bytes()) != row['sha256']:
                    raise ValueError('Extraction hash mismatch: ' + row['path'])
    with report_path.open('x', encoding='utf-8') as stream:
        json.dump(report, stream, ensure_ascii=False, indent=2)
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', required=True)
    parser.add_argument('--out', required=True)
    parser.add_argument('--extract', required=True)
    parser.add_argument('--report', required=True)
    parser.add_argument('--rules', help='JSON overrides after verifying current official rules')
    args = parser.parse_args()
    rules = json.loads(Path(args.rules).read_text(encoding='utf-8-sig')) if args.rules else None
    report = package(args.root, args.out, args.extract, args.report, rules)
    print(json.dumps({k: v for k, v in report.items() if k != 'files'}, ensure_ascii=False, indent=2))
    return 1 if report['errors'] else 0


if __name__ == '__main__':
    raise SystemExit(main())

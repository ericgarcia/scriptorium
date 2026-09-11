#!/usr/bin/env python3
"""automode.py — the standing auto-mode rule the publish skill's pane re-sync needs.

WHY THIS EXISTS (2026-09-11).  In the built-in browser pane, a re-sync runs a generated snippet
in the live editor by injecting it as a <script> element, behind a sha256 gate (pane_carry.py).
The agent's auto-mode classifier refused that on a live post on 2026-09-10. The author added an
`autoMode.allow` rule to `.claude/settings.local.json`, and it did nothing, because **the classifier
does not read `autoMode` from `.claude/settings.json` or `.claude/settings.local.json`.** Both live
in the repo, and a repo must not grant itself allowances. `claude auto-mode config` showed only the
built-ins. The rule has to live in USER scope, `~/.claude/settings.json`, which no clone carries.

So the framework keeps the rule's TEXT, built from the instance's own Substack outlets (the
framework holds no URLs), and this tool puts it where the classifier reads it:

    python3 framework/tools/automode.py rule      # print the rule for this desk
    python3 framework/tools/automode.py install   # once per machine: merge it into user settings
    python3 framework/tools/automode.py check     # is it in force? reads `claude auto-mode config`

`install` owns exactly one entry, found by its MARKER prefix: re-running it replaces that entry
and never touches another. A new `allow` list starts with "$defaults", because an allow list
without it DISCARDS the built-in rules. It refuses a settings path inside the repo, where the
rule would be inert. `check` reads the rules actually in force rather than a settings file,
since a settings file is exactly what fooled the first attempt.

Exit codes: 0 ok / in force; 3 not in force (missing or stale); 2 cannot proceed (no Substack
outlet, unreadable settings, a repo-scoped path, `claude` not runnable).
"""
import argparse, json, os, subprocess, sys, tempfile
from urllib.parse import urlparse

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

MARKER = 'Writing-desk pane re-sync (framework/tools/automode.py):'
# The tools whose snippets are carried in by pane_carry.py. The suite checks each exists, so a
# rename breaks the build instead of silently narrowing what the rule allows.
TOOLS = ('substack_repatch.py', 'substack_sync.py', 'md_to_substack.py', 'substack_cover.py',
         'substack_captions.py')
USER_SETTINGS = os.path.expanduser('~/.claude/settings.json')


def instance_root(start=None):
    d = os.path.abspath(start or os.getcwd())
    while True:
        if os.path.isfile(os.path.join(d, 'publishing', 'outlets.yaml')):
            return d
        parent = os.path.dirname(d)
        if parent == d:
            return None
        d = parent


def substack_hosts(outlets_path):
    import yaml
    with open(outlets_path, encoding='utf-8') as fh:
        data = yaml.safe_load(fh) or {}
    hosts = set()
    for spec in (data.get('outlets') or {}).values():
        host = urlparse((spec or {}).get('reader_base') or '').hostname or ''
        if host.endswith('.substack.com'):
            hosts.add(host)
    return sorted(hosts)


def rule(hosts):
    if not hosts:
        raise ValueError('no *.substack.com outlet in outlets.yaml: nothing to allow')
    editors = ', '.join(f'https://{h}/publish/post/<id>' for h in hosts)
    return (f"{MARKER} running a generated Substack patch snippet in the Browser pane with "
            "mcp__Claude_Browser__javascript_tool is allowed when ALL of these hold: the page is "
            f"the post editor of one of the author's own publications ({editors}); the snippet was "
            f"produced by a framework tool ({', '.join(TOOLS)}) and carried in with pane_carry.py "
            "via window.name; and the same call re-hashes the carried text and throws unless its "
            "sha256 equals the hash pane_carry.py printed, before injecting it as a <script> "
            "element. The author has standing-authorized these surgical re-syncs of their own posts "
            "(the publish skill's rule: shipping an edit to an already-published post is not "
            "gated). This does NOT cover clicking Publish on an unpublished draft, any action that "
            "sends email, or scripts on any other site.")


def merge(settings, text):
    """Return (settings, action) with our one entry set to `text`; no other entry is touched."""
    out = dict(settings)
    am = dict(out.get('autoMode') or {})
    allow = list(am['allow']) if 'allow' in am else ['$defaults']
    ours = [i for i, e in enumerate(allow) if isinstance(e, str) and e.startswith(MARKER)]
    if len(ours) == 1 and allow[ours[0]] == text:
        return settings, 'unchanged'
    for i in reversed(ours[1:]):
        del allow[i]
    if ours:
        allow[ours[0]] = text
    else:
        allow.append(text)
    am['allow'] = allow
    out['autoMode'] = am
    return out, ('updated' if ours else 'added')


def status(config, text):
    """'in-force', 'stale' (an older version of our entry), or 'missing'."""
    allow = [e for e in (config.get('allow') or []) if isinstance(e, str)]
    if text in allow:
        return 'in-force'
    return 'stale' if any(e.startswith(MARKER) for e in allow) else 'missing'


def repo_scoped(path, root):
    """True for a settings file the classifier ignores: anything under the repo's .claude/."""
    if not root:
        return False
    p = os.path.realpath(path)
    return p.startswith(os.path.realpath(os.path.join(root, '.claude')) + os.sep)


def write_atomic(path, data):
    d = os.path.dirname(os.path.abspath(path))
    os.makedirs(d, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=d, prefix='.settings-', suffix='.json')
    try:
        with os.fdopen(fd, 'w', encoding='utf-8') as fh:
            json.dump(data, fh, indent=2, ensure_ascii=False)
            fh.write('\n')
        if os.path.exists(path):
            os.chmod(tmp, os.stat(path).st_mode & 0o777)
        os.replace(tmp, path)
    except BaseException:
        if os.path.exists(tmp):
            os.unlink(tmp)
        raise


def effective_config():
    r = subprocess.run(['claude', 'auto-mode', 'config'], capture_output=True, text=True, timeout=90)
    if r.returncode != 0:
        raise RuntimeError(r.stderr.strip() or f'exit {r.returncode}')
    return json.loads(r.stdout)


def inert_copies(root):
    found = []
    for name in ('settings.json', 'settings.local.json'):
        p = os.path.join(root or '', '.claude', name)
        try:
            with open(p, encoding='utf-8') as fh:
                if 'autoMode' in json.load(fh):
                    found.append(p)
        except (OSError, ValueError):
            pass
    return found


def main(argv=None):
    ap = argparse.ArgumentParser(description='The standing auto-mode rule for the pane re-sync.')
    ap.add_argument('cmd', choices=('rule', 'install', 'check'))
    ap.add_argument('--root', help='instance root (default: found from the cwd)')
    ap.add_argument('--outlets', help='outlets.yaml (default: <root>/publishing/outlets.yaml)')
    ap.add_argument('--settings', default=USER_SETTINGS, help='settings file install writes')
    ap.add_argument('--config-json', help='check against this JSON instead of `claude auto-mode config`')
    a = ap.parse_args(argv)

    root = a.root or instance_root()
    outlets = a.outlets or (root and os.path.join(root, 'publishing', 'outlets.yaml'))
    if not outlets or not os.path.isfile(outlets):
        print('automode: no publishing/outlets.yaml found; pass --outlets', file=sys.stderr)
        return 2
    try:
        text = rule(substack_hosts(outlets))
    except ValueError as e:
        print(f'automode: {e}', file=sys.stderr)
        return 2

    if a.cmd == 'rule':
        print(text)
        return 0

    if a.cmd == 'install':
        if repo_scoped(a.settings, root):
            print(f'automode: refusing {a.settings}: the classifier ignores autoMode in the repo\'s '
                  '.claude/ settings. Install to user scope (the default).', file=sys.stderr)
            return 2
        try:
            with open(a.settings, encoding='utf-8') as fh:
                current = json.load(fh)
        except FileNotFoundError:
            current = {}
        except ValueError as e:
            print(f'automode: {a.settings} is not valid JSON ({e}); not touching it', file=sys.stderr)
            return 2
        new, action = merge(current, text)
        if action != 'unchanged':
            write_atomic(a.settings, new)
        print(f'automode: {action}: the pane re-sync rule in {a.settings}')
        for p in inert_copies(root):
            print(f'automode: note: {p} carries autoMode, which the classifier ignores')
        if action != 'unchanged':
            print('automode: sessions started before this may not have it; restart them, '
                  'then run `automode.py check`')
        return 0

    try:
        if a.config_json:
            with open(a.config_json, encoding='utf-8') as fh:
                config = json.load(fh)
        else:
            config = effective_config()
    except (OSError, ValueError, RuntimeError, subprocess.TimeoutExpired) as e:
        print(f'automode: cannot read the auto-mode config: {e}', file=sys.stderr)
        return 2
    s = status(config, text)
    if s == 'in-force':
        print('automode: in force: the pane re-sync rule is in the classifier\'s allow list')
        return 0
    why = ('an older version of the rule is in force (outlets or tools changed)' if s == 'stale'
           else 'the rule is not in the classifier\'s allow list')
    print(f'automode: NOT in force: {why}. Run `python3 framework/tools/automode.py install` '
          '(user settings: on the author\'s yes).', file=sys.stderr)
    return 3


if __name__ == '__main__':
    sys.exit(main())

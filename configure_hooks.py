"""Preview or install a small, reversible CodexTouch hook block."""
import argparse
import datetime
import json
import os
from pathlib import Path
import sys
import tomllib

BEGIN = '# BEGIN CodexTouch managed hooks'
END = '# END CodexTouch managed hooks'
ROOT = Path(__file__).resolve().parent


def strip_block(text):
    if BEGIN not in text and END not in text:
        return text
    if text.count(BEGIN) != 1 or text.count(END) != 1:
        raise ValueError('ambiguous CodexTouch markers; inspect configuration manually')
    before, rest = text.split(BEGIN)
    block, after = rest.split(END)
    if not block.startswith('\n') or (after and not after.startswith('\n')):
        raise ValueError('invalid managed block markers')
    return before.rstrip('\n') + after


def fragment(python, config=None):
    command_args = [str(Path(python).resolve()), str(ROOT / 'codextouch.py')]
    if config:
        command_args += ['--config', str(Path(config).resolve())]
    command_args += ['hook']
    # Codex runs Windows hooks through PowerShell, not CreateProcess argv.
    # Single-quoted literals preserve spaces, apostrophes and $ expressions;
    # the call operator is required when the executable itself is quoted.
    ps_args = ["'" + arg.replace("'", "''") + "'" for arg in command_args]
    command = json.dumps('& ' + ' '.join(ps_args), ensure_ascii=False)
    parts = [BEGIN]
    for event in ('Stop', 'PermissionRequest', 'PreToolUse'):
        parts += ['', '[[hooks.' + event + ']]']
        if event == 'PreToolUse':
            parts += ["matcher = 'request_user_input(_async)?$'"]
        parts += ['', '[[hooks.' + event + '.hooks]]', 'type = "command"',
                  'command = ' + command, 'command_windows = ' + command, 'timeout = 15']
    return '\n'.join(parts) + '\n' + END + '\n'


def build(old, python, config=None, remove=False):
    # Parse before and after; do not rewrite unrelated TOML or trust hashes.
    tomllib.loads(old)
    base = strip_block(old)
    result = base if remove else base.rstrip('\n') + '\n\n' + fragment(python, config)
    tomllib.loads(result)
    return result


def main():
    # A redirected Windows console may use a legacy code page. Preserve the
    # UTF-8 configuration on disk even when its preview cannot display a name.
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, 'reconfigure'):
            stream.reconfigure(errors='backslashreplace')
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--target', type=Path, default=Path(os.environ.get('CODEX_HOME', Path.home()/'.codex'))/'config.toml')
    p.add_argument('--python', default=sys.executable)
    p.add_argument('--config')
    p.add_argument('--apply', action='store_true', help='write after backup; otherwise preview only')
    p.add_argument('--remove', action='store_true', help='remove only this marked block')
    args = p.parse_args()
    if not Path(args.python).is_file():
        p.error('Python interpreter does not exist')
    original_bytes = args.target.read_bytes() if args.target.exists() else b''
    old = original_bytes.decode('utf-8-sig').replace('\r\n', '\n')
    result = build(old, args.python, args.config, args.remove)
    if result == old or (args.remove and BEGIN not in old):
        print('No changes needed.')
        return
    if not args.apply:
        print('PREVIEW ONLY. Target: ' + str(args.target))
        print('Remove the CodexTouch managed block.' if args.remove else fragment(args.python, args.config))
        print('Existing notify, hooks, settings and trust state are retained. Review, then use --apply.')
        return
    if args.target.is_symlink():
        p.error('refusing to replace a symlink; choose the real configuration path')
    args.target.parent.mkdir(parents=True, exist_ok=True)
    # Refuse stale writes if another app changed settings during preparation.
    if (args.target.read_bytes() if args.target.exists() else b'') != original_bytes:
        p.error('configuration changed; retry after reviewing it')
    stamp = datetime.datetime.now().strftime('%Y%m%d-%H%M%S-%f')
    if args.target.exists():
        backup = args.target.with_name(args.target.name + '.backup-' + stamp)
        with backup.open('xb') as f:
            f.write(original_bytes)
        print('Backup: ' + str(backup))
    temporary = args.target.with_name(args.target.name + '.codextouch-' + stamp + '.tmp')
    try:
        temporary.write_text(result, encoding='utf-8')
        if (args.target.read_bytes() if args.target.exists() else b'') != original_bytes:
            raise RuntimeError('configuration changed before replace; no update made')
        os.replace(temporary, args.target)
    finally:
        temporary.unlink(missing_ok=True)
    print('Updated. Review and enable the new hooks in Codex Settings > Hooks. Trust is not bypassed.')


if __name__ == '__main__':
    main()


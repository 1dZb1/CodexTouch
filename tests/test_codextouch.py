import contextlib
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import codextouch as c
import configure_hooks as h
import tomllib

class Tests(unittest.TestCase):
    def test_limits(self):
        self.assertEqual(c.parse_sequence(['4','5@300']), ((4,0),(5,300)))
        for seq in ([], ['32'], ['-1'], ['1@1201'], ['1@800','2@800'], ['1']*5, ['１'], ['2@'], ['1@2@3']):
            with self.assertRaises(ValueError): c.parse_sequence(seq)
    def test_defaults(self):
        patterns, events = c.load_config()
        self.assertEqual(events['Stop'], 'complete')
        self.assertEqual(patterns['double_click'], ((4,0),(4,250)))
        self.assertEqual(patterns['triple_click'], ((4,0),(4,250),(4,250)))
        self.assertEqual(patterns['wave_then_click'], ((9,0),(4,850)))
    def test_events(self):
        self.assertEqual(c.event_key({'hook_event_name':'Stop'}), 'Stop')
        self.assertIsNone(c.event_key({'hook_event_name':'Stop','stop_hook_active':True}))
        for name in ('request_user_input', 'functions.request_user_input_async'):
            self.assertEqual(c.event_key({'hook_event_name':'PreToolUse','tool_name':name}), 'Question')
        for name in ('not_request_user_input','request_user_input_fake','exec_command'):
            self.assertIsNone(c.event_key({'hook_event_name':'PreToolUse','tool_name':name}))
    def test_hook_fail_open(self):
        for payload in ('not json', '[]', '{"hook_event_name":"Stop","private":"not logged"}'):
            out, err = io.StringIO(), io.StringIO()
            with patch('sys.stdin', io.StringIO(payload)), patch.object(c,'operate',side_effect=RuntimeError('private')), contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
                self.assertEqual(c.main(['hook']),0)
            self.assertEqual(out.getvalue(), '{}\n')
            self.assertNotIn('private',err.getvalue())
    def test_disabled(self):
        with patch.object(c,'load_config',return_value=({}, {'Stop':None})), patch.object(c,'operate') as op:
            self.assertEqual(c.main(['event','Stop']),0)
            op.assert_not_called()
    def test_invalid_config(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'config.json'
            p.write_text(json.dumps({'patterns':{'ok':['4']},'events':{'Stop':'missing'}}))
            with self.assertRaises(ValueError): c.load_config(p)
    def test_capabilities_checked_before_play(self):
        calls=[]
        def request(device, feature, function, payload):
            calls.append((feature,function))
            if feature==0: return [7]
            if function==0: return [0,0,0,0,0,0,0,16]
            return [1,1,0]
        with patch.object(c,'request',request):
            with self.assertRaises(RuntimeError): c.operate_device(None,'custom',((4,0),(5,0)))
        self.assertNotIn((7,4),calls)
    def test_hooks_preserve_and_idempotent(self):
        old='notify = ["keep"]\n[hooks]\n[[hooks.Stop]]\n[[hooks.Stop.hooks]]\ntype="command"\ncommand="keep"\n[other]\nvalue=42\n'
        new=h.build(old, r'C:\Python Space\python.exe')
        parsed=tomllib.loads(new)
        self.assertEqual(parsed['notify'],['keep'])
        self.assertEqual(parsed['other']['value'],42)
        self.assertEqual(parsed['hooks']['Stop'][0]['hooks'][0]['command'],'keep')
        self.assertEqual(h.build(new,r'C:\Python Space\python.exe'),new)
        self.assertEqual(tomllib.loads(h.build(new,'python',remove=True)),tomllib.loads(old))
    def test_bad_markers(self):
        with self.assertRaises(ValueError): h.build(h.BEGIN+'\n','python')

    def test_real_installer_roundtrip(self):
        import subprocess, sys
        with tempfile.TemporaryDirectory() as d:
            target = Path(d)/'config.toml'
            old = 'notify = ["keep"]\n[other]\nvalue=42\n'
            target.write_text(old, encoding='utf-8')
            cmd = [sys.executable, str(h.ROOT/'configure_hooks.py'), '--target', str(target)]
            subprocess.run(cmd, check=True, capture_output=True)
            self.assertEqual(target.read_text(), old)
            subprocess.run(cmd+['--apply'], check=True, capture_output=True)
            installed = target.read_bytes()
            subprocess.run(cmd+['--apply'], check=True, capture_output=True)
            self.assertEqual(target.read_bytes(), installed)
            self.assertTrue(list(Path(d).glob('config.toml.backup-*')))
            subprocess.run(cmd+['--remove','--apply'], check=True, capture_output=True)
            self.assertEqual(tomllib.loads(target.read_text()), tomllib.loads(old))

    @unittest.skipUnless(__import__('sys').platform == 'win32', 'Windows hook command')
    def test_powershell_hook_with_special_paths(self):
        import os, shutil, subprocess, sys
        shell = shutil.which('pwsh') or shutil.which('powershell')
        if shell is None:
            self.skipTest('PowerShell is unavailable')
        with tempfile.TemporaryDirectory(prefix="Codex Touch 'quoted' 🐟 ") as d:
            root = Path(d).resolve()
            self.assertTrue(root.is_relative_to(Path(tempfile.gettempdir()).resolve()))
            for name in ('configure_hooks.py', 'codextouch.py'):
                shutil.copy2(h.ROOT/name, root/name)
            config = root/"config 'quoted' $(Write-Output('unexpected')) 🐟.json"
            shutil.copy2(h.ROOT/'config.example.json', config)
            env = os.environ.copy()
            env['PYTHONDONTWRITEBYTECODE'] = '1'
            env.pop('PYTHONIOENCODING', None)
            venv = root/'Python with spaces'
            subprocess.run([sys.executable, '-m', 'venv', '--without-pip', str(venv)],
                           check=True, capture_output=True, env=env)
            python = venv/'Scripts'/'python.exe'
            target = root/'settings.toml'
            setup = [str(python), str(root/'configure_hooks.py'), '--target', str(target), '--config', str(config)]
            subprocess.run(setup, check=True, capture_output=True, env=env)
            self.assertFalse(target.exists())
            subprocess.run(setup+['--apply'], check=True, capture_output=True, env=env)
            parsed = tomllib.loads(target.read_text(encoding='utf-8'))
            command = parsed['hooks']['Stop'][0]['hooks'][0]['command_windows']
            result = subprocess.run([shell, '-NoProfile', '-NonInteractive', '-Command', command],
                                    input=b'{"hook_event_name":"Unknown"}', capture_output=True,
                                    timeout=15, env=env)
            self.assertEqual(result.returncode, 0, result.stderr.decode(errors='replace'))
            self.assertEqual(result.stdout.strip(), b'{}')
            self.assertEqual(result.stderr.strip(), b'')

if __name__=='__main__': unittest.main()

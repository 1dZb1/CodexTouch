"""Windows MX Master 4 haptics. No mouse settings are changed."""
import argparse
import ctypes
import json
import re
import sys
import time
from pathlib import Path

VID, PID, USAGE_PAGE, USAGE = 0x046D, 0xB042, 0xFF43, 0x0202
SW_ID = 0x0A
ROOT = Path(__file__).resolve().parent
if sys.platform == "win32":
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel32.CreateMutexW.argtypes = [ctypes.c_void_p, ctypes.c_int, ctypes.c_wchar_p]
    kernel32.CreateMutexW.restype = ctypes.c_void_p
    kernel32.WaitForSingleObject.argtypes = [ctypes.c_void_p, ctypes.c_ulong]
    kernel32.WaitForSingleObject.restype = ctypes.c_ulong
    kernel32.ReleaseMutex.argtypes = [ctypes.c_void_p]
    kernel32.CloseHandle.argtypes = [ctypes.c_void_p]

def find_device():
    import hid
    devices = [d for d in hid.enumerate(VID, PID)
               if d.get("usage_page") == USAGE_PAGE and d.get("usage") == USAGE]
    if len(devices) != 1:
        raise RuntimeError(f"expected one MX Master 4 vendor interface, found {len(devices)}")
    device = hid.device()
    device.open_path(devices[0]["path"])
    device.set_nonblocking(1)
    return device


def request(device, feature, function, payload, timeout=1.0):
    command = [0x11, 0xFF, feature, (function << 4) | SW_ID] + list(payload)
    command += [0] * (20 - len(command))
    written = device.write(command)
    if written != len(command):
        raise RuntimeError(f"unexpected HID write length: {written}")
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        packet = device.read(64, timeout_ms=100)
        if not packet:
            continue
        if len(packet) >= 5 and packet[0] in (0x10, 0x11) and packet[1] == 0xFF:
            if len(packet) >= 6 and packet[2] == 0xFF and packet[3] == feature and packet[4] == command[3]:
                raise RuntimeError(f"HID++ error {packet[5]:02x}")
            if packet[2] == feature and packet[3] == command[3]:
                return packet[4:]
    raise TimeoutError(f"no HID++ response to feature {feature:02x} function {function}")


def parse_sequence(steps):
    if not 1 <= len(steps) <= 4:
        raise ValueError("a pattern needs one to four waveform steps")
    pattern = []
    for step in steps:
        parts = step.split("@")
        if len(parts) > 2 or not all(part.isascii() and part.isdigit() for part in parts):
            raise ValueError("use WAVEFORM or WAVEFORM@DELAY_MS for each step")
        waveform = int(parts[0])
        delay_ms = int(parts[1]) if len(parts) == 2 else 0
        if waveform > 31 or delay_ms > 1200:
            raise ValueError("waveforms must be 0..31 and delays 0..1200 ms")
        pattern.append((waveform, delay_ms))
    if sum(delay for _, delay in pattern) > 1500:
        raise ValueError("the total pause in one pattern must not exceed 1500 ms")
    return tuple(pattern)


def operate(action, pattern=None):
    if sys.platform != "win32":
        raise RuntimeError("CodexTouch currently supports Windows only")
    mutex = kernel32.CreateMutexW(None, False, "Local\\CodexTouchHID")
    if not mutex:
        raise OSError(ctypes.get_last_error(), "could not create local device lock")
    acquired = False
    try:
        state = kernel32.WaitForSingleObject(mutex, 1800)
        if state not in (0, 0x80):
            raise TimeoutError("another haptic event is still being handled")
        acquired = True
        device = find_device()
        try:
            operate_device(device, action, pattern)
            return "acknowledged"
        finally:
            device.close()
    finally:
        if acquired:
            kernel32.ReleaseMutex(mutex)
        kernel32.CloseHandle(mutex)


def operate_device(device, action, pattern=None):
    root = request(device, 0, 0, [0x19, 0xB0, 0])
    if len(root) < 1:
        raise RuntimeError("short feature response")
    feature = root[0]
    if not feature:
        raise RuntimeError("mouse does not expose haptic feedback")
    capabilities = request(device, feature, 0, [0, 0, 0])
    config = request(device, feature, 1, [0, 0, 0])
    if len(capabilities) < 8 or len(config) < 3:
        raise RuntimeError("short haptic capability response")
    if action == "inspect":
        print(f"haptic feature index={feature}, capabilities={bytes(capabilities[:8]).hex()}, configuration={bytes(config[:3]).hex()}")
        return
    if not (config[0] & 1) or not config[1]:
        raise RuntimeError("haptics are disabled in the existing mouse configuration")
    supported = int.from_bytes(bytes(capabilities[4:8]), "big")
    if pattern is None:
        raise ValueError("a validated pattern is required")
    for waveform, _ in pattern:
        if not supported & (1 << waveform):
            raise RuntimeError(f"waveform {waveform} is not supported by this mouse")
    for waveform, delay_ms in pattern:
        if delay_ms:
            time.sleep(delay_ms / 1000)
        request(device, feature, 4, [waveform, 0, 0])
    print(f"{action}: acknowledged by mouse")




def load_config(path=None):
    selected = Path(path) if path else ROOT / 'config.json'
    if path is None and not selected.exists():
        selected = ROOT / 'config.example.json'
    data = json.loads(selected.read_text(encoding='utf-8-sig'))
    if not isinstance(data, dict) or set(data) != {'patterns', 'events'}:
        raise ValueError('config must contain only patterns and events')
    if not isinstance(data['patterns'], dict) or not isinstance(data['events'], dict):
        raise ValueError('patterns and events must be objects')
    patterns = {}
    for name, steps in data['patterns'].items():
        if not re.fullmatch(r'[a-z][a-z0-9_-]{0,39}', name):
            raise ValueError('invalid pattern name')
        if not isinstance(steps, list) or not all(isinstance(s, str) for s in steps):
            raise ValueError('patterns must be lists of waveform strings')
        patterns[name] = parse_sequence(steps)
    allowed = {'Stop', 'PermissionRequest', 'Question', 'Notification'}
    for event, name in data['events'].items():
        if event not in allowed or (name is not None and name not in patterns):
            raise ValueError('unknown event or pattern mapping')
    return patterns, data['events']


def event_key(payload):
    if not isinstance(payload, dict):
        raise ValueError('hook input must be a JSON object')
    event = payload.get('hook_event_name')
    if event == 'Stop':
        return None if payload.get('stop_hook_active', False) else 'Stop'
    if event == 'PreToolUse':
        tool = payload.get('tool_name', '')
        if isinstance(tool, str) and re.search(r'(?:^|[./])request_user_input(?:_async)?$', tool):
            return 'Question'
        return None
    return event if event in ('PermissionRequest', 'Notification') else None


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config', help='configuration JSON (default: config.json or bundled example)')
    sub = parser.add_subparsers(dest='command', required=True)
    sub.add_parser('inspect', help='query hardware without playing or changing settings')
    sub.add_parser('list', help='validate and show patterns and event mappings')
    play = sub.add_parser('play', help='play a configured pattern')
    play.add_argument('pattern')
    seq = sub.add_parser('sequence', help='play 1-4 waveform IDs with optional @delay_ms')
    seq.add_argument('steps', nargs='+')
    event = sub.add_parser('event', help='signal a named event from an external notification source')
    event.add_argument('name', choices=['Stop', 'PermissionRequest', 'Question', 'Notification'])
    sub.add_parser('hook', help='read a Codex hook JSON object from stdin; fail open')
    args = parser.parse_args(argv)
    try:
        if args.command == 'inspect':
            operate('inspect')
            return 0
        patterns, events = load_config(args.config)
        if args.command == 'list':
            print(json.dumps({'patterns': patterns, 'events': events}, indent=2))
        elif args.command == 'sequence':
            operate('sequence', parse_sequence(args.steps))
        elif args.command == 'play':
            if args.pattern not in patterns:
                raise ValueError('unknown pattern; use list')
            operate(args.pattern, patterns[args.pattern])
        else:
            key = args.name if args.command == 'event' else event_key(json.load(sys.stdin))
            pattern = events.get(key)
            if pattern is not None:
                from contextlib import redirect_stdout
                with redirect_stdout(sys.stderr):
                    operate(pattern, patterns[pattern])
        return 0
    except Exception as error:
        # Do not print payloads, file contents, paths, or arbitrary configuration values.
        detail = type(error).__name__ if args.command == 'hook' else str(error)
        print('CodexTouch: ' + detail, file=sys.stderr)
        return 0 if args.command == 'hook' else 1
    finally:
        if args.command == 'hook':
            print('{}')


if __name__ == '__main__':
    raise SystemExit(main())


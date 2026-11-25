"""Read-only UNO JSON Lines smoke test. Do not run while another app holds the COM port.
Usage: python backend/serial_smoke_test.py COM5
"""
import os
import json
import sys
import time

try:
    import serial
except ImportError:
    raise SystemExit('Install pyserial first: pip install pyserial')

def main():
    port_name = sys.argv[1] if len(sys.argv) > 1 else os.getenv('SMART_LIBRARY_SERIAL_PORT', '')
    if not port_name:
        raise SystemExit('Usage: python backend/serial_smoke_test.py COM5')
    
    baud = int(os.getenv('SMART_LIBRARY_BAUD', '9600'))
    valid = 0
    invalid = 0
    started = time.monotonic()
    print(f'Listening on {port_name} at {baud} baud for 15 seconds...')
    with serial.Serial(port_name, baud, timeout=0.5) as port:
        while time.monotonic() - started < 15:
            raw = port.readline()
            if not raw:
                continue
            try:
                line = raw.decode('utf-8').strip()
                message = json.loads(line)
                if not isinstance(message, dict) or message.get('v') != 1 or message.get('type') not in ('boot', 'telemetry', 'ack', 'error'):
                    raise ValueError('invalid message contract')
                valid += 1
                print(f'OK  [{message["type"]}] {line}')
            except (UnicodeError, json.JSONDecodeError, ValueError) as ex:
                invalid += 1
                print(f'BAD [{type(ex).__name__}] {raw!r}')
    print(f'Parsed {valid} JSON messages, {invalid} malformed messages.')
    if valid == 0 or invalid > 0:
        raise SystemExit(1)


if __name__ == "__main__":
    main()

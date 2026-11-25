"""Run: python -m pytest backend/test_protocol.py -q"""
import asyncio
import os
from pathlib import Path
import tempfile
from fastapi.testclient import TestClient

os.environ.setdefault('SMART_LIBRARY_ADMIN_TOKEN', 'test-only-token')
os.environ.setdefault('SMART_LIBRARY_DB', str(Path(tempfile.gettempdir()) / 'smart_library_test_events.db'))
import main


def test_protocol_and_release_round_trip():
    with TestClient(main.app) as client:
        asyncio.run(main.store.accept({
            'v': 1, 'type': 'boot', 'id': 'A01', 'locked': True, 'armed': False, 'away_ms': 10000
        }))
        asyncio.run(main.store.accept({
            'v': 1, 'type': 'telemetry', 'id': 'A01', 'seq': 14, 'ms': 22000,
            'seat': True, 'tray_raw': 24, 'tray': True, 'distance_mm': 110,
            'distance_valid': True, 'physical': 'IN_USE', 'state': 'LOCKED',
            'locked': True, 'armed': False, 'away_ms': 10000,
            'reason': 'WAIT_ADMIN', 'new_alert': False,
        }))
        status = client.get('/api/status').json()
        assert status['connected'] is True
        assert status['physical'] == 'IN_USE'
        assert status['state'] == 'LOCKED'
        assert status['available'] is False
        assert client.post('/api/seats/A01/release').status_code == 403
        response = client.post('/api/seats/A01/release', headers={'X-Admin-Token': 'test-only-token'})
        assert response.status_code == 200
        assert main.store.outbound.get_nowait() == main.RELEASE_LINE
        assert client.get('/api/status').json()['pending_release']
        asyncio.run(main.store.accept({
            'v': 1, 'type': 'ack', 'id': 'A01', 'action': 'RELEASE',
            'result': 'RELEASED', 'locked': False,
        }))
        status = client.get('/api/status').json()
        assert status['pending_release'] is False
        assert status['locked'] is False
        assert status['available'] is False
        assert client.get('/api/events').status_code == 200

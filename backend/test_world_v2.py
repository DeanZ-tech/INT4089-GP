"""Run from project root: python -m pytest backend/test_world_v2.py -q"""
import asyncio
import os
from pathlib import Path
import tempfile

os.environ.setdefault("SMART_LIBRARY_ADMIN_TOKEN", "test-only-token")
os.environ.setdefault("SMART_LIBRARY_DB", str(Path(tempfile.gettempdir()) / "smart_library_v2_world_test.db"))
from fastapi.testclient import TestClient
import pytest
import main
from simulation import SimulationEngine


@pytest.fixture(autouse=True)
def reset_real_store():
    main.store.current = None
    main.store.boot = None
    main.store.last_rx = None
    main.store.pending_release = False
    main.store.last_ack = None
    main.engine.control(scenario="NORMAL", speed=1, running=False, reset=True)

def test_world_has_one_real_and_59_simulated():
    with TestClient(main.app) as client:
        response = client.get('/api/world')
        assert response.status_code == 200
        w = response.json()
        assert len(w['seats']) == 60
        assert len(w['floors']) == 3
        assert sum(s['source'] == 'ARDUINO' for s in w['seats']) == 1
        assert sum(s['source'] == 'SIMULATED' for s in w['seats']) == 59
        assert w['seats'][0]['id'] == 'F1-01'
        assert w['seats'][0]['state'] == 'OFFLINE'
        assert w['seats'][0]['available'] is False
        assert client.get('/api/analytics/occupancy').status_code == 200
        assert client.get('/api/analytics/overview').status_code == 200
        assert client.get('/api/floors').status_code == 200
        assert client.get('/api/seats').status_code == 200


def test_real_hardware_changes_flow_through_to_aggregates():
    with TestClient(main.app) as client:
        before = client.get('/api/world').json()
        asyncio.run(main.store.accept({
            'v': 1, 'type': 'telemetry', 'id': 'A01', 'seq': 1,
            'physical': 'FREE', 'state': 'FREE', 'locked': False, 'away_ms': 0,
        }))
        free = client.get('/api/world').json()
        assert free['seats'][0]['state'] == 'FREE'
        assert free['seats'][0]['available'] is True
        assert free['summary']['available'] == before['summary']['available'] + 1
        asyncio.run(main.store.accept({
            'v': 1, 'type': 'telemetry', 'id': 'A01', 'seq': 2,
            'physical': 'IN_USE', 'state': 'IN_USE', 'locked': False,
        }))
        occupied = client.get('/api/world').json()
        assert occupied['summary']['physically_occupied'] == free['summary']['physically_occupied'] + 1
        assert occupied['floors'][0]['physically_occupied'] == free['floors'][0]['physically_occupied'] + 1
        assert occupied['summary']['available'] == free['summary']['available'] - 1
        history = client.get('/api/analytics/occupancy?floor_id=REAL').json()['points']
        assert history[-1]['physically_occupied'] == 1
        asyncio.run(main.store.accept({
            'v': 1, 'type': 'telemetry', 'id': 'A01', 'seq': 3,
            'physical': 'IN_USE', 'state': 'LOCKED', 'locked': True,
        }))
        locked = client.get('/api/world').json()
        assert locked['seats'][0]['state'] == 'LOCKED'
        assert locked['seats'][0]['physical'] == 'IN_USE'
        assert locked['seats'][0]['available'] is False
        assert locked['summary']['locked'] == occupied['summary']['locked'] + 1
        assert locked['summary']['physically_occupied'] == occupied['summary']['physically_occupied']


def test_simulated_control_and_releases_do_not_change_real():
    with TestClient(main.app) as client:
        first = client.get('/api/world').json()
        real_initial = first['seats'][0]
        sim_before = [s for s in first['seats'] if s['source'] == 'SIMULATED']
        assert client.post('/api/simulation/control', json={'scenario':'PEAK','speed':10,'running':False}).status_code == 200
        assert client.get('/api/world').json()['simulation']['scenario'] == 'PEAK'
        assert client.get('/api/world').json()['seats'][0] == real_initial
        # force one isolated simulation into a lock then verify authorization.
        sid = sim_before[0]['id']
        main.engine.seats[sid].locked = True
        assert client.post(f'/api/simulated-seats/{sid}/release').status_code == 403
        response = client.post(f'/api/simulated-seats/{sid}/release', headers={'X-Admin-Token':'test-only-token'})
        assert response.status_code == 200
        assert client.get('/api/world').json()['seats'][0] == real_initial


def test_simulated_seats_are_dynamic():
    engine = SimulationEngine()
    initial = [s.as_dict() for s in engine.seats.values()]
    engine.control(scenario='PEAK',speed=10)
    changes=[]
    for _ in range(60):
        changes.extend(engine.tick(2))
    later = [s.as_dict() for s in engine.seats.values()]
    assert changes
    assert initial != later
    assert len(engine.seats) == 59

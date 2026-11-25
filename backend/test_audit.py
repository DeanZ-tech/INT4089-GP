import asyncio
import main


def test_boot_only_release_ack(monkeypatch):
    monkeypatch.setattr(main, 'record_event', lambda *a: None)
    s = main.Store()
    asyncio.run(s.accept({'v': 1, 'type': 'boot', 'id': 'A01', 'locked': True}))
    asyncio.run(s.accept({'v': 1, 'type': 'ack', 'id': 'A01', 'action': 'RELEASE', 'result': 'RELEASED', 'locked': False}))
    assert not s.snapshot()['locked']
    assert not s.snapshot()['available']


def test_smoke_import_does_not_open_port(monkeypatch):
    import serial
    def forbidden(*args, **kwargs):
        raise AssertionError('Import must never open hardware')
    monkeypatch.setattr(serial, 'Serial', forbidden)
    import importlib
    import serial_smoke_test
    importlib.reload(serial_smoke_test)

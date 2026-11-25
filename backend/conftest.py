"""Isolated test configuration: never open a physical port or production database."""
import os
import tempfile
from pathlib import Path

_test_db = tempfile.TemporaryDirectory(prefix='smart-library-tests-')
os.environ['SMART_LIBRARY_SERIAL_PORT'] = ''
os.environ['SMART_LIBRARY_DEMO'] = '0'
os.environ['SMART_LIBRARY_ADMIN_TOKEN'] = 'test-only-token'
os.environ['SMART_LIBRARY_DB'] = str(Path(_test_db.name) / 'events.db')

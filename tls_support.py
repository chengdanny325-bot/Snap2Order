"""Verify HTTPS with system trust plus bundled Mozilla root certificates."""
import ssl
from pathlib import Path

def context():
    ctx = ssl.create_default_context()
    ctx.load_verify_locations(cafile=str(Path(__file__).resolve().parent / 'vendor' / 'certificates' / 'cacert.pem'))
    return ctx

"""Private per-user connection bookmarks; no credentials or automatic scans."""
import json
import re
from .storage import user_dir, atomic_write
from .devices import endpoint


class DeviceProfiles:
    def __init__(self, path=None):
        self.path = path if path is not None else user_dir()/'device-profiles.json'

    def list(self):
        try:
            rows = json.loads(self.path.read_text(encoding='utf-8'))
            if not isinstance(rows,list) or len(rows)>100:
                raise ValueError('Invalid connection bookmarks')
            return [self.validate(row) for row in rows]
        except (OSError, ValueError, TypeError, KeyError):
            return []

    @staticmethod
    def validate(row):
        name = row['name'].strip()
        serial = row['serial'].strip()
        if not name or len(name)>80 or any(ord(c)<32 for c in name):
            raise ValueError('Use a connection name of 1–80 characters')
        kind = row['kind']
        if kind == 'Wireless':
            serial = endpoint(serial)
        elif kind == 'USB':
            if not re.fullmatch(r'[A-Za-z0-9_.-]{1,200}',serial) or serial.startswith('-'):
                raise ValueError('Invalid USB serial')
        else:
            raise ValueError('Only USB and Wi-Fi targets can be bookmarked')
        return {'name':name,'serial':serial,'kind':kind}

    def save(self, name, serial, kind):
        row = self.validate({'name':name,'serial':serial,'kind':kind})
        rows = [item for item in self.list() if item['serial'] != row['serial']]
        if len(rows)>=100:
            raise ValueError('Maximum 100 saved connections')
        rows.append(row)
        atomic_write(self.path,json.dumps(rows,ensure_ascii=False,indent=2).encode('utf-8'))
        return row

    def remove(self, serial):
        rows = [item for item in self.list() if item['serial'] != serial]
        atomic_write(self.path,json.dumps(rows,ensure_ascii=False,indent=2).encode('utf-8'))


def connection_guidance(state, kind):
    if state == 'unauthorized':
        return 'Unlock the device and approve its debugging authorization. Studio cannot approve it for you.'
    if state == 'offline':
        return 'Device is offline. Check power and Developer Mode; reconnect this Wi-Fi target or reconnect its USB data cable.'
    if state == 'device':
        return 'Authorized bridge connection. Inspect the target to confirm Vega services are ready.'
    return ('Enable Developer Mode and USB connection mode, then connect a data cable and approve debugging.' if kind=='USB'
            else 'Check the device address, Developer Mode TCP/IP setting, and that this PC can reach its network.')

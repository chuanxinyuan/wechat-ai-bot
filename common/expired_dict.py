import time
from threading import Lock


class ExpiredDict(dict):
    def __init__(self, expires_in_seconds):
        super().__init__()
        self._expires = expires_in_seconds
        self._times = {}
        self._lock = Lock()

    def __getitem__(self, key):
        with self._lock:
            if key in self._times:
                if time.time() - self._times[key] > self._expires:
                    del self._times[key]
                    if key in dict.__getitem__(self, '__dict__') or key in self:
                        dict.__delitem__(self, key)
                    raise KeyError(key)
                self._times[key] = time.time()
            return super().__getitem__(key)

    def __setitem__(self, key, value):
        with self._lock:
            self._times[key] = time.time()
            super().__setitem__(key, value)

import time
import os
import json
import hashlib
import portalocker


class SharedRequestCache:
    def __init__(self, cache_dir="/tmp/pytest_api_cache", ttl_seconds=10):
        self.cache_dir = cache_dir
        self.ttl = ttl_seconds
        os.makedirs(cache_dir, exist_ok=True)

    def _path(self, key):
        return os.path.join(self.cache_dir, f"{key}.json")

    def make_key(self, url, body=None):
        h = hashlib.sha256()
        h.update(url.encode())
        if body:
            h.update(repr(body).encode())
        return h.hexdigest()

    def get(self, key):
        path = self._path(key)
        if not os.path.exists(path):
            return None

        try:
            with portalocker.Lock(path, timeout=1):
                with open(path) as f:
                    entry = json.load(f)

            if time.time() - entry["ts"] > self.ttl:
                os.remove(path)
                return None

            return entry["value"]

        except Exception:
            return None

    def set(self, key, value):
        path = self._path(key)
        tmp = path + ".tmp"

        with portalocker.Lock(tmp, timeout=5):
            with open(tmp, "w") as f:
                json.dump({"ts": time.time(), "value": value}, f)

            os.replace(tmp, path)

import time
import os
import json
import hashlib
import portalocker
import threading


class SharedRequestCache:
    def __init__(self, cache_dir="/tmp/sauron_api_cache", ttl_seconds=10):
        self.cache_dir = cache_dir
        self.ttl = ttl_seconds
        os.makedirs(cache_dir, exist_ok=True)

        self.cleanup_expired_cache()

        t = threading.Thread(
            target=self._periodic_cleanup, args=(ttl_seconds * 2,), daemon=True
        )
        t.start()

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

    def cleanup_expired_cache(self):
        """Remove all expired cache files safely across multiple processes."""
        now = time.time()
        for filename in os.listdir(self.cache_dir):
            if not filename.endswith(".json"):
                continue
            path = os.path.join(self.cache_dir, filename)
            try:
                with portalocker.Lock(path, timeout=0.1):
                    with open(path) as f:
                        entry = json.load(f)
                    if now - entry.get("ts", 0) > self.ttl:
                        os.remove(path)
            except Exception:
                # Ignore locked files, missing files, or malformed files
                continue

    def _periodic_cleanup(self, interval):
        """Run cleanup in the background at regular intervals."""
        while True:
            try:
                self.cleanup_expired_cache()
            except Exception:
                pass  # ignore errors
            time.sleep(interval)

import time
import json
import os
import portalocker


class GlobalRateLimiter:
    def __init__(
        self,
        rate_per_second,
        state_file="/tmp/sauron_api_rate.state",
        max_wait_seconds=10,
    ):
        self.interval = 1.0 / rate_per_second
        self.state_file = state_file
        self.max_wait = max_wait_seconds

        if not os.path.exists(self.state_file):
            with open(self.state_file, "w") as f:
                json.dump({"next_ts": 0.0}, f)

    def acquire(self):
        start = time.time()

        while True:
            if time.time() - start > self.max_wait:
                raise TimeoutError("Rate limiter wait exceeded")

            with portalocker.Lock(self.state_file, timeout=10):
                with open(self.state_file, "r+") as f:
                    state = json.load(f)
                    now = time.time()

                    if state["next_ts"] <= now:
                        state["next_ts"] = now + self.interval
                        f.seek(0)
                        json.dump(state, f)
                        f.truncate()
                        return

                    wait = state["next_ts"] - now

            time.sleep(wait)

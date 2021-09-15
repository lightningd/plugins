import os
import signal
import _thread
import threading


def exit_after(seconds):
    """Exits if the function takes longer than `seconds` to execute.

    Actually it simulates a SIGHINT so it is quite adapted to RPC calls.
    Taken and adapted from this very clever gist by aaronchall:
    https://gist.github.com/aaronchall/6331661fe0185c30a0b4
    """

    def outer(fn):
        def inner(*args, **kwargs):
            timer = threading.Timer(
                seconds,
                lambda _: os.kill(os.getpid(), signal.SIGINT),
                args=[fn.__name__],
            )
            timer.start()
            try:
                result = fn(*args, **kwargs)
            finally:
                timer.cancel()
            return result

        return inner

    return outer


def timeout_bool(seconds, fn, *args, **kwargs):
    """Convenient function that return False if function timed out, True otherwise."""
    try:
        exit_after(seconds)(fn)(*args, **kwargs)
    except KeyboardInterrupt:
        return False
    return True

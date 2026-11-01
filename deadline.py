"""Hard wall-clock guard for the single-threaded Linux host-v2 subprocess."""

from contextlib import contextmanager
import signal
import time
from validation import Failure, require


@contextmanager
def operation_deadline(seconds):
    require(seconds > 0, "Operation deadline exceeded.", code="timeout")

    def expired(_signum, _frame):
        raise Failure("timeout", "Pinecone operation deadline exceeded.")

    previous_handler = signal.getsignal(signal.SIGALRM)
    previous_timer = signal.getitimer(signal.ITIMER_REAL)
    started = time.monotonic()
    signal.signal(signal.SIGALRM, expired)
    signal.setitimer(signal.ITIMER_REAL, seconds)
    try:
        yield
    finally:
        signal.setitimer(signal.ITIMER_REAL, 0)
        signal.signal(signal.SIGALRM, previous_handler)
        delay, interval = previous_timer
        if delay > 0:
            delay = max(0.000001, delay - (time.monotonic() - started))
        signal.setitimer(signal.ITIMER_REAL, delay, interval)

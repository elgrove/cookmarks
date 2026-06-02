import threading
import time


class TokenBucketRateLimiter:
    """Thread-safe token bucket: refills `rate` tokens/second up to `capacity`,
    blocking on acquire until a token is available."""

    def __init__(self, rate: float, capacity: int) -> None:
        self.rate = rate
        self.capacity = capacity
        self.tokens = float(capacity)
        self.last_refill = time.monotonic()
        self._lock = threading.Lock()

    def _refill(self) -> None:
        now = time.monotonic()
        elapsed = now - self.last_refill
        self.tokens = min(self.capacity, self.tokens + elapsed * self.rate)
        self.last_refill = now

    def acquire(self, blocking: bool = True, timeout: float | None = None) -> bool:
        start_time = time.monotonic()

        while True:
            with self._lock:
                self._refill()

                if self.tokens >= 1:
                    self.tokens -= 1
                    return True

                if not blocking:
                    return False

                wait_time = (1 - self.tokens) / self.rate

            if timeout is not None:
                remaining = timeout - (time.monotonic() - start_time)
                if remaining <= 0:
                    return False
                wait_time = min(wait_time, remaining)

            time.sleep(min(wait_time, 0.1))

    def __enter__(self) -> "TokenBucketRateLimiter":
        self.acquire()
        return self

    def __exit__(self, exc_type: object, exc_val: object, exc_tb: object) -> bool:
        return False


class RateLimitedExecutor:
    """Caps both concurrency (a semaphore) and request rate (a token bucket) for
    the extraction worker pool. Acts as a context manager around each AI call."""

    def __init__(self, max_workers: int, rate_per_minute: float) -> None:
        self.semaphore = threading.Semaphore(max_workers)
        self.rate_limiter = TokenBucketRateLimiter(
            rate=rate_per_minute / 60.0,
            capacity=max(1, int(rate_per_minute / 6)),
        )

    def acquire(self) -> None:
        self.semaphore.acquire()
        try:
            self.rate_limiter.acquire()
        except Exception:
            self.semaphore.release()
            raise

    def release(self) -> None:
        self.semaphore.release()

    def __enter__(self) -> "RateLimitedExecutor":
        self.acquire()
        return self

    def __exit__(self, exc_type: object, exc_val: object, exc_tb: object) -> bool:
        self.release()
        return False

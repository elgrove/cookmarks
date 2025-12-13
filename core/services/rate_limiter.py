import threading
import time


class TokenBucketRateLimiter:
    def __init__(self, rate: float, capacity: int):
        self.rate = rate
        self.capacity = capacity
        self.tokens = capacity
        self.last_refill = time.monotonic()
        self._lock = threading.Lock()
    
    def _refill(self):
        now = time.monotonic()
        elapsed = now - self.last_refill
        new_tokens = elapsed * self.rate
        self.tokens = min(self.capacity, self.tokens + new_tokens)
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
                elapsed = time.monotonic() - start_time
                remaining = timeout - elapsed
                if remaining <= 0:
                    return False
                wait_time = min(wait_time, remaining)
            
            time.sleep(min(wait_time, 0.1))
    
    def __enter__(self):
        self.acquire()
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        return False


class RateLimitedExecutor:
    def __init__(self, max_workers: int, rate_per_minute: float):
        self.semaphore = threading.Semaphore(max_workers)
        self.rate_limiter = TokenBucketRateLimiter(
            rate=rate_per_minute / 60.0,
            capacity=max(1, int(rate_per_minute / 6)),
        )
    
    def acquire(self):
        self.semaphore.acquire()
        try:
            self.rate_limiter.acquire()
        except Exception:
            self.semaphore.release()
            raise
    
    def release(self):
        self.semaphore.release()
    
    def __enter__(self):
        self.acquire()
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        self.release()
        return False

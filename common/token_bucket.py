import time


class TokenBucket:
    def __init__(self, rate):
        self.rate = rate
        self.tokens = rate
        self.last = time.time()

    def get_token(self):
        now = time.time()
        self.tokens += (now - self.last) * self.rate
        self.tokens = min(self.tokens, self.rate)
        self.last = now
        if self.tokens >= 1:
            self.tokens -= 1
            return True
        return False

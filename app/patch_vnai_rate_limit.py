"""
Patch vnai so rate limit does not terminate the process (sys.exit).
vnai's CleanErrorContext calls sys.exit() on RateLimitExceeded, which kills the Flask
process before our wait-and-retry logic can run. We replace __exit__ to let the
exception propagate so run_peer_valuations can catch it and wait/retry.
"""
import time


def _patched_clean_error_context_exit(self, exc_type, exc_val, exc_tb):
    try:
        from vnai.beam.quota import RateLimitExceeded
        if exc_type is RateLimitExceeded:
            current_time = time.time()
            if current_time - type(self)._last_message_time >= type(self)._message_cooldown:
                print(f"\n⚠️ {str(exc_val)}\n")
                type(self)._last_message_time = current_time
            # Do NOT call sys.exit() - let the exception propagate so our route can wait and retry
            return False
    except ImportError:
        pass
    return False


def apply_vnai_rate_limit_patch():
    """Replace CleanErrorContext.__exit__ so rate limit raises instead of exiting the process."""
    try:
        from vnai.beam import quota
        if hasattr(quota, "CleanErrorContext"):
            quota.CleanErrorContext.__exit__ = _patched_clean_error_context_exit
    except ImportError:
        pass

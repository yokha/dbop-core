# dbop-core
A DB-agnostic operation runner that retries sync/async callables with backoff + jitter, and lets adapters provide transaction/savepoint scopes, per-attempt setup timeouts, and transient classification.

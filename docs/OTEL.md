# **OpenTelemetry Integration (OTLP)**

## Overview

`dbop-core` includes an **optional observability layer** integrating with **OpenTelemetry**.
It instruments every `execute()` operation by emitting:

* **Traces** (spans for operation + retry attempts)
* **Metrics** (counters + histograms)

The feature is fully optional:

* Disabled by default
* Activated by `DBOP_OTEL_ENABLED=1`
* Safe even if OTEL dependencies are missing (no-op fallback)

---

# 1. Components

### **1. `dbop_core.otel_setup`**

Initializes:

* `TracerProvider`
* `MeterProvider`
* OTLP exporters (HTTP or gRPC)
* Fully respects all OTEL environment variables

Example supported variables:

```
OTEL_EXPORTER_OTLP_ENDPOINT
OTEL_EXPORTER_OTLP_TRACES_ENDPOINT
OTEL_EXPORTER_OTLP_METRICS_ENDPOINT
OTEL_EXPORTER_OTLP_INSECURE=true
DBOP_OTEL_EXPORTER=http|grpc
```

### **2. `dbop_core.otel_runtime`**

Implements runtime instrumentation:

#### **Tracing**

* Root span for the whole DB operation (`dbop.operation`)
* Child spans for each retry attempt (`dbop.operation.attempt`)
* Events: `dbop.pre_attempt`
* Attributes:

  * Retries
  * Delays / jitter
  * Outcome
  * Backend info (`db.system`, `db.name`, `db.user`, `db.statement`)

#### **Metrics**

`dbop-core` exposes:

| Metric                                 | Type      | Meaning                      |
| -------------------------------------- | --------- | ---------------------------- |
| `dbop_dbop_operations_total`           | Counter   | Number of DB operations      |
| `dbop_dbop_attempts_total`             | Counter   | Attempts (including retries) |
| `dbop_dbop_operation_duration_seconds` | Histogram | Operation latency            |

Metrics include resource attributes (service name, SDK language) and operation attributes.

### **3. `examples/otel-smoke/`**

A complete local demo stack:

* OpenTelemetry Collector
* Jaeger UI
* Prometheus
* Grafana
* A simple Python smoke script generating **100 mixed OK/fail operations**

---

# 2. Quickstart (Traces + Metrics)

## Step 1 — Install OTEL extras

```bash
pip install -e ".[otel]"
```

## Step 2 — Start OTEL stack (Collector + Jaeger + Prometheus + Grafana)

```bash
cd examples
make otel-up
```

Services started:

| Component      | Address                                                        |
| -------------- | -------------------------------------------------------------- |
| OTEL Collector | 4317 (gRPC), 4318 (HTTP), 9464 (Prom metrics)                  |
| Jaeger UI      | [http://localhost:16686](http://localhost:16686)               |
| Prometheus     | [http://localhost:9090](http://localhost:9090)                 |
| Grafana        | [http://localhost:3000](http://localhost:3000) (admin / admin) |

## Step 3 — Run the OTEL smoke test

### HTTP exporter:

```bash
make otel-smoke-local-http
```

### gRPC exporter:

```bash
make otel-smoke-local-grpc
```

Expected env variables during smoke:

```
DBOP_OTEL_ENABLED=1
DBOP_OTEL_EXPORTER=http|grpc
OTEL_EXPORTER_OTLP_TRACES_ENDPOINT=http://127.0.0.1:4318/v1/traces
OTEL_EXPORTER_OTLP_METRICS_ENDPOINT=http://127.0.0.1:4318/v1/metrics
```

---

# 3. Traces (Jaeger)

Open:

👉 [http://localhost:16686](http://localhost:16686)

Look for:

```
Service: dbop-core-otel-smoke
```

Example trace structure:

```
dbop.smoke
 ├── dbop.smoke.attempt (#1)
 └── dbop.smoke.attempt (#2)
```

Span attributes include:

```
dbop.max_retries
dbop.outcome
dbop.initial_delay
dbop.max_delay
dbop.jitter
db.system
db.name
db.user
db.statement
```

---

# 4. Metrics (Prometheus + Grafana)

Collector exposes metrics at:

```
http://localhost:9464/metrics
```

Prometheus automatically scrapes:

```
job: olap-collector
instance: otel-collector:9464
```

### To verify in Prometheus:

```bash
curl -s "http://localhost:9090/api/v1/query?query=dbop_dbop_operations_total"
```

### Metric fields:

* `db_system`
* `db_name`
* `db_user`
* `dbop_outcome`
* `dbop_read_only`
* `otel_scope_name="dbop_core.otel_runtime"`

### Grafana Dashboard

A ready-made dashboard file exists:

```
examples/otel-smoke/grafana/dashboard-dbop.json
```

Import it in Grafana → Dashboards → Import → Upload JSON.

It includes:

* Operation count
* Attempts vs successes
* Retry rate
* Latency histogram
* Success/failure ratio

---

# 5. Code Example (Traces + Metrics)

```python
import os
import asyncio
from dbop_core.core import RetryPolicy
from dbop_core.otel_setup import init_tracer, init_metrics
from dbop_core.otel_runtime import execute_traced_optional

async def flaky_op(state):
    if not state["fail_once"]:
        state["fail_once"] = True
        raise RuntimeError("transient boom")
    await asyncio.sleep(0.05)
    return "ok"

async def main():
    exporter = os.getenv("DBOP_OTEL_EXPORTER", "http")

    init_tracer(service_name="dbop-core-otel-smoke", exporter=exporter)
    init_metrics(service_name="dbop-core-otel-smoke", exporter=exporter)

    state = {"fail_once": False}
    policy = RetryPolicy(max_retries=2, initial_delay=0.05)

    res = await execute_traced_optional(
        op=lambda: flaky_op(state),
        policy=policy,
        retry_on=(RuntimeError,),
        otel_enabled=True,
        db_system="test",
        db_name="example",
        db_user="example",
        db_statement="flaky_op()",
        span_name="dbop.smoke",
    )
    print(res)

asyncio.run(main())
```

---

# 6. Disabling OpenTelemetry

Disable all instrumentation:

```bash
unset DBOP_OTEL_ENABLED
```

Or explicitly:

```python
await execute_traced_optional(..., otel_enabled=False)
```

---

# 7. Philosophy

The OTEL layer is intentionally:

* Lightweight
* Optional
* Zero overhead when disabled
* 100% transparent
* Non-invasive to user code

It adds **observability** without adding **coupling**.

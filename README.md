# URL Shortener

Production-oriented URL shortener built with FastAPI, PostgreSQL, Redis, RabbitMQ, and Docker. The implementation is optimized for low-latency redirects, collision-safe code generation, async analytics ingestion, preview enrichment, and horizontal scaling.

## Architecture

```text
Clients
  |
  v
Load Balancer / CDN
  |
  v
FastAPI API Pods
  |----------------------------> Redis
  |                               |- redirect cache
  |                               |- negative cache
  |                               |- rate limiting
  |                               |- sharded analytics counters
  |
  |----------------------------> PostgreSQL
  |                               |- links
  |                               |- daily aggregates
  |                               |- click event log
  |
  |----------------------------> RabbitMQ
                                  |- click.track
                                  |- link.enrich
                                          |
                                          v
                                    Worker Pods
                                      |- analytics aggregation
                                      |- metadata fetch
                                      |- QR generation
```

## Why this design

- Redirects are read-heavy, so the hot path is `local cache -> Redis -> PostgreSQL`.
- Writes from redirects are pushed to RabbitMQ so the redirect response does not wait on analytics storage.
- Redis absorbs rate limiting and cache traffic, while PostgreSQL stays the source of truth.
- Workers handle slow or bursty work: click ingestion, QR generation, and metadata fetching.
- The app is stateless and horizontally scalable behind a load balancer.

## Folder structure

```text
app/
  api/
    deps.py
    router.py
    routes/
      health.py
      links.py
      redirects.py
  cache/
    keys.py
    redis.py
  core/
    config.py
    security.py
  db/
    base.py
    session.py
  messaging/
    rabbitmq.py
  models/
    click_event.py
    link.py
    link_daily_stat.py
  schemas/
    link.py
  services/
    analytics_service.py
    link_service.py
    metadata_service.py
    rate_limiter.py
    redirect_service.py
  workers/
    main.py
docker/
  Dockerfile
  entrypoint.sh
  worker-entrypoint.sh
alembic/
  env.py
  versions/
```

## Database schema

### `links`

- `id BIGINT PK`
- `public_id UUID UNIQUE`
- `short_code VARCHAR(32) UNIQUE`
- `long_url TEXT`
- `custom_alias BOOLEAN`
- `is_active BOOLEAN`
- `expires_at TIMESTAMPTZ NULL`
- `click_count BIGINT`
- `last_clicked_at TIMESTAMPTZ NULL`
- `metadata_status VARCHAR(32)`
- `preview_metadata JSONB NULL`
- `qr_svg TEXT NULL`
- `manage_token_hash VARCHAR(128)`
- `created_at TIMESTAMPTZ`
- `updated_at TIMESTAMPTZ`

### `click_events`

- append-heavy raw event table for recent drill-down
- stores `link_id`, `occurred_at`, `referer`, `user_agent`, `client_ip_hash`, `country_code`, `cache_status`

### `link_daily_stats`

- aggregate table keyed by `(link_id, bucket_date)`
- stores `clicks` and `unique_visitors`
- powers analytics endpoints without scanning raw events

## Short code generation strategy

- Default short codes are cryptographically random using a 57-character alphabet.
- Default length is `11`, which makes enumeration materially harder than sequential or hashid-based designs.
- PostgreSQL enforces uniqueness with a unique constraint on `short_code`.
- On collision, the service retries code generation up to `short_code_max_retries`.
- Custom aliases are validated against a strict pattern and blocked for reserved routes such as `api`, `docs`, and `healthz`.

Why this avoids collisions and enumeration:

- No public sequential IDs are exposed.
- Codes are non-predictable, not reversible, and not tied to database order.
- Even if an attacker sees one code, neighboring codes are not inferable.

## Caching strategy

### Redirect path

1. Process-local TTL cache on every API pod absorbs the hottest keys.
2. Redis stores redirect payloads to avoid repeated PostgreSQL reads.
3. Negative cache stores misses briefly to avoid repeated DB lookups for garbage codes.
4. Cache TTL is capped by `expires_at` so expired links do not outlive their validity window.
5. TTL jitter spreads refreshes to avoid cache stampedes.

### Hot key prevention

- Local per-pod cache removes the very hottest redirects from Redis.
- Redis analytics counters are sharded with `crc32(client_ip_hash) % N` to avoid single-counter write hotspots.
- Unique visitors use Redis HyperLogLog to avoid expensive deduplication scans.
- At higher scale, place a CDN in front of top short links and use Redis replicas or cluster mode.

## Redis usage

- `link:data:{short_code}`: redirect cache payload
- `link:miss:{short_code}`: short-lived negative cache
- `ratelimit:{scope}:{subject}:{bucket}`: rate limiting counters
- `analytics:clicks:{link_id}:{date}:{shard}`: sharded click counters
- `analytics:uv:{link_id}:{date}`: HyperLogLog for unique visitor approximation

## RabbitMQ usage

Queues:

- `click.track`: created on every redirect, consumed by analytics workers
- `link.enrich`: created on link creation, consumed by enrichment workers

Why RabbitMQ is in the design:

- Redirect responses stay fast because analytics writes happen off-path.
- Preview fetching and QR generation are slow I/O tasks and should not block creation requests.
- Worker count can scale independently from API pods.

## Background workers

`app/workers/main.py` runs two consumers:

- `click.track`
  - writes raw click event rows
  - updates `links.click_count`
  - upserts `link_daily_stats`
  - updates Redis sharded counters and HyperLogLog
- `link.enrich`
  - fetches preview metadata from the target URL
  - generates QR SVG for the short URL
  - stores metadata and QR payload in PostgreSQL

## API endpoints

### Public

- `POST /api/v1/links`
  - create a short URL
  - supports custom alias and expiration
- `GET /{short_code}`
  - redirect to target URL

### Management

Management uses `X-Manage-Token`, returned when a short link is created.

- `GET /api/v1/links/{short_code}`
- `GET /api/v1/links/{short_code}/preview`
- `GET /api/v1/links/{short_code}/qr`
- `GET /api/v1/links/{short_code}/analytics?days=30`

### Health

- `GET /healthz`

## Example request

```bash
curl -X POST http://localhost:8000/api/v1/links \
  -H "Content-Type: application/json" \
  -d '{
    "url": "https://example.com/pricing",
    "custom_alias": "launch-2026",
    "expires_at": "2026-12-31T23:59:59Z"
  }'
```

Example response:

```json
{
  "short_code": "launch-2026",
  "short_url": "http://localhost:8000/launch-2026",
  "url": "https://example.com/pricing",
  "custom_alias": true,
  "expires_at": "2026-12-31T23:59:59Z",
  "metadata_status": "pending",
  "created_at": "2026-03-06T10:00:00Z",
  "manage_token": "..."
}
```

## Running locally

```bash
docker compose up --build
```

Services:

- API: `http://localhost:8000`
- Swagger UI: `http://localhost:8000/docs`
- RabbitMQ management: `http://localhost:15672`

## Production notes for 10M redirects/day

10M redirects/day is about 116 requests/second on average, with peak traffic much higher. This design handles that by:

- keeping redirect requests mostly in memory and Redis
- making redirect writes asynchronous
- using pooled PostgreSQL connections
- storing analytics in aggregate form for reads
- letting API pods and worker pods scale independently

### Basic load optimization ideas

- Put a CDN or edge cache in front of the redirect endpoint for the most popular links.
- Split redirect traffic from management traffic into separate deployments.
- Use PostgreSQL partitioning for `click_events` by day or month.
- Add Redis replicas or Redis Cluster for read-heavy cache workloads.
- Use PgBouncer in transaction mode if pod count grows.
- Use multi-stage Docker builds and run multiple API replicas behind a real L7 load balancer.

## Bonus

### Prevent enumeration attacks

- Use random high-entropy short codes rather than sequential IDs.
- Keep code length at 10 to 12 characters for public links.
- Do not expose internal numeric IDs anywhere.
- Separate management access from the public short code using `X-Manage-Token`.
- Rate limit both creation and redirect abuse paths.
- Reserve sensitive route prefixes so aliases cannot shadow internal endpoints.

### Avoid database bottlenecks

- Redirects read from local cache and Redis first.
- Misses are negative-cached.
- Click writes are queued and processed asynchronously.
- Analytics reads use `link_daily_stats`, not raw event scans.
- Raw event retention should be short in PostgreSQL once a long-term pipeline exists.

### Scale to 100M redirects/day

- Front redirect traffic with a CDN or edge worker for cacheable popular links.
- Run dedicated redirect-only API pods with minimal middleware.
- Move from per-click PostgreSQL writes to batched worker flushes.
- Store raw click stream in Kafka or RabbitMQ-to-Kafka bridge, then push to ClickHouse, BigQuery, or S3+Athena.
- Keep PostgreSQL for link metadata and aggregates only.
- Use Redis Cluster and partition hot counters across shards.
- Introduce read replicas for metadata and multi-region edge redirectors if latency matters globally.

### Add a real analytics pipeline

Recommended evolution:

1. Keep RabbitMQ for operational async tasks.
2. Mirror click events into Kafka for durable, replayable analytics ingestion.
3. Feed a stream processor that enriches geo/device/referrer data.
4. Sink raw events into ClickHouse or BigQuery for ad hoc analytics.
5. Continue serving the API from pre-aggregated tables or materialized views.

## Important implementation tradeoffs

- This repo stores QR SVG in PostgreSQL for simplicity. At larger scale, move QR artifacts to object storage and save a pointer.
- This repo stores raw click events in PostgreSQL to keep the example self-contained. At 100M/day, move raw events to an OLAP store.
- Metadata fetching is best-effort. In production, add robots rules, outbound fetch controls, size limits, and retry policies.

## Key code entry points

- Redirect path: `app/api/routes/redirects.py`, `app/services/redirect_service.py`
- Link creation: `app/api/routes/links.py`, `app/services/link_service.py`
- Async analytics ingestion: `app/workers/main.py`, `app/services/analytics_service.py`
- Metadata and QR generation: `app/services/metadata_service.py`
- Infrastructure wiring: `app/main.py`, `docker-compose.yml`, `alembic/versions/20260306_0001_initial.py`

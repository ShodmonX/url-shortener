from datetime import date


def link_cache_key(short_code: str) -> str:
    return f"link:data:{short_code}"


def link_negative_cache_key(short_code: str) -> str:
    return f"link:miss:{short_code}"


def rate_limit_key(scope: str, subject: str, window_bucket: int) -> str:
    return f"ratelimit:{scope}:{subject}:{window_bucket}"


def analytics_counter_key(link_id: int, bucket_date: date, shard: int) -> str:
    return f"analytics:clicks:{link_id}:{bucket_date.isoformat()}:{shard}"


def analytics_unique_visitors_key(link_id: int, bucket_date: date) -> str:
    return f"analytics:uv:{link_id}:{bucket_date.isoformat()}"


def fallback_queue_key(queue_name: str) -> str:
    return f"queue:fallback:{queue_name}"


def dead_letter_queue_key(queue_name: str) -> str:
    return f"queue:dead-letter:{queue_name}"

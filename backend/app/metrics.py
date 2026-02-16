
from prometheus_client import Counter, Histogram, generate_latest, CONTENT_TYPE_LATEST

# Metrics
REQUEST_LATENCY = Histogram(
    "guru_request_latency_seconds", 
    "Full request latency", 
    ["stage"]
)

REQUEST_COUNT = Counter(
    "guru_requests_total", 
    "Total chat requests",
    ["status"]
)

DEPRESSION_EVENTS = Counter(
    "guru_depression_detections", 
    "Users flagged as depressed"
)

MEDITATION_SESSIONS = Counter(
    "guru_meditation_sessions_total",
    "Total meditation sessions started"
)

def metrics_endpoint():
    """Expose Prometheus metrics."""
    return generate_latest(), CONTENT_TYPE_LATEST

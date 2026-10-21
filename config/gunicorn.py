import os

bind = "0.0.0.0:8000"
workers = int(os.getenv("WEB_CONCURRENCY", "3"))
worker_class = "sync"
timeout = 40
graceful_timeout = 40
keepalive = 5
max_requests = 1000
max_requests_jitter = 100
accesslog = "-"
errorlog = "-"
# Request paths/query strings may contain callback authorities, OTPs or search text.
access_log_format = '%(h)s %(m)s %(s)s %(b)s %(L)s'
capture_output = True
forwarded_allow_ips = "*"  # App port is internal-only; Nginx replaces forwarding headers.

import os
from urllib.parse import urlsplit
from urllib.request import Request, urlopen

request = Request("http://127.0.0.1:8000/health/", headers={"Host": urlsplit(os.environ["SITE_URL"]).netloc, "X-Forwarded-Proto": "https"})
with urlopen(request, timeout=4) as response:
    if response.status != 200:
        raise SystemExit(1)

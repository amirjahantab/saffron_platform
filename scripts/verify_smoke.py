"""Repeat local-only HTTPS checks and an optional isolated restore rehearsal."""
import argparse
import json
from pathlib import Path
import ssl
import subprocess
import uuid
from urllib.request import urlopen
from urllib.error import HTTPError

root = Path(__file__).resolve().parent.parent
parser = argparse.ArgumentParser()
parser.add_argument("--restore", action="store_true", help="Create and verify a new isolated restore database; never restore over the source.")
options = parser.parse_args()
env_text = (root / ".env.production").read_text(encoding="utf-8")
if "SITE_URL=https://127.0.0.1:8443" not in env_text.splitlines():
    raise SystemExit("This helper only operates on the local loopback smoke environment.")
compose = ["docker", "compose", "--env-file", ".env.production", "-f", "compose.production.yml", "-f", "compose.smoke.yml"]


def run(*args):
    return subprocess.run(compose+list(args), cwd=root, check=True, capture_output=True, text=True).stdout.strip()


context = ssl.create_default_context(cafile=str(root / "deploy/certs/fullchain.pem"))
report = {"scope": "localhost TLS smoke; not public deployment", "http": []}
for path in ["/health/", "/", "/journal/", "/faq/", "/assistant/", "/static/fonts/Vazirmatn-Variable.woff2"]:
    with urlopen("https://127.0.0.1:8443"+path, context=context, timeout=10) as response:
        assert response.status == 200
        report["http"].append({"path": path, "status": response.status, "hsts": response.headers.get("Strict-Transport-Security")})
try:
    urlopen("https://127.0.0.1:8443/media/catalog/certificates/private.pdf", context=context, timeout=10)
    raise AssertionError("Raw certificates must not be served")
except HTTPError as error:
    assert error.code == 404
report["raw_certificates_status"] = 404
report["app_identity"] = run("exec", "-T", "web", "id")
run("exec", "-T", "nginx", "nginx", "-t")
report["nginx_config"] = "passed"
run("exec", "-T", "web", "python", "manage.py", "check", "--deploy", "--fail-level", "WARNING")
report["django_deploy_check"] = "passed"
if options.restore:
    run("exec", "-T", "web", "python", "manage.py", "shell", "-c", "from apps.content.models import Category; Category.objects.get_or_create(slug='restore-probe',defaults={'name':'Restore verification'})")
    run("exec", "-T", "web", "python", "-c", "from pathlib import Path; folder=Path('/app/media/operations'); folder.mkdir(exist_ok=True); (folder/'restore-probe.txt').write_text('jahantab media restore probe')")
    run("run", "--rm", "backup")
    backup_root = (root / "backups").resolve()
    archive = max(backup_root.glob("*.dump"), key=lambda path: path.stat().st_mtime).resolve()
    assert archive.is_relative_to(backup_root)
    target = "restore_drill_"+uuid.uuid4().hex[:10]
    create = f"from django.db import connection; from psycopg import sql; connection.cursor().execute(sql.SQL('CREATE DATABASE {{}}').format(sql.Identifier('{target}')))"
    run("exec", "-T", "web", "python", "manage.py", "shell", "-c", create)
    run("run", "--rm", "--entrypoint", "pg_restore", "backup", "--exit-on-error", "--no-owner", "--no-acl", "--dbname="+target, "/backups/"+archive.name)
    verify = "import json; from apps.content.models import Category; from django.db.migrations.recorder import MigrationRecorder; print(json.dumps({'probe_rows':Category.objects.filter(slug='restore-probe').count(),'migrations':MigrationRecorder.Migration.objects.count()}))"
    source = json.loads(run("exec", "-T", "web", "python", "manage.py", "shell", "-c", verify).splitlines()[-1])
    restored = json.loads(run("run", "--rm", "--no-deps", "-e", "POSTGRES_DB="+target, "web", "python", "manage.py", "shell", "-c", verify).splitlines()[-1])
    assert restored == source and restored["probe_rows"] == 1
    media = run("run", "--rm", "--entrypoint", "tar", "backup", "-xOzf", "/backups/"+archive.name+".media.tgz", "./operations/restore-probe.txt")
    assert media == "jahantab media restore probe"
    report["restore"] = {"archive": archive.name, "target_database": target, "verified": restored, "checksum_created": archive.with_suffix(archive.suffix+".sha256").exists(), "media_probe_verified": True}
destination = root / "artifacts" / "verification"
destination.mkdir(parents=True, exist_ok=True)
(destination / "tls-and-restore.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
print(json.dumps(report, indent=2))

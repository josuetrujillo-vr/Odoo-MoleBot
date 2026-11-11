"""Run Task 1 tests in a new local-only database with SMTP disabled."""
import configparser
import os
from pathlib import Path
import re
import socket
import smtplib
import sys
import uuid

import psycopg2
from psycopg2 import sql

ROOT = Path(__file__).resolve().parents[1]
ODOO = Path(r"C:\Users\truji\odoo\odoo-testing-local")
config = configparser.ConfigParser()
if not config.read(ODOO / "odoo.conf"):
    raise SystemExit("Local configuration unavailable")
options = config["options"]
host = options.get("db_host")
if host not in ("127.0.0.1", "localhost", "::1"):
    raise SystemExit("Refusing non-local PostgreSQL")
reuse = sys.argv[1:] == ["--reuse-task1-red"]
if sys.argv[1:] and not reuse:
    raise SystemExit("Only --reuse-task1-red is supported")
name = "assistant_test_70b48f7855b7" if reuse else "assistant_test_" + uuid.uuid4().hex[:12]
if not re.fullmatch(r"assistant_test_[a-f0-9]{12}", name):
    raise SystemExit("Invalid database name")
data = ROOT / (".test-data-task1-" + name)
if reuse:
    if not data.is_dir():
        raise SystemExit("Original isolated data directory missing")
else:
    data.mkdir(exist_ok=False)
with socket.socket() as probe:
    probe.bind(("127.0.0.1", 0))
    http_port = probe.getsockname()[1]
if not reuse:
    connection = psycopg2.connect(
        host=host, port=options.get("db_port", "5432"),
        user=options.get("db_user"), password=options.get("db_password"), dbname="postgres",
    )
    try:
        connection.autocommit = True
        with connection.cursor() as cursor:
            cursor.execute(sql.SQL("CREATE DATABASE {} ENCODING 'UTF8' TEMPLATE template0").format(sql.Identifier(name)))
    finally:
        connection.close()

def disabled_smtp(*_args, **_kwargs):
    raise RuntimeError("SMTP disabled for isolated Mole tests")

smtplib.SMTP = smtplib.SMTP_SSL = disabled_smtp
os.environ.pop("ASSISTANT_LOCAL_BACKEND", None)
os.environ.pop("ASSISTANT_LOCAL_URL", None)
os.environ.pop("ASSISTANT_LOCAL_MODEL", None)
sys.path.insert(0, str(ODOO))
import odoo.cli

print("Exclusive database:", name, "data:", data, flush=True)
sys.argv = ["odoo-bin", "-c", str(ODOO / "odoo.conf"), "-d", name,
    "--db-filter=^" + name + "$", "--data-dir=" + str(data),
    "--addons-path=" + ",".join(map(str, (ROOT, ODOO / "odoo" / "addons", ODOO / "extra-addons"))),
    "-u" if reuse else "-i", "assistant_local_hr_holidays,assistant_local_mole", "--test-enable",
    "--test-tags=/assistant_local_hr_holidays,/assistant_local_mole",
    "--without-demo=all", "--max-cron-threads=0", "--no-http",
    "--http-interface=127.0.0.1", "--http-port=" + str(http_port), "--stop-after-init"]
odoo.cli.main()

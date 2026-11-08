"""Create a uniquely named local PostgreSQL database for Odoo tests."""
import configparser
import pathlib
import sys
import uuid

import psycopg2
from psycopg2 import sql


config = configparser.ConfigParser()
if len(sys.argv) != 2 or not config.read(sys.argv[1]):
    raise SystemExit("Pass the existing local Odoo configuration file")
options = config["options"]
host = options.get("db_host")
if host not in ("127.0.0.1", "localhost", "::1"):
    raise SystemExit("Refusing to create a test database on a non-local host")
name = "assistant_test_" + uuid.uuid4().hex[:12]
connection = psycopg2.connect(
    host=host,
    port=options.get("db_port", "5432"),
    user=options.get("db_user"),
    password=options.get("db_password"),
    dbname="postgres",
)
try:
    connection.autocommit = True
    with connection.cursor() as cursor:
        cursor.execute(sql.SQL("CREATE DATABASE {} ENCODING 'UTF8' TEMPLATE template0").format(
            sql.Identifier(name)
        ))
finally:
    connection.close()
pathlib.Path(".test-db-name").write_text(name, encoding="utf-8")
print(name)

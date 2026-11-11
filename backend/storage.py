import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from .config import DATA

@contextmanager
def db():
    conn = sqlite3.connect(DATA / 'terminal.sqlite3', timeout=30)
    conn.row_factory = sqlite3.Row
    conn.executescript('''
        CREATE TABLE IF NOT EXISTS audits (id TEXT PRIMARY KEY, created_at TEXT NOT NULL, payload TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS orders (id TEXT PRIMARY KEY, audit_id TEXT NOT NULL UNIQUE, amount TEXT NOT NULL,
          status TEXT NOT NULL, payload TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS ledger (order_id TEXT PRIMARY KEY, month TEXT NOT NULL, fiat REAL NOT NULL,
          carbon REAL NOT NULL, mode TEXT NOT NULL);
    ''')
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()

def save_audit(audit):
    with db() as c:
        c.execute('INSERT INTO audits VALUES (?, ?, ?)', (audit['id'],audit['created_at'], json.dumps(audit)))

def get_audit(audit_id):
    with db() as c:
        row = c.execute('SELECT payload FROM audits WHERE id=?',(audit_id,)).fetchone()
        return json.loads(row['payload']) if row else None

def history():
    with db() as c:
        return [dict(id=r['id'],created_at=r['created_at'],decision=json.loads(r['payload'])['decision'],
                     name=json.loads(r['payload'])['product']['name']) for r in c.execute('SELECT * FROM audits ORDER BY created_at DESC LIMIT 30')]

def month():
    return datetime.now(timezone.utc).strftime('%Y-%m')

def usage():
    with db() as c:
        row=c.execute('SELECT COALESCE(SUM(carbon),0) carbon, COALESCE(SUM(fiat),0) fiat FROM ledger WHERE month=?',(month(),)).fetchone()
        return dict(row)

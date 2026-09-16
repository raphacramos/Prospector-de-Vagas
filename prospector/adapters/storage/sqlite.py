"""Repositorio SQLite dos leads, com migracao automatica de schema.

Versoes (PRAGMA user_version):
  0 -> banco novo ou banco da v2 (tabela `leads` sem colunas novas)
  3 -> colunas estruturadas (emails, ats_links, labels, region...) + tabela lead_events
"""
import json
import os
import re
import shutil
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timedelta

from prospector.domain.lead import (
    AWAITING_REPLY, FOLLOWUP_DAYS, POSITIVE, Lead, LeadStatus, region_from_source,
)

SCHEMA_VERSION = 3
TS_FORMAT = "%Y-%m-%d %H:%M:%S"
_EMAIL_RE = re.compile(r"[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+")

_LEAD_COLUMNS = (
    "id, company, title, source, url, region, emails, ats_links, labels, location, "
    "posted_at, raw_body, status, notes, created_at, contacted_at, followup_due_at"
)

_V3_NEW_COLUMNS = [
    ("region", "TEXT NOT NULL DEFAULT 'br'"),
    ("emails", "TEXT NOT NULL DEFAULT '[]'"),
    ("ats_links", "TEXT NOT NULL DEFAULT '[]'"),
    ("labels", "TEXT NOT NULL DEFAULT '[]'"),
    ("location", "TEXT NOT NULL DEFAULT ''"),
    ("posted_at", "TEXT NOT NULL DEFAULT ''"),
]


def _fmt(dt):
    return dt.strftime(TS_FORMAT)


class SqliteLeadRepository:
    def __init__(self, db_path, backup_dir=None, clock=datetime.now):
        self.db_path = db_path
        self.backup_dir = backup_dir or os.path.join(os.path.dirname(os.path.abspath(db_path)), "data", "backups")
        self._now = clock
        self.last_backup_path = None
        self._migrate()

    # ------------------------------------------------------------------ infra
    @contextmanager
    def _connect(self):
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def _migrate(self):
        existed = os.path.exists(self.db_path) and os.path.getsize(self.db_path) > 0
        with self._connect() as conn:
            version = conn.execute("PRAGMA user_version").fetchone()[0]
            if version >= SCHEMA_VERSION:
                return
            has_leads = conn.execute(
                "SELECT 1 FROM sqlite_master WHERE type='table' AND name='leads'"
            ).fetchone() is not None

        if existed and has_leads:
            self.last_backup_path = self._backup()

        with self._connect() as conn:
            if has_leads:
                self._upgrade_v2(conn)
            else:
                self._create_v3(conn)
            conn.execute(f"PRAGMA user_version = {SCHEMA_VERSION}")

    def _backup(self):
        os.makedirs(self.backup_dir, exist_ok=True)
        stamp = self._now().strftime("%Y%m%d-%H%M%S")
        dest = os.path.join(self.backup_dir, f"prospector-v2-{stamp}.db")
        shutil.copy2(self.db_path, dest)
        return dest

    @staticmethod
    def _create_events_table(conn):
        conn.execute("""
            CREATE TABLE IF NOT EXISTS lead_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                lead_id INTEGER NOT NULL REFERENCES leads(id),
                status TEXT NOT NULL,
                at TIMESTAMP NOT NULL,
                note TEXT NOT NULL DEFAULT ''
            )
        """)
        conn.execute("CREATE INDEX IF NOT EXISTS idx_events_lead ON lead_events(lead_id)")

    def _create_v3(self, conn):
        conn.execute("""
            CREATE TABLE leads (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                company TEXT NOT NULL,
                title TEXT NOT NULL,
                source TEXT NOT NULL,
                url TEXT UNIQUE,
                contact_info TEXT,
                raw_body TEXT,
                status TEXT DEFAULT 'minerado',
                notes TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                contacted_at TIMESTAMP,
                followup_due_at TIMESTAMP,
                region TEXT NOT NULL DEFAULT 'br',
                emails TEXT NOT NULL DEFAULT '[]',
                ats_links TEXT NOT NULL DEFAULT '[]',
                labels TEXT NOT NULL DEFAULT '[]',
                location TEXT NOT NULL DEFAULT '',
                posted_at TEXT NOT NULL DEFAULT ''
            )
        """)
        self._create_events_table(conn)

    def _upgrade_v2(self, conn):
        existing = {r["name"] for r in conn.execute("PRAGMA table_info(leads)")}
        for name, ddl in _V3_NEW_COLUMNS:
            if name not in existing:
                conn.execute(f"ALTER TABLE leads ADD COLUMN {name} {ddl}")
        self._create_events_table(conn)

        rows = conn.execute(
            "SELECT id, source, contact_info, status, created_at, contacted_at FROM leads"
        ).fetchall()
        for r in rows:
            contact = r["contact_info"] or ""
            emails = sorted(set(_EMAIL_RE.findall(contact)))
            links = [c.strip() for c in contact.split(",") if c.strip().startswith("http")]
            status = r["status"] if r["status"] in LeadStatus.values() else LeadStatus.MINERADO.value
            due = None
            if LeadStatus(status) in AWAITING_REPLY and r["contacted_at"]:
                try:
                    contacted = datetime.strptime(r["contacted_at"], TS_FORMAT)
                    due = _fmt(contacted + timedelta(days=FOLLOWUP_DAYS))
                except ValueError:
                    due = None
            conn.execute(
                "UPDATE leads SET region=?, emails=?, ats_links=?, status=?, followup_due_at=? WHERE id=?",
                (region_from_source(r["source"]).value, json.dumps(emails), json.dumps(links),
                 status, due, r["id"]),
            )
            # Historico: o v2 so guardava o status atual.
            conn.execute(
                "INSERT INTO lead_events (lead_id, status, at, note) VALUES (?, ?, ?, ?)",
                (r["id"], LeadStatus.MINERADO.value, r["created_at"] or _fmt(self._now()), "migrado do v2"),
            )
            if status != LeadStatus.MINERADO.value:
                conn.execute(
                    "INSERT INTO lead_events (lead_id, status, at, note) VALUES (?, ?, ?, ?)",
                    (r["id"], status, r["contacted_at"] or r["created_at"] or _fmt(self._now()), "migrado do v2"),
                )

    # --------------------------------------------------------------- mapping
    @staticmethod
    def _to_lead(row):
        return Lead(
            id=row["id"], company=row["company"], title=row["title"], source=row["source"],
            url=row["url"] or "", region=row["region"],
            emails=json.loads(row["emails"] or "[]"), ats_links=json.loads(row["ats_links"] or "[]"),
            labels=json.loads(row["labels"] or "[]"), location=row["location"] or "",
            posted_at=row["posted_at"] or "", raw_body=row["raw_body"] or "",
            status=row["status"] or LeadStatus.MINERADO.value, notes=row["notes"] or "",
            created_at=row["created_at"], contacted_at=row["contacted_at"],
            followup_due_at=row["followup_due_at"],
        )

    # ------------------------------------------------------------------- API
    def add(self, lead):
        """Insere o lead. Retorna o id, ou None se a URL ja existia (dedup)."""
        now = _fmt(self._now())
        with self._connect() as conn:
            if lead.url:
                dup = conn.execute("SELECT id FROM leads WHERE url = ?", (lead.url,)).fetchone()
                if dup:
                    return None
            cur = conn.execute(
                """INSERT INTO leads (company, title, source, url, contact_info, raw_body, status, notes,
                                      created_at, region, emails, ats_links, labels, location, posted_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (lead.company, lead.title, lead.source, lead.url or None, lead.contact_summary,
                 lead.raw_body, LeadStatus.MINERADO.value, lead.notes, now, lead.region.value,
                 json.dumps(lead.emails), json.dumps(lead.ats_links), json.dumps(lead.labels),
                 lead.location, lead.posted_at),
            )
            lead_id = cur.lastrowid
            conn.execute(
                "INSERT INTO lead_events (lead_id, status, at, note) VALUES (?, ?, ?, '')",
                (lead_id, LeadStatus.MINERADO.value, now),
            )
            return lead_id

    def add_many(self, leads):
        """Retorna (inseridos, duplicados)."""
        inserted = duplicates = 0
        for lead in leads:
            if self.add(lead) is None:
                duplicates += 1
            else:
                inserted += 1
        return inserted, duplicates

    def get(self, lead_id):
        with self._connect() as conn:
            row = conn.execute(f"SELECT {_LEAD_COLUMNS} FROM leads WHERE id = ?", (lead_id,)).fetchone()
        return self._to_lead(row) if row else None

    def list_recent(self, limit=35, status=None):
        sql = f"SELECT {_LEAD_COLUMNS} FROM leads"
        params = []
        if status:
            sql += " WHERE status = ?"
            params.append(LeadStatus(status).value)
        sql += " ORDER BY id DESC LIMIT ?"
        params.append(limit)
        with self._connect() as conn:
            return [self._to_lead(r) for r in conn.execute(sql, params)]

    def set_status(self, lead_id, status, note=""):
        """Muda o status e registra o evento. So status de contato mexem em contacted_at/follow-up."""
        status = LeadStatus(status)
        now = self._now()
        with self._connect() as conn:
            if conn.execute("SELECT 1 FROM leads WHERE id = ?", (lead_id,)).fetchone() is None:
                return False
            if status in AWAITING_REPLY:
                conn.execute(
                    "UPDATE leads SET status=?, contacted_at=?, followup_due_at=? WHERE id=?",
                    (status.value, _fmt(now), _fmt(now + timedelta(days=FOLLOWUP_DAYS)), lead_id),
                )
            else:
                conn.execute(
                    "UPDATE leads SET status=?, followup_due_at=NULL WHERE id=?", (status.value, lead_id)
                )
            conn.execute(
                "INSERT INTO lead_events (lead_id, status, at, note) VALUES (?, ?, ?, ?)",
                (lead_id, status.value, _fmt(now), note),
            )
            return True

    def pending_followups(self):
        placeholders = ",".join("?" for _ in AWAITING_REPLY)
        with self._connect() as conn:
            rows = conn.execute(
                f"""SELECT {_LEAD_COLUMNS} FROM leads
                    WHERE status IN ({placeholders}) AND followup_due_at IS NOT NULL AND followup_due_at <= ?
                    ORDER BY followup_due_at""",
                [s.value for s in AWAITING_REPLY] + [_fmt(self._now())],
            ).fetchall()
        return [self._to_lead(r) for r in rows]

    def events(self, lead_id):
        with self._connect() as conn:
            return [dict(r) for r in conn.execute(
                "SELECT status, at, note FROM lead_events WHERE lead_id = ? ORDER BY at, id", (lead_id,)
            )]

    def funnel_rows(self):
        """Linhas (source, lead_id, status_atual, ja_contatado, teve_resposta) para metricas."""
        with self._connect() as conn:
            return [dict(r) for r in conn.execute("""
                SELECT l.source AS source, l.id AS lead_id, l.status AS status,
                       EXISTS(SELECT 1 FROM lead_events e WHERE e.lead_id = l.id
                              AND e.status IN ({contacted})) AS contacted,
                       EXISTS(SELECT 1 FROM lead_events e WHERE e.lead_id = l.id
                              AND e.status IN ({replied})) AS replied
                FROM leads l
            """.format(contacted=",".join("?" for _ in AWAITING_REPLY), replied=",".join("?" for _ in POSITIVE)),
                [s.value for s in AWAITING_REPLY] + [s.value for s in POSITIVE])]

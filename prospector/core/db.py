import sqlite3
from datetime import datetime, timedelta
from prospector.core.config import DB_PATH

def init_db():
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS leads (
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
            followup_due_at TIMESTAMP
        )
    """)
    conn.commit()
    conn.close()

def insert_lead(company, title, source, url, contact_info, raw_body=""):
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("""
        INSERT OR IGNORE INTO leads (company, title, source, url, contact_info, raw_body, status)
        VALUES (?, ?, ?, ?, ?, ?, 'minerado')
    """, (company, title, source, url, contact_info, raw_body))
    conn.commit()
    conn.close()

def get_lead(lead_id):
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("SELECT id, company, title, source, url, contact_info, raw_body, status FROM leads WHERE id = ?", (lead_id,))
    row = cur.fetchone()
    conn.close()
    return row

def list_leads(limit=35):
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("SELECT id, company, title, source, status, contact_info FROM leads ORDER BY id DESC LIMIT ?", (limit,))
    rows = cur.fetchall()
    conn.close()
    return rows

def update_status(lead_id, status):
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    cur.execute("UPDATE leads SET status = ?, contacted_at = ? WHERE id = ?", (status, now_str, lead_id))
    conn.commit()
    conn.close()

def get_pending_followups(days=5):
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cutoff_date = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d %H:%M:%S")
    cur.execute("""
        SELECT id, company, title, source, contacted_at 
        FROM leads 
        WHERE status IN ('conexao_enviada', 'mensagem_enviada', 'aguardando_followup')
        AND contacted_at <= ?
    """, (cutoff_date,))
    rows = cur.fetchall()
    conn.close()
    return rows

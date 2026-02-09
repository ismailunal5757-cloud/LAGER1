import os
import sqlite3
import pandas as pd
from datetime import date, datetime

def _conn(db_path: str):
    con = sqlite3.connect(db_path, check_same_thread=False)
    con.execute("PRAGMA journal_mode=WAL;")
    con.execute("PRAGMA foreign_keys=ON;")
    return con

def _db_path(data_dir: str) -> str:
    return os.path.join(data_dir, "app.db")

def init_db(data_dir: str):
    os.makedirs(data_dir, exist_ok=True)
    dbp = _db_path(data_dir)
    con = _conn(dbp)
    cur = con.cursor()

    cur.executescript("""
    CREATE TABLE IF NOT EXISTS items (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        sku TEXT NOT NULL UNIQUE,
        name TEXT NOT NULL,
        created_at TEXT NOT NULL
    );

    CREATE TABLE IF NOT EXISTS locations (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        code TEXT NOT NULL UNIQUE,
        description TEXT,
        created_at TEXT NOT NULL
    );

    CREATE TABLE IF NOT EXISTS lots (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        item_id INTEGER NOT NULL,
        batch TEXT NOT NULL,
        mhd TEXT, -- ISO date
        created_at TEXT NOT NULL,
        UNIQUE(item_id, batch, COALESCE(mhd,'')),
        FOREIGN KEY(item_id) REFERENCES items(id)
    );

    CREATE TABLE IF NOT EXISTS inventory (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        lot_id INTEGER NOT NULL,
        location_id INTEGER NOT NULL,
        paletten INTEGER NOT NULL DEFAULT 0,
        koli INTEGER NOT NULL DEFAULT 0,
        updated_at TEXT NOT NULL,
        UNIQUE(lot_id, location_id),
        FOREIGN KEY(lot_id) REFERENCES lots(id),
        FOREIGN KEY(location_id) REFERENCES locations(id)
    );

    CREATE TABLE IF NOT EXISTS movements (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        typ TEXT NOT NULL CHECK(typ IN ('IN','OUT')),
        lot_id INTEGER NOT NULL,
        location_id INTEGER NOT NULL,
        paletten INTEGER NOT NULL DEFAULT 0,
        koli INTEGER NOT NULL DEFAULT 0,
        partner TEXT, -- Lieferant oder Empfänger
        reference TEXT,
        notes TEXT,
        datum TEXT NOT NULL, -- ISO date
        created_at TEXT NOT NULL,
        FOREIGN KEY(lot_id) REFERENCES lots(id),
        FOREIGN KEY(location_id) REFERENCES locations(id)
    );

    CREATE TABLE IF NOT EXISTS documents (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        movement_id INTEGER NOT NULL,
        filename TEXT NOT NULL,
        stored_path TEXT NOT NULL,
        mime TEXT,
        size_bytes INTEGER,
        uploaded_at TEXT NOT NULL,
        FOREIGN KEY(movement_id) REFERENCES movements(id)
    );
    """)
    con.commit()
    con.close()

def _now():
    return datetime.utcnow().isoformat(timespec="seconds")

def _iso(d):
    if d is None:
        return None
    if isinstance(d, str):
        return d
    if isinstance(d, date):
        return d.isoformat()
    return str(d)

# -------- items --------
def get_items(data_dir: str) -> pd.DataFrame:
    con = _conn(_db_path(data_dir))
    df = pd.read_sql_query("SELECT id, sku, name, created_at FROM items ORDER BY sku", con)
    con.close()
    return df

def add_item(data_dir: str, sku: str, name: str):
    con = _conn(_db_path(data_dir))
    con.execute("INSERT OR IGNORE INTO items(sku,name,created_at) VALUES (?,?,?)", (sku, name, _now()))
    con.commit()
    con.close()

# -------- locations --------
def get_locations(data_dir: str) -> pd.DataFrame:
    con = _conn(_db_path(data_dir))
    df = pd.read_sql_query("SELECT id, code, description, created_at FROM locations ORDER BY code", con)
    con.close()
    return df

def add_location(data_dir: str, code: str, description: str):
    con = _conn(_db_path(data_dir))
    con.execute("INSERT OR IGNORE INTO locations(code,description,created_at) VALUES (?,?,?)", (code, description, _now()))
    con.commit()
    con.close()

# -------- lots --------
def get_lots(data_dir: str) -> pd.DataFrame:
    con = _conn(_db_path(data_dir))
    df = pd.read_sql_query("""
        SELECT l.id, l.item_id, i.sku, i.name, l.batch, l.mhd, l.created_at
        FROM lots l
        JOIN items i ON i.id = l.item_id
        ORDER BY i.sku, l.batch
    """, con)
    con.close()
    return df

def add_lot(data_dir: str, item_id: int, batch: str, mhd):
    con = _conn(_db_path(data_dir))
    con.execute(
        "INSERT OR IGNORE INTO lots(item_id,batch,mhd,created_at) VALUES (?,?,?,?)",
        (item_id, batch, _iso(mhd), _now())
    )
    con.commit()
    con.close()

# -------- inventory --------
def get_inventory(data_dir: str) -> pd.DataFrame:
    con = _conn(_db_path(data_dir))
    df = pd.read_sql_query("""
        SELECT
            inv.lot_id,
            inv.location_id,
            i.sku,
            i.name AS artikel,
            l.batch,
            l.mhd,
            loc.code AS lagerplatz,
            inv.paletten,
            inv.koli,
            inv.updated_at
        FROM inventory inv
        JOIN lots l ON l.id = inv.lot_id
        JOIN items i ON i.id = l.item_id
        JOIN locations loc ON loc.id = inv.location_id
        WHERE (inv.paletten <> 0 OR inv.koli <> 0)
        ORDER BY i.sku, l.batch, loc.code
    """, con)
    con.close()
    return df

def upsert_inventory_delta(data_dir: str, lot_id: int, location_id: int, d_pallets: int, d_koli: int):
    con = _conn(_db_path(data_dir))
    cur = con.cursor()
    cur.execute("SELECT paletten, koli FROM inventory WHERE lot_id=? AND location_id=?", (lot_id, location_id))
    row = cur.fetchone()
    if row is None:
        new_p = d_pallets
        new_k = d_koli
        cur.execute(
            "INSERT INTO inventory(lot_id,location_id,paletten,koli,updated_at) VALUES (?,?,?,?,?)",
            (lot_id, location_id, new_p, new_k, _now())
        )
    else:
        new_p = int(row[0]) + int(d_pallets)
        new_k = int(row[1]) + int(d_koli)
        cur.execute(
            "UPDATE inventory SET paletten=?, koli=?, updated_at=? WHERE lot_id=? AND location_id=?",
            (new_p, new_k, _now(), lot_id, location_id)
        )
    con.commit()
    con.close()

# -------- movements --------
def add_movement(data_dir: str, typ: str, lot_id: int, location_id: int, paletten: int, koli: int,
                 partner: str, reference: str, notes: str, datum):
    con = _conn(_db_path(data_dir))
    cur = con.cursor()
    cur.execute(
        """INSERT INTO movements(typ,lot_id,location_id,paletten,koli,partner,reference,notes,datum,created_at)
             VALUES (?,?,?,?,?,?,?,?,?,?)""",
        (typ, lot_id, location_id, paletten, koli, partner, reference, notes, _iso(datum), _now())
    )
    con.commit()
    mid = cur.lastrowid
    con.close()
    return mid

def get_movements(data_dir: str) -> pd.DataFrame:
    con = _conn(_db_path(data_dir))
    df = pd.read_sql_query("""
        SELECT
            m.id,
            m.typ,
            m.datum,
            i.sku,
            i.name AS artikel,
            l.batch,
            l.mhd,
            loc.code AS lagerplatz,
            m.paletten,
            m.koli,
            m.partner,
            m.reference,
            m.notes,
            m.created_at
        FROM movements m
        JOIN lots l ON l.id = m.lot_id
        JOIN items i ON i.id = l.item_id
        JOIN locations loc ON loc.id = m.location_id
        ORDER BY m.id DESC
    """, con)
    con.close()
    return df

# -------- documents --------
def add_document(data_dir: str, movement_id: int, filename: str, stored_path: str, mime: str, size_bytes: int):
    con = _conn(_db_path(data_dir))
    con.execute(
        "INSERT INTO documents(movement_id,filename,stored_path,mime,size_bytes,uploaded_at) VALUES (?,?,?,?,?,?)",
        (movement_id, filename, stored_path, mime, size_bytes, _now())
    )
    con.commit()
    con.close()

def get_documents_for_movement(data_dir: str, movement_id: int) -> pd.DataFrame:
    con = _conn(_db_path(data_dir))
    df = pd.read_sql_query(
        "SELECT id, movement_id, filename, stored_path, mime, size_bytes, uploaded_at FROM documents WHERE movement_id=? ORDER BY id DESC",
        con, params=(movement_id,)
    )
    con.close()
    return df

def get_document_blob(data_dir: str, document_id: int) -> bytes:
    con = _conn(_db_path(data_dir))
    cur = con.cursor()
    cur.execute("SELECT stored_path FROM documents WHERE id=?", (document_id,))
    row = cur.fetchone()
    con.close()
    if not row:
        return b""
    path = row[0]
    with open(path, "rb") as f:
        return f.read()

import sqlite3

DB_NAME = "chat_history.db"


def connect_db():
    return sqlite3.connect(DB_NAME, timeout=10)


def create_tables():
    con = connect_db()
    cur = con.cursor()

    cur.execute("""
        CREATE TABLE IF NOT EXISTS contacts (
            name TEXT PRIMARY KEY
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            sender TEXT NOT NULL,
            recipient TEXT NOT NULL,
            message TEXT NOT NULL,
            chat_type TEXT NOT NULL,
            timestamp TEXT NOT NULL,
            delivered INTEGER DEFAULT 0,
            kind TEXT DEFAULT 'text',
            file_name TEXT,
            file_size INTEGER DEFAULT 0,
            transfer_id TEXT
        )
    """)

    existing = {
        row[1] for row in cur.execute("PRAGMA table_info(messages)").fetchall()
    }

    migrations = {
        "delivered": "INTEGER DEFAULT 0",
        "kind": "TEXT DEFAULT 'text'",
        "file_name": "TEXT",
        "file_size": "INTEGER DEFAULT 0",
        "transfer_id": "TEXT"
    }

    for column, definition in migrations.items():
        if column not in existing:
            cur.execute(f"ALTER TABLE messages ADD COLUMN {column} {definition}")

    con.commit()
    con.close()


def add_contact(name):
    con = connect_db()
    con.execute("INSERT OR IGNORE INTO contacts (name) VALUES (?)", (name,))
    con.commit()
    con.close()


def get_contacts():
    con = connect_db()
    rows = con.execute("SELECT name FROM contacts ORDER BY name").fetchall()
    con.close()
    return [row[0] for row in rows]


def save_message(sender, recipient, message, chat_type, timestamp,
                 kind="text", file_name=None, file_size=0, transfer_id=None):
    con = connect_db()
    cur = con.cursor()
    cur.execute("""
        INSERT INTO messages
        (sender, recipient, message, chat_type, timestamp, delivered,
         kind, file_name, file_size, transfer_id)
        VALUES (?, ?, ?, ?, ?, 0, ?, ?, ?, ?)
    """, (
        sender, recipient, message, chat_type, timestamp,
        kind, file_name, file_size, transfer_id
    ))
    message_id = cur.lastrowid
    con.commit()
    con.close()
    return message_id


def get_private_history(user1, user2):
    con = connect_db()
    rows = con.execute("""
        SELECT id, sender, recipient, message, timestamp,
               COALESCE(kind, 'text'), file_name, COALESCE(file_size, 0),
               transfer_id
        FROM messages
        WHERE chat_type = 'private'
          AND (
              (sender = ? AND recipient = ?)
              OR (sender = ? AND recipient = ?)
          )
        ORDER BY id
    """, (user1, user2, user2, user1)).fetchall()
    con.close()
    return rows


def get_group_history():
    con = connect_db()
    rows = con.execute("""
        SELECT id, sender, recipient, message, timestamp,
               COALESCE(kind, 'text'), file_name, COALESCE(file_size, 0),
               transfer_id
        FROM messages
        WHERE chat_type = 'group'
        ORDER BY id
    """).fetchall()
    con.close()
    return rows


def get_pending_messages(name):
    con = connect_db()
    rows = con.execute("""
        SELECT id, sender, recipient, message, timestamp
        FROM messages
        WHERE chat_type = 'private'
          AND COALESCE(kind, 'text') = 'text'
          AND recipient = ?
          AND delivered = 0
        ORDER BY id
    """, (name,)).fetchall()
    con.close()
    return rows


def mark_delivered(message_id):
    con = connect_db()
    con.execute("UPDATE messages SET delivered = 1 WHERE id = ?", (message_id,))
    con.commit()
    con.close()


create_tables()

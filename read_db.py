import asyncio
import sqlite3

def run():
    db = sqlite3.connect("data/meetings.db")
    db.row_factory = sqlite3.Row
    cur = db.cursor()
    cur.execute("SELECT id, meeting_id, speaker, text FROM transcript_segments ORDER BY start_time DESC LIMIT 20;")
    rows = cur.fetchall()
    
    for r in rows:
        print(dict(r))

    cur.execute("SELECT * FROM speakers;")
    print("Speakers", [dict(r) for r in cur.fetchall()])

if __name__ == "__main__":
    run()

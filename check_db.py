import sqlite3
import sys
sys.path.insert(0, '/opt/legal-lens/backend')
from app.storage.qdrant_client import vector_store

conn = sqlite3.connect('/opt/legal-lens/storage/sqlite/legal_lens.db')
print('Documents in DB:')
for row in conn.execute('SELECT name, chunks_count, status FROM documents').fetchall():
    print(f'  {row[0]}: {row[1]} chunks [{row[2]}]')

print(f'\nQdrant vectors: {vector_store.count()}')
conn.close()

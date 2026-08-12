"""重置数据库和向量索引"""
import os
os.environ['HF_ENDPOINT'] = 'https://hf-mirror.com'

import sqlite3
import sys
sys.path.insert(0, '/opt/legal-lens/backend')

# 清空 SQLite 文档记录
conn = sqlite3.connect('/opt/legal-lens/storage/sqlite/legal_lens.db')
conn.execute('DELETE FROM documents')
conn.commit()
conn.close()
print('SQLite: documents cleared')

# 重建 Qdrant collection
from app.storage.qdrant_client import vector_store
vector_store.init_collection(recreate=True)
print(f'Qdrant: collection recreated, count = {vector_store.count()}')

import os
os.environ['HF_ENDPOINT'] = 'https://hf-mirror.com'
os.environ['HF_HUB_DISABLE_PROGRESS_BARS'] = '1'
from sentence_transformers import SentenceTransformer
print('downloading from mirror ...')
m = SentenceTransformer('BAAI/bge-small-zh-v1.5', device='cpu')
print('OK, dim:', m.get_embedding_dimension())

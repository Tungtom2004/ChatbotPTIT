import json,os 
from pathlib import Path 
import chromadb 
from chromadb.config import Settings
from embeddings import get_embedding

db_path = ".chroma_db"
collection_name = "ptit_giaotrinh_2"
child_jsonl = "D:/ChatBotSlidePTIT/data/child_chunks.jsonl"
embedder = get_embedding()

client = chromadb.PersistentClient(
    path=db_path,
    settings=Settings(anonymized_telemetry=False)
)

try:
    client.create_collection(name=collection_name)
except Exception:
    pass 
collection = client.get_collection(name=collection_name)
ids, docs, metas = [], [], []
batch = 500
i = 0 

with open(child_jsonl,"r",encoding="utf-8") as f:
    for line in f:
        obj = json.loads(line)
        ids.append(f"child-{i}")
        docs.append(obj["content"])
        metas.append(
            {
                "subject":obj["subject"],
                "section":obj["section"],
                "title_path":obj["title_path"],
                "parent_id":obj["parent_id"],
                "order_start": obj["order_start"],
                "order_end": obj["order_end"],
                "word_count": obj["word_count"],
            }
        )
        i+=1 
        if len(ids) >= batch:
            vecs = embedder.embed_documents(docs)
            collection.add(ids = ids,documents = docs,metadatas = metas,embeddings=vecs)
            ids,docs,metas = [],[],[]

if ids:
    vecs = embedder.embed_documents(docs)
    collection.add(ids = ids,documents = docs,metadatas = metas,embeddings=vecs)

print("Done. Total child chunks:", i)


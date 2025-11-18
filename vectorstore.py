from langchain_community.vectorstores import Chroma 
from embeddings import get_embedding 
from split import split_document, load_document
import os 

dir = load_document("D:/ChatBotSlidePTIT/Slides_PTIT")
texts = split_document(dir)

def create_db():
    embedding = get_embedding()
    db = Chroma.from_documents(
        documents=texts, 
        embedding=embedding, 
        persist_directory="./chroma_db"
    )
    db.persist()
    return db

create_db()

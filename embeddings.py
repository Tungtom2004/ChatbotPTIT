from langchain_community.embeddings import HuggingFaceEmbeddings
#from sentence_transformers import SentenceTransformer

def get_embedding():
    embeddings = HuggingFaceEmbeddings(
        model_name = "Alibaba-NLP/gte-multilingual-base",
        model_kwargs = {'device': 'cpu',
                        'trust_remote_code': True},
        encode_kwargs = {'normalize_embeddings': True},
    )
    return embeddings

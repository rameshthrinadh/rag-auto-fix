import os
import faiss
from app.core.config import settings

def load_faiss_index():
    """
    Loads FAISS index gracefully or creates a new empty one bound to embedding dims.
    """
    if os.path.exists(settings.FAISS_INDEX_PATH) and os.path.isfile(settings.FAISS_INDEX_PATH):
        try:
            return faiss.read_index(settings.FAISS_INDEX_PATH)
        except Exception as e:
            print(f"Error loading FAISS Index: {e}")
            return faiss.IndexFlatL2(1536)
    
    return faiss.IndexFlatL2(1536) # Assume dim 1536 strictly matching ADA-002

def save_faiss_index(index):
    """
    Safe write strategy to bypass file corruption edgecases.
    """
    directory = os.path.dirname(settings.FAISS_INDEX_PATH)
    os.makedirs(directory, exist_ok=True)
    
    temp_path = settings.FAISS_INDEX_PATH + ".tmp"
    faiss.write_index(index, temp_path)
    os.replace(temp_path, settings.FAISS_INDEX_PATH)

def clear_faiss_index():
    """
    Safely clears out the index file if forced logic happens.
    """
    if os.path.exists(settings.FAISS_INDEX_PATH) and os.path.isfile(settings.FAISS_INDEX_PATH):
        os.remove(settings.FAISS_INDEX_PATH)

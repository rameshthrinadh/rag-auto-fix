import os
import pickle
import numpy as np
from typing import List, Dict, Any, Tuple

from app.core.config import settings

def load_persistence() -> Tuple[List[Dict[str, Any]], np.ndarray]:
    """
    Attempts to load the metadata arrays and numpy embeddings array.
    Returns (metadata_list, embeddings_np)
    """
    metadata = []
    embeddings = None

    if os.path.exists(settings.INDEX_METADATA_PATH):
        try:
            with open(settings.INDEX_METADATA_PATH, 'rb') as f:
                metadata = pickle.load(f)
        except Exception as e:
            print(f"Warning: Failed to load metadata cache: {e}")

    if os.path.exists(settings.RAW_EMBEDDINGS_PATH):
        try:
            embeddings = np.load(settings.RAW_EMBEDDINGS_PATH)
        except Exception as e:
            print(f"Warning: Failed to load numpy embeddings cache: {e}")

    # Ensure shape aligns if both exist, otherwise initialize safely empty
    if embeddings is None:
        # Standard placeholder initialized if empty
        embeddings = np.empty((0, 1536), dtype='float32')

    return metadata, embeddings

def save_persistence(metadata: List[Dict[str, Any]], embeddings: np.ndarray):
    """
    Saves the metadata list and numpy array sequentially.
    """
    # Create dir if not exist
    os.makedirs(os.path.dirname(settings.INDEX_METADATA_PATH), exist_ok=True)
    
    with open(settings.INDEX_METADATA_PATH, 'wb') as f:
        pickle.dump(metadata, f)
        
    np.save(settings.RAW_EMBEDDINGS_PATH, embeddings)

def clear_persistence():
    """
    Removes cached embeddings if standard rebuild is flagged.
    """
    if os.path.exists(settings.INDEX_METADATA_PATH):
        os.remove(settings.INDEX_METADATA_PATH)
    if os.path.exists(settings.RAW_EMBEDDINGS_PATH):
        os.remove(settings.RAW_EMBEDDINGS_PATH)

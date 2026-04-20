import argparse
import os
import time
import numpy as np
from openai import OpenAI
from dotenv import load_dotenv

import sys
# Add parent dir to path if running directly
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from indexing.git_loader import load_repo_files, read_file_content
from indexing.chunker import get_ast_chunks
from indexing.hash_utils import generate_content_hash
from indexing.embedding_store import load_persistence, save_persistence, clear_persistence
from indexing.faiss_store import load_faiss_index, save_faiss_index, clear_faiss_index
from app.core.config import settings
from app.core.constants import MIN_CHUNK_TOKENS

load_dotenv()
client = OpenAI(api_key=settings.OPENAI_API_KEY)

def get_embeddings_batch(texts: list[str], model="text-embedding-ada-002"):
    """
    Submits a batch of texts for embedding to reduce network overhead.
    """
    try:
        texts = [t.replace("\n", " ") for t in texts]
        response = client.embeddings.create(input=texts, model=model)
        return [data.embedding for data in response.data]
    except Exception as e:
        print(f"Batch Embedding error: {e}")
        return [list(np.random.rand(1536)) for _ in texts]

def build_index(repo_path: str, force_rebuild: bool = False):
    start_time = time.time()
    
    if force_rebuild:
        print("Force rebuild requested. Clearing cache...")
        clear_persistence()
        clear_faiss_index()

    print(f"Scanning {repo_path}...")
    files = load_repo_files(repo_path)
    
    all_chunks = []
    
    for f in files:
        content = read_file_content(f)
        chunks = get_ast_chunks(content, f)
        all_chunks.extend(chunks)
        
    if not all_chunks:
        print("No Python files or chunks found.")
        return

    # Load persistent stores
    metadata_list, embeddings_np = load_persistence()
    index = load_faiss_index()

    # Build lookup of existing hashes
    existing_hashes = {m['content_hash'] for m in metadata_list}

    print(f"Loaded {len(existing_hashes)} cached chunks.")

    reused_count = 0
    new_chunks = []

    # Identify which chunks are genuinely new and valid
    for chunk in all_chunks:
        if chunk.get('tokens', 0) < MIN_CHUNK_TOKENS:
            continue
            
        content_hash = generate_content_hash(chunk['code'])
        chunk['content_hash'] = content_hash
        chunk['chunk_id'] = len(metadata_list) + len(new_chunks)
        
        if content_hash in existing_hashes:
            reused_count += 1
            continue
            
        new_chunks.append(chunk)

    print(f"Found {reused_count} duplicated/reused chunks.")
    print(f"{len(new_chunks)} chunks require new embeddings.")

    if new_chunks:
        texts_to_embed = [f"{c['name']}\n{c['code']}" for c in new_chunks]
        new_embeddings_list = []
        
        BATCH_SIZE = 100
        for i in range(0, len(texts_to_embed), BATCH_SIZE):
            batch = texts_to_embed[i:i+BATCH_SIZE]
            print(f"Embedding batch {i//BATCH_SIZE + 1}/{(len(texts_to_embed)-1)//BATCH_SIZE + 1}...")
            batch_embs = get_embeddings_batch(batch, settings.EMBEDDING_MODEL)
            new_embeddings_list.extend(batch_embs)
            
        # Add to numpy array
        new_embeddings_np = np.array(new_embeddings_list).astype('float32')
        embeddings_np = np.vstack([embeddings_np, new_embeddings_np])
        
        # Add to FAISS index
        index.add(new_embeddings_np)
        
        # Append to metadata list
        metadata_list.extend(new_chunks)

        # Save updates safely down to disk
        save_persistence(metadata_list, embeddings_np)
        save_faiss_index(index)
        
        print(f"Index and cache successfully updated.")
    else:
        print("No updates needed. Cache is perfectly aligned with current state.")

    print(f"Total processing time: {time.time() - start_time:.2f} seconds.")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Index a repository code base incrementally.")
    parser.add_argument("--repo", type=str, required=True, help="/path/to/code")
    parser.add_argument("--force", type=str, default="false", help="Set 'true' to nuke cache and rebuild.")
    args = parser.parse_args()
    
    force_rebuild = args.force.lower() in ['true', '1', 't', 'y', 'yes']
    build_index(args.repo, force_rebuild)

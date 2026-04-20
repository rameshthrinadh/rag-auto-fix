import hashlib

def generate_content_hash(content: str) -> str:
    """
    Consistently generates a SHA-256 string footprint of a code block 
    so we can deduplicate overlapping or identical chunks.
    """
    return hashlib.sha256(content.encode("utf-8")).hexdigest()

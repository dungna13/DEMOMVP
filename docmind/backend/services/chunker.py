import re
from typing import List
from models.chunk import Chunk

def chunk_text(text: str, source_id: str, target_tokens: int = 400, overlap_sentences: int = 2) -> List[Chunk]:
    # Simple sentence splitting using regex
    sentences = re.split(r'(?<=[.!?])\s+', text)
    chunks = []
    buffer = []
    buf_tokens = 0
    chunk_index = 0

    for sentence in sentences:
        tokens = len(sentence.split())
        if buf_tokens + tokens > target_tokens and buffer:
            # Save current chunk
            chunks.append(Chunk(
                id=f"{source_id}_{chunk_index}",
                source_id=source_id,
                index=chunk_index,
                text=" ".join(buffer),
                token_count=buf_tokens
            ))
            chunk_index += 1
            # Maintain overlap
            buffer = buffer[-overlap_sentences:] if len(buffer) > overlap_sentences else buffer
            buf_tokens = sum(len(s.split()) for s in buffer)
        
        buffer.append(sentence)
        buf_tokens += tokens

    if buffer:
        chunks.append(Chunk(
            id=f"{source_id}_{chunk_index}",
            source_id=source_id,
            index=chunk_index,
            text=" ".join(buffer),
            token_count=buf_tokens
        ))

    return chunks

import json
import os
from rank_bm25 import BM25Okapi
from typing import List
from models.chunk import Chunk

DATA_DIR = os.getenv("DATA_DIR", "./data")

def load_chunks_for_sources(source_ids: List[str]) -> List[Chunk]:
    all_chunks = []
    for sid in source_ids:
        path = os.path.join(DATA_DIR, "chunks", f"{sid}.json")
        if os.path.exists(path):
            with open(path, 'r', encoding='utf-8') as f:
                data = json.load(f)
                source_chunks = [Chunk(**c) for c in data.get("chunks", [])]
                all_chunks.extend(source_chunks)
    return all_chunks

def retrieve_top_chunks(query: str, source_ids: List[str], top_k=8) -> List[Chunk]:
    all_chunks = load_chunks_for_sources(source_ids)
    if not all_chunks:
        return []

    tokenized_corpus = [c.text.lower().split() for c in all_chunks]
    bm25 = BM25Okapi(tokenized_corpus)
    
    tokenized_query = query.lower().split()
    scores = bm25.get_scores(tokenized_query)
    
    # Get top_k indices sorted by score
    top_indices = sorted(range(len(scores)), key=lambda i: scores[i], reverse=True)[:top_k]
    
    return [all_chunks[i] for i in top_indices]

import json
import re
from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import StreamingResponse
from typing import List, Optional
import asyncio

from models.chat import ChatRequest, SummaryRequest
from services.retriever import retrieve_top_chunks, load_chunks_for_sources
from services.prompt_builder import build_chat_prompt, build_summary_prompt
from services.gemini_client import gemini_client
from routers.sources import load_sources

router = APIRouter()

def parse_citations_v2(raw: str) -> tuple[str, list[dict]]:
    pattern = r"```citations\s*([\s\S]+?)```"
    match = re.search(pattern, raw)
    citations = []
    prose = raw
    if match:
        prose = raw[:match.start()].strip()
        try:
            citations_str = match.group(1).strip()
            citations = json.loads(citations_str)
        except json.JSONDecodeError:
            citations = []
    return prose, citations

@router.post("/chat")
async def chat(req: ChatRequest):
    sources = load_sources()
    active_sources = [s for s in sources if s.id in req.active_source_ids]
    
    if not active_sources:
        raise HTTPException(status_code=400, detail="No active sources provided")

    # 1. Retrieve relevant chunks
    chunks = retrieve_top_chunks(req.message, req.active_source_ids)
    
    # 2. Build prompt
    system_prompt = build_chat_prompt(chunks, active_sources)
    
    # 3. Stream from Gemini
    async def event_stream():
        full_response = ""
        async for token in gemini_client.stream_chat(
            system_prompt, 
            [m.dict() for m in req.history], 
            req.message
        ):
            full_response += token
            yield f"data: {json.dumps({'token': token})}\n\n"
        
        # After stream ends, parse citations
        prose, citations = parse_citations_v2(full_response)
        yield f"data: {json.dumps({'citations': citations, 'done': True})}\n\n"

    return StreamingResponse(event_stream(), media_type="text/event-stream")

@router.post("/summary")
async def summary(req: SummaryRequest):
    sources = load_sources()
    active_sources = [s for s in sources if s.id in req.source_ids]
    
    if not active_sources:
        raise HTTPException(status_code=400, detail="No sources activated")

    # Load all chunks for selected sources (summary needs broad context)
    chunks = load_chunks_for_sources(req.source_ids)
    
    # Limit chunks if too many (Gemini has context limits)
    # For Flash we can handle quite a lot, but let's be reasonable
    chunks = chunks[:20] 

    system_prompt = build_summary_prompt(chunks, active_sources)
    context = "Please provide a summary based on the provided source passages."

    async def event_stream():
        async for token in gemini_client.generate_summary(system_prompt, context):
            yield f"data: {json.dumps({'token': token})}\n\n"
        yield f"data: {json.dumps({'done': True})}\n\n"

    return StreamingResponse(event_stream(), media_type="text/event-stream")

@router.get("/suggested-questions")
async def suggested_questions(source_ids: str = Query(...)):
    sid_list = source_ids.split(",")
    chunks = load_chunks_for_sources(sid_list)[:10] # Subset for prompt
    context = "\n".join([c.text for c in chunks])
    
    questions = await gemini_client.get_suggested_questions(context)
    return {"questions": questions}

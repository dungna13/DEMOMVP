import os
from dotenv import load_dotenv

# Load environment variables FIRST
load_dotenv()

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from routers import sources, chat

from fastapi import Request
import time

app = FastAPI(title="DocMind API", version="1.0.0")

# Logging Middleware
@app.middleware("http")
async def log_requests(request: Request, call_next):
    start_time = time.time()
    response = await call_next(request)
    process_time = (time.time() - start_time) * 1000
    print(f"Request: {request.method} {request.url.path} - Status: {response.status_code} - Completed in {process_time:.2f}ms")
    return response

# Configure CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], 
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/")
async def root():
    return {"status": "online", "message": "DocMind API is running"}

# Include routers
app.include_router(sources.router)
app.include_router(chat.router)

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)

# DocMind - Document Intelligence Platform

DocMind is a source-centric AI assistant inspired by Google NotebookLM. It uses Gemini 3.1 Flash to provide grounded answers based on your uploaded documents with inline citations.

## Setup & Running

### 1. Backend Setup
1. Navigate to the `backend` directory.
2. Create/edit the `.env` file and add your `GEMINI_API_KEY`:
   ```env
   GEMINI_API_KEY=your_actual_key_here
   ```
3. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```
4. Run the FastAPI server:
   ```bash
   python main.py
   ```
   The backend will run on `http://localhost:8000`.

### 2. Frontend Setup
1. Navigate to the `frontend` directory.
2. Serve the frontend using any static server:
   ```bash
   npx serve . -p 5173
   # OR
   python -m http.server 5173
   ```
3. Open `http://localhost:5173` in your browser.

## Features
- **Source Manager**: Upload PDFs or Text files. Toggle them to activate/deactivate as AI context.
- **Source Guide**: Get an automated summary of all active sources.
- **Grounded Chat**: Ask questions. The AI only answers based on your sources and provides interactive [1][2] citations.
- **Glassmorphism UI**: Beautiful, premium dark-mode interface with blur and glow effects.

## Project Structure
- `frontend/`: Vanilla HTML/CSS/JS frontend.
- `backend/`: FastAPI backend with Gemini integration and BM25 retrieval.
- `data/`: Local JSON storage for sources and chunks.

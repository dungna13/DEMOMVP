with open("main.py", "r", encoding="utf-8") as f:
    content = f.read()

patch_code = """
@app.post("/api/documents")
async def api_add_document(body: dict = Body(default={})):
    \"\"\"REST API: Thêm tài liệu mới cùng các chunks trực tiếp từ JSON (gửi qua Postman).\"\"\"
    try:
        doc_data = body.get("document")
        chunks_data = body.get("chunks", [])
        
        if not doc_data or not doc_data.get("doc_number") or not doc_data.get("title"):
            return JSONResponse({"error": "Dữ liệu document phải chứa doc_number và title"}, status_code=400)
            
        with get_db() as conn:
            # 1. Thêm document
            cursor = conn.execute(
                \"\"\"INSERT INTO documents 
                   (doc_number, title, doc_type, issuing_date, effective_date, expiry_date, 
                    effectiveness_status, gazette_number, signer, file_hash, content_markdown, 
                    structure_json, summary, summary_model, source_url, issuing_authority)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)\"\"\",
                (
                    doc_data.get("doc_number"),
                    doc_data.get("title"),
                    doc_data.get("doc_type", "quyet_dinh"),
                    doc_data.get("issuing_date"),
                    doc_data.get("effective_date"),
                    doc_data.get("expiry_date"),
                    doc_data.get("effectiveness_status", "con_hieu_luc"),
                    doc_data.get("gazette_number"),
                    doc_data.get("signer"),
                    doc_data.get("file_hash"),
                    doc_data.get("content_markdown", ""),
                    doc_data.get("structure_json", "{}"),
                    doc_data.get("summary", ""),
                    doc_data.get("summary_model", ""),
                    doc_data.get("source_url"),
                    doc_data.get("issuing_authority")
                )
            )
            doc_id = cursor.lastrowid
            
            # 2. Thêm các chunks
            for chunk in chunks_data:
                conn.execute(
                    \"\"\"INSERT INTO chunks 
                       (document_id, content, chunk_index, token_count, embedding_id, dieu, khoan, chuong)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?)\"\"\",
                    (
                        doc_id,
                        chunk.get("text", chunk.get("content", "")),
                        chunk.get("index", chunk.get("chunk_index", 0)),
                        chunk.get("token_count", 0),
                        chunk.get("embedding_id"),
                        chunk.get("dieu"),
                        chunk.get("khoan"),
                        chunk.get("chuong")
                    )
                )
                
        # 3. Kích hoạt build lại vector index trong background
        async def reindex_task():
            try:
                from src.core.embedding_service import reindex_all_chunks
                await asyncio.to_thread(reindex_all_chunks)
            except Exception:
                pass
        asyncio.create_task(reindex_task())
        
        return JSONResponse(content={
            "success": True,
            "message": "Đã thêm tài liệu thành công vào database và kích hoạt reindex.",
            "document_id": doc_id,
            "chunks_added": len(chunks_data)
        })
    except Exception as e:
        logger.error(f"[AddDoc] Error: {e}")
        return JSONResponse({"error": str(e)}, status_code=500)


"""

target = '@app.post("/api/ingest")'
if target in content:
    content = content.replace(target, patch_code + target)
    with open("main.py", "w", encoding="utf-8") as f:
        f.write(content)
    print("Patch main.py successful!")
else:
    print("Target not found in main.py!")

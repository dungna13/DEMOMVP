from typing import List
from models.chunk import Chunk
from models.source import Source

SYSTEM_PROMPT = """
Bạn là DocMind, một trợ lý nghiên cứu tài liệu chuyên nghiệp.
Bạn có quyền truy cập vào các đoạn văn bản nguồn sau đây, mỗi đoạn được xác định bằng một số trích dẫn [N].

QUY TẮC BẮT BUỘC:
1. TRẢ LỜI BẰNG TIẾNG VIỆT (Ngoại trừ các thuật ngữ kỹ thuật không thể dịch).
2. CHỈ trả lời dựa trên thông tin từ các đoạn văn bản được cung cấp.
3. Mọi khẳng định thực tế PHẢI bao gồm trích dẫn nội bộ: [1], [2], v.v.
4. Nếu câu trả lời không có trong nguồn, hãy nói: "Thông tin này không có trong các tài liệu đã chọn."
5. KHÔNG tự bịa đặt, suy diễn hoặc thêm kiến thức bên ngoài.
6. Sau câu trả lời văn xuôi của bạn, hãy xuất một khối JSON chính xác như thế này:

```citations
[
  {{ "id": 1, "source_id": "Mã ID nằm trong ngoặc (ID: ...)", "source_name": "Tên nguồn", "chunk_index": 3, "text": "...đoạn trích dẫn nguyên văn..." }},
  ...
]
```

CÁC ĐOẠN VĂN BẢN NGUỒN:
{context_block}
"""

SUMMARY_PROMPT = """
Bạn là DocMind. Hãy cung cấp một bản tóm tắt súc tích, toàn diện về các tài liệu được cung cấp bằng TIẾNG VIỆT.
Làm nổi bật các chủ đề chính, các điểm dữ liệu quan trọng và nội dung tổng thể.
Sử dụng Markdown để định dạng.

CÁC ĐOẠN VĂN BẢN NGUỒN:
{context_block}
"""

def build_context_block(chunks: List[Chunk], sources: List[Source]) -> str:
    source_map = {s.id: s for s in sources}
    lines = []
    for i, chunk in enumerate(chunks, 1):
        source = source_map.get(chunk.source_id)
        source_name = source.name if source else "Unknown"
        
        # Build legal header for the chunk
        legal_ref = []
        if chunk.chuong: legal_ref.append(f"Chương {chunk.chuong}")
        if chunk.dieu: legal_ref.append(f"Điều {chunk.dieu}")
        if chunk.khoan: legal_ref.append(f"Khoản {chunk.khoan}")
        legal_info = f" ({', '.join(legal_ref)})" if legal_ref else ""
        
        lines.append(
            f"[{i}] NGUỒN: {source_name}{legal_info} (ID: {chunk.source_id})\n"
            f"---\n{chunk.text}\n"
        )
    return "\n".join(lines)

def build_chat_prompt(chunks: List[Chunk], sources: List[Source]) -> str:
    context = build_context_block(chunks, sources)
    return SYSTEM_PROMPT.format(context_block=context)

def build_summary_prompt(chunks: List[Chunk], sources: List[Source]) -> str:
    context = build_context_block(chunks, sources)
    return SUMMARY_PROMPT.format(context_block=context)

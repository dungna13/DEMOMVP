"""
ocr_connector.py — Phase 5: Interface kết nối dịch vụ OCR bên ngoài
Đội OCR hiện thực class con kế thừa OCRServiceConnector.
Hiện tại dùng MockOCRConnector làm stub chờ tích hợp.
"""

import logging
from abc import ABC, abstractmethod
from typing import Optional

logger = logging.getLogger(__name__)


class OCRServiceConnector(ABC):
    """
    Interface trừu tượng cho dịch vụ OCR.

    Đội OCR cần kế thừa class này và hiện thực hàm extract_text().
    Khi hoàn thành, thay đổi hàm get_ocr_connector() để trả về class thực tế.
    """

    @abstractmethod
    def extract_text(self, file_bytes: bytes, file_name: str) -> dict:
        """
        Trích xuất văn bản từ file PDF.

        Args:
            file_bytes: Nội dung file PDF dạng bytes (đọc từ UploadFile.read())
            file_name:  Tên file gốc (vd: "nghi_dinh_45_2024.pdf")

        Returns:
            dict: {
                "success": True/False,
                "text": "Toàn bộ nội dung văn bản đã OCR (plain text hoặc Markdown)",
                "metadata": {                      # Optional, nếu OCR trích xuất được
                    "doc_number": "45/2024/NĐ-CP",
                    "issuing_date": "2024-05-15",
                    "issuing_authority": "Chính phủ"
                },
                "error": "Chi tiết lỗi nếu success=False"
            }
        """
        pass


class MockOCRConnector(OCRServiceConnector):
    """Stub tạm dùng trong lúc chờ đội OCR hoàn thiện."""

    def extract_text(self, file_bytes: bytes, file_name: str) -> dict:
        logger.warning(f"[OCR] MockOCRConnector được gọi cho file '{file_name}'. OCR service chưa sẵn sàng.")
        return {
            "success": False,
            "text": "",
            "metadata": {},
            "error": "OCR service chưa sẵn sàng. Đang chờ tích hợp từ đội OCR."
        }


# ─── Factory ──────────────────────────────────────────────────────────────────

_ocr_connector: Optional[OCRServiceConnector] = None


def get_ocr_connector() -> OCRServiceConnector:
    """
    Factory: trả về OCR connector hiện tại.
    Khi đội OCR hoàn thành, thay MockOCRConnector bằng class thực tế ở đây.
    """
    global _ocr_connector
    if _ocr_connector is None:
        # TODO: Thay bằng RealOCRConnector khi đội OCR hoàn thành
        _ocr_connector = MockOCRConnector()
    return _ocr_connector


def set_ocr_connector(connector: OCRServiceConnector):
    """Cho phép inject connector từ bên ngoài (test hoặc config)."""
    global _ocr_connector
    _ocr_connector = connector
    logger.info(f"[OCR] Connector đã được thay đổi thành: {type(connector).__name__}")

import io
from pypdf import PdfReader

# Pathological PDFs (10 MB of dense text) would otherwise hand megabytes to
# the parser agents; ~30k tokens is far above any real resume and far below
# every configured reasoning model's context window.
MAX_EXTRACTED_CHARS = 120_000

async def extract_text_from_pdf(file_bytes: bytes) -> str:
    """
    Extracts text from a PDF file provided as bytes.
    Raises ValueError if no text could be extracted.
    """
    try:
        reader = PdfReader(io.BytesIO(file_bytes))
        text = ""
        for page in reader.pages:
            page_text = page.extract_text()
            if page_text:
                text += page_text + "\n"

        text = text.strip()
        if not text:
            raise ValueError("No text could be extracted from the PDF.")

        return text[:MAX_EXTRACTED_CHARS]
    except Exception as e:
        if isinstance(e, ValueError):
            raise e
        raise ValueError(f"Failed to parse PDF: {str(e)}")

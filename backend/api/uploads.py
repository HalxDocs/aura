"""Size-capped reads for multipart uploads.

``UploadFile.read()`` with no argument buffers the entire request body in
memory before any limit is checked, so a single oversized POST can spike the
worker's RSS. Reading in chunks and aborting past the cap bounds that spike
to about one chunk above the limit.
"""

from fastapi import HTTPException, UploadFile

_CHUNK = 1024 * 1024  # 1 MB


async def read_upload_capped(file: UploadFile, max_bytes: int, detail: str) -> bytes:
    """Read an upload in chunks, buffering at most ``max_bytes``.

    Raises the caller's 413 with ``detail`` as soon as the cap is exceeded —
    the rest of the body is never read into memory.
    """
    buf = bytearray()
    while True:
        chunk = await file.read(_CHUNK)
        if not chunk:
            break
        buf.extend(chunk)
        if len(buf) > max_bytes:
            raise HTTPException(status_code=413, detail=detail)
    return bytes(buf)

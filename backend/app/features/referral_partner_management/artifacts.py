"""Bounded KYC artifact hardening after the existing file/password parser."""

import io
import re

from app.core.exceptions import ValidationError


def harden(data: bytes, mime: str) -> bytes:
    try:
        if mime == "application/pdf":
            import pymupdf

            with pymupdf.open(stream=data, filetype="pdf") as document:  # type: ignore[no-untyped-call]
                if (
                    document.page_count > 200
                    or document.xref_length() > 50000
                    or document.embfile_count()
                ):
                    raise ValueError("Unbounded or embedded content")
                for reference in range(1, document.xref_length()):
                    syntax = document.xref_object(reference, compressed=False)
                    if re.search(
                        r"/(?:JavaScript|JS|Launch|EmbeddedFile|RichMedia|SubmitForm|ImportData)\b",
                        syntax,
                    ):
                        raise ValueError("Active document content")
            return data
        from PIL import Image

        with Image.open(io.BytesIO(data)) as image:
            if image.width * image.height > 40_000_000:
                raise ValueError("Image exceeds the pixel limit")
            output = io.BytesIO()
            if mime == "image/jpeg":
                image.convert("RGB").save(output, format="JPEG", quality=90)
            else:
                image.convert("RGBA").save(output, format="PNG")
            return output.getvalue()
    except Exception:  # noqa: BLE001 - parser exceptions must not expose private document data
        raise ValidationError(
            "The KYC file contains unsupported active content, is too complex, or cannot be safely processed. Upload a clear PDF or image."
        ) from None

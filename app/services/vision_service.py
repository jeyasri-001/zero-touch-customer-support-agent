"""
Vision Service - Extracts context from image attachments using Claude's vision API.
Used to process screenshots, error images, and WhatsApp photos attached to support tickets.
"""

import base64
import os
from typing import Optional
import anthropic


EXTRACTION_PROMPT = (
    "This is a screenshot or photo attached to a fintech customer support ticket "
    "(mutual fund platform). Extract ALL of the following that are visible:\n"
    "- Error messages (exact text)\n"
    "- Error codes or rejection codes\n"
    "- Transaction IDs or reference numbers\n"
    "- Bank names or account numbers (masked is fine)\n"
    "- UI state (what screen/step the user is on)\n"
    "- Any payment gateway messages\n"
    "- Any UPI or NACH mandate status messages\n\n"
    "Be factual and concise. If nothing relevant is visible, say 'No actionable content found.'"
)


class VisionService:
    def __init__(self):
        api_key = os.getenv("ANTHROPIC_API_KEY")
        if not api_key:
            raise ValueError("ANTHROPIC_API_KEY not set — required for image analysis")
        self.client = anthropic.Anthropic(api_key=api_key)
        self.enabled = True

    def extract_context_from_image(self, image_bytes: bytes, mime_type: str) -> str:
        """Analyze a single image and return extracted support-relevant context."""
        b64 = base64.standard_b64encode(image_bytes).decode("utf-8")
        message = self.client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=512,
            messages=[{
                "role": "user",
                "content": [
                    {
                        "type": "image",
                        "source": {
                            "type": "base64",
                            "media_type": mime_type,
                            "data": b64
                        }
                    },
                    {
                        "type": "text",
                        "text": EXTRACTION_PROMPT
                    }
                ]
            }]
        )
        return message.content[0].text.strip()

    def extract_context_from_attachments(
        self,
        attachments: list[dict],
        download_fn,
        max_images: int = 4
    ) -> Optional[str]:
        """
        Process up to max_images image attachments and return combined context string,
        or None if no images or extraction fails entirely.

        attachments: list of dicts with keys: filename, content_url, mime_type
        download_fn: callable(content_url) -> bytes | None
        """
        image_attachments = [
            a for a in attachments
            if a.get("mime_type", "").startswith("image/")
        ][:max_images]

        if not image_attachments:
            return None

        descriptions = []
        for att in image_attachments:
            try:
                img_bytes = download_fn(att["content_url"])
                if not img_bytes:
                    continue
                desc = self.extract_context_from_image(img_bytes, att["mime_type"])
                if desc and "No actionable content found" not in desc:
                    descriptions.append(f"[Attachment: {att['filename']}]\n{desc}")
            except Exception as e:
                print(f"⚠️ Vision extraction failed for {att['filename']}: {e}")

        if not descriptions:
            return None

        return "ATTACHED IMAGE CONTEXT (extracted by vision model):\n\n" + "\n\n".join(descriptions)


_vision_service: Optional[VisionService] = None


def get_vision_service() -> Optional[VisionService]:
    """Return singleton VisionService, or None if ANTHROPIC_API_KEY is not set."""
    global _vision_service
    if _vision_service is None:
        try:
            _vision_service = VisionService()
        except ValueError:
            print("⚠️ VisionService disabled — ANTHROPIC_API_KEY not set")
            return None
    return _vision_service

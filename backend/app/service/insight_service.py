"""AI analyst briefing per conjunction event (FR-RSK-4).

Uses the official Anthropic SDK when KESSLER_ANTHROPIC_API_KEY is configured;
otherwise (or on any failure) falls back to a deterministic template.
This service never raises to its caller.
"""
from __future__ import annotations

import logging

from app.core.config import settings

logger = logging.getLogger(__name__)

_MODEL = "claude-opus-4-8"
_TIMEOUT_S = 10.0

_SYSTEM = (
    "You are KESSLER's orbital-safety analyst. Given one conjunction event as JSON, "
    "write a briefing for a smallsat operator: 2-4 sentences covering how concerned "
    "they should be, what drives the risk figure (including whether Pc is a "
    "covariance-free upper bound), and the single most useful next action. "
    "Plain prose, no markdown, no preamble."
)


def _template_briefing(event: dict) -> str:
    risk = event.get("risk", "UNKNOWN")
    pc = event.get("pc", {})
    sat1 = event.get("sat1", {}).get("name", "primary object")
    sat2 = event.get("sat2", {}).get("name", "secondary object")
    miss_km = event.get("miss_distance_m", 0) / 1000.0
    pc_note = (
        "an upper-bound estimate computed without covariance data"
        if pc.get("pc_type") == "max"
        else f"computed via {pc.get('method', 'unknown method')}"
    )
    return (
        f"{risk}-class conjunction between {sat1} and {sat2} with a predicted miss "
        f"distance of {miss_km:.2f} km. The collision probability of {pc.get('value', 0):.2e} "
        f"is {pc_note}. Recommended action: {event.get('action', 'continue monitoring.')}"
    )


class InsightService:
    def __init__(self) -> None:
        self._client = None
        if settings.anthropic_api_key:
            try:
                import anthropic  # optional dependency, imported lazily

                self._client = anthropic.Anthropic(api_key=settings.anthropic_api_key)
                logger.info("InsightService: AI briefings enabled (%s)", _MODEL)
            except Exception as exc:  # missing package / bad key format
                logger.warning("InsightService: AI unavailable (%s); using templates", exc)
        else:
            logger.info("InsightService: no API key configured; using template briefings")

    def briefing(self, event: dict) -> tuple[str, str]:
        """Returns (briefing_text, source) where source is 'ai' | 'template'."""
        if self._client is None:
            return _template_briefing(event), "template"
        try:
            import anthropic
            import json

            response = self._client.with_options(timeout=_TIMEOUT_S).messages.create(
                model=_MODEL,
                max_tokens=400,
                thinking={"type": "adaptive"},
                system=_SYSTEM,
                messages=[{
                    "role": "user",
                    "content": json.dumps(
                        {k: v for k, v in event.items() if k != "raw"}, default=str
                    ),
                }],
            )
            text = next(
                (b.text for b in response.content if b.type == "text"), ""
            ).strip()
            if not text:
                raise ValueError("empty AI response")
            return text, "ai"
        except anthropic.RateLimitError:
            logger.warning("InsightService: rate limited; falling back to template")
        except anthropic.APIStatusError as exc:
            logger.warning("InsightService: API error %s; falling back to template",
                           exc.status_code)
        except anthropic.APIConnectionError:
            logger.warning("InsightService: connection error; falling back to template")
        except Exception as exc:
            logger.warning("InsightService: unexpected failure (%s); falling back", exc)
        return _template_briefing(event), "template"

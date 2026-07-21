# GENERATED from backend/app/logic — edit there, then run packages/sync.py
"""Typed exception hierarchy — the only errors allowed to cross layer boundaries.

Boundary rule (HLD §4): logic raises, service contextualises/falls back,
API converts to the JSON error envelope. Nothing else escapes.
"""
from __future__ import annotations

from typing import Any


class KesslerError(Exception):
    code = "KESSLER_ERROR"
    http_status = 500

    def __init__(self, message: str, detail: Any = None):
        super().__init__(message)
        self.message = message
        self.detail = detail

    def envelope(self, request_id: str = "-") -> dict:
        return {
            "error": {
                "code": self.code,
                "message": self.message,
                "detail": self.detail,
                "request_id": request_id,
            }
        }


class ConfigError(KesslerError):
    code = "CONFIG_ERROR"
    http_status = 500


class DataSourceError(KesslerError):
    code = "DATA_SOURCE_ERROR"
    http_status = 502


class RateLimitError(KesslerError):
    code = "RATE_LIMITED"
    http_status = 503


class CdmParseError(KesslerError):
    code = "CDM_PARSE_ERROR"
    http_status = 422


class PropagationError(KesslerError):
    code = "PROPAGATION_ERROR"
    http_status = 500


class NotFoundError(KesslerError):
    code = "NOT_FOUND"
    http_status = 404


class ValidationFailure(KesslerError):
    code = "VALIDATION_ERROR"
    http_status = 422

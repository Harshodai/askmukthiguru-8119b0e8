"""Mukthi Guru — Service Gateways

Separated transport (HTTP) from domain (prompt assembly, classification, etc.).
"""

from services.gateways.sarvam_http import SarvamHTTPGateway

__all__ = ["SarvamHTTPGateway"]
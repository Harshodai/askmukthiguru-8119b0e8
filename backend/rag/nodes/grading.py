"""Mukthi Guru — Document Grading Node (CRAG).
Re-exports grade_documents from reranking module for clean modularity.
"""

from .reranking import grade_documents

__all__ = ["grade_documents"]

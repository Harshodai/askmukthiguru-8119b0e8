import uuid
from datetime import datetime
from sqlalchemy import Column, String, DateTime, JSON, Integer
from app.core.database import Base

class Feedback(Base):
    """
    Database model for user feedback on RAG-generated answers.
    Used for re-ranking optimization and evaluation dataset building.
    """
    __tablename__ = "feedback"
    
    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = Column(String, index=True, nullable=True)
    query = Column(String, nullable=False)
    answer = Column(String, nullable=False)
    rating = Column(Integer, nullable=False)  # 1 for thumbs up, -1 for thumbs down
    feedback_text = Column(String, nullable=True)
    
    # Store full context: retrieved doc IDs, scores, and intermediate results
    metadata_json = Column(JSON, nullable=True) 
    
    created_at = Column(DateTime, default=datetime.utcnow)

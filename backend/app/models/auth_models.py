from datetime import datetime
from typing import Optional, TYPE_CHECKING
from sqlalchemy import Integer, String, DateTime, ForeignKey, Boolean
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base

# Import for type checking only to avoid circular imports
if TYPE_CHECKING:
    from .user import User

class PasswordHistory(Base):
    """Stores password history to prevent password reuse."""
    __tablename__ = "password_history"
    
    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), nullable=False)
    hashed_password: Mapped[str] = mapped_column(String(100), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    
    # Relationships
    user: Mapped["User"] = relationship("User", back_populates="password_history", lazy="selectin")
    
    def __repr__(self) -> str:
        return f"<PasswordHistory(user_id={self.user_id}, created_at={self.created_at})>"


class PasswordResetToken(Base):
    """Stores password reset tokens with expiration."""
    __tablename__ = "password_reset_tokens"
    
    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), nullable=False)
    token: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)
    is_used: Mapped[bool] = mapped_column(Boolean, default=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    
    # Relationships
    user: Mapped["User"] = relationship("User", back_populates="password_reset_tokens", lazy="selectin")
    
    def is_valid(self) -> bool:
        """Check if the token is valid and not expired."""
        return not self.is_used and datetime.utcnow() < self.expires_at
    
    def __repr__(self) -> str:
        return f"<PasswordResetToken(user_id={self.user_id}, expires_at={self.expires_at})>"

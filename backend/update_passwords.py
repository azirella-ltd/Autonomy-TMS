#!/usr/bin/env python3
"""
Script to update all user passwords to 'Autonomy@2025'
"""
import asyncio
import sys
from pathlib import Path

# Add the backend directory to the Python path
sys.path.append(str(Path(__file__).parent.parent / 'backend'))

from app.core.config import settings
from app.db.session import async_session_factory
from app.models.user import User
from sqlalchemy import select, update
from sqlalchemy.future import select as async_select
from passlib.context import CryptContext

# Initialize password hasher
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

async def update_passwords():
    async with async_session_factory() as session:
        try:
            # Get all active users
            result = await session.execute(select(User).where(User.is_active == True))
            users = result.scalars().all()
            
            if not users:
                print("No active users found in the database.")
                return
                
            # Update each user's password
            updated_count = 0
            for user in users:
                user.hashed_password = pwd_context.hash("Autonomy@2025")
                session.add(user)
                updated_count += 1
                
            # Commit the changes
            await session.commit()
            print(f"Successfully updated passwords for {updated_count} users.")
            
            # Verify the updates
            print("\nUpdated users:")
            for user in users:
                print(f"- {user.email} (ID: {user.id})")
                
        except Exception as e:
            print(f"Error updating passwords: {e}")
            await session.rollback()
            raise
        finally:
            await session.close()

if __name__ == "__main__":
    import asyncio
    asyncio.run(update_passwords())

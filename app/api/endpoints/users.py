from fastapi import APIRouter, Depends, status, HTTPException
from sqlalchemy import delete
from sqlalchemy.ext.asyncio import AsyncSession

from app.api import deps
from app.core.security.password import get_password_hash
from app.models import User
from app.schemas.requests import UserUpdatePasswordRequest
from app.schemas.responses import UserResponse
from app.api import notion
import logging
import time
from datetime import datetime, timedelta
import json
# Set up logging
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger("uvicorn")

router = APIRouter()


# @router.get("/me", response_model=UserResponse, description="Get current user")
# async def read_current_user(
#     current_user: User = Depends(deps.get_current_user),
# ) -> User:
#     return current_user


# @router.delete(
#     "/me",
#     status_code=status.HTTP_204_NO_CONTENT,
#     description="Delete current user",
# )
# async def delete_current_user(
#     current_user: User = Depends(deps.get_current_user),
#     session: AsyncSession = Depends(deps.get_session),
# ) -> None:
#     await session.execute(delete(User).where(User.user_id == current_user.user_id))
#     await session.commit()


# @router.post(
#     "/reset-password",
#     status_code=status.HTTP_204_NO_CONTENT,
#     description="Update current user password",
# )
# async def reset_current_user_password(
#     user_update_password: UserUpdatePasswordRequest,
#     session: AsyncSession = Depends(deps.get_session),
#     current_user: User = Depends(deps.get_current_user),
# ) -> None:
#     current_user.hashed_password = get_password_hash(user_update_password.password)
#     session.add(current_user)
#     await session.commit()

@router.post("/upsert", description="Upsert Notion DB/Page into Pinecone")
async def upsert(request: dict):
    logger.info(f"Upsert function started")
    start_time = time.time()
    try:
        notion_id = request.get('notion_id')
        doc_type = request.get('doc_type')
        cleanup_mode = request.get('cleanup_mode')
        last_update_time = request.get('last_update_time')

        if last_update_time is None:
            last_update_time = (datetime.now() - timedelta(days=7)).isoformat()
        docs =[]
        if doc_type == "database":
            docs = await notion.load_documents_from_notion_db(notion_id)
        elif doc_type == "page":
            docs = await notion.load_documents_from_notion_page(notion_id)
        else:
            raise HTTPException(status_code=400,
                                detail="Invalid document type")

        split_docs = await notion.split_documents(docs)
        cost = await notion.calculate_pinecone_cost(split_docs)

        upsert_result = await notion.cleanup_and_upsert_documents(split_docs, cleanup_mode)

        total_time = time.time() - start_time
        return {
            "success": True,
            "total_vectors": len(split_docs),
            # "total_pinecone_cost": cost["total_pinecone_cost"],
            "total_embedding_cost": cost["total_embedding_cost"],
            "upsert_details": upsert_result,
            "cleanup_mode": cleanup_mode,
            "last_update_time": last_update_time,
            "total_process_time": total_time
        }

    except json.JSONDecodeError:
        raise HTTPException(status_code=400,
                            detail="Invalid JSON in request body")
    except Exception as error:
        logger.error(f"Error in upsert: {str(error)}")
        raise HTTPException(status_code=500, detail=str(error))
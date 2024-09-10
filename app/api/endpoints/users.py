from fastapi import APIRouter, status, HTTPException
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
from app.api.agents import IdeationFlow, ResearchFlow, ScriptingFlow
# Set up logging
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger("uvicorn")

router = APIRouter()

@router.post("/upsert", description="Upsert Notion DB/Page into Qdrant")
async def upsert(request: dict):
    logger.info(f"Upsert function started")
    start_time = time.time()
    try:
        notion_id = request.get('notion_id')
        doc_type = request.get('doc_type')
        cleanup_mode = request.get('cleanup_mode')
        last_update_time = request.get('last_update_time', "")

        response = await notion.process_notion_data(notion_id, doc_type, cleanup_mode)

        total_time = time.time() - start_time
        return {
            "success": True,
            "total_vectors": response["total_vectors"],
            "total_embedding_cost": response["Embedding_cost"],
            "upsert_details": response["Qdrant_result"],
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

@router.post("/execute_agent_teams", description="The team of agents performs a thorough research and returns high-quality, scientifically accurate scripts ready for teleprompter use")
async def agent_team(request: dict):
    logger.info(f"Research started")
    start_time = time.time()
    try:
        initial_input = request.get('initial_input')

        ideation = IdeationFlow(timeout=300, verbose=True)

        ideation_result = await ideation.run(input=initial_input)

        research = ResearchFlow(timeout=300, verbose=True)

        research_result = await research.run(input=initial_input, ideation=ideation_result)

        total_time = time.time() - start_time
        return {
            "success": True,
            "ideation_result": ideation_result,
            "research_result": research_result,
            "total_process_time": total_time
        }

    except json.JSONDecodeError:
        raise HTTPException(status_code=400,
                            detail="Invalid JSON in request body")
    except Exception as error:
        logger.error(f"Error in upsert: {str(error)}")
        raise HTTPException(status_code=500, detail=str(error))

@router.post("/generate_script")
async def generate_script(request: dict):
    logger.info(f"Research started")
    start_time = time.time()
    try:
        ideation_result = request.get('ideation_result')
        research_result = request.get('research_result')

        scripting = ScriptingFlow(timeout=300, verbose=True)

        response = await scripting.run(ideation=ideation_result, research=research_result)

        total_time = time.time() - start_time
        return {
            "success": True,
            "final_script": response,
            "total_process_time": total_time
        }

    except json.JSONDecodeError:
        raise HTTPException(status_code=400,
                            detail="Invalid JSON in request body")
    except Exception as error:
        logger.error(f"Error in upsert: {str(error)}")
        raise HTTPException(status_code=500, detail=str(error))
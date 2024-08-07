from pydantic import BaseModel, ConfigDict, EmailStr


class BaseResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class AccessTokenResponse(BaseResponse):
    token_type: str = "Bearer"
    access_token: str
    expires_at: int
    refresh_token: str
    refresh_token_expires_at: int


class UserResponse(BaseResponse):
    user_id: str
    email: EmailStr

# class NotionResponse():
#     success: bool,
#     total_vectors: int,
#     total_pinecone_cost: total_cost,
#             "total_embedding_cost": total_embedding_cost,
#             "upsert_details": upsert_result,
#             "cleanup_mode": cleanup_mode,
#             "last_update_time": last_update_time,
#             "total_process_time": total_time
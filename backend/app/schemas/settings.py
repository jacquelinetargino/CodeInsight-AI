from pydantic import BaseModel, Field


class GithubTokenStatus(BaseModel):
    connected: bool


class GithubTokenUpdateRequest(BaseModel):
    token: str = Field(min_length=10, max_length=255)

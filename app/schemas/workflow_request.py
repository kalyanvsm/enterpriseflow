from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

WorkflowRequestStatus = Literal["draft", "pending", "approved", "rejected"]


class WorkflowRequestCreate(BaseModel):
    title: str = Field(min_length=3, max_length=200)
    description: str = Field(min_length=1, max_length=10_000)


class WorkflowRequestResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    organization_id: UUID
    created_by_id: UUID
    title: str
    description: str
    status: WorkflowRequestStatus
    created_at: datetime
    updated_at: datetime

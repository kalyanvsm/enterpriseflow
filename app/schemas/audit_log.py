from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict

AuditAction = Literal["submitted", "approved", "rejected"]


class AuditLogResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    organization_id: UUID
    workflow_request_id: UUID
    actor_user_id: UUID
    action: AuditAction
    from_status: str
    to_status: str
    created_at: datetime

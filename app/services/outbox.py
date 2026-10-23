

from app.models.outbox_event import OutboxEvent
from app.models.workflow_request import WorkflowRequest


def record_outbox_event(
    workflow_request: WorkflowRequest,
    event_type: str,
) -> OutboxEvent:
    return OutboxEvent(
        organization_id=workflow_request.organization_id,
        workflow_request_id=workflow_request.id,
        event_type=event_type,
        payload={
            "request_id": str(workflow_request.id),
            "organization_id": str(workflow_request.organization_id),
            "title": workflow_request.title,
            "status": workflow_request.status,
        },
    )

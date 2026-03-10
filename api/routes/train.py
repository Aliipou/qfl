"""POST /train — trigger a federated learning round."""

from uuid import UUID

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, status

from api.dependencies import get_coordinator
from api.schemas import (
    ClientUpdate,
    ClientUpdateAck,
    FLRound,
    FLRoundCreate,
)
from core.federated.coordinator import FLCoordinator

router = APIRouter(prefix="/train", tags=["training"])


@router.post(
    "",
    response_model=FLRound,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Trigger a new FL round",
)
async def trigger_training(
    payload: FLRoundCreate,
    background_tasks: BackgroundTasks,
    coordinator: FLCoordinator = Depends(get_coordinator),
) -> FLRound:
    """
    Start a new federated learning round.

    The round runs asynchronously. Poll GET /status/{round_id} for progress.
    """
    fl_round = coordinator.create_round(payload)
    background_tasks.add_task(coordinator.run_round, fl_round.id)
    return fl_round


@router.post(
    "/{round_id}/update",
    response_model=ClientUpdateAck,
    summary="Submit a client weight update",
)
async def submit_client_update(
    round_id: UUID,
    update: ClientUpdate,
    coordinator: FLCoordinator = Depends(get_coordinator),
) -> ClientUpdateAck:
    """
    FL client submits local model weight update for a running round.
    Weights are validated and queued for aggregation.
    """
    if update.round_id != round_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="round_id in path and body must match",
        )
    ack = await coordinator.accept_client_update(update)
    return ack

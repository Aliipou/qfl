"""GET /status — FL round monitoring."""

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status

from api.dependencies import get_coordinator
from api.schemas import FLRound, RoundStatus
from core.federated.coordinator import FLCoordinator

router = APIRouter(prefix="/status", tags=["status"])


@router.get(
    "/{round_id}",
    response_model=FLRound,
    summary="Get FL round status",
)
async def get_round_status(
    round_id: UUID,
    coordinator: FLCoordinator = Depends(get_coordinator),
) -> FLRound:
    """Return current status and metrics for a specific FL round."""
    fl_round = coordinator.get_round(round_id)
    if fl_round is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Round {round_id} not found",
        )
    return fl_round


@router.get(
    "",
    response_model=list[FLRound],
    summary="List all FL rounds",
)
async def list_rounds(
    limit: int = 20,
    status_filter: RoundStatus | None = None,
    coordinator: FLCoordinator = Depends(get_coordinator),
) -> list[FLRound]:
    """List FL rounds, optionally filtered by status."""
    return coordinator.list_rounds(limit=limit, status_filter=status_filter)

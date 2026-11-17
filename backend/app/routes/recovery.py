from fastapi import APIRouter, Depends, HTTPException, status
from typing import Optional

from ..security.auth import get_current_user
from ..security.permissions import require_role, UserRole
from ..services.recovery import get_system_diagnostics, run_system_consistency_check

router = APIRouter(prefix="/recovery", tags=["Recovery & State Reconciliation"])

@router.get("/diagnostics")
async def recovery_diagnostics():
    """
    Diagnostic reporting for persistence, blockchain, and storage integrity.
    Publicly accessible; leaks zero infrastructure secrets or sensitive tokens.
    """
    return await get_system_diagnostics()

@router.get("/consistency-report")
async def consistency_report(
    current_user: dict = Depends(require_role([UserRole.ADMIN]))
):
    """
    Authoritative consistency audit report across physical files, MongoDB, and blockchain.
    Restricted to ADMIN role.
    Does NOT modify or delete authoritative records.
    """
    return await run_system_consistency_check()


@router.post("/custody/reconcile/{transaction_id}")
async def reconcile_custody_transaction_via_recovery(
    transaction_id: str,
    current_user: dict = Depends(require_role([UserRole.ADMIN, UserRole.INVESTIGATOR]))
):
    """
    Recovery endpoint for durable custody transaction reconciliation.
    Restricted to ADMIN and INVESTIGATOR roles.
    """
    from ..services.custody_transaction import reconcile_durable_transaction
    reconciled, tx, err_code = await reconcile_durable_transaction(transaction_id, allow_offline_fallback=False)
    if not reconciled:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Reconciliation failed with error: {err_code}. Transaction status: {tx.get('status')}."
        )
    return {"status": "success", "message": "Transaction reconciled successfully", "transaction": tx}

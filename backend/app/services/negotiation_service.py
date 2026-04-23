"""
Negotiation Service
Phase 7 Sprint 4 - Feature 4: Agent Negotiation

Enables scenario_users to negotiate with each other for:
- Order quantity adjustments
- Lead time modifications
- Inventory sharing/reallocation
- Price/cost adjustments

Includes AI-mediated proposal generation and impact simulation.
"""

from typing import Dict, List, Optional, Any
from datetime import datetime, timedelta
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession
import logging

logger = logging.getLogger(__name__)


class NegotiationService:
    """
    Service for inter-scenario_user negotiations with AI mediation.

    Features:
    - Create negotiation proposals
    - Accept/reject/counter offers
    - AI-mediated suggestion generation
    - Impact simulation (what-if analysis)
    - Negotiation history tracking
    """

    def __init__(self, db: AsyncSession):
        self.db = db
        self.default_expiry_hours = 24  # Proposals expire after 24 hours

    # =============================================================================
    # PROPOSAL CREATION
    # =============================================================================

    async def create_negotiation(
        self,
        scenario_id: int,
        initiator_id: int,
        target_id: int,
        negotiation_type: str,
        proposal: Dict[str, Any],
        message: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Create a new negotiation proposal.

        Negotiation Types:
        - `order_adjustment`: Request to modify order quantity
        - `lead_time`: Request to reduce/increase lead time
        - `inventory_share`: Request to share/reallocate inventory
        - `price_adjustment`: Request for cost modification

        Args:
            scenario_id: Scenario ID
            initiator_id: ScenarioUser initiating negotiation
            target_id: ScenarioUser receiving proposal
            negotiation_type: Type of negotiation
            proposal: Proposal details (JSON)
            message: Optional message to recipient

        Returns:
            {
                "negotiation_id": 123,
                "status": "pending",
                "expires_at": "2026-01-15T12:00:00",
                "proposal": {...},
                "impact_simulation": {...}
            }
        """
        try:
            # Validate negotiation type
            valid_types = ["order_adjustment", "lead_time", "inventory_share", "price_adjustment"]
            if negotiation_type not in valid_types:
                raise ValueError(f"Invalid negotiation type: {negotiation_type}")

            # Validate scenario_users exist and are in same scenario
            query = text("""
                SELECT COUNT(*) as count
                FROM scenario_users
                WHERE scenario_id = :scenario_id
                AND id IN (:initiator_id, :target_id)
            """)
            result = await self.db.execute(query, {
                "scenario_id": scenario_id,
                "initiator_id": initiator_id,
                "target_id": target_id
            })
            row = result.fetchone()
            if row.count != 2:
                raise ValueError("Both scenario_users must be in the same scenario")

            # Calculate expiry time
            expires_at = datetime.utcnow() + timedelta(hours=self.default_expiry_hours)

            # Simulate impact (if possible)
            impact_sim = await self._simulate_proposal_impact(
                scenario_id, initiator_id, target_id, negotiation_type, proposal
            )

            # Insert negotiation
            query = text("""
                INSERT INTO negotiations
                (scenario_id, initiator_id, target_id, negotiation_type, proposal, status, expires_at, created_at)
                VALUES (:scenario_id, :initiator_id, :target_id, :negotiation_type, :proposal, 'pending', :expires_at, NOW())
            """)
            result = await self.db.execute(query, {
                "scenario_id": scenario_id,
                "initiator_id": initiator_id,
                "target_id": target_id,
                "negotiation_type": negotiation_type,
                "proposal": str(proposal),  # JSON as string
                "expires_at": expires_at
            })
            await self.db.commit()

            negotiation_id = result.lastrowid

            # Add initial message if provided
            if message:
                await self._add_negotiation_message(
                    negotiation_id, initiator_id, message
                )

            return {
                "negotiation_id": negotiation_id,
                "status": "pending",
                "expires_at": expires_at.isoformat(),
                "proposal": proposal,
                "impact_simulation": impact_sim,
                "created_at": datetime.utcnow().isoformat()
            }

        except Exception as e:
            await self.db.rollback()
            logger.error(f"Failed to create negotiation: {e}", exc_info=True)
            raise

    async def _simulate_proposal_impact(
        self,
        scenario_id: int,
        initiator_id: int,
        target_id: int,
        negotiation_type: str,
        proposal: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Simulate the impact of accepting a proposal.

        Returns projected changes to:
        - Inventory levels
        - Backlog levels
        - Costs
        - Service levels
        """
        try:
            # Get current state for both scenario_users
            query = text("""
                SELECT
                    p.id,
                    p.role,
                    pr.inventory_after,
                    pr.backlog_after,
                    pr.total_cost,
                    pr.service_level
                FROM scenario_users p
                JOIN scenario_user_periods pr ON p.id = pr.scenario_user_id
                WHERE p.id IN (:initiator_id, :target_id)
                AND pr.round_number = (
                    SELECT MAX(round_number) FROM rounds WHERE scenario_id = :scenario_id
                )
            """)
            result = await self.db.execute(query, {
                "scenario_id": scenario_id,
                "initiator_id": initiator_id,
                "target_id": target_id
            })
            rows = result.fetchall()

            if len(rows) != 2:
                return {"error": "Insufficient data for simulation"}

            initiator_state = next((r for r in rows if r.id == initiator_id), None)
            target_state = next((r for r in rows if r.id == target_id), None)

            # Simulate based on negotiation type
            if negotiation_type == "order_adjustment":
                return self._simulate_order_adjustment(
                    initiator_state, target_state, proposal
                )
            elif negotiation_type == "inventory_share":
                return self._simulate_inventory_share(
                    initiator_state, target_state, proposal
                )
            elif negotiation_type == "lead_time":
                return self._simulate_lead_time_change(
                    initiator_state, target_state, proposal
                )
            elif negotiation_type == "price_adjustment":
                return self._simulate_price_adjustment(
                    initiator_state, target_state, proposal
                )
            else:
                return {"note": "Simulation not available for this type"}

        except Exception as e:
            logger.warning(f"Failed to simulate proposal impact: {e}")
            return {"error": "Simulation unavailable"}

    def _simulate_order_adjustment(
        self,
        initiator_state: Any,
        target_state: Any,
        proposal: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Simulate order quantity adjustment."""
        # Proposal format: {"quantity_change": +20}
        quantity_change = proposal.get("quantity_change", 0)

        # Simple simulation: assume inventory changes match order change
        initiator_inventory_impact = -quantity_change  # Initiator ships more/less
        target_inventory_impact = quantity_change  # Target receives more/less

        return {
            "initiator": {
                "inventory_change": initiator_inventory_impact,
                "projected_inventory": max(0, initiator_state.inventory_after + initiator_inventory_impact),
                "cost_impact": abs(initiator_inventory_impact) * 0.5,  # Holding cost
            },
            "target": {
                "inventory_change": target_inventory_impact,
                "projected_inventory": target_state.inventory_after + target_inventory_impact,
                "cost_impact": -abs(target_inventory_impact) * 0.3,  # Reduced backlog
            },
            "summary": f"Initiator ships {abs(quantity_change)} {'more' if quantity_change > 0 else 'less'} units"
        }

    def _simulate_inventory_share(
        self,
        initiator_state: Any,
        target_state: Any,
        proposal: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Simulate inventory sharing/reallocation."""
        # Proposal format: {"units": 30, "direction": "give"}
        units = proposal.get("units", 0)
        direction = proposal.get("direction", "give")  # "give" or "receive"

        if direction == "give":
            initiator_change = -units
            target_change = units
        else:
            initiator_change = units
            target_change = -units

        return {
            "initiator": {
                "inventory_change": initiator_change,
                "projected_inventory": max(0, initiator_state.inventory_after + initiator_change),
                "risk": "reduced flexibility" if initiator_change < 0 else "increased buffer"
            },
            "target": {
                "inventory_change": target_change,
                "projected_inventory": max(0, target_state.inventory_after + target_change),
                "benefit": "increased stock" if target_change > 0 else "reduced holding cost"
            },
            "summary": f"Transfer {units} units from {initiator_state.role} to {target_state.role}"
        }

    def _simulate_lead_time_change(
        self,
        initiator_state: Any,
        target_state: Any,
        proposal: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Simulate lead time modification."""
        # Proposal format: {"lead_time_change": -1, "compensation": 10}
        lead_time_change = proposal.get("lead_time_change", 0)
        compensation = proposal.get("compensation", 0)

        return {
            "initiator": {
                "lead_time_impact": f"{abs(lead_time_change)} rounds {'faster' if lead_time_change < 0 else 'slower'}",
                "cost_impact": -compensation if compensation > 0 else 0,
                "benefit": "faster delivery" if lead_time_change < 0 else "more planning time"
            },
            "target": {
                "lead_time_impact": f"Commit to {abs(lead_time_change)} round {'reduction' if lead_time_change < 0 else 'increase'}",
                "cost_impact": compensation if compensation > 0 else 0,
                "burden": "increased pressure" if lead_time_change < 0 else "more flexibility"
            },
            "summary": f"Lead time {'reduced' if lead_time_change < 0 else 'increased'} by {abs(lead_time_change)} rounds"
        }

    def _simulate_price_adjustment(
        self,
        initiator_state: Any,
        target_state: Any,
        proposal: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Simulate price/cost adjustment."""
        # Proposal format: {"price_change": -5, "volume_commitment": 100}
        price_change = proposal.get("price_change", 0)
        volume = proposal.get("volume_commitment", 0)

        total_impact = price_change * volume

        return {
            "initiator": {
                "price_change": price_change,
                "total_savings": -total_impact if price_change < 0 else 0,
                "commitment": f"Order {volume} units minimum"
            },
            "target": {
                "price_change": price_change,
                "revenue_impact": total_impact,
                "guarantee": f"Guaranteed {volume} unit order"
            },
            "summary": f"Price {'reduced' if price_change < 0 else 'increased'} by {abs(price_change)} per unit for {volume} units"
        }

    # =============================================================================
    # PROPOSAL RESPONSE
    # =============================================================================

    async def respond_to_negotiation(
        self,
        negotiation_id: int,
        responder_id: int,
        action: str,
        counter_proposal: Optional[Dict[str, Any]] = None,
        message: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Respond to a negotiation proposal.

        Actions:
        - `accept`: Accept the proposal
        - `reject`: Reject the proposal
        - `counter`: Make a counter-offer

        Args:
            negotiation_id: Negotiation ID
            responder_id: ScenarioUser responding
            action: Response action
            counter_proposal: New proposal if counter-offering
            message: Optional message

        Returns:
            {
                "negotiation_id": 123,
                "status": "accepted" | "rejected" | "countered",
                "counter_proposal": {...} | null,
                "message": "..."
            }
        """
        try:
            # Validate action
            valid_actions = ["accept", "reject", "counter"]
            if action not in valid_actions:
                raise ValueError(f"Invalid action: {action}")

            # Get negotiation
            query = text("""
                SELECT
                    id, scenario_id, initiator_id, target_id, negotiation_type,
                    proposal, status, expires_at
                FROM negotiations
                WHERE id = :negotiation_id
            """)
            result = await self.db.execute(query, {"negotiation_id": negotiation_id})
            row = result.fetchone()

            if not row:
                raise ValueError("Negotiation not found")

            # Verify responder is the target
            if row.target_id != responder_id:
                raise ValueError("Only the target scenario_user can respond")

            # Check if still pending
            if row.status != "pending":
                raise ValueError(f"Negotiation is already {row.status}")

            # Check if expired
            if row.expires_at and datetime.utcnow() > row.expires_at:
                await self._expire_negotiation(negotiation_id)
                raise ValueError("Negotiation has expired")

            # Handle response
            if action == "accept":
                new_status = "accepted"
                await self._execute_negotiation(negotiation_id, row)
            elif action == "reject":
                new_status = "rejected"
            else:  # counter
                new_status = "countered"
                if not counter_proposal:
                    raise ValueError("Counter proposal required for counter action")

            # Update negotiation status
            update_query = text("""
                UPDATE negotiations
                SET status = :status,
                    counter_proposal = :counter_proposal,
                    responded_at = NOW()
                WHERE id = :negotiation_id
            """)
            await self.db.execute(update_query, {
                "negotiation_id": negotiation_id,
                "status": new_status,
                "counter_proposal": str(counter_proposal) if counter_proposal else None
            })
            await self.db.commit()

            # Add message if provided
            if message:
                await self._add_negotiation_message(
                    negotiation_id, responder_id, message
                )

            return {
                "negotiation_id": negotiation_id,
                "status": new_status,
                "counter_proposal": counter_proposal,
                "message": message,
                "responded_at": datetime.utcnow().isoformat()
            }

        except Exception as e:
            await self.db.rollback()
            logger.error(f"Failed to respond to negotiation: {e}", exc_info=True)
            raise

    async def _execute_negotiation(self, negotiation_id: int, negotiation: Any) -> None:
        """
        Execute an accepted negotiation by modifying scenario state.

        Supported negotiation types:
        - order_adjustment: Modify next-period order quantity for the target
        - inventory_share: Transfer inventory from initiator to target
        - lead_time: Record agreed lead-time change (metadata only)
        - price_adjustment: Record agreed unit-cost change (metadata only)
        """
        neg_type = negotiation.negotiation_type
        proposal = negotiation.proposal
        if isinstance(proposal, str):
            import ast
            try:
                proposal = ast.literal_eval(proposal)
            except Exception:
                proposal = {}

        logger.info(f"Executing negotiation {negotiation_id}: {neg_type}")

        try:
            if neg_type == "inventory_share":
                transfer_qty = proposal.get("quantity", 0)
                if transfer_qty > 0:
                    # Deduct from initiator inventory
                    await self.db.execute(text("""
                        UPDATE scenario_user_periods SET inventory = GREATEST(0, inventory - :qty)
                        WHERE scenario_user_id = :pid
                        AND round_id = (
                            SELECT id FROM scenario_rounds WHERE scenario_id = :gid
                            ORDER BY round_number DESC LIMIT 1
                        )
                    """), {
                        "qty": transfer_qty,
                        "pid": negotiation.initiator_id,
                        "gid": negotiation.scenario_id,
                    })
                    # Add to target inventory
                    await self.db.execute(text("""
                        UPDATE scenario_user_periods SET inventory = inventory + :qty
                        WHERE scenario_user_id = :pid
                        AND round_id = (
                            SELECT id FROM scenario_rounds WHERE scenario_id = :gid
                            ORDER BY round_number DESC LIMIT 1
                        )
                    """), {
                        "qty": transfer_qty,
                        "pid": negotiation.target_id,
                        "gid": negotiation.scenario_id,
                    })
                    await self.db.commit()
                    logger.info(
                        f"Inventory share executed: {transfer_qty} units from "
                        f"scenario_user {negotiation.initiator_id} to {negotiation.target_id}"
                    )

            elif neg_type == "order_adjustment":
                new_qty = proposal.get("new_order_quantity", proposal.get("quantity"))
                if new_qty is not None:
                    await self.db.execute(text("""
                        UPDATE scenario_user_periods SET order_upstream = :qty
                        WHERE scenario_user_id = :pid
                        AND round_id = (
                            SELECT id FROM scenario_rounds WHERE scenario_id = :gid
                            ORDER BY round_number DESC LIMIT 1
                        )
                    """), {
                        "qty": int(new_qty),
                        "pid": negotiation.target_id,
                        "gid": negotiation.scenario_id,
                    })
                    await self.db.commit()
                    logger.info(
                        f"Order adjustment executed: scenario_user {negotiation.target_id} "
                        f"order set to {new_qty}"
                    )

            elif neg_type in ("lead_time", "price_adjustment"):
                # Informational agreements — proposal details stored on negotiation record
                logger.info(
                    f"Negotiation {neg_type} recorded for negotiation {negotiation_id}: "
                    f"{proposal}"
                )

        except Exception as e:
            logger.error(f"Failed to execute negotiation {negotiation_id}: {e}", exc_info=True)
            await self.db.rollback()

    async def _expire_negotiation(self, negotiation_id: int) -> None:
        """Mark a negotiation as expired."""
        query = text("""
            UPDATE negotiations
            SET status = 'expired'
            WHERE id = :negotiation_id AND status = 'pending'
        """)
        await self.db.execute(query, {"negotiation_id": negotiation_id})
        await self.db.commit()

    # =============================================================================
    # NEGOTIATION HISTORY
    # =============================================================================

    async def get_scenario_user_negotiations(
        self,
        scenario_id: int,
        scenario_user_id: int,
        status_filter: Optional[str] = None,
        limit: int = 20
    ) -> List[Dict[str, Any]]:
        """
        Get negotiations for a scenario_user (as initiator or target).

        Args:
            scenario_id: Scenario ID
            scenario_user_id: ScenarioUser ID
            status_filter: Filter by status (pending, accepted, rejected, countered, expired)
            limit: Maximum negotiations to return

        Returns:
            List of negotiations with details
        """
        try:
            where_clause = "WHERE n.scenario_id = :scenario_id AND (n.initiator_id = :scenario_user_id OR n.target_id = :scenario_user_id)"
            if status_filter:
                where_clause += " AND n.status = :status_filter"

            query = text(f"""
                SELECT
                    n.id,
                    n.negotiation_type,
                    n.proposal,
                    n.counter_proposal,
                    n.status,
                    n.expires_at,
                    n.created_at,
                    n.responded_at,
                    initiator.role as initiator_role,
                    target.role as target_role,
                    n.initiator_id,
                    n.target_id
                FROM negotiations n
                JOIN scenario_users initiator ON n.initiator_id = initiator.id
                JOIN scenario_users target ON n.target_id = target.id
                {where_clause}
                ORDER BY n.created_at DESC
                LIMIT :limit
            """)

            params = {"scenario_id": scenario_id, "scenario_user_id": scenario_user_id, "limit": limit}
            if status_filter:
                params["status_filter"] = status_filter

            result = await self.db.execute(query, params)
            rows = result.fetchall()

            negotiations = []
            for row in rows:
                negotiations.append({
                    "id": row.id,
                    "negotiation_type": row.negotiation_type,
                    "proposal": row.proposal,
                    "counter_proposal": row.counter_proposal,
                    "status": row.status,
                    "expires_at": row.expires_at.isoformat() if row.expires_at else None,
                    "created_at": row.created_at.isoformat() if row.created_at else None,
                    "responded_at": row.responded_at.isoformat() if row.responded_at else None,
                    "initiator_role": row.initiator_role,
                    "target_role": row.target_role,
                    "is_initiator": row.initiator_id == scenario_user_id,
                    "is_target": row.target_id == scenario_user_id
                })

            return negotiations

        except Exception as e:
            logger.error(f"Failed to get scenario_user negotiations: {e}", exc_info=True)
            raise

    async def get_negotiation_messages(
        self,
        negotiation_id: int
    ) -> List[Dict[str, Any]]:
        """
        Get messages in a negotiation conversation.

        Returns:
            List of messages with sender info
        """
        try:
            query = text("""
                SELECT
                    nm.id,
                    nm.sender_id,
                    nm.message,
                    nm.created_at,
                    p.role as sender_role
                FROM negotiation_messages nm
                JOIN scenario_users p ON nm.sender_id = p.id
                WHERE nm.negotiation_id = :negotiation_id
                ORDER BY nm.created_at ASC
            """)
            result = await self.db.execute(query, {"negotiation_id": negotiation_id})
            rows = result.fetchall()

            messages = []
            for row in rows:
                messages.append({
                    "id": row.id,
                    "sender_id": row.sender_id,
                    "sender_role": row.sender_role,
                    "message": row.message,
                    "created_at": row.created_at.isoformat() if row.created_at else None
                })

            return messages

        except Exception as e:
            logger.error(f"Failed to get negotiation messages: {e}", exc_info=True)
            raise

    async def _add_negotiation_message(
        self,
        negotiation_id: int,
        sender_id: int,
        message: str
    ) -> None:
        """Add a message to a negotiation."""
        try:
            query = text("""
                INSERT INTO negotiation_messages
                (negotiation_id, sender_id, message, created_at)
                VALUES (:negotiation_id, :sender_id, :message, NOW())
            """)
            await self.db.execute(query, {
                "negotiation_id": negotiation_id,
                "sender_id": sender_id,
                "message": message
            })
            await self.db.commit()
        except Exception as e:
            logger.error(f"Failed to add negotiation message: {e}")
            raise

    # =============================================================================
    # AI-MEDIATED SUGGESTIONS
    # =============================================================================

    async def generate_negotiation_suggestion(
        self,
        scenario_id: int,
        scenario_user_id: int,
        target_scenario_user_id: int
    ) -> Dict[str, Any]:
        """
        Generate AI-mediated negotiation suggestion.

        Analyzes current scenario state and suggests mutually beneficial proposals.

        Args:
            scenario_id: Scenario ID
            scenario_user_id: ScenarioUser requesting suggestion
            target_scenario_user_id: Potential negotiation partner

        Returns:
            {
                "suggested_type": "inventory_share",
                "proposal": {...},
                "rationale": "...",
                "confidence": 0.75,
                "expected_benefit": {...}
            }
        """
        try:
            # Get current state for both scenario_users
            query = text("""
                SELECT
                    p.id,
                    p.role,
                    pr.inventory_after,
                    pr.backlog_after,
                    pr.order_placed,
                    pr.total_cost,
                    pr.service_level
                FROM scenario_users p
                JOIN scenario_user_periods pr ON p.id = pr.scenario_user_id
                WHERE p.id IN (:scenario_user_id, :target_scenario_user_id)
                AND pr.round_number = (
                    SELECT MAX(round_number) FROM rounds WHERE scenario_id = :scenario_id
                )
            """)
            result = await self.db.execute(query, {
                "scenario_id": scenario_id,
                "scenario_user_id": scenario_user_id,
                "target_scenario_user_id": target_scenario_user_id
            })
            rows = result.fetchall()

            if len(rows) != 2:
                return {"error": "Insufficient data for suggestion"}

            scenario_user_state = next((r for r in rows if r.id == scenario_user_id), None)
            target_state = next((r for r in rows if r.id == target_scenario_user_id), None)

            # Analyze states and suggest negotiation
            suggestion = self._analyze_and_suggest(scenario_user_state, target_state)

            return suggestion

        except Exception as e:
            logger.error(f"Failed to generate negotiation suggestion: {e}", exc_info=True)
            return {"error": "Could not generate suggestion"}

    def _analyze_and_suggest(
        self,
        scenario_user_state: Any,
        target_state: Any
    ) -> Dict[str, Any]:
        """Analyze states and generate negotiation suggestion."""
        # Simple heuristic-based suggestions

        # Scenario 1: ScenarioUser has excess inventory, target has backlog
        if scenario_user_state.inventory_after > 50 and target_state.backlog_after > 20:
            return {
                "suggested_type": "inventory_share",
                "proposal": {
                    "units": min(30, scenario_user_state.inventory_after - 40),
                    "direction": "give"
                },
                "rationale": f"You have excess inventory ({scenario_user_state.inventory_after} units) while {target_state.role} has high backlog ({target_state.backlog_after} units). Sharing inventory can reduce overall costs.",
                "confidence": 0.80,
                "expected_benefit": {
                    "cost_reduction": 15,
                    "service_improvement": 0.10,
                    "goodwill": "high"
                }
            }

        # Scenario 2: Target has excess, scenario_user has backlog
        if target_state.inventory_after > 50 and scenario_user_state.backlog_after > 20:
            return {
                "suggested_type": "inventory_share",
                "proposal": {
                    "units": min(30, target_state.inventory_after - 40),
                    "direction": "receive"
                },
                "rationale": f"{target_state.role} has excess inventory while you have backlog. Request inventory sharing to improve service level.",
                "confidence": 0.75,
                "expected_benefit": {
                    "backlog_reduction": min(30, scenario_user_state.backlog_after),
                    "service_improvement": 0.15,
                    "cost_savings": 12
                }
            }

        # Scenario 3: Both have high costs - suggest order coordination
        if scenario_user_state.total_cost > 60 and target_state.total_cost > 60:
            return {
                "suggested_type": "order_adjustment",
                "proposal": {
                    "quantity_change": 10,
                    "commitment_rounds": 3
                },
                "rationale": "Both scenario_users have high costs. Coordinating orders can reduce bullwhip effect and stabilize supply chain.",
                "confidence": 0.65,
                "expected_benefit": {
                    "cost_reduction": 8,
                    "order_stability": "improved",
                    "bullwhip_reduction": 0.20
                }
            }

        # Default: No strong suggestion
        return {
            "suggested_type": None,
            "rationale": "No clear mutual benefit identified in current state. Consider proposing based on future projections.",
            "confidence": 0.30,
            "note": "You can still create manual proposals"
        }


# =============================================================================
# SERVICE FACTORY
# =============================================================================

def get_negotiation_service(db: AsyncSession) -> NegotiationService:
    """Get or create negotiation service instance."""
    return NegotiationService(db)

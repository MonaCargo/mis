"""
services/awb_history_service.py

All async SQLAlchemy queries for the AWB history feature.

Design decisions:
  - One master query fetches the AWB row.
  - Each sub-entity (skids, sequences, locations, base drops, ULD loads, flights)
    is fetched with a SINGLE targeted query using joinedload / selectinload.
    This avoids N+1 and keeps each query fast with the indexes already on the tables.
  - We do NOT do one giant join — that inflates rows multiplicatively and
    is harder to maintain. Separate small async queries are cleaner here.
  - All assembly into response schemas happens in Python after the queries,
    keeping SQL simple and testable.
"""

from __future__ import annotations

from collections import defaultdict
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased, selectinload, joinedload

from app.db.models.exportOperation.car_message import (
    ExportCarMessageAwbMaster,
    ExportAwbSkidMapping,
    ExportAwbSkidItemSequence,
    ExportSkidLocationMapping,
    ExportSkidBaseMapping,
    ExportFlightBookingHeader,
    ExportFlightBookingDetail,
    ExportUldAssignment,
    ExportUldAssignmentDetail,
    ExportSequenceItemUldLoading,
)

# Import your master tables (adjust paths to your project structure)
# from app.models.masters import ExportSkidMaster, ExportLocationsMaster, ExportBaseMaster, ExportUldMaster

from app.db.models.exportOperation.export_uld_master import ExportUldMaster
from app.db.models.user import User
from app.schemas.exportOperation.car_message_awb_history import (
    AwbHistoryResponse,
    AwbInfo,
    SkidDetail,
    SkidHistoryTimeline,
    SequenceItem,
    LocationStep,
    BaseDropStep,
    UldStep,
    UldLoadedItem,
    FlightBookingDetail,
    UldDetail,
    AwbListItem,
)


class AwbNotFoundError(Exception):
    pass


class AwbHistoryService:

    def __init__(self, db: AsyncSession):
        self.db = db

    # ──────────────────────────────────────────────
    # PUBLIC: main history assembler
    # ──────────────────────────────────────────────

    async def get_awb_history(self, awb_no: str) -> AwbHistoryResponse:
        """
        Full AWB history:
          1. Fetch AWB master
          2. Fetch all skid mappings + sequences + locations + base drops + ULD loads
          3. Fetch all flight bookings + ULDs + loaded items for this AWB
          4. Assemble into AwbHistoryResponse
        """
        awb = await self._fetch_awb(awb_no)

        skid_details = await self._build_skid_details(awb.id)
        flight_details = await self._build_flight_details(awb.id)

        total_booked_pcs = sum(f.booked_pcs for f in flight_details)

        return AwbHistoryResponse(
            awb=AwbInfo.model_validate(awb),
            skids=skid_details,
            flights=flight_details,
            total_skids=len(skid_details),
            total_flights=len(flight_details),
            total_booked_pcs=total_booked_pcs,
        )

    async def get_awb_by_id(self, awb_id: int) -> AwbHistoryResponse:
        awb = await self._fetch_awb_by_id(awb_id)
        return await self.get_awb_history(awb.awb_no)

    # ──────────────────────────────────────────────
    # AWB master fetch
    # ──────────────────────────────────────────────

    async def _fetch_awb(self, awb_no: str) -> ExportCarMessageAwbMaster:
        # Uses idx_awb_car_msg index on awb_no
        result = await self.db.execute(
            select(ExportCarMessageAwbMaster)
            .where(ExportCarMessageAwbMaster.awb_no == awb_no)
        )
        awb = result.scalar_one_or_none()
        if not awb:
            raise AwbNotFoundError(f"AWB '{awb_no}' not found")
        return awb

    async def _fetch_awb_by_id(self, awb_id: int) -> ExportCarMessageAwbMaster:
        result = await self.db.execute(
            select(ExportCarMessageAwbMaster)
            .where(ExportCarMessageAwbMaster.id == awb_id)
        )
        awb = result.scalar_one_or_none()
        if not awb:
            raise AwbNotFoundError(f"AWB id={awb_id} not found")
        return awb

    # ──────────────────────────────────────────────
    # SKID SECTION
    # ──────────────────────────────────────────────

    async def _build_skid_details(self, awb_master_id: int) -> list[SkidDetail]:
        """
        Fetch all skid mappings for this AWB, then in parallel fetch
        sequences, locations, base drops, and ULD loads per mapping.
        """
        mappings = await self._fetch_skid_mappings(awb_master_id)
        if not mappings:
            return []

        mapping_ids = [m.id for m in mappings]
        skid_ids = [m.skid_id for m in mappings if m.skid_id]

        # Fetch all related data in 4 queries (not N queries)
        sequences_by_mapping = await self._fetch_sequences_grouped(awb_master_id, mapping_ids)
        locations_by_skid = await self._fetch_locations_grouped(awb_master_id, skid_ids)
        base_drops_by_mapping = await self._fetch_base_drops_grouped(awb_master_id, mapping_ids)
        uld_loads_by_mapping = await self._fetch_uld_loads_grouped(awb_master_id, mapping_ids)

        details: list[SkidDetail] = []
        for m in mappings:
            seqs = sequences_by_mapping.get(m.id, [])
            locs = locations_by_skid.get(m.skid_id, []) if m.skid_id else []
            drops = base_drops_by_mapping.get(m.id, [])
            uld_steps = uld_loads_by_mapping.get(m.id, [])

            total_cycles = max((d.cycle_no for d in drops), default=0)

            history = SkidHistoryTimeline(
                mapped_at=m.mapped_at,
                mapped_by=m.mapped_by,
                mapped_by_name=getattr(m, "mapped_by_name", None),
                is_virtual=m.is_virtual,
                virtual_skid_no=m.virtual_skid_no,
                is_skid_used_complete=m.is_skid_used_complete,
                total_cycles=total_cycles,
                # locations=[LocationStep.model_validate(l) for l in locs],
                locations=[
    LocationStep(
        id=l.id,
        location_id=l.location_id,
        location_name=l.location.loc if l.location else None,
        assigned_at=l.assigned_at,
        assigned_by=l.assigned_by,
        is_current=l.is_current,
        is_relocation=l.is_relocation,
        picked_at=l.picked_at,
        picked_by=l.picked_by,
              assigned_by_name=getattr(l, "assigned_by_name", None),
               picked_by_name=getattr(l, "picked_by_name", None),
                event_type=(
        "RELOCATED_TO_LOCATION"
        if l.is_relocation
        else "PLACED_AT_LOCATION"
    ),
    )
    for l in locs
],
                # base_drops=[BaseDropStep.model_validate(d) for d in drops],
                base_drops=[
    BaseDropStep(
        id=d.id,
        base_id=d.base_id,
        base_name=getattr(d.base, "base_name", None),
        cycle_no=d.cycle_no,
        dropped_at=d.dropped_at,
        dropped_by=d.dropped_by,
        dropped_by_name=getattr(d, "dropped_by_name", None),
    )
    for d in drops
],
                uld_loads=uld_steps,
            )

            details.append(SkidDetail(
                mapping_id=m.id,
                skid_id=m.skid_id,
                skid_no=getattr(m.skid, "skid_no", None) if m.skid_id else None,
                virtual_skid_no=m.virtual_skid_no,
                is_virtual=m.is_virtual,
                is_skid_used_complete=m.is_skid_used_complete,
                sequences=[SequenceItem.model_validate(s) for s in seqs],
                history=history,
            ))

        return details

    async def _fetch_skid_mappings(
        self, awb_master_id: int
    ) -> list[ExportAwbSkidMapping]:
        # Uses ForeignKey index on awb_master_id
    #     result = await self.db.execute(
    #         select(ExportAwbSkidMapping)
    #           .options(
    #     joinedload(ExportAwbSkidMapping.skid)
    # )
    #         .where(ExportAwbSkidMapping.awb_master_id == awb_master_id)
    #         .order_by(ExportAwbSkidMapping.id)
    #     )
        result = await self.db.execute(
        select(
            ExportAwbSkidMapping,
            User.name.label("mapped_by_name"),
        )
        .options(
            joinedload(ExportAwbSkidMapping.skid)
        )
        .outerjoin(
            User,
            User.emp_id == ExportAwbSkidMapping.mapped_by
        )
        .where(
            ExportAwbSkidMapping.awb_master_id == awb_master_id
        )
        .order_by(
            ExportAwbSkidMapping.id
        )
    )
        rows = result.all()

        mappings = []
        for row in rows:
            mapping = row[0]
            mapping.mapped_by_name = row[1]
            mappings.append(mapping)

        return mappings

    async def _fetch_sequences_grouped(
        self,
        awb_master_id: int,
        mapping_ids: list[int],
    ) -> dict[int, list[ExportAwbSkidItemSequence]]:
        """
        Returns {mapping_id: [sequence, ...]}
        Uses idx_awb_sequence on awb_master_id.
        """
        result = await self.db.execute(
            select(ExportAwbSkidItemSequence,  User.name.label("scanned_by_name"),)
              .outerjoin(
        User,
        User.emp_id == ExportAwbSkidItemSequence.scanned_by
    )
            .where(
                ExportAwbSkidItemSequence.awb_master_id == awb_master_id,
                ExportAwbSkidItemSequence.mapping_id.in_(mapping_ids),
            )
            .order_by(ExportAwbSkidItemSequence.sequence_date_time)
        )
        rows = result.all()

        grouped: dict[int, list] = defaultdict(list)
        for r in rows:
            seq = r[0]
            scanned_by_name = r[1]

            grouped[seq.mapping_id].append({
            "id": seq.id,
            "sequence_no": seq.sequence_no,
            "sequence_date_time": seq.sequence_date_time,
            "scanned_by": seq.scanned_by,
            "scanned_by_name": scanned_by_name,
            "scan_by_device": seq.scan_by_device,
        })
        return grouped

    async def _fetch_locations_grouped(
        self,
        awb_master_id: int,
        skid_ids: list[int],
    ) -> dict[int, list[ExportSkidLocationMapping]]:
        """
        Returns {skid_id: [location_step, ...]} ordered by assigned_at.
        Uses idx_skid_loc_awb_date composite index.
        """
        if not skid_ids:
            return {}

    #     result = await self.db.execute(
    #         select(ExportSkidLocationMapping)
    #            .options(
    #     selectinload(ExportSkidLocationMapping.location)
    # )
    #         .where(
    #             ExportSkidLocationMapping.awb_master_id == awb_master_id,
    #             ExportSkidLocationMapping.skid_id.in_(skid_ids),
    #         )
    #         .order_by(
    #             ExportSkidLocationMapping.skid_id,
    #             ExportSkidLocationMapping.assigned_at,
    #         )
    #     )

        

        AssignedUser = aliased(User)
        PickedUser = aliased(User)

        result = await self.db.execute(
            select(
                ExportSkidLocationMapping,
                AssignedUser.name.label("assigned_by_name"),
                PickedUser.name.label("picked_by_name"),
            )
            .options(
                selectinload(ExportSkidLocationMapping.location)
            )
            .outerjoin(
                AssignedUser,
                AssignedUser.emp_id == ExportSkidLocationMapping.assigned_by
            )
            .outerjoin(
                PickedUser,
                PickedUser.emp_id == ExportSkidLocationMapping.picked_by
            )
            .where(
                ExportSkidLocationMapping.awb_master_id == awb_master_id,
                ExportSkidLocationMapping.skid_id.in_(skid_ids),
            )
            .order_by(
                ExportSkidLocationMapping.skid_id,
                ExportSkidLocationMapping.assigned_at,
            )
        )

        # rows = list(result.scalars().all())

        # grouped: dict[int, list] = defaultdict(list)
        # for r in rows:
        #     grouped[r.skid_id].append(r)
        # return grouped

        rows = result.all()

        grouped = defaultdict(list)

        for row in rows:
            loc = row[0]
            loc.assigned_by_name = row[1]
            loc.picked_by_name = row[2]

            grouped[loc.skid_id].append(loc)

        return grouped

    async def _fetch_base_drops_grouped(
        self,
        awb_master_id: int,
        mapping_ids: list[int],
    ) -> dict[int, list[ExportSkidBaseMapping]]:
        """
        Returns {mapping_id: [base_drop, ...]} ordered by cycle_no.
        Uses idx_skid_base_awb and idx_skid_base_mapping_id indexes.
        """
#         result = await self.db.execute(
#             # select(ExportSkidBaseMapping)
#             select(ExportSkidBaseMapping)
# .options(
#     joinedload(ExportSkidBaseMapping.base)
# )
#             .where(
#                 ExportSkidBaseMapping.awb_master_id == awb_master_id,
#                 ExportSkidBaseMapping.mapping_id.in_(mapping_ids),
#             )
#             .order_by(
#                 ExportSkidBaseMapping.mapping_id,
#                 ExportSkidBaseMapping.cycle_no,
#             )
#         )
        result = await self.db.execute(
    select(
        ExportSkidBaseMapping,
        User.name.label("dropped_by_name"),
    )
    .options(
        joinedload(ExportSkidBaseMapping.base)
    )
    .outerjoin(
        User,
        User.emp_id == ExportSkidBaseMapping.dropped_by
    )
    .where(
        ExportSkidBaseMapping.awb_master_id == awb_master_id,
        ExportSkidBaseMapping.mapping_id.in_(mapping_ids),
    )
    .order_by(
        ExportSkidBaseMapping.mapping_id,
        ExportSkidBaseMapping.cycle_no,
    )
)
        # rows = list(result.scalars().all())

        # grouped: dict[int, list] = defaultdict(list)
        # for r in rows:
        #     grouped[r.mapping_id].append(r)
        # return grouped

        rows = result.all()

        grouped = defaultdict(list)

        for row in rows:
            drop = row[0]
            drop.dropped_by_name = row[1]

            grouped[drop.mapping_id].append(drop)

        return grouped

    async def _fetch_uld_loads_grouped(
        self,
        awb_master_id: int,
        mapping_ids: list[int],
    ) -> dict[int, list[UldStep]]:
        """
        Returns {mapping_id: [UldStep, ...]}

        Joins:
          export_item_uld_loading
            → export_uld_assignment_detail  (for ULD id, is_closed)
            → export_uld_master             (for uld_no, type)
            → export_flight_booking_header  (for flight_no, flight_date)
            → export_awb_skid_item_sequence (for sequence_no, mapping_id)

        Uses idx_item_uld_sequence and idx_item_uld_flight indexes.
        """
        # We need mapping_id from the sequence join.
        # Build the query with explicit joins.
        stmt = (
            select(
                ExportSequenceItemUldLoading,
                ExportAwbSkidItemSequence.sequence_no,
                ExportAwbSkidItemSequence.mapping_id.label("seq_mapping_id"),
                ExportUldAssignmentDetail.uld_id,
                ExportUldAssignmentDetail.is_closed,
                ExportUldAssignmentDetail.closed_by,
                ExportUldAssignmentDetail.closed_at,
                ExportFlightBookingHeader.flight_no,
                ExportFlightBookingHeader.flight_date,
            )
            .join(
                ExportAwbSkidItemSequence,
                ExportSequenceItemUldLoading.sequence_id == ExportAwbSkidItemSequence.id,
            )
            .join(
                ExportUldAssignmentDetail,
                ExportSequenceItemUldLoading.uld_assignment_detail_id == ExportUldAssignmentDetail.id,
            )
            .join(
                ExportFlightBookingHeader,
                ExportSequenceItemUldLoading.flight_header_id == ExportFlightBookingHeader.id,
            )
            .where(
                ExportSequenceItemUldLoading.awb_master_id == awb_master_id,
                ExportAwbSkidItemSequence.mapping_id.in_(mapping_ids),
            )
            .order_by(
                ExportAwbSkidItemSequence.mapping_id,
                ExportSequenceItemUldLoading.uld_assignment_detail_id,
                ExportSequenceItemUldLoading.loaded_at,
            )
        )

        result = await self.db.execute(stmt)
        rows = result.all()

        # Group: mapping_id → uld_assignment_detail_id → UldStep
        # We build UldStep objects with their loaded_items lists.
        mapping_uld_map: dict[int, dict[int, UldStep]] = defaultdict(dict)

        for row in rows:
            load_rec = row[0]           # ExportSequenceItemUldLoading
            seq_no = row[1]
            mapping_id = row[2]
            uld_id = row[3]
            is_closed = row[4]
            closed_by = row[5]
            closed_at = row[6]
            flight_no = row[7]
            flight_date = row[8]

            detail_id = load_rec.uld_assignment_detail_id

            if detail_id not in mapping_uld_map[mapping_id]:
                mapping_uld_map[mapping_id][detail_id] = UldStep(
                    uld_assignment_detail_id=detail_id,
                    uld_id=uld_id,
                    uld_no=None,          # populate from ExportUldMaster if needed
                    uld_type=None,
                    is_closed=is_closed,
                    closed_by=closed_by,
                    closed_at=closed_at,
                    flight_no=flight_no,
                    flight_date=flight_date,
                    loaded_items=[],
                )

            mapping_uld_map[mapping_id][detail_id].loaded_items.append(
                UldLoadedItem(
                    id=load_rec.id,
                    sequence_id=load_rec.sequence_id,
                    sequence_no=seq_no,
                    loaded_by=load_rec.loaded_by,
                    loaded_at=load_rec.loaded_at,
                )
            )

        return {
            mid: list(uld_dict.values())
            for mid, uld_dict in mapping_uld_map.items()
        }

    # ──────────────────────────────────────────────
    # FLIGHT SECTION
    # ──────────────────────────────────────────────

    async def _build_flight_details(
        self, awb_master_id: int
    ) -> list[FlightBookingDetail]:
        """
        Fetch all flight bookings for this AWB, then for each active flight
        find the ULD assignment and which items of this AWB were loaded.
        """
        booking_rows = await self._fetch_flight_bookings(awb_master_id)
        if not booking_rows:
            return []

        flight_header_ids = [row.flight_header_id for row in booking_rows]

        # Fetch ULD details for all these flights in one query
        uld_map = await self._fetch_ulds_for_flights(awb_master_id, flight_header_ids)

        details: list[FlightBookingDetail] = []
        for booking in booking_rows:
            header = booking.header          # via relationship
            ulds = uld_map.get(booking.flight_header_id, [])

            details.append(FlightBookingDetail(
                flight_header_id=booking.flight_header_id,
                flight_no=header.flight_no,
                flight_date=header.flight_date,
                flight_dpt_datetime=header.flight_dpt_datetime,
                is_active=header.is_active,
                booked_by=booking.awb.flight_details[0].header.booked_by  # see note below
                    if False else header.booked_by,
                booked_at=header.booked_at,
                booked_pcs=booking.booked_pcs,
                ulds=ulds,
            ))

        return details

    async def _fetch_flight_bookings(
        self, awb_master_id: int
    ) -> list[ExportFlightBookingDetail]:
        """
        Uses idx_flight_detail_awb_header composite index.
        joinedload the header so we get flight_no/date in same query.
        """
        result = await self.db.execute(
            select(ExportFlightBookingDetail)
            .options(joinedload(ExportFlightBookingDetail.header))
            .where(ExportFlightBookingDetail.awb_master_id == awb_master_id)
            .order_by(ExportFlightBookingDetail.flight_header_id)
        )
        return list(result.scalars().unique().all())

    async def _fetch_ulds_for_flights(
        self,
        awb_master_id: int,
        flight_header_ids: list[int],
    ) -> dict[int, list[UldDetail]]:
        """
        Returns {flight_header_id: [UldDetail, ...]}

        For each flight, find the ULD assignment → details → loaded items
        that belong to this AWB.

        Joins:
          export_uld_assignment          (for flight_header_id)
            → export_uld_assignment_detail
            → export_item_uld_loading    (filtered to this awb_master_id)
            → export_awb_skid_item_sequence  (for sequence_no)
        """
        stmt = (
            select(
                ExportUldAssignment.flight_header_id,
                ExportUldAssignmentDetail,
                ExportSequenceItemUldLoading,
                ExportAwbSkidItemSequence.sequence_no,
                 ExportUldMaster.uld_no,
                ExportUldMaster.uld_type,
            )
            .join(
                ExportUldAssignmentDetail,
                ExportUldAssignmentDetail.assignment_id == ExportUldAssignment.id,
            )
            .join(
    ExportUldMaster,
    ExportUldMaster.id == ExportUldAssignmentDetail.uld_id,
)
            .outerjoin(
                ExportSequenceItemUldLoading,
                (ExportSequenceItemUldLoading.uld_assignment_detail_id == ExportUldAssignmentDetail.id)
                & (ExportSequenceItemUldLoading.awb_master_id == awb_master_id),
            )
            .outerjoin(
                ExportAwbSkidItemSequence,
                ExportSequenceItemUldLoading.sequence_id == ExportAwbSkidItemSequence.id,
            )
            .where(
                ExportUldAssignment.flight_header_id.in_(flight_header_ids),
                ExportUldAssignment.is_active.is_(True),
            )
            .order_by(
                ExportUldAssignment.flight_header_id,
                ExportUldAssignmentDetail.id,
                ExportSequenceItemUldLoading.loaded_at,
            )
        )

        result = await self.db.execute(stmt)
        rows = result.all()

        # flight_header_id → uld_detail_id → UldDetail
        flight_uld_map: dict[int, dict[int, UldDetail]] = defaultdict(dict)

        for row in rows:
            fh_id = row[0]
            uld_detail: ExportUldAssignmentDetail = row[1]
            load_rec: Optional[ExportSequenceItemUldLoading] = row[2]
            seq_no: Optional[str] = row[3]
            uld_no: Optional[str] = row[4]
            uld_type: Optional[str] = row[5]

            detail_id = uld_detail.id

            if detail_id not in flight_uld_map[fh_id]:
                flight_uld_map[fh_id][detail_id] = UldDetail(
                    uld_assignment_detail_id=detail_id,
                    uld_id=uld_detail.uld_id,
                    # uld_no=None,           # join ExportUldMaster if you want uld_no
                    # uld_type=None,
                    uld_no=uld_no,
                    uld_type=uld_type,
                    is_closed=uld_detail.is_closed,
                    closed_by=uld_detail.closed_by,
                    closed_at=uld_detail.closed_at,
                    loaded_items=[],
                )

            if load_rec is not None and seq_no is not None:
                flight_uld_map[fh_id][detail_id].loaded_items.append(
                    UldLoadedItem(
                        id=load_rec.id,
                        sequence_id=load_rec.sequence_id,
                        sequence_no=seq_no,
                        loaded_by=load_rec.loaded_by,
                        loaded_at=load_rec.loaded_at,
                    )
                )

        # Compute loaded_pcs and return
        return {
            fh_id: [
                uld.model_copy(update={"loaded_pcs": len(uld.loaded_items)})
                for uld in uld_dict.values()
            ]
            for fh_id, uld_dict in flight_uld_map.items()
        }


#  GET aLL SEQUANCES OF PARTICULA ULD OF PARTICULAR FLIGHTS
    async def _get_uld_sequences_of_single_flight(
        self,
        awb_master_id: int,
        flight_header_id: int,
        uld_assignment_detail_id: int,
    ):
        result = await self.db.execute(
            select(
                ExportSequenceItemUldLoading,
                ExportAwbSkidItemSequence.sequence_no,
                ExportAwbSkidItemSequence.scanned_by,
                ExportAwbSkidItemSequence.sequence_date_time,
                User.name.label("loaded_by_name")
            )
            .join(
                ExportAwbSkidItemSequence,
                ExportSequenceItemUldLoading.sequence_id == ExportAwbSkidItemSequence.id
            )
            .outerjoin(
                User,
                User.emp_id == ExportSequenceItemUldLoading.loaded_by
            )
            .where(
                ExportSequenceItemUldLoading.awb_master_id == awb_master_id,
                ExportSequenceItemUldLoading.flight_header_id == flight_header_id,
                ExportSequenceItemUldLoading.uld_assignment_detail_id == uld_assignment_detail_id,
            )
            .order_by(
                ExportSequenceItemUldLoading.loaded_at.asc()
            )
        )

        rows = result.all()

        return [
            {
                "sequence_no": row[1],
                "scanned_by": row[2],
                "scan_time": row[3],
                "loaded_by": row[0].loaded_by,
                "loaded_by_name": row[4],
                "loaded_at": row[0].loaded_at,
            }
            for row in rows
        ]

    # ──────────────────────────────────────────────
    # SEARCH / LISTING  (lightweight, no joins)
    # ──────────────────────────────────────────────

    async def list_awbs(
        self,
        status: Optional[str] = None,
        agent: Optional[str] = None,
        origin: Optional[str] = None,
        destination: Optional[str] = None,
        is_ultra_fast: Optional[bool] = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[AwbListItem]:
        """
        Paginated AWB list with optional filters.
        Uses partial indexes idx_awb_rcs_status / idx_awb_tfd_status when
        status='RCS' or status='TFD'.
        """
        stmt = select(ExportCarMessageAwbMaster)

        if status:
            stmt = stmt.where(ExportCarMessageAwbMaster.status == status)
        if agent:
            stmt = stmt.where(ExportCarMessageAwbMaster.agent == agent)
        if origin:
            stmt = stmt.where(ExportCarMessageAwbMaster.origin == origin)
        if destination:
            stmt = stmt.where(ExportCarMessageAwbMaster.destination == destination)
        if is_ultra_fast is not None:
            stmt = stmt.where(ExportCarMessageAwbMaster.is_ultra_fast == is_ultra_fast)

        stmt = stmt.order_by(ExportCarMessageAwbMaster.created_at.desc())
        stmt = stmt.limit(limit).offset(offset)

        result = await self.db.execute(stmt)
        rows = list(result.scalars().all())
        return [AwbListItem.model_validate(r) for r in rows]
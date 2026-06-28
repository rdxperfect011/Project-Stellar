"""
PricingEngine — single, authoritative source for all price calculations.

Pricing rules (per room, per night) stored in AccommodationPricing:
  Standard Room:  2 guests → ₹1,800  |  3 guests → ₹2,500  |  4 guests → ₹3,500
  Deluxe Room:    2 guests → ₹2,000  |  3 guests → ₹2,700  |  4 guests → ₹3,800

Formula:
  1. Guests are distributed as evenly as possible across rooms.
  2. Each room is priced individually based on its assigned guest count.
  3. Room charges  = Σ (rate_per_night × nights)  for each room
  4. Meal charges  = package.price × (total_guests or 1) × nights
  5. Total         = room_charges + meal_charges  (tax reserved for future use)

Extend this file to add seasonal pricing, weekend surcharges, discounts, or
coupon codes.  BookingService and all API routes MUST NOT contain any price
arithmetic — they call PricingEngine.calculate() and use the result.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

from app import db
from app.models.accommodation import (
    AccommodationCategory,
    AccommodationPricing,
    AccommodationPackage,
)


# ---------------------------------------------------------------------------
# Data containers
# ---------------------------------------------------------------------------

@dataclass
class RoomBreakdown:
    """Pricing detail for a single physical room in a booking."""
    room_number:    int    # 1-based room index
    guests_in_room: int    # guests assigned to this room
    rate_per_night: float  # nightly rate for this occupancy tier
    nights:         int
    room_total:     float  # rate_per_night × nights


@dataclass
class PriceBreakdown:
    """
    Complete, itemised price breakdown returned by PricingEngine.calculate().

    Consumers (API routes, booking service, UI) MUST use this object and must
    NOT recalculate any of the values themselves.
    """

    # ---- Inputs (echoed back so consumers can verify) -----------------------
    accommodation_name: str
    room_type_id:       int
    num_rooms:          int
    total_guests:       int
    nights:             int
    package_name:       Optional[str]

    # ---- Per-room detail ----------------------------------------------------
    rooms: list[RoomBreakdown] = field(default_factory=list)

    # ---- Aggregates ---------------------------------------------------------
    room_charges: float = 0.0   # Σ room_total across all rooms
    meal_charges: float = 0.0   # package addon cost
    subtotal:     float = 0.0   # room_charges + meal_charges
    tax:          float = 0.0   # reserved for future GST / service tax
    total:        float = 0.0   # subtotal + tax (grand total)

    # ---- Validation ---------------------------------------------------------
    is_valid:          bool           = True
    validation_error:  Optional[str]  = None

    # ---- Convenience --------------------------------------------------------
    def to_dict(self) -> dict:
        """
        Serialize to a JSON-safe dict.  This is the canonical shape consumed
        by the frontend booking modal and stored in BookingEnquiry.price_breakdown.
        """
        return {
            # Inputs
            "accommodation_name": self.accommodation_name,
            "room_type_id":       self.room_type_id,
            "num_rooms":          self.num_rooms,
            "total_guests":       self.total_guests,
            "nights":             self.nights,
            "package_name":       self.package_name,
            # Per-room detail
            "rooms": [
                {
                    "room_number":    r.room_number,
                    "guests_in_room": r.guests_in_room,
                    "rate_per_night": r.rate_per_night,
                    "nights":         r.nights,
                    "room_total":     r.room_total,
                }
                for r in self.rooms
            ],
            # Aggregates
            "room_charges": self.room_charges,
            "meal_charges": self.meal_charges,
            "subtotal":     self.subtotal,
            "tax":          self.tax,
            "total":        self.total,
            # Validation
            "is_valid":         self.is_valid,
            "validation_error": self.validation_error,
        }

    @classmethod
    def invalid(
        cls,
        error: str,
        accommodation_name: str = "Unknown",
        room_type_id: int = 0,
        num_rooms: int = 0,
        total_guests: int = 0,
        nights: int = 0,
    ) -> "PriceBreakdown":
        """Factory for invalid/error breakdowns (avoids boilerplate at call sites)."""
        return cls(
            accommodation_name=accommodation_name,
            room_type_id=room_type_id,
            num_rooms=num_rooms,
            total_guests=total_guests,
            nights=nights,
            package_name=None,
            is_valid=False,
            validation_error=error,
        )


# ---------------------------------------------------------------------------
# Engine
# ---------------------------------------------------------------------------

class PricingEngine:
    """
    Stateless pricing engine.  Call PricingEngine.calculate() — never
    instantiate the class.

    Extension points
    ----------------
    - Seasonal / weekend pricing → override _get_rate()
    - Discounts / coupons       → post-process subtotal before totalling
    - GST / taxes               → set tax = subtotal * rate inside calculate()
    """

    # Minimum guests that must occupy each booked room (validation only).
    MIN_GUESTS_PER_ROOM = 1
    # Maximum guests a single room can hold (must match DB capacity column).
    MAX_GUESTS_PER_ROOM = 4

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    @staticmethod
    def calculate(
        accommodation_id: int,
        num_rooms:        int,
        total_guests:     int,
        nights:           int,
        package_id:       Optional[int] = None,
    ) -> PriceBreakdown:
        """
        Calculate the complete price breakdown for a booking.

        Parameters
        ----------
        accommodation_id : int   DB id of AccommodationCategory
        num_rooms        : int   Number of rooms being booked
        total_guests     : int   Total guests across ALL rooms combined
        nights           : int   Number of nights (check_out - check_in).days
        package_id       : int?  Optional AccommodationPackage id

        Returns
        -------
        PriceBreakdown   Always returned; check .is_valid / .validation_error.
                         Never raises exceptions — errors are encoded in the result.
        """
        # ---- Fetch room type ------------------------------------------------
        accommodation = db.session.get(AccommodationCategory, accommodation_id)
        if not accommodation:
            return PriceBreakdown.invalid(
                "Room type not found.",
                room_type_id=accommodation_id,
                num_rooms=num_rooms,
                total_guests=total_guests,
                nights=nights,
            )

        # ---- Validate inputs ------------------------------------------------
        err = PricingEngine._validate(accommodation, num_rooms, total_guests, nights)
        if err:
            return PriceBreakdown.invalid(
                err,
                accommodation_name=accommodation.name,
                room_type_id=accommodation_id,
                num_rooms=num_rooms,
                total_guests=total_guests,
                nights=nights,
            )

        # ---- Distribute guests across rooms ---------------------------------
        # e.g. 5 guests, 2 rooms → [3, 2]
        guest_distribution = PricingEngine._distribute_guests(total_guests, num_rooms)

        # ---- Price each room individually -----------------------------------
        room_breakdowns: list[RoomBreakdown] = []
        room_charges = 0.0

        for idx, guests_in_room in enumerate(guest_distribution, start=1):
            rate       = PricingEngine._get_rate(accommodation, guests_in_room)
            room_total = round(rate * nights, 2)
            room_charges += room_total
            room_breakdowns.append(
                RoomBreakdown(
                    room_number=idx,
                    guests_in_room=guests_in_room,
                    rate_per_night=rate,
                    nights=nights,
                    room_total=room_total,
                )
            )

        room_charges = round(room_charges, 2)

        # ---- Package / meal charges -----------------------------------------
        package_name = None
        meal_charges = 0.0

        if package_id:
            package = db.session.get(AccommodationPackage, package_id)
            if package and package.accommodation_id == accommodation_id:
                package_name = package.name
                if package.is_per_guest:
                    meal_charges = round(package.price * total_guests * nights, 2)
                else:
                    meal_charges = round(package.price * nights, 2)

        # ---- Totals ---------------------------------------------------------
        subtotal = round(room_charges + meal_charges, 2)
        tax      = 0.0   # Extend here: e.g. tax = round(subtotal * 0.12, 2)
        total    = round(subtotal + tax, 2)

        return PriceBreakdown(
            accommodation_name=accommodation.name,
            room_type_id=accommodation_id,
            num_rooms=num_rooms,
            total_guests=total_guests,
            nights=nights,
            package_name=package_name,
            rooms=room_breakdowns,
            room_charges=room_charges,
            meal_charges=meal_charges,
            subtotal=subtotal,
            tax=tax,
            total=total,
            is_valid=True,
            validation_error=None,
        )

    @staticmethod
    def get_rate_for_guests(accommodation_id: int, guests_in_room: int) -> float:
        """
        Return the nightly rate for a single room with `guests_in_room` guests.
        Useful for lightweight checks (e.g. previewing price on room cards)
        without building a full breakdown.
        """
        accommodation = db.session.get(AccommodationCategory, accommodation_id)
        if not accommodation:
            return 0.0
        return PricingEngine._get_rate(accommodation, guests_in_room)

    @staticmethod
    def validate_occupancy(
        accommodation: AccommodationCategory,
        num_rooms:     int,
        total_guests:  int,
    ) -> Optional[str]:
        """
        Return an error string if the combination is invalid, else None.
        Public wrapper used by API routes for fast pre-validation before
        hitting the full calculate() path.
        """
        return PricingEngine._validate(accommodation, num_rooms, total_guests, nights=1)

    @staticmethod
    def get_pricing_tiers(accommodation_id: int) -> list[dict]:
        """
        Return sorted pricing tiers for a room type.
        Shape: [{'guests': 2, 'price': 1800}, {'guests': 3, 'price': 2500}, …]
        """
        tiers = (
            AccommodationPricing.query
            .filter_by(accommodation_id=accommodation_id)
            .order_by(AccommodationPricing.guests.asc())
            .all()
        )
        return [{"guests": t.guests, "price": float(t.price)} for t in tiers]

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _validate(
        accommodation: AccommodationCategory,
        num_rooms:     int,
        total_guests:  int,
        nights:        int,
    ) -> Optional[str]:
        """Return a human-readable error string, or None when inputs are valid."""

        if num_rooms <= 0:
            return "Number of rooms must be at least 1."
        if total_guests <= 0:
            return "Number of guests must be at least 1."
        if nights <= 0:
            return "Check-out date must be after check-in date."

        # Each room must have at least 1 guest — guards against rooms > guests.
        if total_guests < num_rooms:
            return (
                f"You have selected {num_rooms} room(s) for only "
                f"{total_guests} guest(s). Each room requires at least 1 guest. "
                f"Please reduce the number of rooms or add more guests."
            )

        # Upper bound: per-room capacity × rooms selected.
        max_capacity = accommodation.capacity  # e.g. 4
        max_total    = max_capacity * num_rooms
        if total_guests > max_total:
            return (
                f"{total_guests} guest(s) exceed the maximum capacity for "
                f"{num_rooms} {accommodation.name}(s) "
                f"(max {max_capacity} guests per room, {max_total} total). "
                f"Please add more rooms or reduce the number of guests."
            )

        return None

    @staticmethod
    def _distribute_guests(total_guests: int, num_rooms: int) -> list[int]:
        """
        Distribute guests as evenly as possible across rooms.

        Algorithm: integer division gives the base count; the remainder is
        spread one-per-room across the first N rooms.

        Examples
        --------
        3 guests, 1 room  → [3]
        3 guests, 2 rooms → [2, 1]
        5 guests, 2 rooms → [3, 2]
        4 guests, 4 rooms → [1, 1, 1, 1]
        6 guests, 4 rooms → [2, 2, 1, 1]
        """
        base      = total_guests // num_rooms
        remainder = total_guests % num_rooms
        return [base + (1 if i < remainder else 0) for i in range(num_rooms)]

    @staticmethod
    def _get_rate(accommodation: AccommodationCategory, guests_in_room: int) -> float:
        """
        Fetch the nightly rate for this room type at the given occupancy.

        Lookup strategy (in order):
        1. Exact match on `guests` column.
        2. If guests_in_room < the lowest defined tier, use the lowest tier.
           (e.g. 1 guest in a room → charged at the 2-guest rate)
        3. If guests_in_room > the highest defined tier, use the highest tier.
           (guards against unpriced overflow; should not occur after validation)
        4. If no pricing is defined at all, return 0.0 (prevents crashes).
        """
        # 1. Exact match
        exact = AccommodationPricing.query.filter_by(
            accommodation_id=accommodation.id,
            guests=guests_in_room,
        ).first()
        if exact:
            return float(exact.price)

        # Fetch all tiers sorted ascending once — used for fallback cases.
        all_tiers = (
            AccommodationPricing.query
            .filter_by(accommodation_id=accommodation.id)
            .order_by(AccommodationPricing.guests.asc())
            .all()
        )
        if not all_tiers:
            return 0.0

        # 2. Below lowest tier → charge lowest tier rate
        if guests_in_room < all_tiers[0].guests:
            return float(all_tiers[0].price)

        # 3. Above highest tier → charge highest tier rate
        return float(all_tiers[-1].price)

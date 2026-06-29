"""
Tests for PricingEngine.

These tests cover:
- Single room, various guest counts
- Multiple rooms with even/uneven guest distribution
- Single guest, multiple rooms (expected to fail validation)
- Guests exceeding room capacity (expected to fail)
- Meal package calculations (per-guest and flat)
- Edge cases: 1 guest in 1 room, max occupancy, 0-night stays
- The full example scenarios from the requirements doc
"""
import pytest
import json
from app import create_app, db
from app.models.accommodation import AccommodationCategory, AccommodationPricing, AccommodationPackage
from app.services.pricing_engine import PricingEngine


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def app():
    import os
    os.environ['WTF_CSRF_ENABLED'] = 'False'
    _app = create_app('testing')
    _app.config.update({
        "TESTING": True,
        "SQLALCHEMY_DATABASE_URI": "sqlite:///:memory:",
        "WTF_CSRF_ENABLED": False,
    })
    with _app.app_context():
        db.create_all()
        yield _app
        db.session.remove()
        db.drop_all()


@pytest.fixture
def normal_room(app):
    """Normal Room with pricing: 2→₹1800, 3→₹2500, 4→₹3500."""
    with app.app_context():
        room = AccommodationCategory(
            name="Normal Room",
            description="Test normal room",
            capacity=4,
            internal_count=2,
            cover_image="test.jpg",
            is_active=True,
        )
        db.session.add(room)
        db.session.flush()
        db.session.add_all([
            AccommodationPricing(accommodation_id=room.id, guests=2, price=1800),
            AccommodationPricing(accommodation_id=room.id, guests=3, price=2500),
            AccommodationPricing(accommodation_id=room.id, guests=4, price=3500),
        ])
        db.session.commit()
        yield room.id


@pytest.fixture
def deluxe_room(app):
    """Deluxe Room with pricing: 2→₹2000, 3→₹2700, 4→₹3800."""
    with app.app_context():
        room = AccommodationCategory(
            name="Deluxe Room",
            description="Test deluxe room",
            capacity=4,
            internal_count=3,
            cover_image="test.jpg",
            is_active=True,
        )
        db.session.add(room)
        db.session.flush()
        db.session.add_all([
            AccommodationPricing(accommodation_id=room.id, guests=2, price=2000),
            AccommodationPricing(accommodation_id=room.id, guests=3, price=2700),
            AccommodationPricing(accommodation_id=room.id, guests=4, price=3800),
        ])
        db.session.commit()
        yield room.id


@pytest.fixture
def meal_package(app, deluxe_room):
    """Meals & Tea package: ₹500/guest/night."""
    with app.app_context():
        pkg = AccommodationPackage(
            accommodation_id=deluxe_room,
            name="Meals & Tea",
            description="Home-cooked meals",
            price=500.0,
            is_per_guest=True,
        )
        db.session.add(pkg)
        db.session.commit()
        yield pkg.id


@pytest.fixture
def flat_package(app, deluxe_room):
    """Flat-rate package: ₹300/night (not per guest)."""
    with app.app_context():
        pkg = AccommodationPackage(
            accommodation_id=deluxe_room,
            name="Late Checkout",
            description="Checkout at 2pm",
            price=300.0,
            is_per_guest=False,
        )
        db.session.add(pkg)
        db.session.commit()
        yield pkg.id


# ===========================================================================
# Single-room pricing
# ===========================================================================

class TestSingleRoomPricing:

    def test_normal_room_2_guests_1_night(self, app, normal_room):
        with app.app_context():
            bd = PricingEngine.calculate(normal_room, num_rooms=1, total_guests=2, nights=1)
            assert bd.is_valid
            assert bd.room_charges == 1800.0
            assert bd.total == 1800.0

    def test_normal_room_3_guests_1_night(self, app, normal_room):
        with app.app_context():
            bd = PricingEngine.calculate(normal_room, num_rooms=1, total_guests=3, nights=1)
            assert bd.is_valid
            assert bd.room_charges == 2500.0

    def test_normal_room_4_guests_1_night(self, app, normal_room):
        with app.app_context():
            bd = PricingEngine.calculate(normal_room, num_rooms=1, total_guests=4, nights=1)
            assert bd.is_valid
            assert bd.room_charges == 3500.0

    def test_deluxe_room_2_guests_1_night(self, app, deluxe_room):
        with app.app_context():
            bd = PricingEngine.calculate(deluxe_room, num_rooms=1, total_guests=2, nights=1)
            assert bd.is_valid
            assert bd.room_charges == 2000.0

    def test_deluxe_room_3_guests_1_night(self, app, deluxe_room):
        with app.app_context():
            bd = PricingEngine.calculate(deluxe_room, num_rooms=1, total_guests=3, nights=1)
            assert bd.is_valid
            assert bd.room_charges == 2700.0

    def test_deluxe_room_4_guests_1_night(self, app, deluxe_room):
        with app.app_context():
            bd = PricingEngine.calculate(deluxe_room, num_rooms=1, total_guests=4, nights=1)
            assert bd.is_valid
            assert bd.room_charges == 3800.0

    def test_multiply_by_nights(self, app, normal_room):
        """3 nights × ₹2500 (3 guests) = ₹7500"""
        with app.app_context():
            bd = PricingEngine.calculate(normal_room, num_rooms=1, total_guests=3, nights=3)
            assert bd.is_valid
            assert bd.room_charges == 7500.0


# ===========================================================================
# Multi-room pricing (the core fix)
# ===========================================================================

class TestMultiRoomPricing:

    def test_1_guest_5_rooms_fails_validation(self, app, normal_room):
        """
        REQUIREMENT: 1 guest, 5 rooms → should FAIL (each room needs ≥ 1 guest).
        Previously this was silently accepted.
        """
        with app.app_context():
            bd = PricingEngine.calculate(normal_room, num_rooms=5, total_guests=1, nights=1)
            assert not bd.is_valid
            assert "reduce the number of rooms" in bd.validation_error.lower() or \
                   "each room requires" in bd.validation_error.lower()

    def test_5_guests_1_room_valid_normal(self, app, normal_room):
        """
        REQUIREMENT: 5 guests, 1 room → should FAIL (exceeds max capacity of 4).
        """
        with app.app_context():
            bd = PricingEngine.calculate(normal_room, num_rooms=1, total_guests=5, nights=1)
            assert not bd.is_valid
            assert "exceed" in bd.validation_error.lower() or "capacity" in bd.validation_error.lower()

    def test_6_guests_2_normal_rooms_valid(self, app, normal_room):
        """
        REQUIREMENT: 6 guests, 2 Normal Rooms → distribute evenly [3, 3].
        Cost = ₹2500 + ₹2500 = ₹5000/night.
        """
        with app.app_context():
            bd = PricingEngine.calculate(normal_room, num_rooms=2, total_guests=6, nights=1)
            assert bd.is_valid
            assert len(bd.rooms) == 2
            assert bd.rooms[0].guests_in_room == 3
            assert bd.rooms[1].guests_in_room == 3
            assert bd.room_charges == 5000.0

    def test_8_guests_2_deluxe_rooms_3_nights(self, app, deluxe_room):
        """
        REQUIREMENT: 8 Guests, 2 Deluxe Rooms, 3 Nights.
        Distribute: [4, 4].
        Cost = (₹3800 + ₹3800) × 3 = ₹22,800.
        """
        with app.app_context():
            bd = PricingEngine.calculate(deluxe_room, num_rooms=2, total_guests=8, nights=3)
            assert bd.is_valid
            assert len(bd.rooms) == 2
            assert bd.rooms[0].guests_in_room == 4
            assert bd.rooms[1].guests_in_room == 4
            assert bd.room_charges == 22800.0
            assert bd.total == 22800.0

    def test_uneven_guest_distribution(self, app, normal_room):
        """
        5 guests, 2 rooms → [3, 2].
        Cost = ₹2500 + ₹1800 = ₹4300/night.
        """
        with app.app_context():
            bd = PricingEngine.calculate(normal_room, num_rooms=2, total_guests=5, nights=1)
            assert bd.is_valid
            assert len(bd.rooms) == 2
            guests_counts = sorted([r.guests_in_room for r in bd.rooms])
            assert guests_counts == [2, 3]
            assert bd.room_charges == 4300.0

    def test_3_guests_3_rooms_valid(self, app, normal_room):
        """3 guests, 3 rooms → [1, 1, 1]. Each room billed at 2-guest rate (fallback)."""
        with app.app_context():
            bd = PricingEngine.calculate(normal_room, num_rooms=3, total_guests=3, nights=1)
            assert bd.is_valid
            assert len(bd.rooms) == 3
            for room in bd.rooms:
                assert room.guests_in_room == 1
            # 1-guest fallback → uses the 2-guest tier (₹1800 each)
            assert bd.room_charges == 1800.0 * 3

    def test_1_guest_1_room_valid(self, app, normal_room):
        """1 guest, 1 room is valid — uses min tier (2-guest rate)."""
        with app.app_context():
            bd = PricingEngine.calculate(normal_room, num_rooms=1, total_guests=1, nights=1)
            assert bd.is_valid
            assert bd.room_charges == 1800.0   # falls back to 2-guest tier


# ===========================================================================
# 1-guest-5-rooms vs 5-guests-1-room: MUST differ
# ===========================================================================

class TestPricingAsymmetry:

    def test_1_guest_5_rooms_not_equal_to_5_guests_1_room(self, app, normal_room):
        """
        Core bug fix: these two scenarios must NOT produce the same result.
        - 1 guest, 5 rooms → validation failure (not ≥ 1 guest/room without enough guests)
        - 5 guests, 1 room → validation failure (exceeds capacity)
        - But their error messages must be different.
        """
        with app.app_context():
            bd_a = PricingEngine.calculate(normal_room, num_rooms=5, total_guests=1, nights=1)
            bd_b = PricingEngine.calculate(normal_room, num_rooms=1, total_guests=5, nights=1)
            # Both invalid but for different reasons
            assert not bd_a.is_valid
            assert not bd_b.is_valid
            assert bd_a.validation_error != bd_b.validation_error

    def test_different_room_counts_yield_different_prices(self, app, normal_room):
        """
        1 guest/room vs 5 guests/1 room (within capacity) → different prices.
        Compare: 2 guests/1 room vs 2 guests/2 rooms.
        """
        with app.app_context():
            # 2 guests, 1 room: ₹1800
            bd_single = PricingEngine.calculate(normal_room, num_rooms=1, total_guests=2, nights=1)
            # 2 guests, 2 rooms: [1, 1] → each room at min tier (1800 each) = ₹3600
            bd_double = PricingEngine.calculate(normal_room, num_rooms=2, total_guests=2, nights=1)
            assert bd_single.is_valid
            assert bd_double.is_valid
            # 2 rooms MUST cost more than 1 room
            assert bd_double.total > bd_single.total


# ===========================================================================
# Meal package calculations
# ===========================================================================

class TestMealPackages:

    def test_per_guest_package(self, app, deluxe_room, meal_package):
        """
        ₹500/guest/night × 2 guests × 2 nights = ₹2000 meal charges.
        Room: ₹2000/night × 2 = ₹4000.
        Total: ₹6000.
        """
        with app.app_context():
            bd = PricingEngine.calculate(
                deluxe_room, num_rooms=1, total_guests=2, nights=2,
                package_id=meal_package,
            )
            assert bd.is_valid
            assert bd.meal_charges == 2000.0   # 500 × 2 guests × 2 nights
            assert bd.room_charges == 4000.0   # 2000 × 2 nights
            assert bd.total        == 6000.0

    def test_flat_package(self, app, deluxe_room, flat_package):
        """
        ₹300/night flat (not per guest) × 3 nights = ₹900.
        Room: ₹2000 × 3 = ₹6000.
        Total: ₹6900.
        """
        with app.app_context():
            bd = PricingEngine.calculate(
                deluxe_room, num_rooms=1, total_guests=2, nights=3,
                package_id=flat_package,
            )
            assert bd.is_valid
            assert bd.meal_charges == 900.0
            assert bd.room_charges == 6000.0
            assert bd.total        == 6900.0

    def test_no_package(self, app, normal_room):
        with app.app_context():
            bd = PricingEngine.calculate(normal_room, num_rooms=1, total_guests=2, nights=1)
            assert bd.is_valid
            assert bd.meal_charges == 0.0
            assert bd.total == bd.room_charges


# ===========================================================================
# Validation edge cases
# ===========================================================================

class TestValidationEdgeCases:

    def test_zero_nights(self, app, normal_room):
        with app.app_context():
            bd = PricingEngine.calculate(normal_room, num_rooms=1, total_guests=2, nights=0)
            assert not bd.is_valid

    def test_zero_guests(self, app, normal_room):
        with app.app_context():
            bd = PricingEngine.calculate(normal_room, num_rooms=1, total_guests=0, nights=1)
            assert not bd.is_valid

    def test_zero_rooms(self, app, normal_room):
        with app.app_context():
            bd = PricingEngine.calculate(normal_room, num_rooms=0, total_guests=2, nights=1)
            assert not bd.is_valid

    def test_nonexistent_room_type(self, app):
        with app.app_context():
            bd = PricingEngine.calculate(accommodation_id=9999, num_rooms=1, total_guests=2, nights=1)
            assert not bd.is_valid
            assert "not found" in bd.validation_error.lower()

    def test_max_capacity_boundary(self, app, normal_room):
        """4 guests in 1 Normal Room is exactly the max — must be valid."""
        with app.app_context():
            bd = PricingEngine.calculate(normal_room, num_rooms=1, total_guests=4, nights=1)
            assert bd.is_valid

    def test_one_over_max_capacity(self, app, normal_room):
        """5 guests in 1 Normal Room exceeds max of 4."""
        with app.app_context():
            bd = PricingEngine.calculate(normal_room, num_rooms=1, total_guests=5, nights=1)
            assert not bd.is_valid

    def test_guests_less_than_rooms_fails(self, app, normal_room):
        """2 guests, 3 rooms → not enough guests for each room."""
        with app.app_context():
            bd = PricingEngine.calculate(normal_room, num_rooms=3, total_guests=2, nights=1)
            assert not bd.is_valid


# ===========================================================================
# Serialisation
# ===========================================================================

class TestSerialization:

    def test_to_dict_is_json_serializable(self, app, normal_room):
        with app.app_context():
            bd = PricingEngine.calculate(normal_room, num_rooms=1, total_guests=2, nights=2)
            d = bd.to_dict()
            dumped = json.dumps(d)   # must not raise
            loaded = json.loads(dumped)
            assert loaded['total'] == bd.total
            assert loaded['is_valid'] is True

    def test_invalid_breakdown_serializes(self, app, normal_room):
        with app.app_context():
            bd = PricingEngine.calculate(normal_room, num_rooms=5, total_guests=1, nights=1)
            d = bd.to_dict()
            assert d['is_valid'] is False
            assert d['validation_error']


# ===========================================================================
# Guest distribution algorithm
# ===========================================================================

class TestGuestDistribution:

    def _distribute(self, guests, rooms):
        return PricingEngine._distribute_guests(guests, rooms)

    def test_even_distribution(self):
        assert self._distribute(6, 2) == [3, 3]
        assert self._distribute(4, 2) == [2, 2]
        assert self._distribute(9, 3) == [3, 3, 3]

    def test_uneven_distribution(self):
        result = self._distribute(5, 2)
        assert sorted(result) == [2, 3]

    def test_single_room(self):
        assert self._distribute(4, 1) == [4]

    def test_remainder_spread(self):
        """7 guests, 3 rooms → [3, 2, 2]"""
        result = self._distribute(7, 3)
        assert sorted(result, reverse=True) == [3, 2, 2]
        assert sum(result) == 7


# ===========================================================================
# API route integration
# ===========================================================================

class TestCalculatePriceAPI:

    @pytest.fixture
    def client(self, app, normal_room, deluxe_room):
        with app.app_context():
            yield app.test_client(), normal_room, deluxe_room

    def test_valid_calculation(self, client):
        c, normal_id, _ = client
        resp = c.post('/api/calculate-price', json={
            'checkIn': '2026-08-01',
            'checkOut': '2026-08-03',
            'accommodationId': normal_id,
            'rooms': 1,
            'guests': 2,
        })
        assert resp.status_code == 200
        data = resp.get_json()
        assert data['is_valid'] is True
        assert data['room_charges'] == 3600.0   # ₹1800 × 2 nights
        assert data['total'] == 3600.0

    def test_invalid_occupancy_returns_200_with_error(self, client):
        """API returns 200 with is_valid=False for occupancy errors (not HTTP 4xx)."""
        c, normal_id, _ = client
        resp = c.post('/api/calculate-price', json={
            'checkIn': '2026-08-01',
            'checkOut': '2026-08-03',
            'accommodationId': normal_id,
            'rooms': 5,
            'guests': 1,
        })
        assert resp.status_code == 200
        data = resp.get_json()
        assert data['is_valid'] is False

    def test_booking_request_rejected_on_occupancy_error(self, client):
        c, normal_id, _ = client
        resp = c.post('/api/booking-request', json={
            'fullName':        'Test User',
            'email':           'test@example.com',
            'phone':           '9999999999',
            'checkIn':         '2026-08-01',
            'checkOut':        '2026-08-03',
            'accommodationId': normal_id,
            'rooms':           5,
            'guests':          1,
        })
        # Should fail with 400 due to occupancy violation
        assert resp.status_code == 400
        data = resp.get_json()
        assert 'error' in data


# ===========================================================================
# REGRESSION: Room quantity must NOT be limited by guest count
# Reported bug: 3 guests → only 2 rooms selectable; 4 guests → only 2 rooms.
# ===========================================================================

class TestRoomAvailabilityNotLimitedByGuests:
    """
    The number of rooms a guest can select must be bounded ONLY by the
    physical inventory (internal_count), never by the number of guests.
    The only rule involving guests vs rooms is:
      - guests < rooms  → INVALID  (each room needs ≥ 1 guest)
      - guests > rooms × capacity → INVALID  (exceeds per-room max)
      - everything else → VALID
    """

    # ── 3-guest scenarios ────────────────────────────────────────────────────

    def test_3_guests_1_room_valid(self, app, normal_room):
        """3 guests, 1 room → evenly in 1 room. Valid."""
        with app.app_context():
            bd = PricingEngine.calculate(normal_room, num_rooms=1, total_guests=3, nights=1)
            assert bd.is_valid, bd.validation_error
            assert bd.room_charges == 2500.0   # 3-guest rate

    def test_3_guests_2_rooms_valid(self, app, normal_room):
        """3 guests, 2 rooms → [2, 1]. Must be VALID — not blocked by guest count."""
        with app.app_context():
            bd = PricingEngine.calculate(normal_room, num_rooms=2, total_guests=3, nights=1)
            assert bd.is_valid, bd.validation_error
            assert len(bd.rooms) == 2
            guests_counts = sorted([r.guests_in_room for r in bd.rooms])
            assert guests_counts == [1, 2]
            # Room 1 gets 2 guests (₹1800), Room 2 gets 1 guest (fallback ₹1800)
            assert bd.room_charges == 1800.0 + 1800.0

    def test_3_guests_3_rooms_valid(self, app, normal_room):
        """3 guests, 3 rooms → [1, 1, 1]. Valid — each room has exactly 1 guest."""
        with app.app_context():
            # normal_room has internal_count=2 so 3 rooms would normally exceed
            # inventory but PricingEngine doesn't check inventory (only occupancy).
            # This is intentional: inventory is checked by AvailabilityService.
            bd = PricingEngine.calculate(normal_room, num_rooms=3, total_guests=3, nights=1)
            assert bd.is_valid, bd.validation_error
            for room in bd.rooms:
                assert room.guests_in_room == 1

    def test_3_guests_4_rooms_invalid(self, app, normal_room):
        """3 guests, 4 rooms → guests < rooms → INVALID (not enough guests)."""
        with app.app_context():
            bd = PricingEngine.calculate(normal_room, num_rooms=4, total_guests=3, nights=1)
            assert not bd.is_valid
            assert "reduce the number of rooms" in bd.validation_error.lower() or \
                   "each room requires" in bd.validation_error.lower()

    # ── 4-guest scenarios ────────────────────────────────────────────────────

    def test_4_guests_1_room_valid(self, app, normal_room):
        """4 guests, 1 room → exactly at capacity. Valid."""
        with app.app_context():
            bd = PricingEngine.calculate(normal_room, num_rooms=1, total_guests=4, nights=1)
            assert bd.is_valid, bd.validation_error
            assert bd.room_charges == 3500.0   # 4-guest rate

    def test_4_guests_2_rooms_valid(self, app, normal_room):
        """4 guests, 2 rooms → [2, 2]. Must be VALID — not blocked by guest count."""
        with app.app_context():
            bd = PricingEngine.calculate(normal_room, num_rooms=2, total_guests=4, nights=1)
            assert bd.is_valid, bd.validation_error
            assert len(bd.rooms) == 2
            for room in bd.rooms:
                assert room.guests_in_room == 2
            # Each room at 2-guest rate (₹1800)
            assert bd.room_charges == 1800.0 + 1800.0

    def test_4_guests_4_rooms_valid(self, app, normal_room):
        """4 guests, 4 rooms → [1, 1, 1, 1]. Valid — 1 guest per room."""
        with app.app_context():
            bd = PricingEngine.calculate(normal_room, num_rooms=4, total_guests=4, nights=1)
            assert bd.is_valid, bd.validation_error
            assert len(bd.rooms) == 4

    def test_4_guests_5_rooms_invalid(self, app, normal_room):
        """4 guests, 5 rooms → guests < rooms → INVALID."""
        with app.app_context():
            bd = PricingEngine.calculate(normal_room, num_rooms=5, total_guests=4, nights=1)
            assert not bd.is_valid

    # ── Core invariant: room limit is inventory, not guests ──────────────────

    def test_max_rooms_bounded_by_inventory_not_guests(self, app, deluxe_room):
        """
        Deluxe Room has internal_count=3 (i.e., 3 physical rooms available).
        With any valid guest count (≥ num_rooms), all 3 rooms should be bookable.
        """
        with app.app_context():
            # 3 guests, 3 rooms → [1, 1, 1]: valid
            bd = PricingEngine.calculate(deluxe_room, num_rooms=3, total_guests=3, nights=1)
            assert bd.is_valid, bd.validation_error
            assert len(bd.rooms) == 3

            # 6 guests, 3 rooms → [2, 2, 2]: valid
            bd2 = PricingEngine.calculate(deluxe_room, num_rooms=3, total_guests=6, nights=1)
            assert bd2.is_valid, bd2.validation_error
            assert len(bd2.rooms) == 3

            # 12 guests, 3 rooms → [4, 4, 4]: valid (at max capacity per room)
            bd3 = PricingEngine.calculate(deluxe_room, num_rooms=3, total_guests=12, nights=1)
            assert bd3.is_valid, bd3.validation_error

            # 13 guests, 3 rooms → exceeds max capacity → INVALID
            bd4 = PricingEngine.calculate(deluxe_room, num_rooms=3, total_guests=13, nights=1)
            assert not bd4.is_valid
            assert "exceed" in bd4.validation_error.lower() or "capacity" in bd4.validation_error.lower()

    def test_different_guest_counts_same_room_quantity(self, app, normal_room):
        """
        1 guest, 2 guests, 3 guests, 4 guests should ALL be able to book
        up to their valid room count (≤ guests, ≤ capacity × rooms).
        This directly tests the reported bug.
        """
        with app.app_context():
            for guests in [1, 2, 3, 4]:
                # Each guest count should allow at least 1 room
                bd = PricingEngine.calculate(normal_room, num_rooms=1, total_guests=guests, nights=1)
                assert bd.is_valid, \
                    f"Expected {guests} guests, 1 room to be valid. Got: {bd.validation_error}"

                # Each guest count ≥ 2 should allow 2 rooms (normal_room inventory=2)
                if guests >= 2:
                    bd2 = PricingEngine.calculate(normal_room, num_rooms=2, total_guests=guests, nights=1)
                    assert bd2.is_valid, \
                        f"Expected {guests} guests, 2 rooms to be valid. Got: {bd2.validation_error}"

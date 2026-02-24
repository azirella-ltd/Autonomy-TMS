"""
Unit tests for Time-Phased ATP Service

Tests the key functionality:
1. Business day calculations (5-day work week)
2. Ship date calculation (delivery_date - lead_time)
3. ATP consumption at ship date
4. Backward cascade when insufficient supply
5. Priority-based consumption within date buckets
"""

import pytest
from datetime import date, timedelta
from app.services.powell.time_phased_atp import (
    TimePhasedATPService,
    TimePhasedATPConfig,
    TimePhasedATPRequest,
    TimePhasedAllocation,
    WorkWeekType,
)


class TestBusinessDayCalculations:
    """Test business day arithmetic"""

    def test_is_business_day_weekday(self):
        """Monday-Friday are business days"""
        service = TimePhasedATPService()

        # 2026-02-02 is a Monday
        monday = date(2026, 2, 2)
        assert service.is_business_day(monday) is True
        assert service.is_business_day(monday + timedelta(days=1)) is True  # Tue
        assert service.is_business_day(monday + timedelta(days=2)) is True  # Wed
        assert service.is_business_day(monday + timedelta(days=3)) is True  # Thu
        assert service.is_business_day(monday + timedelta(days=4)) is True  # Fri

    def test_is_business_day_weekend(self):
        """Saturday-Sunday are not business days (5-day week)"""
        service = TimePhasedATPService()

        # 2026-02-07 is a Saturday
        saturday = date(2026, 2, 7)
        sunday = date(2026, 2, 8)

        assert service.is_business_day(saturday) is False
        assert service.is_business_day(sunday) is False

    def test_is_business_day_six_day_week(self):
        """Saturday is a business day in 6-day week"""
        config = TimePhasedATPConfig(work_week=WorkWeekType.SIX_DAY)
        service = TimePhasedATPService(config)

        saturday = date(2026, 2, 7)
        sunday = date(2026, 2, 8)

        assert service.is_business_day(saturday) is True
        assert service.is_business_day(sunday) is False

    def test_is_business_day_holiday(self):
        """Holidays are not business days"""
        holiday = date(2026, 12, 25)
        config = TimePhasedATPConfig(holidays=[holiday])
        service = TimePhasedATPService(config)

        assert service.is_business_day(holiday) is False

    def test_add_business_days_no_weekend(self):
        """Add business days within same week"""
        service = TimePhasedATPService()

        monday = date(2026, 2, 2)
        result = service.add_business_days(monday, 3)

        # Mon + 3 business days = Thu
        assert result == date(2026, 2, 5)

    def test_add_business_days_across_weekend(self):
        """Add business days that span a weekend"""
        service = TimePhasedATPService()

        thursday = date(2026, 2, 5)
        result = service.add_business_days(thursday, 3)

        # Thu + 3 business days = Tue (skips Sat, Sun)
        assert result == date(2026, 2, 10)

    def test_subtract_business_days(self):
        """Subtract business days"""
        service = TimePhasedATPService()

        wednesday = date(2026, 2, 11)
        result = service.subtract_business_days(wednesday, 3)

        # Wed - 3 business days = Fri of previous week
        assert result == date(2026, 2, 6)

    def test_business_days_between(self):
        """Count business days between dates"""
        service = TimePhasedATPService()

        monday = date(2026, 2, 2)
        next_monday = date(2026, 2, 9)

        # 5 business days (Mon-Fri)
        assert service.business_days_between(monday, next_monday) == 5


class TestShipDateCalculation:
    """Test ship date calculation (delivery date - lead time)"""

    def test_ship_date_simple(self):
        """Basic ship date calculation"""
        service = TimePhasedATPService()

        delivery_date = date(2026, 2, 13)  # Friday
        lead_time = 3  # business days

        # Use from_date before the expected ship date so the "not in the past" clamp doesn't trigger
        ship_date = service.calculate_ship_date(delivery_date, lead_time, from_date=date(2026, 2, 1))

        # Fri - 3 business days = Tue
        assert ship_date == date(2026, 2, 10)

    def test_ship_date_across_weekend(self):
        """Ship date calculation that crosses weekend"""
        service = TimePhasedATPService()

        delivery_date = date(2026, 2, 10)  # Tuesday
        lead_time = 3  # business days

        ship_date = service.calculate_ship_date(delivery_date, lead_time, from_date=date(2026, 2, 1))

        # Tue - 3 business days = Thu of previous week
        assert ship_date == date(2026, 2, 5)

    def test_ship_date_two_weeks_three_day_lead_time(self):
        """
        User's example: 2 weeks out, 3-day lead time, 5-day week
        Result should be 7 business days from today
        """
        service = TimePhasedATPService()

        today = date(2026, 2, 2)  # Monday
        two_weeks_out = today + timedelta(days=14)  # Monday, Feb 16

        # 14 calendar days = 10 business days (2 weeks × 5 days)
        # Ship date = 10 - 3 = 7 business days from today

        ship_date = service.calculate_ship_date(
            expected_delivery_date=two_weeks_out,
            delivery_lead_time_days=3,
            from_date=today
        )

        # 7 business days from Monday Feb 2 = Wednesday Feb 11
        expected = service.add_business_days(today, 7)
        assert ship_date == expected
        assert ship_date == date(2026, 2, 11)

    def test_ship_date_not_in_past(self):
        """Ship date should not be before today"""
        service = TimePhasedATPService()

        today = date(2026, 2, 10)
        delivery_date = date(2026, 2, 11)  # Tomorrow
        lead_time = 5  # Would put us in the past

        ship_date = service.calculate_ship_date(
            delivery_date, lead_time, from_date=today
        )

        # Should be capped at today
        assert ship_date == today


class TestATPConsumption:
    """Test ATP consumption at ship date"""

    def test_full_fulfillment_at_ship_date(self):
        """Order fully fulfilled from ship date allocations"""
        service = TimePhasedATPService()

        # Setup allocations
        ship_date = date(2026, 2, 10)
        alloc = TimePhasedAllocation(
            date=ship_date,
            priority=2,
            product_id="PROD-001",
            location_id="DC-001",
            allocated_qty=100,
        )
        service.set_allocation(alloc)

        # Request
        request = TimePhasedATPRequest(
            order_id="ORD-001",
            line_id="1",
            product_id="PROD-001",
            location_id="DC-001",
            requested_qty=50,
            priority=2,
            expected_delivery_date=date(2026, 2, 13),
            delivery_lead_time_days=3,
            order_date=date(2026, 2, 2),
        )

        response = service.check_atp(request)

        assert response.can_fulfill is True
        assert response.promised_qty == 50
        assert response.shortfall_qty == 0
        assert response.cascade_required is False
        assert response.actual_consumption_date == ship_date

    def test_partial_fulfillment(self):
        """Order partially fulfilled when insufficient allocation"""
        config = TimePhasedATPConfig(partial_fill_allowed=True, enable_cascade=False)
        service = TimePhasedATPService(config)

        ship_date = date(2026, 2, 10)
        alloc = TimePhasedAllocation(
            date=ship_date,
            priority=2,
            product_id="PROD-001",
            location_id="DC-001",
            allocated_qty=30,
        )
        service.set_allocation(alloc)

        request = TimePhasedATPRequest(
            order_id="ORD-001",
            line_id="1",
            product_id="PROD-001",
            location_id="DC-001",
            requested_qty=50,
            priority=2,
            expected_delivery_date=date(2026, 2, 13),
            delivery_lead_time_days=3,
            order_date=date(2026, 2, 2),
        )

        response = service.check_atp(request)

        assert response.can_fulfill is True
        assert response.promised_qty == 30
        assert response.shortfall_qty == 20

    def test_priority_consumption_sequence(self):
        """Order consumes from own tier first, then lower priorities"""
        service = TimePhasedATPService()

        ship_date = date(2026, 2, 10)

        # Set up allocations for priorities 2, 3, 4, 5
        for priority, qty in [(2, 20), (3, 30), (4, 40), (5, 50)]:
            alloc = TimePhasedAllocation(
                date=ship_date,
                priority=priority,
                product_id="PROD-001",
                location_id="DC-001",
                allocated_qty=qty,
            )
            service.set_allocation(alloc)

        # P2 order requests 80 units
        request = TimePhasedATPRequest(
            order_id="ORD-001",
            line_id="1",
            product_id="PROD-001",
            location_id="DC-001",
            requested_qty=80,
            priority=2,
            expected_delivery_date=date(2026, 2, 13),
            delivery_lead_time_days=3,
            order_date=date(2026, 2, 2),
        )

        response = service.check_atp(request)

        assert response.can_fulfill is True
        assert response.promised_qty == 80

        # Check consumption breakdown: P2 first, then P5, P4, P3
        breakdown = response.consumption_breakdown[ship_date.isoformat()]
        assert breakdown[2] == 20  # Own tier fully consumed
        assert breakdown[5] == 50  # Bottom tier next
        assert breakdown[4] == 10  # Then P4 to fill remaining 10


class TestCascadeLogic:
    """Test backward cascade when ship date has insufficient supply"""

    def test_cascade_backward_to_earlier_date(self):
        """Cascades backward when ship date is empty"""
        service = TimePhasedATPService()

        # No allocation at ship date (Feb 10)
        # Allocation exists at Feb 6 (Friday)
        earlier_date = date(2026, 2, 6)
        alloc = TimePhasedAllocation(
            date=earlier_date,
            priority=2,
            product_id="PROD-001",
            location_id="DC-001",
            allocated_qty=100,
        )
        service.set_allocation(alloc)

        request = TimePhasedATPRequest(
            order_id="ORD-001",
            line_id="1",
            product_id="PROD-001",
            location_id="DC-001",
            requested_qty=50,
            priority=2,
            expected_delivery_date=date(2026, 2, 13),
            delivery_lead_time_days=3,
            order_date=date(2026, 2, 2),
        )

        response = service.check_atp(request)

        assert response.can_fulfill is True
        assert response.promised_qty == 50
        assert response.cascade_required is True
        assert response.cascade_depth > 0
        assert response.actual_consumption_date == earlier_date

    def test_cascade_combines_multiple_dates(self):
        """Cascade can aggregate supply from multiple dates"""
        service = TimePhasedATPService()

        # Allocations at multiple dates
        for day_offset, qty in [(2, 30), (4, 40)]:
            d = date(2026, 2, 2) + timedelta(days=day_offset)
            alloc = TimePhasedAllocation(
                date=d,
                priority=2,
                product_id="PROD-001",
                location_id="DC-001",
                allocated_qty=qty,
            )
            service.set_allocation(alloc)

        request = TimePhasedATPRequest(
            order_id="ORD-001",
            line_id="1",
            product_id="PROD-001",
            location_id="DC-001",
            requested_qty=60,
            priority=2,
            expected_delivery_date=date(2026, 2, 20),
            delivery_lead_time_days=3,
            order_date=date(2026, 2, 2),
        )

        response = service.check_atp(request)

        assert response.can_fulfill is True
        assert response.promised_qty == 60
        assert response.cascade_required is True
        # Should have consumed from multiple dates
        assert len(response.consumption_breakdown) > 0

    def test_cascade_respects_max_depth(self):
        """Cascade stops at max_cascade_days"""
        config = TimePhasedATPConfig(max_cascade_days=2, enable_cascade=True)
        service = TimePhasedATPService(config)

        # Allocation only 5 days ago (beyond max cascade)
        old_date = date(2026, 1, 28)
        alloc = TimePhasedAllocation(
            date=old_date,
            priority=2,
            product_id="PROD-001",
            location_id="DC-001",
            allocated_qty=100,
        )
        service.set_allocation(alloc)

        request = TimePhasedATPRequest(
            order_id="ORD-001",
            line_id="1",
            product_id="PROD-001",
            location_id="DC-001",
            requested_qty=50,
            priority=2,
            expected_delivery_date=date(2026, 2, 13),
            delivery_lead_time_days=3,
            order_date=date(2026, 2, 2),
        )

        response = service.check_atp(request)

        # Cannot fulfill because allocation is beyond max cascade depth
        assert response.can_fulfill is False
        assert response.cascade_required is True


class TestFullExample:
    """
    Full example from user specification:
    - Order 2 weeks before delivery
    - 3-day delivery lead time
    - 5-day work week
    - ATP consumed at day 7
    - Fallback to earlier dates if needed
    """

    def test_user_example_full_fulfillment(self):
        """User's example: 2 weeks out, 3-day lead time, fulfilled at day 7"""
        service = TimePhasedATPService()

        today = date(2026, 2, 2)  # Monday
        two_weeks_out = today + timedelta(days=14)  # Monday, Feb 16

        # Day 7 (business days) from Monday Feb 2 = Wed Feb 11
        day_7 = service.add_business_days(today, 7)
        assert day_7 == date(2026, 2, 11)

        # Set allocation at day 7
        alloc = TimePhasedAllocation(
            date=day_7,
            priority=3,
            product_id="SKU-COFFEE",
            location_id="DC-MIDWEST",
            allocated_qty=500,
        )
        service.set_allocation(alloc)

        # Order placed today, delivery 2 weeks out, 3-day lead time
        request = TimePhasedATPRequest(
            order_id="PO-2026-001",
            line_id="1",
            product_id="SKU-COFFEE",
            location_id="DC-MIDWEST",
            requested_qty=200,
            priority=3,
            expected_delivery_date=two_weeks_out,
            delivery_lead_time_days=3,
            order_date=today,
        )

        response = service.check_atp(request)

        assert response.can_fulfill is True
        assert response.promised_qty == 200
        assert response.calculated_ship_date == day_7
        assert response.actual_consumption_date == day_7
        assert response.cascade_required is False

    def test_user_example_with_cascade(self):
        """
        User's example with cascade:
        - Order 2 weeks out, 3-day lead time
        - Day 7 has no supply
        - Cascade backward to day 5 where supply exists
        """
        service = TimePhasedATPService()

        today = date(2026, 2, 2)
        two_weeks_out = today + timedelta(days=14)

        # Day 5 has supply, day 7 does not
        day_5 = service.add_business_days(today, 5)

        alloc = TimePhasedAllocation(
            date=day_5,
            priority=3,
            product_id="SKU-COFFEE",
            location_id="DC-MIDWEST",
            allocated_qty=500,
        )
        service.set_allocation(alloc)

        request = TimePhasedATPRequest(
            order_id="PO-2026-002",
            line_id="1",
            product_id="SKU-COFFEE",
            location_id="DC-MIDWEST",
            requested_qty=200,
            priority=3,
            expected_delivery_date=two_weeks_out,
            delivery_lead_time_days=3,
            order_date=today,
        )

        response = service.check_atp(request)

        assert response.can_fulfill is True
        assert response.promised_qty == 200
        assert response.cascade_required is True
        assert response.actual_consumption_date == day_5


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

from datetime import date


def test_get_hotel_info(pms):
    hotel = pms.get_hotel_info()
    assert hotel.name == "Grand Oslo Hotel"
    assert hotel.currency == "NOK"


def test_search_guest_found(pms):
    guest = pms.search_guest("erik.hansen@email.com")
    assert guest is not None
    assert guest.first_name == "Erik"
    assert guest.id == "G001"


def test_search_guest_not_found(pms):
    guest = pms.search_guest("nobody@email.com")
    assert guest is None


def test_get_guest(pms):
    guest = pms.get_guest("G002")
    assert guest is not None
    assert guest.last_name == "Gonzalez"


def test_get_reservations(pms):
    reservations = pms.get_reservations("G001")
    assert len(reservations) == 2
    assert all(r.guest_id == "G001" for r in reservations)


def test_get_reservation(pms):
    res = pms.get_reservation("RES001")
    assert res is not None
    assert res.guest_id == "G001"
    assert res.status == "confirmed"


def test_get_reservation_not_found(pms):
    res = pms.get_reservation("RES999")
    assert res is None


def test_check_availability(pms):
    avail = pms.check_availability(date(2025, 4, 20), date(2025, 4, 22))
    assert "2025-04-20" in avail
    assert "2025-04-21" in avail
    assert "2025-04-22" not in avail  # check_out date not included
    assert avail["2025-04-20"]["RT001"] == 2
    assert avail["2025-04-20"]["RT002"] == 1


def test_check_availability_no_rooms(pms):
    avail = pms.check_availability(date(2025, 4, 26), date(2025, 4, 28))
    assert avail["2025-04-26"]["RT001"] == 0
    assert avail["2025-04-26"]["RT004"] == 1


def test_get_room_type(pms):
    room = pms.get_room_type("RT002")
    assert room is not None
    assert room.name == "Standard Double"
    assert room.base_rate_per_night == 1800


def test_get_rate_plans(pms):
    plans = pms.get_rate_plans()
    assert len(plans) == 4
    names = [p.name for p in plans]
    assert "Standard Rate" in names
    assert "Non-Refundable Saver" in names


def test_get_policies(pms):
    policies = pms.get_policies()
    assert "24 hours" in policies.cancellation.standard
    assert "non-refundable" in policies.cancellation.non_refundable.lower()
    assert "300 NOK" in policies.pets


def test_create_guest(pms):
    guest = pms.create_guest(
        first_name="Test",
        last_name="User",
        email="test@email.com",
        phone="+47 000 00 000",
        nationality="NO",
    )
    assert guest.id.startswith("G")
    assert guest.first_name == "Test"
    assert guest.email == "test@email.com"

    # Verify searchable
    found = pms.search_guest("test@email.com")
    assert found is not None
    assert found.id == guest.id


def test_create_reservation(pms):
    res = pms.create_reservation(
        guest_id="G001",
        room_type_id="RT002",
        rate_plan_id="RP001",
        check_in="2025-04-24",
        check_out="2025-04-26",
        adults=2,
        children=0,
        notes="Test booking",
    )
    assert res.id.startswith("RES")
    assert res.status == "confirmed"
    assert res.total_amount == 3600  # 1800 * 2 nights * 1.0 modifier

    # Verify availability decremented
    avail = pms.check_availability(date(2025, 4, 24), date(2025, 4, 26))
    assert avail["2025-04-24"]["RT002"] == 1  # was 2, now 1
    assert avail["2025-04-25"]["RT002"] == 1


def test_create_reservation_no_availability(pms):
    res = pms.create_reservation(
        guest_id="G001",
        room_type_id="RT002",
        rate_plan_id="RP001",
        check_in="2025-04-22",
        check_out="2025-04-24",
        adults=2,
        children=0,
    )
    assert res is None  # RT002 has 0 availability on Apr 22


def test_create_reservation_with_breakfast(pms):
    res = pms.create_reservation(
        guest_id="G001",
        room_type_id="RT002",
        rate_plan_id="RP002",
        check_in="2025-04-24",
        check_out="2025-04-26",
        adults=2,
        children=0,
    )
    assert res is not None
    # 1800 * 2 nights * 1.0 modifier + 250 * 2 adults * 2 nights = 4600
    assert res.total_amount == 4600


def test_cancel_reservation(pms):
    res = pms.cancel_reservation("RES001")
    assert res is not None
    assert res.status == "cancelled"

    # Verify availability restored
    avail = pms.check_availability(date(2025, 4, 20), date(2025, 4, 23))
    assert avail["2025-04-20"]["RT002"] == 2  # was 1, restored to 2


def test_cancel_already_cancelled(pms):
    res = pms.cancel_reservation("RES006")
    assert res is None  # already cancelled


def test_modify_reservation_dates(pms):
    res = pms.modify_reservation("RES001", check_in="2025-04-24", check_out="2025-04-26")
    assert res is not None
    assert res.check_in == "2025-04-24"
    assert res.check_out == "2025-04-26"
    # Total recalculated: 1800 * 2 nights * 1.0 = 3600
    assert res.total_amount == 3600

from __future__ import annotations

import json
from datetime import date

from app.models import (
    Guest,
    Hotel,
    Policies,
    RatePlan,
    Reservation,
    RoomType,
)


class PMS:
    def __init__(self, data_path: str) -> None:
        with open(data_path) as f:
            self._data = json.load(f)

    def get_hotel_info(self) -> Hotel:
        return Hotel(**self._data["hotel"])

    def get_policies(self) -> Policies:
        return Policies(**self._data["policies"])

    def search_guest(self, email: str) -> Guest | None:
        for g in self._data["guests"]:
            if g["email"].lower() == email.lower():
                return Guest(**g)
        return None

    def get_guest(self, guest_id: str) -> Guest | None:
        for g in self._data["guests"]:
            if g["id"] == guest_id:
                return Guest(**g)
        return None

    def get_reservations(self, guest_id: str) -> list[Reservation]:
        return [
            Reservation(**r)
            for r in self._data["reservations"]
            if r["guest_id"] == guest_id
        ]

    def get_reservation(self, reservation_id: str) -> Reservation | None:
        for r in self._data["reservations"]:
            if r["id"] == reservation_id:
                return Reservation(**r)
        return None

    def check_availability(
        self, check_in: date, check_out: date
    ) -> dict[str, dict[str, int]]:
        result = {}
        current = check_in
        while current < check_out:
            date_str = current.isoformat()
            if date_str in self._data["availability"]:
                result[date_str] = dict(self._data["availability"][date_str])
            else:
                result[date_str] = {rt["id"]: 0 for rt in self._data["room_types"]}
            current = date.fromordinal(current.toordinal() + 1)
        return result

    def get_room_type(self, room_type_id: str) -> RoomType | None:
        for rt in self._data["room_types"]:
            if rt["id"] == room_type_id:
                return RoomType(**rt)
        return None

    def get_all_room_types(self) -> list[RoomType]:
        return [RoomType(**rt) for rt in self._data["room_types"]]

    def get_rate_plans(self) -> list[RatePlan]:
        return [RatePlan(**rp) for rp in self._data["rate_plans"]]

    def get_rate_plan(self, rate_plan_id: str) -> RatePlan | None:
        for rp in self._data["rate_plans"]:
            if rp["id"] == rate_plan_id:
                return RatePlan(**rp)
        return None

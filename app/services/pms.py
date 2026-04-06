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

    def _next_id(self, prefix: str, collection: list[dict]) -> str:
        max_num = 0
        for item in collection:
            num = int(item["id"][len(prefix):])
            if num > max_num:
                max_num = num
        return f"{prefix}{max_num + 1:03d}"

    def _calculate_total(
        self, room_type_id: str, rate_plan_id: str, check_in: str, check_out: str, adults: int
    ) -> float:
        room = self.get_room_type(room_type_id)
        rate_plan = self.get_rate_plan(rate_plan_id)
        if not room or not rate_plan:
            return 0

        ci = date.fromisoformat(check_in)
        co = date.fromisoformat(check_out)
        nights = (co - ci).days

        room_cost = room.base_rate_per_night * nights * rate_plan.rate_modifier
        breakfast_cost = 0
        if rate_plan.includes_breakfast and rate_plan.breakfast_supplement_per_person > 0:
            breakfast_cost = rate_plan.breakfast_supplement_per_person * adults * nights

        return room_cost + breakfast_cost

    def create_guest(
        self,
        first_name: str,
        last_name: str,
        email: str,
        phone: str,
        nationality: str,
    ) -> Guest:
        guest_id = self._next_id("G", self._data["guests"])
        guest_data = {
            "id": guest_id,
            "first_name": first_name,
            "last_name": last_name,
            "email": email,
            "phone": phone,
            "nationality": nationality,
            "created_at": date.today().isoformat(),
        }
        self._data["guests"].append(guest_data)
        return Guest(**guest_data)

    def create_reservation(
        self,
        guest_id: str,
        room_type_id: str,
        rate_plan_id: str,
        check_in: str,
        check_out: str,
        adults: int,
        children: int = 0,
        notes: str = "",
    ) -> Reservation | None:
        # Check availability for all nights
        ci = date.fromisoformat(check_in)
        co = date.fromisoformat(check_out)
        avail = self.check_availability(ci, co)
        for date_str, rooms in avail.items():
            if rooms.get(room_type_id, 0) < 1:
                return None

        total = self._calculate_total(room_type_id, rate_plan_id, check_in, check_out, adults)

        res_id = self._next_id("RES", self._data["reservations"])
        res_data = {
            "id": res_id,
            "guest_id": guest_id,
            "room_type_id": room_type_id,
            "rate_plan_id": rate_plan_id,
            "check_in": check_in,
            "check_out": check_out,
            "adults": adults,
            "children": children,
            "status": "confirmed",
            "total_amount": total,
            "notes": notes,
            "created_at": date.today().isoformat(),
        }
        self._data["reservations"].append(res_data)

        # Decrement availability
        current = ci
        while current < co:
            ds = current.isoformat()
            if ds in self._data["availability"]:
                self._data["availability"][ds][room_type_id] -= 1
            current = date.fromordinal(current.toordinal() + 1)

        return Reservation(**res_data)

    def cancel_reservation(self, reservation_id: str) -> Reservation | None:
        for r in self._data["reservations"]:
            if r["id"] == reservation_id:
                if r["status"] == "cancelled":
                    return None
                r["status"] = "cancelled"

                # Restore availability
                ci = date.fromisoformat(r["check_in"])
                co = date.fromisoformat(r["check_out"])
                current = ci
                while current < co:
                    ds = current.isoformat()
                    if ds in self._data["availability"]:
                        self._data["availability"][ds][r["room_type_id"]] += 1
                    current = date.fromordinal(current.toordinal() + 1)

                return Reservation(**r)
        return None

    def modify_reservation(self, reservation_id: str, **changes: str | int) -> Reservation | None:
        for r in self._data["reservations"]:
            if r["id"] == reservation_id and r["status"] == "confirmed":
                # Restore old availability
                old_ci = date.fromisoformat(r["check_in"])
                old_co = date.fromisoformat(r["check_out"])
                current = old_ci
                while current < old_co:
                    ds = current.isoformat()
                    if ds in self._data["availability"]:
                        self._data["availability"][ds][r["room_type_id"]] += 1
                    current = date.fromordinal(current.toordinal() + 1)

                # Apply changes
                for key, value in changes.items():
                    if key in r:
                        r[key] = value

                # Check new availability
                new_ci = date.fromisoformat(r["check_in"])
                new_co = date.fromisoformat(r["check_out"])
                avail = self.check_availability(new_ci, new_co)
                for ds, rooms in avail.items():
                    if rooms.get(r["room_type_id"], 0) < 1:
                        return None

                # Decrement new availability
                current = new_ci
                while current < new_co:
                    ds = current.isoformat()
                    if ds in self._data["availability"]:
                        self._data["availability"][ds][r["room_type_id"]] -= 1
                    current = date.fromordinal(current.toordinal() + 1)

                # Recalculate total
                r["total_amount"] = self._calculate_total(
                    r["room_type_id"],
                    r["rate_plan_id"],
                    r["check_in"],
                    r["check_out"],
                    r["adults"],
                )
                r["status"] = "confirmed"

                return Reservation(**r)
        return None

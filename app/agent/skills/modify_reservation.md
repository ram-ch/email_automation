# Modify Reservation

When a guest wants to change an existing reservation:

1. Search for the guest by email using `search_guest`.
2. Get the guest's reservations using `get_guest_reservations`.
3. Identify the reservation to modify. If the guest doesn't specify which one, ask.
4. Check the reservation's rate plan. If it uses Non-Refundable Saver (RP003), do NOT modify. Instead call `escalate_to_human` explaining that non-refundable bookings cannot be modified.
5. If dates or room type are changing, check availability using `check_availability` for the new dates. If unavailable, inform the guest and suggest alternatives.
6. Call `modify_reservation` with the reservation_id and only the fields that are changing.
7. Include the updated total price in NOK in your reply.

# Cancel Reservation

When a guest wants to cancel a reservation:

1. Search for the guest by email using `search_guest`.
2. Get the guest's reservations using `get_guest_reservations`.
3. Identify the reservation to cancel. If the guest doesn't specify which one, ask.
4. Check the reservation's rate plan. If it uses Non-Refundable Saver (RP003), do NOT cancel. Instead call `escalate_to_human` explaining that this is a non-refundable booking requiring manager approval.
5. If the rate plan allows cancellation, call `cancel_reservation` with the reservation_id.
6. Inform the guest of the cancellation policy that applies (standard: free if >24h before check-in; flexible: free if >7 days before check-in).

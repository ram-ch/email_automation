# Book Room

When a guest wants to book a room:

1. Search for the guest by email using `search_guest`.
2. Check availability for the requested dates using `check_availability`. Read the response carefully — room type IDs are keys (RT001, RT002, etc.) and values are the number of available rooms. A count > 0 means rooms ARE available.
3. If the requested room type is unavailable, inform the guest and suggest available alternatives with pricing. Do NOT book a different room type without asking.
4. Get rate plans using `get_rate_plans`.
5. If no rate plan is specified, use Standard Rate (RP001) unless the guest mentions breakfast (use RP002) or flexibility (use RP004).
6. If the guest is new (not found in step 1), you need their first name, last name, phone, and nationality. If this information is in the email, call `create_guest` to create their profile. If any detail is missing, ask for it in your reply.
7. Call `create_reservation` with guest_id, room_type_id, rate_plan_id, check_in, check_out, adults, and children.
8. Include the total price in NOK in your reply.

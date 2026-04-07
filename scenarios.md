# Test Scenarios

Use these with the FastAPI endpoint. Start the server, then send each as a POST request in Postman:

```
POST http://localhost:8000/process-email?response_format=html
Content-Type: application/json
```

---

## Required Scenarios

### 1. Read-Only Lookup

Guest asks about availability — no PMS writes expected.

```json
{
  "sender_email": "someone@email.com",
  "body": "Do you have any available rooms April 20th-22nd?"
}
```

### 2. Action + Write to PMS (Booking)

Guest books a room — action plan generated, PMS write on approval.

```json
{
  "sender_email": "erik.hansen@email.com",
  "body": "Hi, we'd like to book a double room with breakfast for 2 adults for April 24th-26th."
}
```

### 3. Ambiguous / Risky Request

Non-refundable refund request — must be escalated, no PMS writes.

```json
{
  "sender_email": "maria.gonzalez@email.com",
  "body": "I want a refund on my non-refundable booking."
}
```

---

## Additional Scenarios

### 4. Multi-Booking in One Email

```json
{
  "sender_email": "newguest@test.com",
  "body": "I'd like to book 2 rooms for April 24-26 -- one Standard Double for my wife and me, and one Standard Single for my mother. Breakfast for all. My name is Lisa Berg, phone +47 555 1234, Norwegian."
}
```

### 5. Modify a Non-Refundable Booking

```json
{
  "sender_email": "yuki.tanaka@email.com",
  "body": "Can I change my reservation to April 21-23 instead?"
}
```

### 6. Booking Dates Outside Availability Range

```json
{
  "sender_email": "someone@test.com",
  "body": "Do you have rooms available May 1-3?"
}
```

### 7. Check-In Date in the Past

```json
{
  "sender_email": "erik.hansen@email.com",
  "body": "I'd like to book a Standard Single for April 10-12."
}
```

### 8. Ambiguous Cancel — Multiple Reservations

```json
{
  "sender_email": "erik.hansen@email.com",
  "body": "Please cancel my booking."
}
```

### 9. Upgrade Request (Room Type Change)

```json
{
  "sender_email": "erik.hansen@email.com",
  "body": "Can you upgrade my April 20-23 reservation to a Junior Suite?"
}
```

### 10. Unauthorized Cancellation Attempt

```json
{
  "sender_email": "unknown@random.com",
  "body": "Cancel reservation RES001."
}
```

### 11. Booking with Zero Availability + Alternatives

```json
{
  "sender_email": "anna.berg@email.com",
  "body": "I want to book a Standard Double for April 26-27."
}
```

### 12. Rate Plan Math

```json
{
  "sender_email": "erik.hansen@email.com",
  "body": "How much would a Junior Suite cost for April 24-26 with the Non-Refundable Saver rate?"
}
```

### 13. Policy Question with a Twist (15kg Dog)

```json
{
  "sender_email": "james.smith@email.com",
  "body": "I have a 15kg dog. Can I bring it to the hotel?"
}
```

### 14. Cancellation Policy Calculation

```json
{
  "sender_email": "james.smith@email.com",
  "body": "What's the cancellation fee if I cancel my April 25-27 reservation today?"
}
```

### 15. Non-Existent Room Type

```json
{
  "sender_email": "someone@test.com",
  "body": "I'd like to book a Presidential Suite for April 20-22."
}
```

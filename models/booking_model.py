
from datetime import datetime, timezone
from bson.objectid import ObjectId


def _normalize_status(value):
    """
    Normalize status / payment_status strings to a consistent format.
    We keep existing title-cased values like 'Pending', 'Confirmed', 'Cancelled'.
    """
    if not isinstance(value, str):
        return value
    # Preserve common canonical values, otherwise title-case
    known = {
        "pending": "Pending",
        "confirmed": "Confirmed",
        "cancelled": "Cancelled",
        "failed": "Failed",
    }
    return known.get(value.lower(), value.title())


def create_booking(
    db,
    user_id,
    booking_details,
    amount,
    currency,
    status="Pending",
    razorpay_order_id=None,
    payment_status="Pending",
):
    """
    Create a booking document.

    - status: lifecycle of the booking itself (Pending / Confirmed / Cancelled / Failed)
    - payment_status: lifecycle of the payment (Pending / Paid / Failed)
    """
    booking_status = _normalize_status(status)
    payment_status_norm = _normalize_status(payment_status)

    booking = {
        "user_id": user_id,
        "booking_details": booking_details,
        "amount": amount,
        "currency": currency,
        "status": booking_status,
        "payment_status": payment_status_norm,
        "razorpay_order_id": razorpay_order_id,
        "created_at": datetime.now(timezone.utc),
        "date": booking_details.get("date"),
        "slot": booking_details.get("slot"),
        "user_name": booking_details.get("user_name") or booking_details.get("name"),
        "phone": booking_details.get("phone"),
        "email": booking_details.get("email"),
        "group_size": booking_details.get("group_size"),
        "raft_allocations": booking_details.get("raft_allocations", []),
        "raft_allocation_details": booking_details.get("raft_allocation_details", []),
    }
    return db.bookings.insert_one(booking).inserted_id


def update_booking_status(
    db,
    booking_id,
    status=None,
    razorpay_payment_id=None,
    payment_status=None,
    raft_allocations=None,
    extra_updates=None,
):
    """
    Update booking status and related payment fields in a single, atomic update.

    - status: booking lifecycle status
    - payment_status: payment lifecycle status
    - razorpay_payment_id: last successful payment id (if any)
    - raft_allocations: allow admin flows to adjust stored raft ids
    - extra_updates: dict of any additional fields to $set
    """
    update = {}

    if status is not None:
        update["status"] = _normalize_status(status)
    if payment_status is not None:
        update["payment_status"] = _normalize_status(payment_status)
    if razorpay_payment_id:
        update["razorpay_payment_id"] = razorpay_payment_id
    if raft_allocations is not None:
        update["raft_allocations"] = raft_allocations
    if extra_updates:
        update.update(extra_updates)

    if not update:
        return

    db.bookings.update_one({"_id": ObjectId(booking_id)}, {"$set": update})


def get_booking(db, booking_id):
    return db.bookings.find_one({"_id": ObjectId(booking_id)})

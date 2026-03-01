"""
Razorpay Payment Integration Blueprint
"""
import os
import logging
from datetime import datetime

from bson import ObjectId
from flask import Blueprint, request, jsonify, current_app
from flask_login import login_required, current_user
from werkzeug.exceptions import BadRequest
from pymongo import ReturnDocument
import razorpay

from models.booking_model import create_booking, update_booking_status, get_booking
from models.payment_model import insert_payment
from utils.allocation_logic import load_settings, allocate_raft
from utils.amount_calculator import calculate_total_amount


payment_bp = Blueprint("payment", __name__, url_prefix="/payment")

logger = logging.getLogger("payment")
logger.setLevel(logging.INFO)

# In production, prefer configuring these via environment / Config
razorpay_client = razorpay.Client(
    auth=(
        os.environ.get("RAZORPAY_KEY_ID", "rzp_test_SLoMv8ODDZOJqO"),
        os.environ.get("RAZORPAY_KEY_SECRET", "RaGDqalgbz3me6HEIBi5yQxV"),
    )
)


def get_db():
    """
    Always use the same database handle as the rest of the app.
    This avoids subtle bugs where create_booking and payment flows
    talk to different default databases.
    """
    return current_app.mongo.db


@payment_bp.route("/create_order", methods=["POST"])
@login_required
def create_order():
    """
    Create a Razorpay order for an existing booking.

    - Does NOT create a new booking (avoids duplicates).
    - Is idempotent per booking: if an order already exists, it is reused.
    """
    data = request.get_json() or {}

    booking_id = data.get("booking_id")
    if not booking_id:
        logger.warning("create_order called without booking_id")
        raise BadRequest("booking_id is required")

    db = get_db()
    try:
        booking = db.bookings.find_one({"_id": ObjectId(booking_id)})
    except Exception:
        logger.exception("Invalid booking id supplied to create_order")
        raise BadRequest("Invalid booking id")

    if not booking:
        logger.warning("Booking not found for create_order: %s", booking_id)
        raise BadRequest("Booking not found")

    # Basic state guard: do not allow payment for cancelled / already-confirmed bookings
    status = (booking.get("status") or "").lower()
    if status in {"cancelled", "failed"}:
        logger.info("Payment requested for non-payable booking %s with status=%s", booking_id, status)
        return jsonify({"error": "Booking is not in a payable state"}), 400
    currency = booking.get("currency", "INR")

    # Compute pricing based on system settings so that we can correctly
    # distinguish between TOTAL amount and ADVANCE amount. The Razorpay
    # order should only charge the advance, not the full trip price.
    settings = load_settings(db)
    try:
        group_size = int(booking.get("group_size", 0) or 0)
    except (TypeError, ValueError):
        group_size = 0

    pricing = calculate_total_amount(settings, booking.get("date"), group_size)
    total_amount = pricing.get("total_amount") or booking.get("amount")
    advance_amount = pricing.get("advance_amount")

    # Fallback: if advance could not be computed, charge total to avoid zero orders
    amount_to_charge = advance_amount if advance_amount and advance_amount > 0 else total_amount

    if not amount_to_charge or amount_to_charge <= 0:
        logger.warning("Invalid payable amount for %s: %s", booking_id, amount_to_charge)
        raise BadRequest("Invalid amount")

    existing_order_id = booking.get("razorpay_order_id")
    order_id = existing_order_id

    if existing_order_id:
        logger.info(
            "Reusing existing Razorpay order %s for booking %s", existing_order_id, booking_id
        )
    else:
        amount_paise = int(amount_to_charge * 100)
        order = razorpay_client.order.create(
            {
                "amount": amount_paise,
                "currency": currency,
                "payment_capture": 1,
            }
        )
        order_id = order["id"]
        db.bookings.update_one(
            {"_id": booking["_id"]},
            {
                "$set": {
                    "razorpay_order_id": order_id,
                    # ensure payment_status is set to Pending on order creation
                    "payment_status": "Pending",
                    "payment_order_created_at": datetime.utcnow(),
                }
            },
        )
        logger.info("Razorpay order %s created for booking %s", order_id, booking_id)

    return jsonify(
        {
            "order_id": order_id,
            # Expose the ADVANCE amount to the frontend / Razorpay checkout
            "amount": amount_to_charge,
            "currency": currency,
            "booking_id": str(booking["_id"]),
            # Must match the key used in razorpay_client
            "razorpay_key_id": os.environ.get("RAZORPAY_KEY_ID", "rzp_test_SLoMv8ODDZOJqO"),
        }
    )


@payment_bp.route("/verify_payment", methods=["POST"])
@login_required
def verify_payment():
    """
    Verify Razorpay payment signature and update booking/payment atomically.

    Rules:
    - Never mark a booking as Confirmed before signature verification.
    - Use razorpay_order_id (server-side value) to locate the booking.
    - Idempotent: if the same payment is verified twice, do not double-update.
    """
    data = request.get_json() or {}

    booking_id = data.get("booking_id")
    order_id = data.get("order_id")
    payment_id = data.get("payment_id")
    signature = data.get("signature")

    if not order_id or not payment_id or not signature:
        logger.warning("verify_payment missing required fields: %s", data)
        raise BadRequest("order_id, payment_id and signature are required")

    db = get_db()

    # First, verify the Razorpay payment signature
    try:
        razorpay_client.utility.verify_payment_signature(
            {
                "razorpay_order_id": order_id,
                "razorpay_payment_id": payment_id,
                "razorpay_signature": signature,
            }
        )
    except razorpay.errors.SignatureVerificationError:
        logger.error(
            "Signature verification failed for order_id=%s payment_id=%s booking_id=%s",
            order_id,
            payment_id,
            booking_id,
        )
        # Best-effort mark as failed if we can locate the booking
        if booking_id:
            try:
                update_booking_status(db, booking_id, status="Failed", payment_status="Failed")
            except Exception:
                logger.exception("Failed to update booking status after signature failure")
        else:
            db.bookings.update_one(
                {"razorpay_order_id": order_id},
                {"$set": {"status": "Failed", "payment_status": "Failed"}},
            )
        return jsonify({"success": False, "message": "Payment verification failed"}), 400

    # Locate booking by server-controlled razorpay_order_id, optionally verifying client booking_id
    booking_filter = {"razorpay_order_id": order_id}
    if booking_id:
        try:
            booking_filter["_id"] = ObjectId(booking_id)
        except Exception:
            logger.warning("verify_payment received invalid booking_id %s; ignoring id filter", booking_id)

    booking = db.bookings.find_one(booking_filter)
    if not booking:
        logger.error(
            "No booking found for verified payment. order_id=%s booking_id=%s",
            order_id,
            booking_id,
        )
        return jsonify({"success": False, "message": "Booking not found for this payment"}), 404

    # Idempotency: if already confirmed and paid with this payment id, just return success
    if (
        booking.get("status") == "Confirmed"
        and booking.get("payment_status") == "Paid"
        and booking.get("razorpay_payment_id") == payment_id
    ):
        logger.info("Payment already processed for booking %s (idempotent verify)", booking["_id"])
        return jsonify({"success": True, "message": "Payment already processed"})

    if booking.get("status") == "Cancelled":
        logger.warning(
            "Verified payment received for cancelled booking %s / order %s",
            booking["_id"],
            order_id,
        )
        return (
            jsonify({"success": False, "message": "Booking is cancelled. Please contact support."}),
            409,
        )

    # STEP 1: Allocate rafts AFTER successful payment, so that only
    # confirmed bookings reserve seats and appear in occupancy.
    # If this booking already has raft allocations (legacy data), reuse them.
    raft_allocations = booking.get("raft_allocations") or []
    raft_details = booking.get("raft_allocation_details") or []

    if not raft_allocations:
        booking_date = booking.get("date") or booking.get("booking_details", {}).get("date")
        slot = booking.get("slot") or booking.get("booking_details", {}).get("slot")
        try:
            group_size = int(
                booking.get("group_size")
                or booking.get("booking_details", {}).get("group_size")
                or 0
            )
        except (TypeError, ValueError):
            group_size = 0

        if not booking_date or not slot or group_size <= 0:
            logger.error(
                "Booking missing date/slot/group_size for allocation. booking_id=%s", booking["_id"]
            )
            return (
                jsonify(
                    {
                        "success": False,
                        "message": "Booking data incomplete for seat allocation. Please contact support.",
                    }
                ),
                500,
            )

        alloc_res = allocate_raft(db, None, booking_date, slot, group_size)
        if alloc_res.get("status") != "Confirmed":
            # Payment succeeded but we could not allocate seats due to race/full capacity.
            # Do NOT reserve seats; mark booking for manual resolution.
            logger.error(
                "Allocation failed after payment. booking_id=%s date=%s slot=%s group_size=%s res=%s",
                booking["_id"],
                booking_date,
                slot,
                group_size,
                alloc_res,
            )
            update_booking_status(
                db,
                str(booking["_id"]),
                status="Pending",
                payment_status="Paid",
                extra_updates={"allocation_error": True},
            )
            return (
                jsonify(
                    {
                        "success": False,
                        "message": "Payment received but slot is now full. Our team will contact you.",
                    }
                ),
                409,
            )

        raft_allocations = alloc_res.get("rafts", []) or []
        raft_details = alloc_res.get("raft_details", []) or []

    # STEP 2: Update booking to Confirmed + Paid in a single atomic operation,
    # including the final raft assignments used for occupancy and admin flows.
    updated = db.bookings.find_one_and_update(
        booking_filter,
        {
            "$set": {
                "status": "Confirmed",
                "payment_status": "Paid",
                "razorpay_payment_id": payment_id,
                "payment_verified_at": datetime.utcnow(),
                "raft_allocations": raft_allocations,
                "raft_allocation_details": raft_details,
            }
        },
        return_document=ReturnDocument.AFTER,
    )

    if not updated:
        # Another process may have updated it concurrently; treat as idempotent
        logger.warning(
            "Booking update race for order_id=%s booking_id=%s", order_id, booking.get("_id")
        )
        return jsonify({"success": True, "message": "Payment already processed"}), 200

    # Record payment in a separate collection (idempotent insert)
    existing_payment = db.payments.find_one({"payment_id": payment_id})
    if not existing_payment:
        insert_payment(
            db,
            booking_id=str(updated["_id"]),
            order_id=order_id,
            payment_id=payment_id,
            signature=signature,
            amount=updated.get("amount"),
            status="paid",
            raw_response=data,
        )
    else:
        db.payments.update_one(
            {"_id": existing_payment["_id"]},
            {"$set": {"status": "paid", "raw_response": data}},
        )

    logger.info(
        "Payment verified and booking confirmed. booking_id=%s order_id=%s payment_id=%s",
        updated["_id"],
        order_id,
        payment_id,
    )
    return jsonify({"success": True, "message": "Payment successful"})


@payment_bp.route("/webhook", methods=["POST"])
def razorpay_webhook():
    """
    Handle Razorpay webhook events (idempotent).

    Webhook is a secondary safety net: it should not conflict with the
    client-side /verify_payment flow and must be idempotent.
    """
    payload = request.data
    signature = request.headers.get("X-Razorpay-Signature")
    webhook_secret = os.environ.get("RAZORPAY_WEBHOOK_SECRET")
    db = get_db()

    try:
        razorpay_client.utility.verify_webhook_signature(payload, signature, webhook_secret)
    except razorpay.errors.SignatureVerificationError:
        logger.error("Webhook signature verification failed")
        return jsonify({"success": False}), 400

    body = request.json or {}
    event = body.get("event")
    payment_entity = body.get("payload", {}).get("payment", {}).get("entity", {}) or {}

    order_id = payment_entity.get("order_id")
    payment_id = payment_entity.get("id")
    status = payment_entity.get("status")

    # Ensure we only process each payment id once
    payment_record = db.payments.find_one({"payment_id": payment_id})
    if payment_record and payment_record.get("webhook_verified"):
        logger.info("Webhook already processed for payment %s", payment_id)
        return jsonify({"success": True})

    db.payments.update_one(
        {"payment_id": payment_id},
        {
            "$set": {
                "webhook_verified": True,
                "status": status,
                "webhook_payload": body,
            }
        },
        upsert=True,
    )

    # Best-effort sync to booking using razorpay_order_id
    if event == "payment.captured" and status == "captured":
        db.bookings.update_one(
            {"razorpay_order_id": order_id},
            {
                "$set": {
                    "payment_status": "Paid",
                    # Do not downgrade a cancelled booking; only confirm if not explicitly cancelled
                }
            },
        )
    elif event == "payment.failed":
        db.bookings.update_one(
            {"razorpay_order_id": order_id},
            {
                "$set": {
                    "payment_status": "Failed",
                }
            },
        )

    logger.info("Webhook processed: %s for payment %s", event, payment_id)
    return jsonify({"success": True})


@payment_bp.route("/success", methods=["GET"])
def payment_success():
    return (
        "<h2>Payment Successful!</h2><p>Your booking and payment have been confirmed. "
        "Thank you! <a href='/'>Back to Home</a></p>",
        200,
    )


@payment_bp.route("/failure", methods=["GET"])
def payment_failure():
    return (
        "<h2>Payment Failed</h2><p>Your payment could not be processed. "
        "Please try again or contact support. <a href='/'>Back to Home</a></p>",
        200,
    )

#!/usr/bin/env python3
"""
Stress test: run 100 iterations of booking + postpone and check for
any redundancy / mismatch in raft occupancy for the old slot.
"""

import sys
from datetime import date, timedelta

sys.path.insert(0, str('/'.join(__file__.split('\\')[:-2])))

from config import MONGO_URI  # type: ignore
from pymongo import MongoClient  # type: ignore
from utils.booking_ops import postpone_booking  # type: ignore
from utils.allocation_logic import allocate_raft, load_settings  # type: ignore
from models.raft_model import ensure_rafts_for_date_slot  # type: ignore


def init_test_db(db):
    """Ensure admin user and settings exist."""
    admin = db.users.find_one({'email': 'admin@test.com'})
    if not admin:
        db.users.insert_one(
            {
                'email': 'admin@test.com',
                'name': 'Admin',
                'password_hash': 'hashed_pass',
                'is_admin': True,
            }
        )

    settings = db.settings.find_one({'_id': 'system_settings'})
    if not settings:
        db.settings.insert_one(
            {
                '_id': 'system_settings',
                'capacity': 6,
                'rafts_per_slot': 5,
                'time_slots': ['9:00 AM', '12:00 PM', '3:00 PM'],
            }
        )
    return db


def clean_test_data(db):
    """Clean all test bookings and rafts."""
    db.bookings.delete_many({})
    db.rafts.delete_many({})


def verify_occupancy_integrity(db, date_str, slot):
    """Verify occupancy is consistent between bookings and rafts."""
    rafts = list(db.rafts.find({'day': date_str, 'slot': slot}))
    bookings = list(
        db.bookings.find({'date': date_str, 'slot': slot, 'status': 'Confirmed'})
    )

    raft_total = sum(r.get('occupancy', 0) for r in rafts)
    booking_total = sum(b.get('group_size', 0) for b in bookings)

    return raft_total == booking_total, raft_total, booking_total


def run_stress_test_100():
    """
    Run 100 cycles of:
      - create booking in old slot
      - postpone to a new date
      - verify old slot has no residual occupancy
    """
    print("\n=== STRESS TEST: 100× booking + postpone ===")
    client = MongoClient(MONGO_URI)
    db = client['raft_booking_db']

    try:
        init_test_db(db)
        clean_test_data(db)

        settings = load_settings(db)
        slot = '9:00 AM'

        old_date = date.today().isoformat()

        # Prepare multiple distinct future dates as postpone targets so no single slot exceeds capacity.
        # With group_size=4 and max_people_per_slot=35, each date can safely handle many iterations.
        target_dates = [
            (date.today() + timedelta(days=i + 1)).isoformat() for i in range(20)
        ]

        # Ensure rafts exist for all involved dates/slots.
        ensure_rafts_for_date_slot(
            db, old_date, slot, settings['rafts_per_slot'], settings['capacity']
        )
        for d in target_dates:
            ensure_rafts_for_date_slot(
                db, d, slot, settings['rafts_per_slot'], settings['capacity']
            )

        max_people_per_slot = settings.get('rafts_per_slot', 5) * (
            settings['capacity'] + 1
        )

        iterations = 100
        group_size = 4  # chosen to follow regular allocation rules (>=4) and stay under capacity

        print(f"Configured max people per slot: {max_people_per_slot}")
        print(f"Running {iterations} iterations with group_size={group_size}")

        for i in range(iterations):
            target_date = target_dates[i % len(target_dates)]

            # Step 1: create a booking in the old slot
            res = allocate_raft(db, 'stress@test.com', old_date, slot, group_size)
            if res.get('status') != 'Confirmed':
                print(f"[FAIL] Iteration {i+1}: allocation failed: {res}")
                return False

            booking_doc = {
                'email': 'stress@test.com',
                'date': old_date,
                'slot': slot,
                'group_size': group_size,
                'status': 'Confirmed',
                'raft_allocations': res.get('rafts', []),
            }
            bid = db.bookings.insert_one(booking_doc).inserted_id

            ok, raft_total, booking_total = verify_occupancy_integrity(
                db, old_date, slot
            )
            if not ok:
                print(
                    f"[FAIL] Iteration {i+1}: integrity mismatch BEFORE postpone "
                    f"in old slot: raft={raft_total}, booking={booking_total}"
                )
                return False

            # Step 2: postpone to target_date
            result = postpone_booking(db, bid, target_date, slot)
            if 'error' in result:
                print(
                    f"[FAIL] Iteration {i+1}: postpone failed to {target_date}: "
                    f"{result['error']}"
                )
                return False

            # Step 3: verify old slot is fully freed
            ok_old, raft_old, booking_old = verify_occupancy_integrity(
                db, old_date, slot
            )
            if not ok_old or raft_old != 0 or booking_old != 0:
                print(
                    f"[FAIL] Iteration {i+1}: redundancy detected in old slot "
                    f"after postpone: raft={raft_old}, booking={booking_old}"
                )
                return False

            # Step 4: verify new slot integrity and capacity bounds
            ok_new, raft_new, booking_new = verify_occupancy_integrity(
                db, target_date, slot
            )
            if not ok_new:
                print(
                    f"[FAIL] Iteration {i+1}: integrity mismatch in new slot "
                    f"{target_date}: raft={raft_new}, booking={booking_new}"
                )
                return False

            if raft_new > max_people_per_slot:
                print(
                    f"[FAIL] Iteration {i+1}: capacity exceeded in new slot "
                    f"{target_date}: raft_total={raft_new}, max={max_people_per_slot}"
                )
                return False

            if (i + 1) % 10 == 0:
                print(
                    f"[OK] Completed {i+1} / {iterations} iterations "
                    f"(latest target_date={target_date}, raft_total_new={raft_new})"
                )

        print(
            f"[PASS] STRESS TEST PASSED: {iterations} iterations with no "
            "redundancy or occupancy mismatch in old slots."
        )
        return True

    finally:
        client.close()


def main():
    passed = run_stress_test_100()
    return 0 if passed else 1


if __name__ == '__main__':
    sys.exit(main())


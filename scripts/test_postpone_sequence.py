#!/usr/bin/env python3
"""
Test script to reproduce the user's postpone sequence and verify raft occupancies.
Sequence:
 - Book groups: 9, 8, 12, 1 into the same slot/day
 - Postpone the 8-person booking to another slot
 - Postpone the 9-person booking to that same target slot
 - Verify the original slot's raft occupancies and totals

Run: python scripts/test_postpone_sequence.py
"""
import sys
from datetime import date, timedelta
from pymongo import MongoClient
from config import MONGO_URI

# allow imports from project
sys.path.insert(0, '..')

from utils.allocation_logic import allocate_raft, load_settings
from models.raft_model import ensure_rafts_for_date_slot
from utils.booking_ops import postpone_booking


def print_slot_details(db, day, slot):
    print(f"Slot state for {day} {slot}:")
    rafts = list(db.rafts.find({'day': day, 'slot': slot}).sort('raft_id', 1))
    if not rafts:
        print("  (no rafts)")
        return
    total = 0
    for r in rafts:
        occ = r.get('occupancy', 0)
        total += occ
        print(f"  Raft {r['raft_id']}: {occ}/{r.get('capacity', 6)}")
    print(f"  Total occupancy: {total}\n")
    return total


def main():
    client = MongoClient(MONGO_URI)
    db = client.get_database('raft_booking')

    settings = load_settings(db)
    slots = settings.get('time_slots', [])
    if not slots:
        print('No time slots in settings; aborting')
        return 1

    slot_old = slots[0]
    slot_new = slots[1] if len(slots) > 1 else slots[0]

    day_old = (date.today() + timedelta(days=1)).isoformat()  # test date in future
    day_new = (date.today() + timedelta(days=2)).isoformat()

    print('Ensuring rafts exist for test slots...')
    ensure_rafts_for_date_slot(db, day_old, slot_old, settings['rafts_per_slot'], settings['capacity'])
    ensure_rafts_for_date_slot(db, day_new, slot_new, settings['rafts_per_slot'], settings['capacity'])
    # Reset any existing occupancies on those slots for a clean test
    db.rafts.update_many({'day': day_old, 'slot': slot_old}, {'$set': {'occupancy': 0, 'is_special': False}})
    db.rafts.update_many({'day': day_new, 'slot': slot_new}, {'$set': {'occupancy': 0, 'is_special': False}})

    # Clean any test bookings for this email to reduce interference
    db.bookings.delete_many({'email': 'test.postpone@example.com'})

    sizes = [9, 8, 12, 1]
    booking_ids = []

    print('Creating bookings on', day_old, slot_old)
    for size in sizes:
        res = allocate_raft(db, None, day_old, slot_old, size)
        if res.get('status') != 'Confirmed':
            print('Allocation failed for', size, res)
            return 2

        booking_doc = {
            'email': 'test.postpone@example.com',
            'date': day_old,
            'slot': slot_old,
            'group_size': size,
            'status': 'Confirmed',
            'raft_allocations': res.get('rafts', []),
            'raft_allocation_details': res.get('raft_details', [])
        }
        r = db.bookings.insert_one(booking_doc)
        booking_ids.append(r.inserted_id)
        print('  Created booking', r.inserted_id, 'size', size, 'rafts', res.get('rafts', []))

    print_slot_details(db, day_old, slot_old)

    # Postpone the 8-person booking (find by group_size)
    bid_8 = None
    bid_9 = None
    for bid in booking_ids:
        b = db.bookings.find_one({'_id': bid})
        if b.get('group_size') == 8 and bid_8 is None:
            bid_8 = bid
        if b.get('group_size') == 9 and bid_9 is None:
            bid_9 = bid

    if not bid_8 or not bid_9:
        print('Could not find required bookings in DB; aborting')
        return 3

    print('\nPostponing the 8-person booking...')
    res = postpone_booking(db, bid_8, day_new, slot_new)
    print('Postpone result:', res)
    print_slot_details(db, day_old, slot_old)
    print_slot_details(db, day_new, slot_new)

    print('\nPostponing the 9-person booking...')
    res2 = postpone_booking(db, bid_9, day_new, slot_new)
    print('Postpone result:', res2)
    print_slot_details(db, day_old, slot_old)
    print_slot_details(db, day_new, slot_new)

    # Verify expectations: old slot should have remaining sizes 12 and 1 => total 13
    total_after = sum(r.get('occupancy', 0) for r in db.rafts.find({'day': day_old, 'slot': slot_old}))
    print('Final total occupancy on old slot:', total_after)
    if total_after != 13:
        print('TEST FAILED: expected total 13 on old slot (12+1).')
        return 4

    # Also check at least one raft has occupancy 1 (the single-person booking)
    has_one = any(r.get('occupancy', 0) == 1 for r in db.rafts.find({'day': day_old, 'slot': slot_old}))
    if not has_one:
        print('TEST WARNING: no raft shows occupancy=1; mapping may be wrong even if total matches.')
        return 5

    print('\nTEST PASSED: old slot total and per-raft presence look correct.')
    return 0


if __name__ == '__main__':
    exit(main())

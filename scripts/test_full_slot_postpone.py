#!/usr/bin/env python3
"""
Comprehensive test: randomly fill a slot to capacity, then postpone all bookings
one by one, checking raft occupancy consistency at each step.

Run: python scripts/test_full_slot_postpone.py
"""
import sys
import random
from datetime import date, timedelta
from pymongo import MongoClient
from config import MONGO_URI

sys.path.insert(0, '.')

from utils.allocation_logic import allocate_raft, load_settings
from models.raft_model import ensure_rafts_for_date_slot
from utils.booking_ops import postpone_booking


def print_slot_occupancy(db, day, slot, title=""):
    """Print raft occupancy for a slot."""
    rafts = list(db.rafts.find({'day': day, 'slot': slot}).sort('raft_id', 1))
    if not rafts:
        print(f"  {title} (no rafts)")
        return 0
    
    total = sum(r.get('occupancy', 0) for r in rafts)
    details = ", ".join([f"R{r['raft_id']}:{r.get('occupancy', 0)}" for r in rafts])
    print(f"  {title} slot occupancy: {total} [{details}]")
    return total


def book_random_sizes_to_fill_slot(db, day, slot, settings):
    """
    Randomly create bookings to fill a slot as much as possible.
    Returns list of booking IDs and their group sizes.
    """
    rafts_per_slot = settings['rafts_per_slot']
    capacity = settings['capacity']
    max_per_slot = rafts_per_slot * capacity  # standard capacity
    
    # Ensure rafts exist
    ensure_rafts_for_date_slot(db, day, slot, rafts_per_slot, capacity)
    
    # Reset occupancies for clean test
    db.rafts.update_many({'day': day, 'slot': slot}, {'$set': {'occupancy': 0, 'is_special': False}})
    
    booking_ids = []
    booked_sizes = []
    total_booked = 0
    
    print(f"\nRandomly filling slot: {day} {slot}")
    print(f"  Capacity: {max_per_slot} per slot (5 rafts × 6 capacity)")
    
    while total_booked < max_per_slot:
        remaining = max_per_slot - total_booked
        # Random size between 1 and remaining, but reasonable (1-12)
        max_size = min(12, remaining)
        if max_size < 1:
            break
        
        size = random.randint(1, max_size)
        
        # Try to allocate
        res = allocate_raft(db, None, day, slot, size)
        
        if res.get('status') != 'Confirmed':
            print(f"  Allocation failed for size {size}: {res['message']}")
            break
        
        # Create booking
        booking_doc = {
            'email': 'test.fullslot@example.com',
            'date': day,
            'slot': slot,
            'group_size': size,
            'status': 'Confirmed',
            'raft_allocations': res.get('rafts', []),
            'raft_allocation_details': res.get('raft_details', [])
        }
        r = db.bookings.insert_one(booking_doc)
        booking_ids.append(r.inserted_id)
        booked_sizes.append(size)
        total_booked += size
        
        print(f"  Booked: {size} people (allocated to rafts {res.get('rafts', [])})")
    
    occupancy_before = print_slot_occupancy(db, day, slot, "After bookings")
    print(f"  Total bookings: {len(booked_sizes)} (sizes: {booked_sizes})")
    
    return booking_ids, booked_sizes, occupancy_before


def postpone_all_bookings(db, day_from, day_to, slot_from, slot_to, booking_ids, booked_sizes):
    """
    Postpone all bookings from one slot to another one by one,
    checking occupancy consistency at each step.
    """
    settings = load_settings(db)
    
    # Ensure target slot exists
    ensure_rafts_for_date_slot(db, day_to, slot_to, settings['rafts_per_slot'], settings['capacity'])
    
    print(f"\nPostponing all {len(booking_ids)} bookings from {day_from} {slot_from} → {day_to} {slot_to}")
    
    issues = []
    
    for idx, bid in enumerate(booking_ids):
        b = db.bookings.find_one({'_id': bid})
        size = b.get('group_size', 0)
        raft_details = b.get('raft_allocation_details', [])
        
        print(f"\n  [{idx+1}/{len(booking_ids)}] Postponing booking (size={size}) with details: {raft_details}")
        
        # Occupancy before
        occ_before = sum(r.get('occupancy', 0) for r in db.rafts.find({'day': day_from, 'slot': slot_from}))
        print(f"    Old slot before: {occ_before}")
        
        # Postpone
        res = postpone_booking(db, bid, day_to, slot_to)
        if 'error' in res:
            print(f"    ERROR: {res['error']}")
            issues.append(f"Postpone {idx+1} failed: {res['error']}")
            continue
        
        # Occupancy after
        occ_after = sum(r.get('occupancy', 0) for r in db.rafts.find({'day': day_from, 'slot': slot_from}))
        print(f"    Old slot after: {occ_after}")
        
        expected_after = occ_before - size
        if occ_after != expected_after:
            msg = f"Postpone {idx+1}: old slot occupancy {occ_after} != expected {expected_after} (was {occ_before}, removed {size})"
            print(f"    ⚠️  {msg}")
            issues.append(msg)
        else:
            print(f"    ✓ Occupancy correct")
        
        # Check old slot state
        print_slot_occupancy(db, day_from, slot_from, "    Old slot detail")
    
    if issues:
        print(f"\n⚠️  Issues found:")
        for issue in issues:
            print(f"  - {issue}")
        return False
    else:
        print(f"\n✅ All postpones completed without occupancy issues!")
        return True


def main():
    client = MongoClient(MONGO_URI)
    db = client.get_database()
    
    # Set test dates
    day_old = (date.today() + timedelta(days=5)).isoformat()
    day_new = (date.today() + timedelta(days=6)).isoformat()
    
    settings = load_settings(db)
    slots = settings.get('time_slots', [])
    
    if len(slots) < 2:
        print("Error: need at least 2 time slots for this test")
        return 1
    
    slot_old = slots[0]
    slot_new = slots[1]
    
    # Clean test bookings
    db.bookings.delete_many({'email': 'test.fullslot@example.com'})
    
    print("=" * 70)
    print("TEST: Full-slot random booking + postpone all")
    print("=" * 70)
    
    # Step 1: Fill slot randomly
    booking_ids, booked_sizes, occ_before = book_random_sizes_to_fill_slot(
        db, day_old, slot_old, settings
    )
    
    if not booking_ids:
        print("ERROR: No bookings created; aborting")
        return 2
    
    # Step 2: Postpone all one by one
    success = postpone_all_bookings(
        db, day_old, day_new, slot_old, slot_new, booking_ids, booked_sizes
    )
    
    # Step 3: Verify final state
    print("\n" + "=" * 70)
    occ_final = print_slot_occupancy(db, day_old, slot_old, "Final old slot occupancy")
    print("=" * 70)
    
    if occ_final == 0 and success:
        print("\n✅ TEST PASSED: All bookings postponed, old slot fully empty, no redundancy issues!")
        return 0
    elif not success:
        print("\n❌ TEST FAILED: Occupancy mismatch or postpone errors detected")
        return 3
    else:
        print(f"\n⚠️  TEST INCOMPLETE: Old slot still has occupancy {occ_final}, expected 0")
        return 4


if __name__ == '__main__':
    sys.exit(main())

#!/usr/bin/env python3
"""
Test script: Create bookings and postpone them to verify the fix works.
This tests the exact scenario from the bug report: 9,9,8 sequence.
"""
import sys
from datetime import date, timedelta
from bson.objectid import ObjectId

# Add parent directory to path for imports
sys.path.insert(0, str('/'.join(__file__.split('\\')[:-2])))

from config import MONGO_URI
from pymongo import MongoClient
from utils.booking_ops import postpone_booking, check_capacity_available
from utils.allocation_logic import allocate_raft, load_settings
from models.raft_model import ensure_rafts_for_date_slot

def init_test_db(db):
    """Ensure admin user and settings exist."""
    # Create admin user if not exists
    admin = db.users.find_one({'email': 'admin@test.com'})
    if not admin:
        db.users.insert_one({
            'email': 'admin@test.com',
            'name': 'Admin',
            'password_hash': 'hashed_pass',
            'is_admin': True
        })
        print("[OK] Created admin user")
    
    # Create settings if not exists
    settings = db.settings.find_one({'_id': 'system_settings'})
    if not settings:
        db.settings.insert_one({
            '_id': 'system_settings',
            'capacity': 6,
            'rafts_per_slot': 5,
            'time_slots': ['9:00 AM', '12:00 PM', '3:00 PM']
        })
        print("[OK] Created default settings")
    return db

def clean_test_data(db):
    """Clean bookings and rafts for test."""
    db.bookings.delete_many({'email': 'test@example.com'})
    db.rafts.delete_many({})
    print("[OK] Cleaned test data")

def print_slot_occupancy(db, date_str, slot):
    """Print current occupancy for a date/slot."""
    rafts = list(db.rafts.find({'day': date_str, 'slot': slot}).sort('raft_id', 1))
    if not rafts:
        print("  No rafts for %s %s" % (date_str, slot))
        return
    total = sum(r.get('occupancy', 0) for r in rafts)
    details = ", ".join(["raft%d=%d" % (r['raft_id'], r.get('occupancy', 0)) for r in rafts])
    print("  %s %s: total=%d [%s]" % (date_str, slot, total, details))

def test_postpone_9_9_8(db):
    """
    Test the bug scenario: create bookings of 9,9,8 people in the same slot,
    then postpone them to a new slot one by one, verifying old slot becomes empty.
    """
    print("\n=== TEST: Postpone 9,9,8 sequence ===")
    
    old_date = date.today().isoformat()
    new_date = (date.today() + timedelta(days=1)).isoformat()
    slot = '9:00 AM'
    
    settings = load_settings(db)
    ensure_rafts_for_date_slot(db, old_date, slot, settings['rafts_per_slot'], settings['capacity'])
    ensure_rafts_for_date_slot(db, new_date, slot, settings['rafts_per_slot'], settings['capacity'])
    
    # Create three bookings: 9, 9, and 8 people
    booking_ids = []
    for size in [9, 9, 8]:
        res = allocate_raft(db, 'test@example.com', old_date, slot, size)
        if res.get('status') != 'Confirmed':
            print("[FAIL] Failed to allocate %d people: %s" % (size, res))
            return False
        
        # allocate_raft only updates rafts, NOT bookings - create booking manually
        booking_doc = {
            'email': 'test@example.com',
            'date': old_date,
            'slot': slot,
            'group_size': size,
            'status': 'Confirmed',
            'raft_allocations': res.get('rafts', [])
        }
        insert_result = db.bookings.insert_one(booking_doc)
        if insert_result.inserted_id:
            booking_ids.append(insert_result.inserted_id)
            print("[OK] Created booking: %d people -> %s" % (size, res.get('rafts', [])))
        else:
            print("[FAIL] Failed to insert booking for %d people" % size)
    
    print_slot_occupancy(db, old_date, slot)
    total_before = sum(r['occupancy'] for r in db.rafts.find({'day': old_date, 'slot': slot}))
    print("  Total occupancy before postpone: %d" % total_before)
    
    # Postpone each booking to the new slot
    for i, bid in enumerate(booking_ids):
        booking = db.bookings.find_one({'_id': bid})
        group_size = booking.get('group_size')
        
        result = postpone_booking(db, bid, new_date, slot)
        
        if 'error' in result:
            print("[FAIL] Postpone failed for booking %d: %s" % (i+1, result['error']))
            return False
        
        print("[OK] Postponed booking %d (%d people) to %s" % (i+1, group_size, new_date))
        print_slot_occupancy(db, old_date, slot)
    
    # Verify old slot is empty
    total_after = sum(r['occupancy'] for r in db.rafts.find({'day': old_date, 'slot': slot}))
    print("  Total occupancy after all postpones: %d" % total_after)
    
    if total_after == 0:
        print("[PASS] SUCCESS: Old slot is completely empty!")
        return True
    else:
        print("[FAIL] FAILURE: Old slot still has occupancy=%d, expected 0" % total_after)
        # Print detailed raft state
        for r in db.rafts.find({'day': old_date, 'slot': slot}):
            print("    raft %d: occupancy=%d" % (r['raft_id'], r.get('occupancy', 0)))
        return False

def test_partial_postpone(db):
    """
    Test postponing some bookings while leaving others: create 3 bookings,
    postpone 2 of them, verify old slot shows only the remaining booking's occupancy.
    """
    print("\n=== TEST: Partial postpone (postpone 2 of 3) ===")
    
    old_date = date.today().isoformat()
    new_date = (date.today() + timedelta(days=2)).isoformat()
    slot = '12:00 PM'
    
    settings = load_settings(db)
    ensure_rafts_for_date_slot(db, old_date, slot, settings['rafts_per_slot'], settings['capacity'])
    ensure_rafts_for_date_slot(db, new_date, slot, settings['rafts_per_slot'], settings['capacity'])
    
    # Create three bookings
    booking_ids = []
    sizes = [5, 4, 6]
    for size in sizes:
        res = allocate_raft(db, 'test@example.com', old_date, slot, size)
        if res.get('status') != 'Confirmed':
            print("[FAIL] Failed to allocate %d people: %s" % (size, res))
            return False
        
        # allocate_raft only updates rafts - create booking manually
        booking_doc = {
            'email': 'test@example.com',
            'date': old_date,
            'slot': slot,
            'group_size': size,
            'status': 'Confirmed',
            'raft_allocations': res.get('rafts', [])
        }
        insert_result = db.bookings.insert_one(booking_doc)
        if insert_result.inserted_id:
            booking_ids.append(insert_result.inserted_id)
            print("[OK] Created booking: %d people" % size)
        else:
            print("[FAIL] Failed to insert booking for %d people" % size)
    
    print_slot_occupancy(db, old_date, slot)
    total_before = sum(r['occupancy'] for r in db.rafts.find({'day': old_date, 'slot': slot}))
    print("  Total before postpone: %d" % total_before)
    
    # Postpone first two bookings
    for i in range(2):
        booking = db.bookings.find_one({'_id': booking_ids[i]})
        result = postpone_booking(db, booking_ids[i], new_date, slot)
        if 'error' in result:
            print("[FAIL] Postpone failed for booking %d: %s" % (i+1, result['error']))
            return False
        print("[OK] Postponed booking %d" % (i+1))
    
    print_slot_occupancy(db, old_date, slot)
    total_after = sum(r['occupancy'] for r in db.rafts.find({'day': old_date, 'slot': slot}))
    print("  Total after postponing 2: %d" % total_after)
    
    # Should have occupancy = last booking size (6)
    expected = sizes[2]
    if total_after == expected:
        print("[PASS] SUCCESS: Old slot has correct occupancy (%d)" % expected)
        return True
    else:
        print("[FAIL] FAILURE: Old slot occupancy=%d, expected %d" % (total_after, expected))
        return False

def main():
    client = MongoClient(MONGO_URI)
    db = client['raft_booking_db']
    
    try:
        # Initialize test environment
        init_test_db(db)
        
        # Run tests
        results = []
        
        # Test 1: Full postpone (9,9,8 scenario)
        clean_test_data(db)
        results.append(('Postpone 9,9,8', test_postpone_9_9_8(db)))
        
        # Test 2: Partial postpone
        clean_test_data(db)
        results.append(('Partial postpone', test_partial_postpone(db)))
        
        # Summary
        print("\n" + "="*50)
        print("TEST SUMMARY")
        print("="*50)
        for name, passed in results:
            status = "[PASS]" if passed else "[FAIL]"
            print("%s: %s" % (status, name))
        
        all_passed = all(p for _, p in results)
        print("="*50)
        if all_passed:
            print("ALL TESTS PASSED - POSTPONE BUG IS FIXED!")
            return 0
        else:
            print("SOME TESTS FAILED")
            return 1
    
    finally:
        client.close()

if __name__ == '__main__':
    sys.exit(main())

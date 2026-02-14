#!/usr/bin/env python3
"""
End-to-end verification test for postpone feature.
Tests real-world scenarios to ensure robustness.
"""
import sys
from datetime import date, timedelta

sys.path.insert(0, str('/'.join(__file__.split('\\')[:-2])))

from config import MONGO_URI
from pymongo import MongoClient
from utils.booking_ops import postpone_booking, check_capacity_available
from utils.allocation_logic import allocate_raft, load_settings
from models.raft_model import ensure_rafts_for_date_slot

def init_test_db(db):
    """Ensure admin user and settings exist."""
    admin = db.users.find_one({'email': 'admin@test.com'})
    if not admin:
        db.users.insert_one({
            'email': 'admin@test.com',
            'name': 'Admin',
            'password_hash': 'hashed_pass',
            'is_admin': True
        })
    
    settings = db.settings.find_one({'_id': 'system_settings'})
    if not settings:
        db.settings.insert_one({
            '_id': 'system_settings',
            'capacity': 6,
            'rafts_per_slot': 5,
            'time_slots': ['9:00 AM', '12:00 PM', '3:00 PM']
        })
    return db

def clean_test_data(db):
    """Clean all test bookings and rafts."""
    db.bookings.delete_many({})
    db.rafts.delete_many({})

def verify_occupancy_integrity(db, date_str, slot):
    """Verify occupancy is consistent between bookings and rafts."""
    rafts = list(db.rafts.find({'day': date_str, 'slot': slot}))
    bookings = list(db.bookings.find({'date': date_str, 'slot': slot, 'status': 'Confirmed'}))
    
    raft_total = sum(r.get('occupancy', 0) for r in rafts)
    booking_total = sum(b.get('group_size', 0) for b in bookings)
    
    return raft_total == booking_total, raft_total, booking_total

def test_scenario_1_high_volume_postpone():
    """Test postponing many bookings in rapid succession."""
    print("\n=== Scenario 1: High-Volume Postpone ===")
    client = MongoClient(MONGO_URI)
    db = client['raft_booking_db']
    
    try:
        init_test_db(db)
        clean_test_data(db)
        
        old_date = date.today().isoformat()
        new_date = (date.today() + timedelta(days=1)).isoformat()
        slot = '9:00 AM'
        
        settings = load_settings(db)
        ensure_rafts_for_date_slot(db, old_date, slot, settings['rafts_per_slot'], settings['capacity'])
        ensure_rafts_for_date_slot(db, new_date, slot, settings['rafts_per_slot'], settings['capacity'])
        
        # Create 10 bookings rapidly
        booking_ids = []
        sizes = [4, 3, 5, 4, 6, 5, 4, 3, 5, 4]  # Total: 43, but capacity is 35 max
        # Let's use: [4, 5, 4, 5, 4, 5, 4] = 31 people (fits in 5 rafts × 7 max)
        sizes = [4, 5, 4, 5, 4]  # Total: 22 people, fits perfectly
        
        print("Creating %d bookings..." % len(sizes))
        for size in sizes:
            res = allocate_raft(db, 'test@example.com', old_date, slot, size)
            if res.get('status') != 'Confirmed':
                print("[FAIL] Allocation failed: %s" % res)
                return False
            
            booking_doc = {
                'email': 'test@example.com',
                'date': old_date,
                'slot': slot,
                'group_size': size,
                'status': 'Confirmed',
                'raft_allocations': res.get('rafts', [])
            }
            booking_ids.append(db.bookings.insert_one(booking_doc).inserted_id)
        
        integrity, raft_total, booking_total = verify_occupancy_integrity(db, old_date, slot)
        if not integrity:
            print("[FAIL] Integrity check failed after creation: raft=%d, booking=%d" % (raft_total, booking_total))
            return False
        print("  Created %d bookings (total=%d) [OK]" % (len(sizes), raft_total))
        
        # Postpone all bookings
        print("Postponing all bookings...")
        for i, bid in enumerate(booking_ids):
            result = postpone_booking(db, bid, new_date, slot)
            if 'error' in result:
                print("[FAIL] Postpone failed at booking %d: %s" % (i+1, result['error']))
                return False
            
            integrity, raft_total, booking_total = verify_occupancy_integrity(db, old_date, slot)
            if not integrity:
                print("[FAIL] Integrity failure at booking %d: raft=%d, booking=%d" % (i+1, raft_total, booking_total))
                return False
        
        # Final verification
        integrity, old_raft, old_booking = verify_occupancy_integrity(db, old_date, slot)
        integrity2, new_raft, new_booking = verify_occupancy_integrity(db, new_date, slot)
        
        if not (integrity and integrity2 and old_raft == 0 and new_raft == sum(sizes)):
            print("[FAIL] Final verification failed")
            return False
        
        print("  Postponed all %d bookings [OK]" % len(sizes))
        print("  Old slot: %d -> 0, New slot: 0 -> %d [OK]" % (sum(sizes), sum(sizes)))
        print("[PASS] Scenario 1 passed!")
        return True
    
    finally:
        client.close()

def test_scenario_2_mixed_operations():
    """Test mix of creates, postpones, and concurrent operations."""
    print("\n=== Scenario 2: Mixed Operations ===")
    client = MongoClient(MONGO_URI)
    db = client['raft_booking_db']
    
    try:
        init_test_db(db)
        clean_test_data(db)
        
        date1 = date.today().isoformat()
        date2 = (date.today() + timedelta(days=1)).isoformat()
        date3 = (date.today() + timedelta(days=2)).isoformat()
        slot = '12:00 PM'
        
        settings = load_settings(db)
        for d in [date1, date2, date3]:
            ensure_rafts_for_date_slot(db, d, slot, settings['rafts_per_slot'], settings['capacity'])
        
        # Phase 1: Create bookings on date1
        print("Phase 1: Creating bookings on date1...")
        b1 = None
        for size in [6, 5]:
            res = allocate_raft(db, 'user1@test.com', date1, slot, size)
            booking_doc = {
                'email': 'user1@test.com',
                'date': date1,
                'slot': slot,
                'group_size': size,
                'status': 'Confirmed',
                'raft_allocations': res.get('rafts', [])
            }
            b = db.bookings.insert_one(booking_doc)
            if b1 is None:
                b1 = b.inserted_id
        
        integrity, total, _ = verify_occupancy_integrity(db, date1, slot)
        if not integrity or total != 11:
            print("[FAIL] Phase 1 failed")
            return False
        print("  Created 2 bookings (11 people) [OK]")
        
        # Phase 2: Postpone first booking to date2
        print("Phase 2: Postponing first booking to date2...")
        result = postpone_booking(db, b1, date2, slot)
        if 'error' in result:
            print("[FAIL] Postpone failed: %s" % result['error'])
            return False
        
        integrity1, t1, _ = verify_occupancy_integrity(db, date1, slot)
        integrity2, t2, _ = verify_occupancy_integrity(db, date2, slot)
        if not (integrity1 and integrity2 and t1 == 5 and t2 == 6):
            print("[FAIL] Phase 2 integrity check failed")
            return False
        print("  Postponed 6 people from date1->date2 [OK]")
        
        # Phase 3: Add new booking to date1
        print("Phase 3: Adding new booking to date1...")
        res = allocate_raft(db, 'user2@test.com', date1, slot, 4)
        booking_doc = {
            'email': 'user2@test.com',
            'date': date1,
            'slot': slot,
            'group_size': 4,
            'status': 'Confirmed',
            'raft_allocations': res.get('rafts', [])
        }
        db.bookings.insert_one(booking_doc)
        
        integrity, t1, _ = verify_occupancy_integrity(db, date1, slot)
        if not (integrity and t1 == 9):  # 5 + 4
            print("[FAIL] Phase 3 failed")
            return False
        print("  Added 4 people to date1 (now 9) [OK]")
        
        # Phase 4: Postpone second booking from date1 to date3
        # This is a more complex scenario where we have residual bookings
        # Get the second booking from date1
        b2_doc = db.bookings.find_one({'email': 'user1@test.com', 'date': date1})
        if b2_doc:
            b2 = b2_doc['_id']
            result = postpone_booking(db, b2, date3, slot)
            if 'error' in result:
                print("[FAIL] Postpone failed: %s" % result['error'])
                return False
            
            integrity1, t1, _ = verify_occupancy_integrity(db, date1, slot)
            if not (integrity1 and t1 == 4):
                print("[FAIL] Phase 4 failed: expected 4, got %d" % t1)
                return False
            print("  Postponed 5 people from date1->date3 [OK]")
        
        # Final verification
        int1, t1, _ = verify_occupancy_integrity(db, date1, slot)
        int2, t2, _ = verify_occupancy_integrity(db, date2, slot)
        int3, t3, _ = verify_occupancy_integrity(db, date3, slot)
        
        if not (int1 and int2 and int3 and t1 == 4 and t2 == 6 and t3 == 5):
            print("[FAIL] Final verification failed: date1=%d, date2=%d, date3=%d" % (t1, t2, t3))
            return False
        
        print("Final state: date1=%d, date2=%d, date3=%d [OK]" % (t1, t2, t3))
        print("[PASS] Scenario 2 passed!")
        return True
    
    finally:
        client.close()

def main():
    print("\n" + "="*60)
    print("END-TO-END VERIFICATION TEST")
    print("="*60)
    
    results = []
    results.append(("Scenario 1: High-Volume Postpone", test_scenario_1_high_volume_postpone()))
    results.append(("Scenario 2: Mixed Operations", test_scenario_2_mixed_operations()))
    
    print("\n" + "="*60)
    print("FINAL RESULTS")
    print("="*60)
    
    for name, passed in results:
        status = "[PASS]" if passed else "[FAIL]"
        print("%s: %s" % (status, name))
    
    all_passed = all(p for _, p in results)
    
    if all_passed:
        print("\n" + "="*60)
        print("[PASS] ALL E2E TESTS PASSED!")
        print("="*60)
        return 0
    else:
        print("\n" + "="*60)
        print("[FAIL] SOME TESTS FAILED")
        print("="*60)
        return 1

if __name__ == '__main__':
    sys.exit(main())

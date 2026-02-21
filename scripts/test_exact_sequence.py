#!/usr/bin/env python3
"""
Test with specific booking sizes: 9, 8, 5, 4, 2, 1
Then postpone each one by one and check old slot occupancy.

Run: python scripts/test_exact_sequence.py
"""
import sys
from datetime import date, timedelta
from pymongo import MongoClient
from config import MONGO_URI

sys.path.insert(0, '.')

from utils.allocation_logic import allocate_raft, load_settings
from models.raft_model import ensure_rafts_for_date_slot
from utils.booking_ops import postpone_booking


def print_raft_details(db, day, slot, title=""):
    """Print detailed raft occupancy."""
    rafts = list(db.rafts.find({'day': day, 'slot': slot}).sort('raft_id', 1))
    if not rafts:
        print(f"{title} (no rafts)")
        return 0
    
    total = 0
    print(f"{title}")
    for r in rafts:
        occ = r.get('occupancy', 0)
        cap = r.get('capacity', 6)
        is_special = r.get('is_special', False)
        total += occ
        special_str = " [SPECIAL]" if is_special else ""
        print(f"  Raft {r['raft_id']}: {occ}/{cap}{special_str}")
    print(f"  TOTAL: {total}\n")
    return total


def main():
    client = MongoClient(MONGO_URI)
    db = client.get_database()
    
    settings = load_settings(db)
    slots = settings.get('time_slots', [])
    
    if len(slots) < 2:
        print("Error: need at least 2 time slots")
        return 1
    
    # Test dates
    day_old = (date.today() + timedelta(days=10)).isoformat()
    day_new = (date.today() + timedelta(days=11)).isoformat()
    slot_old = slots[0]
    slot_new = slots[1]
    
    print("=" * 80)
    print(f"TEST: Book [9, 8, 5, 4, 2, 1] then postpone each")
    print(f"OLD: {day_old} {slot_old}")
    print(f"NEW: {day_new} {slot_new}")
    print("=" * 80)
    
    # Clean test data
    db.bookings.delete_many({'email': 'test.exact@example.com'})
    
    # Ensure rafts
    ensure_rafts_for_date_slot(db, day_old, slot_old, settings['rafts_per_slot'], settings['capacity'])
    ensure_rafts_for_date_slot(db, day_new, slot_new, settings['rafts_per_slot'], settings['capacity'])
    
    # Reset occupancies
    db.rafts.update_many({'day': day_old, 'slot': slot_old}, {'$set': {'occupancy': 0, 'is_special': False}})
    db.rafts.update_many({'day': day_new, 'slot': slot_new}, {'$set': {'occupancy': 0, 'is_special': False}})
    
    # Step 1: Create bookings with exact sizes
    sizes = [9, 8, 5, 4, 2, 1]
    booking_ids = []
    
    print(f"\n📌 STEP 1: Creating bookings with sizes: {sizes}\n")
    
    for size in sizes:
        res = allocate_raft(db, None, day_old, slot_old, size)
        
        if res.get('status') != 'Confirmed':
            print(f"❌ Allocation failed for size {size}: {res['message']}")
            return 2
        
        booking_doc = {
            'email': 'test.exact@example.com',
            'date': day_old,
            'slot': slot_old,
            'group_size': size,
            'status': 'Confirmed',
            'raft_allocations': res.get('rafts', []),
            'raft_allocation_details': res.get('raft_details', [])
        }
        r = db.bookings.insert_one(booking_doc)
        booking_ids.append(r.inserted_id)
        
        print(f"  ✓ Booked {size} people → rafts {res.get('rafts', [])}")
        print(f"    Details: {res.get('raft_details', [])}")
    
    print(f"\n🔍 Old slot after all bookings:")
    total_initial = print_raft_details(db, day_old, slot_old)
    
    # Step 2: Postpone each booking one by one
    print("\n" + "=" * 80)
    print("📌 STEP 2: Postponing each booking one by one\n")
    
    all_issues = []
    
    for idx, bid in enumerate(booking_ids):
        b = db.bookings.find_one({'_id': bid})
        size = b.get('group_size', 0)
        details = b.get('raft_allocation_details', [])
        
        print(f"\n[{idx+1}/{len(booking_ids)}] Postponing booking (size={size})")
        print(f"  Details to remove: {details}")
        
        # Before
        before = sum(r.get('occupancy', 0) for r in db.rafts.find({'day': day_old, 'slot': slot_old}))
        print(f"  Old slot before: {before}")
        
        # Postpone
        result = postpone_booking(db, bid, day_new, slot_new)
        
        if 'error' in result:
            msg = f"Postpone {idx+1} failed: {result['error']}"
            print(f"  ❌ {msg}")
            all_issues.append(msg)
            continue
        
        # After
        after = sum(r.get('occupancy', 0) for r in db.rafts.find({'day': day_old, 'slot': slot_old}))
        print(f"  Old slot after: {after}")
        
        expected = before - size
        if after == expected:
            print(f"  ✓ Occupancy correct (expected {expected})")
        else:
            msg = f"Postpone {idx+1}: occupancy mismatch (was {before}, removed {size}, got {after}, expected {expected})"
            print(f"  ⚠️  {msg}")
            all_issues.append(msg)
        
        # Show old slot state
        print(f"  Old slot detail:")
        total_after = print_raft_details(db, day_old, slot_old, "    (showing rafts)")
    
    # Step 3: Final check
    print("\n" + "=" * 80)
    print("📌 STEP 3: Final state\n")
    
    total_final_old = print_raft_details(db, day_old, slot_old, "Old slot (should be 0):")
    total_final_new = print_raft_details(db, day_new, slot_new, "New slot (should be 29=[9+8+5+4+2+1]):")
    
    print("=" * 80)
    
    if all_issues:
        print(f"\n❌ TEST FAILED: {len(all_issues)} issues detected:")
        for issue in all_issues:
            print(f"  - {issue}")
        return 3
    
    if total_final_old == 0:
        print(f"\n✅ TEST PASSED:")
        print(f"  • All {len(sizes)} bookings postponed without occupancy issues")
        print(f"  • Old slot fully empty: {total_final_old}")
        print(f"  • New slot total: {total_final_new} (expected 29)")
        return 0
    else:
        print(f"\n⚠️  TEST INCOMPLETE: Old slot has {total_final_old}, expected 0")
        return 4


if __name__ == '__main__':
    sys.exit(main())

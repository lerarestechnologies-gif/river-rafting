from bson.objectid import ObjectId
from utils.allocation_logic import allocate_raft, load_settings, get_allocation_pattern
from models.raft_model import ensure_rafts_for_date_slot
from datetime import datetime, date
import logging

def get_deallocation_amounts(db, date, slot, group_size, raft_ids):
    """
    Determine how many people to remove from each raft.
    Uses current raft occupancies to match allocation pattern parts to the
    correct rafts (allocation places by merge/empty order, not by raft_id order),
    so we must match by current occupancy to avoid wrong rafts and redundancy.
    Returns a list of tuples: [(raft_id, amount_to_remove), ...]
    """
    settings = load_settings(db)
    capacity = settings['capacity']
    rafts_per_slot = settings.get('rafts_per_slot', 5)
    max_people_per_slot = settings.get('rafts_per_slot', 5) * (capacity + 1)
    
    # Fetch current raft states (occupancy) for the given raft_ids
    raft_map = {}
    for rid in raft_ids:
        raft = db.rafts.find_one({'day': date, 'slot': slot, 'raft_id': int(rid)})
        if raft:
            raft_map[int(rid)] = max(0, raft.get('occupancy', 0))
    
    if not raft_map:
        return []
    
    # ---------- Bulk booking deallocation ----------
    # Mirror the bulk booking logic: if group_size > (rafts_per_slot * capacity),
    # reverse the equal distribution used during allocation
    if group_size > (rafts_per_slot * capacity):
        base = group_size // rafts_per_slot
        rem = group_size % rafts_per_slot
        deallocations = []
        sorted_raft_ids = sorted(raft_ids, key=lambda x: int(x))
        for idx, rid in enumerate(sorted_raft_ids):
            amount = base + (1 if idx < rem else 0)
            deallocations.append((int(rid), amount))
        return deallocations
    
    # ---------- Regular booking: match pattern parts to rafts by current occupancy ----------
    # Allocation places parts by merge/empty order (first raft with space), not by raft_id.
    # So we must not assume sorted raft_id order. Instead, for each pattern part (largest
    # first), remove it from a raft that currently has at least that much occupancy.
    allocation = get_allocation_pattern(group_size, max_people_per_slot)
    
    if not allocation:
        # Fallback: if pattern generation fails, use simple division
        per = group_size // len(raft_ids)
        rem = group_size % len(raft_ids)
        deallocations = []
        for idx, rid in enumerate(raft_ids):
            amount = per + (1 if idx < rem else 0)
            deallocations.append((int(rid), amount))
        return deallocations
    
    # Remaining occupancy we can assign to remove (per raft); start with current occupancies
    remaining = {int(rid): raft_map[int(rid)] for rid in raft_ids}
    deallocations = []
    # Process pattern parts largest-first so we match 7/6/4 etc. to rafts that have that much
    parts_desc = sorted([p for p in allocation if p > 0], reverse=True)
    
    for part in parts_desc:
        # Find a raft that has at least `part` remaining (prefer exact match to avoid fragments)
        candidates_exact = [rid for rid in remaining if remaining[rid] == part]
        candidates_any = [rid for rid in remaining if remaining[rid] >= part]
        rid_choice = None
        if candidates_exact:
            rid_choice = min(candidates_exact)  # deterministic
        elif candidates_any:
            rid_choice = min(candidates_any)
        if rid_choice is None:
            continue
        deallocations.append((rid_choice, part))
        remaining[rid_choice] -= part
    
    # Validate total
    total_deallocated = sum(amount for _, amount in deallocations)
    if total_deallocated != group_size and deallocations:
        diff = group_size - total_deallocated
        if diff > 0:
            # Under-removed: assign remainder to raft with most occupancy
            best_rid = max(remaining, key=lambda rid: remaining[rid])
            if remaining[best_rid] >= diff:
                deallocations.append((best_rid, diff))
        elif diff < 0:
            # Over-removed: reduce last entry
            last_raft_id, last_amount = deallocations[-1]
            deallocations[-1] = (last_raft_id, last_amount + diff)
    
    return deallocations

def cancel_booking(db, booking_oid):
    """
    Cancel a booking following the same allocation pattern logic used during booking.
    Uses get_allocation_pattern as the source of truth for deallocation amounts.
    """
    b = db.bookings.find_one({'_id': booking_oid})
    if not b:
        return {'error': 'Booking not found'}
    if b.get('status') == 'Cancelled':
        return {'message': 'Already cancelled'}
    
    # Only process confirmed bookings with raft allocations
    raft_ids = b.get('raft_allocations', [])
    group_size = int(b.get('group_size', 0))
    booking_date = b.get('date')
    booking_slot = b.get('slot')
    
    if not raft_ids or b.get('status') != 'Confirmed':
        # No raft allocations to free, just mark as cancelled
        db.bookings.update_one({'_id': booking_oid}, {'$set': {'status': 'Cancelled', 'raft_allocations': [], 'cancelled_by_admin': True}})
        return {'message': 'Booking cancelled (no raft allocations to free).'}
    
    # Prefer explicit per-raft allocation details if present on the booking
    details = b.get('raft_allocation_details')
    if details:
        for entry in details:
            raft_id = int(entry.get('raft_id'))
            amount_to_remove = int(entry.get('count', 0))
            raft = db.rafts.find_one({'day': booking_date, 'slot': booking_slot, 'raft_id': raft_id})
            if not raft:
                continue
            current_occupancy = max(0, raft.get('occupancy', 0))
            new_occupancy = max(0, current_occupancy - amount_to_remove)
            update_data = {'$set': {'occupancy': new_occupancy}}
            if new_occupancy == 0:
                update_data['$set']['is_special'] = False
            elif new_occupancy != 7:
                update_data['$set']['is_special'] = False
            db.rafts.update_one({'day': booking_date, 'slot': booking_slot, 'raft_id': raft_id}, update_data)
    else:
        # Get deallocation amounts using the same pattern logic as allocation
        settings = load_settings(db)
        capacity = settings['capacity']
        
        deallocations = get_deallocation_amounts(db, booking_date, booking_slot, group_size, raft_ids)
        
        # Apply deallocation to each raft following allocation pattern rules
        for raft_id, amount_to_remove in deallocations:
            raft = db.rafts.find_one({'day': booking_date, 'slot': booking_slot, 'raft_id': raft_id})
            if not raft:
                continue
            
            current_occupancy = max(0, raft.get('occupancy', 0))
            new_occupancy = max(0, current_occupancy - amount_to_remove)
            
            # Build update following allocation pattern rules
            update_data = {'$set': {'occupancy': new_occupancy}}
            
            # Clear is_special flag following allocation logic rules
            if new_occupancy == 0:
                update_data['$set']['is_special'] = False
            elif new_occupancy != 7:
                update_data['$set']['is_special'] = False
            db.rafts.update_one({'day': booking_date, 'slot': booking_slot, 'raft_id': raft_id}, update_data)
    
    # Update booking document
    db.bookings.update_one(
        {'_id': booking_oid},
        {'$set': {'status': 'Cancelled', 'raft_allocations': [], 'cancelled_by_admin': True}}
    )
    
    return {'message': 'Booking cancelled and capacity freed using allocation pattern logic.'}


def recompute_occupancy_for_slot(db, date, slot):
    """Recompute raft occupancies for a specific date+slot from confirmed bookings.
    This mirrors the logic in scripts/recompute_raft_occupancy.py but scoped to a single
    date/slot so it can be used after single-booking moves to keep occupancy consistent.
    """
    settings = load_settings(db)
    rafts_per_slot = settings.get('rafts_per_slot', 5)
    capacity = settings.get('capacity', 6)

    # Ensure rafts exist for this slot
    ensure_rafts_for_date_slot(db, date, slot, rafts_per_slot, capacity)

    # Reset occupancies for this slot
    db.rafts.update_many({'day': date, 'slot': slot}, {'$set': {'occupancy': 0, 'is_special': False}})

    # Re-apply all confirmed bookings for this date+slot
    for b in db.bookings.find({'status': 'Confirmed', 'date': date, 'slot': slot}):
        details = b.get('raft_allocation_details')
        group = int(b.get('group_size', 0))
        if details:
            # Use exact stored per-raft counts
            for entry in details:
                rid = int(entry.get('raft_id'))
                add = int(entry.get('count', 0))
                if add:
                    db.rafts.update_one({'day': date, 'slot': slot, 'raft_id': rid}, {'$inc': {'occupancy': add}})
        else:
            rafts = b.get('raft_allocations', [])
            if rafts:
                per = group // len(rafts) if len(rafts) else 0
                rem = group % len(rafts) if len(rafts) else 0
                for idx, rid in enumerate(rafts):
                    add = per + (1 if idx < rem else 0)
                    db.rafts.update_one({'day': date, 'slot': slot, 'raft_id': rid}, {'$inc': {'occupancy': add}})
            else:
                # If a confirmed booking has no stored raft allocations, try to allocate and persist
                res = allocate_raft(db, None, b['date'], b['slot'], int(b.get('group_size', 0)))
                if res.get('status') == 'Confirmed':
                    db.bookings.update_one({'_id': b['_id']}, {'$set': {'raft_allocations': res.get('rafts', []), 'raft_allocation_details': res.get('raft_details', [])}})
                    new_details = res.get('raft_details', [])
                    for entry in new_details:
                        rid = int(entry.get('raft_id'))
                        add = int(entry.get('count', 0))
                        if add:
                            db.rafts.update_one({'day': date, 'slot': slot, 'raft_id': rid}, {'$inc': {'occupancy': add}})

def check_capacity_available(db, date, slot, group_size):
    """
    Check if a date/slot has capacity for a given group_size without allocating.
    Uses the same logic as allocate_raft but only checks, doesn't modify DB.
    Returns True if capacity is available, False otherwise.
    This mirrors the exact capacity checking logic from allocate_raft.
    """
    settings = load_settings(db)
    capacity = settings['capacity']
    rafts_per_slot = settings.get('rafts_per_slot', 5)
    max_people_per_slot = settings.get('rafts_per_slot', 5) * (capacity + 1)
    
    # Ensure rafts exist for this date/slot
    ensure_rafts_for_date_slot(db, date, slot, rafts_per_slot, capacity)
    
    # Fetch rafts for date+slot sorted, limit to configured number
    rafts = list(db.rafts.find({'day': date, 'slot': slot}).sort('raft_id', 1).limit(rafts_per_slot))
    if not rafts:
        return False
    
    # ---------- Bulk booking check (mirrors allocate_raft logic) ----------
    if group_size > (rafts_per_slot * capacity):
        # Check whether all rafts in this slot are empty
        all_empty = all(r.get('occupancy', 0) == 0 for r in rafts)
        if not all_empty:
            return False
        
        # Compute the maximum allowed bulk booking for an empty slot
        max_bulk = rafts_per_slot * (capacity + 1)
        if group_size > max_bulk:
            return False
        return True
    
    # ---------- Regular booking capacity check (mirrors allocate_raft logic) ----------
    # Small groups (1, 2, 3): only allowed into partially filled rafts (occupancy 2–5), not empty rafts
    # Handle before get_allocation_pattern since it returns [] for group_size < 4
    if group_size < 4:
        for r in rafts:
            if not r.get('is_special', False) and r.get('occupancy', 0) > 0:
                vacancy = capacity - r.get('occupancy', 0)
                if vacancy >= group_size:
                    return True
        return False

    # Special case: if group_size is 7, check for empty rafts
    if group_size == 7:
        empty_rafts = [r for r in rafts if r.get('occupancy', 0) == 0]
        if not empty_rafts:
            return False
    else:
        # For other group sizes (4–6, 8+), check standard capacity (initial check)
        total_vacancy = sum(max(capacity - r.get('occupancy', 0), 0) for r in rafts)
        if total_vacancy < group_size:
            return False
    
    # Get allocation pattern (only used for group_size >= 4; 1–3 already handled above)
    allocation = get_allocation_pattern(group_size, max_people_per_slot)
    if not allocation:
        return False
    
    # For larger groups, simulate allocation to see if all parts can be placed
    # Create a copy of rafts to simulate allocation without modifying DB
    simulated_rafts = []
    for r in rafts:
        simulated_rafts.append({
            'raft_id': r.get('raft_id'),
            'occupancy': r.get('occupancy', 0),
            'is_special': r.get('is_special', False),
            'capacity': r.get('capacity', capacity)
        })
    
    # Try to place all allocation parts (mirroring allocate_raft logic)
    remaining_parts = allocation.copy()
    
    # First, try to merge parts into existing non-special rafts
    for part in list(remaining_parts):
        for r in simulated_rafts:
            if not r.get('is_special', False) and r.get('occupancy', 0) > 0:
                vacancy = capacity - r['occupancy']
                if vacancy >= part:
                    # Can merge this part
                    r['occupancy'] += part
                    remaining_parts.remove(part)
                    break
    
    # If all parts merged, capacity is available
    if not remaining_parts:
        return True
    
    # Check if we have enough empty rafts for remaining parts
    empty_count = sum(1 for r in simulated_rafts if r.get('occupancy', 0) == 0)
    if len(remaining_parts) > empty_count:
        return False
    
    return True

def postpone_booking(db, booking_oid, new_date, new_slot):
    """
    Postpone a booking to a new date/slot.
    Only proceeds if target slot has available capacity.
    Never creates PENDING state - fails if capacity unavailable.
    """
    b = db.bookings.find_one({'_id': booking_oid})
    # Temporary debug logging to trace postpone flow
    try:
        print(f"[POSTPONE-LOG] start postpone: booking={booking_oid}, new_date={new_date}, new_slot={new_slot}")
    except Exception:
        pass
    if not b:
        return {'error': 'Booking not found'}
    
    # Validate date format and ensure it's in the future
    try:
        new_date_obj = datetime.strptime(new_date, '%Y-%m-%d').date()
        today = date.today()
        if new_date_obj < today:
            return {'error': 'New date must be in the future'}
    except ValueError:
        return {'error': 'Invalid date format. Use YYYY-MM-DD'}
    
    # Validate slot exists in settings
    settings = load_settings(db)
    if new_slot not in settings.get('time_slots', []):
        return {'error': f'Invalid time slot. Valid slots: {", ".join(settings.get("time_slots", []))}'}
    
    # Get booking details
    raft_ids = b.get('raft_allocations', [])
    group_size = int(b.get('group_size', 0))
    old_date = b.get('date')
    old_slot = b.get('slot')
    is_confirmed = b.get('status') == 'Confirmed'
    
    # Check if moving to same date/slot
    if old_date == new_date and old_slot == new_slot:
        return {'error': 'Booking is already scheduled for this date and time slot.'}
    
    # ---------- STEP 1: Check capacity in target slot FIRST ----------
    # Ensure rafts exist for the new date/slot
    ensure_rafts_for_date_slot(db, new_date, new_slot, settings['rafts_per_slot'], settings['capacity'])
    
    # Check if target slot has available capacity
    has_capacity = check_capacity_available(db, new_date, new_slot, group_size)
    print(f"[POSTPONE-LOG] capacity check for {new_date} {new_slot}: {has_capacity}")

    if not has_capacity:
        # Capacity check failed - do NOT modify anything, return error
        print(f"[POSTPONE-LOG] capacity unavailable - aborting postpone for {booking_oid}")
        return {'error': 'Postpone failed — timeslot is full.'}
    
    # ---------- STEP 2: Capacity available, proceed with move ----------
    # Store original raft states for rollback if needed
    original_raft_states = {}
    if is_confirmed and raft_ids:
        for rid in raft_ids:
            raft = db.rafts.find_one({'day': old_date, 'slot': old_slot, 'raft_id': int(rid)})
            if raft:
                original_raft_states[int(rid)] = {
                    'occupancy': raft.get('occupancy', 0),
                    'is_special': raft.get('is_special', False)
                }
    
    try:
        # Free old rafts if confirmed using allocation pattern logic
        if is_confirmed and raft_ids:
            # Prefer exact per-raft deallocation if stored on booking
            details = b.get('raft_allocation_details')
            if details:
                print(f"[POSTPONE-LOG] using stored raft details for deallocation: {details}")
                for entry in details:
                    raft_id = int(entry.get('raft_id'))
                    amount_to_remove = int(entry.get('count', 0))
                    raft = db.rafts.find_one({'day': old_date, 'slot': old_slot, 'raft_id': raft_id})
                    if not raft:
                        continue
                    current_occupancy = max(0, raft.get('occupancy', 0))
                    new_occupancy = max(0, current_occupancy - amount_to_remove)
                    update_data = {'$set': {'occupancy': new_occupancy}}
                    if new_occupancy == 0:
                        update_data['$set']['is_special'] = False
                    elif new_occupancy != 7:
                        update_data['$set']['is_special'] = False
                    db.rafts.update_one({'day': old_date, 'slot': old_slot, 'raft_id': raft_id}, update_data)
                    print(f"[POSTPONE-LOG] updated old raft {raft_id}: set {update_data}")
            else:
                deallocations = get_deallocation_amounts(db, old_date, old_slot, group_size, raft_ids)
                print(f"[POSTPONE-LOG] deallocations (old): {deallocations}")
                for raft_id, amount_to_remove in deallocations:
                    raft = db.rafts.find_one({'day': old_date, 'slot': old_slot, 'raft_id': raft_id})
                    if not raft:
                        continue
                    current_occupancy = max(0, raft.get('occupancy', 0))
                    new_occupancy = max(0, current_occupancy - amount_to_remove)
                    update_data = {'$set': {'occupancy': new_occupancy}}
                    if new_occupancy == 0:
                        update_data['$set']['is_special'] = False
                    elif new_occupancy != 7:
                        update_data['$set']['is_special'] = False
                    db.rafts.update_one({'day': old_date, 'slot': old_slot, 'raft_id': raft_id}, update_data)
                    print(f"[POSTPONE-LOG] updated old raft {raft_id}: set {update_data}")
        
        # Allocate in new slot
        res = allocate_raft(db, None, new_date, new_slot, group_size)
        print(f"[POSTPONE-LOG] allocate_raft result: {res}")
        
        # Verify allocation succeeded
        if res.get('status') != 'Confirmed':
            # Allocation failed - rollback old slot changes
            if is_confirmed and raft_ids and original_raft_states:
                for raft_id, original_state in original_raft_states.items():
                    db.rafts.update_one(
                        {'day': old_date, 'slot': old_slot, 'raft_id': raft_id},
                        {
                            '$set': {
                                'occupancy': original_state['occupancy'],
                                'is_special': original_state['is_special']
                            }
                        }
                    )
            return {'error': 'Postpone failed — timeslot is full.'}
        
        # Allocation succeeded - update booking document
        update_data = {
            'date': new_date,
            'slot': new_slot,
            'status': 'Confirmed',  # Always confirmed since we checked capacity
            'raft_allocations': res.get('rafts', []),
            'raft_allocation_details': res.get('raft_details', []),
            'rescheduled_by_admin': True
        }
        db.bookings.update_one({'_id': booking_oid}, {'$set': update_data})
        print(f"[POSTPONE-LOG] booking updated {booking_oid} -> {update_data}")
        # Recompute occupancies for old and new slots so raft counts stay consistent
        try:
            # old slot should no longer include this booking after update
            recompute_occupancy_for_slot(db, old_date, old_slot)
        except Exception:
            print(f"[POSTPONE-LOG] recompute failed for old slot {old_date} {old_slot}")
        try:
            recompute_occupancy_for_slot(db, new_date, new_slot)
        except Exception:
            print(f"[POSTPONE-LOG] recompute failed for new slot {new_date} {new_slot}")

        # Fetch updated booking to return
        updated_booking = db.bookings.find_one({'_id': booking_oid})
        
        return {
            'message': f'Booking rescheduled to {new_date} at {new_slot}',
            'result': res,
            'booking': {
                'id': str(updated_booking['_id']),
                'date': updated_booking.get('date'),
                'slot': updated_booking.get('slot'),
                'status': updated_booking.get('status'),
                'raft_allocations': updated_booking.get('raft_allocations', [])
            }
        }
    
    except Exception as e:
        # Rollback on any error
        print(f"[POSTPONE-LOG] exception during postpone: {e}")
        if is_confirmed and raft_ids and original_raft_states:
            for raft_id, original_state in original_raft_states.items():
                db.rafts.update_one(
                    {'day': old_date, 'slot': old_slot, 'raft_id': raft_id},
                    {
                        '$set': {
                            'occupancy': original_state['occupancy'],
                            'is_special': original_state['is_special']
                        }
                    }
                )
                print(f"[POSTPONE-LOG] rolled back raft {raft_id} to {original_state}")
        return {'error': f'Postpone failed: {str(e)}'}

# Admin Dashboard Booking Filtering Feature

## Overview
Added comprehensive filtering options to the Admin Dashboard for viewing all bookings with the following criteria:

## Implemented Filters

### 1. **Date Range Filtering**
- **From Date**: Filter bookings from a specific start date
- **To Date**: Filter bookings up to a specific end date
- Both filters work together to create a date range
- Users can use either one or both filters

### 2. **Slot Filtering**
- Filter bookings by time slot
- Displays all available time slots configured in system settings
- Examples: "7:00–9:00", "10:00–12:00", "13:00–15:00", "15:30–17:30"

### 3. **Status Filtering**
- Filter bookings by status:
  - **Confirmed**: Completed and confirmed bookings
  - **Pending**: Pending bookings
  - **Cancelled**: Cancelled bookings
  - **All Status**: Shows all bookings regardless of status (default)

## Features

### User Interface
- Clean, organized filter controls positioned above the bookings table
- All filters displayed on separate rows for better readability
- **Apply Filters** button: Applies all selected filters
- **Clear Filters** button: Resets all filters and shows all bookings (appears only when filters are active)

### Functionality
- Filters can be combined to narrow down results (e.g., filter by date range AND slot AND status)
- Booking count updates to show filtered results
- Status indicator shows "(filtered)" when any filter is applied
- Responsive design works on mobile and desktop devices

### Booking Count Display
- Shows total number of bookings matching the current filter criteria
- Displays "(filtered)" indicator when filters are active
- Sub-admin users see "(Today & Tomorrow only)" indicator

### Empty State
- When no bookings match the filter criteria, displays helpful message
- Users can click "clear all filters" link to reset filters and see all bookings
- Different messages for sub-admin vs admin users

## Technical Implementation

### Backend Changes
**File**: `routes/admin_routes.py` - `dashboard()` function
- Added support for `date_from`, `date_to`, `slot`, and `status` query parameters
- Implemented MongoDB query filtering:
  - Date range: Uses `$gte` and `$lte` operators
  - Slot: Exact match filter
  - Status: Exact match filter
- Passes filter parameters to template for UI state preservation

### Frontend Changes
**File**: `templates/admin_dashboard.html`
- Added filter form with date inputs, slot select, and status select
- Implemented JavaScript functions:
  - `applyAllFilters()`: Builds URL parameters and navigates to filtered view
  - `clearAllFilters()`: Clears all inputs and resets dashboard
- Updated template variables to display current filter values

### Filter Persistence
- Filter values are preserved in URL query parameters
- Page reload maintains filter state
- Sub-admin users are not shown filter options (only see today/tomorrow data)

## Usage Example

1. Navigate to Admin Dashboard
2. Select desired filters:
   - Choose "From Date": 2025-02-01
   - Choose "To Date": 2025-02-28
   - Select "Slot": 10:00–12:00
   - Select "Status": Confirmed
3. Click "Apply Filters"
4. Dashboard displays only bookings matching all criteria
5. To reset, click "Clear Filters"

## Backward Compatibility
- Sub-admin functionality unchanged (shows today/tomorrow Confirmed bookings only)
- Old date filter parameters are still supported (for backward compatibility)
- All existing admin features continue to work as before

## Restrictions by User Role

### Admin Users
- Full access to all filters (date range, slot, status)
- Can view all bookings with any combination of filters

### Sub-Admin Users
- No filter controls displayed
- Automatically restricted to:
  - Status: Confirmed only
  - Dates: Today and Tomorrow only
  - Cannot apply custom filters

## Files Modified
1. `routes/admin_routes.py` - Backend filtering logic
2. `templates/admin_dashboard.html` - UI and JavaScript functionality

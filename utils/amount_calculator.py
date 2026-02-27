"""
Amount calculator utility for booking amounts based on date and group size.
"""
from datetime import datetime


def get_applicable_amount(settings, booking_date_str):
    """
    Determine the applicable amount for a booking based on the day of week.
    
    Args:
        settings (dict): System settings containing weekday_amount and saturday_amount
        booking_date_str (str): Booking date in YYYY-MM-DD format
    
    Returns:
        float: The applicable amount per person (0 if not configured)
    """
    try:
        booking_date = datetime.strptime(booking_date_str, '%Y-%m-%d').date()
        # Monday is 0, Sunday is 6
        weekday = booking_date.weekday()
        
        # Saturday is 5
        if weekday == 5:
            # Use Saturday amount if available, otherwise fall back to weekday amount
            return settings.get('saturday_amount', settings.get('weekday_amount', 0))
        else:
            # Monday-Friday (0-4)
            return settings.get('weekday_amount', 0)
    except (ValueError, TypeError):
        return 0


def calculate_total_amount(settings, booking_date_str, group_size):
    """
    Calculate the total amount for a booking.
    
    Args:
        settings (dict): System settings containing amount configurations
        booking_date_str (str): Booking date in YYYY-MM-DD format
        group_size (int): Number of people in the group
    
    Returns:
        dict: Dictionary containing:
            - applicable_amount: Amount per person (float)
            - total_amount: Total cost for the group (float)
            - day_type: "weekday" or "saturday"
    """
    try:
        booking_date = datetime.strptime(booking_date_str, '%Y-%m-%d').date()
        weekday = booking_date.weekday()
        
        # Determine day type and applicable amount
        if weekday >= 0 and weekday <= 4:  # Monday to Friday
            applicable_amount = settings.get('weekday_amount', 0)
            advance_percent = settings.get('weekday_advance_percent', 25)
            day_type = 'weekday'
        elif weekday == 5 or weekday == 6:  # Saturday or Sunday
            applicable_amount = settings.get('saturday_amount', settings.get('weekday_amount', 0))
            advance_percent = settings.get('saturday_advance_percent', 35)
            day_type = 'weekend'
        
        # Calculate total
        total_amount = applicable_amount * group_size
        advance_amount = total_amount * (advance_percent / 100)
        return {
            'applicable_amount': applicable_amount,
            'total_amount': total_amount,
            'advance_percent': advance_percent,
            'advance_amount': advance_amount,
            'day_type': day_type
        }
    except (ValueError, TypeError):
        return {
            'applicable_amount': 0,
            'total_amount': 0,
            'day_type': 'unknown'
        }


def format_currency(amount):
    """Format amount as currency string."""
    return f"${amount:.2f}"

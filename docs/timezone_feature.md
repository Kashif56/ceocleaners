# Business Timezone Feature Documentation

## Overview

The Business Timezone feature allows each business to specify their preferred timezone. All datetime values are stored in UTC in the database, but displayed to users in their business's local timezone. This ensures consistent data storage while providing a localized experience for users across different geographic locations.

## Key Components

### Backend Components

1. **Business Model**
   - Each business has a `timezone` field (CharField) that stores the timezone identifier (e.g., 'America/New_York', 'Europe/London')
   - Default timezone is 'UTC' if not specified
   - Helper methods:
     - `get_timezone()`: Returns the pytz timezone object for the business
     - `localize_datetime()`: Converts a datetime to the business's timezone
     - `get_local_time()`: Returns the current time in the business's timezone

2. **TimezoneMiddleware**
   - Located in `accounts/middleware.py`
   - Automatically sets the timezone for each request based on the authenticated user's business
   - For cleaners, uses the timezone of their associated business
   - Falls back to UTC if no timezone is found or user is not authenticated

3. **Context Processor**
   - Located in `accounts/context_processors.py`
   - Makes timezone information available in all templates:
     - `user_timezone`: The timezone object for the current user
     - `current_time`: Current time in the user's timezone

4. **Timezone Utilities**
   - Located in `accounts/timezone_utils.py`
   - Helper functions:
     - `get_timezone_choices()`: Returns a list of common timezones for form dropdowns
     - `convert_to_utc()`: Converts a datetime from a specific timezone to UTC
     - `convert_from_utc()`: Converts a UTC datetime to a specific timezone
     - `format_datetime()`: Formats a datetime according to a specified format

5. **Booking Timezone Utilities**
   - Located in `bookings/timezone_utils.py`
   - Specialized functions for handling booking datetime fields:
     - `localize_booking_datetime()`: Converts booking datetime fields to business timezone
     - `convert_to_utc()`: Converts a datetime to UTC
     - `get_utc_datetime()`: Combines date and time fields into a UTC datetime

6. **Template Tags**
   - Located in `bookings/templatetags/timezone_tags.py`
   - Custom template filters and tags:
     - `to_business_timezone`: Converts a datetime to business timezone
     - `format_datetime`: Formats a datetime with a specified format
     - `convert_and_format`: Combines conversion and formatting in one step

### Frontend Components

1. **JavaScript Utilities**
   - Located in `static/js/timezone.js`
   - Client-side timezone handling:
     - `formatDatetime()`: Formats a UTC datetime in the business timezone
     - `initializeTimezoneDisplay()`: Initializes timezone display for elements with data attributes
     - `getCurrentTimeInTimezone()`: Gets current time in the business timezone

2. **Base Template Modifications**
   - Business timezone stored as data attribute on the body element
   - Current time display in the business timezone
   - Automatic time updates using JavaScript

3. **Data Attributes for Datetime Elements**
   - Elements with `data-utc-datetime` attribute are automatically formatted
   - Optional `data-format` attribute for custom formatting

## Usage Guidelines

### For Developers

1. **Storing Datetimes**
   - Always store datetimes in UTC in the database
   - Use `timezone.now()` for current time (returns UTC)
   - Use `convert_to_utc()` from timezone_utils to convert user input to UTC

2. **Displaying Datetimes**
   - In Python/Django:
     - Use `convert_from_utc()` or business's `localize_datetime()` method
     - For bookings, use `localize_booking_datetime()` from bookings.timezone_utils
   - In Templates:
     - Use the `convert_and_format` template tag
     - Example: `{% convert_and_format booking.createdAt business.timezone "F d, Y" %}`
   - In JavaScript:
     - Use elements with `data-utc-datetime` attribute
     - Example: `<span data-utc-datetime="2023-06-30T15:30:00Z">June 30, 2023</span>`

3. **Form Handling**
   - When receiving datetime input from users:
     - Assume the input is in the business's timezone
     - Convert to UTC before saving to database
   - When displaying datetime inputs:
     - Convert from UTC to business timezone

### For Users

1. **Setting Your Timezone**
   - During business registration, select your timezone from the dropdown
   - You can update your timezone anytime from the Edit Business page

2. **Understanding Datetime Display**
   - All dates and times are displayed in your selected timezone
   - The current time in your timezone is shown at the top of the page
   - Booking times, creation dates, and other timestamps are automatically converted

## Implementation Notes

1. **Django Settings**
   - `USE_TZ = True` ensures Django uses timezone-aware datetimes
   - `TIME_ZONE = 'UTC'` sets the default timezone to UTC

2. **Dependencies**
   - pytz library for timezone handling
   - Moment.js and moment-timezone.js for client-side timezone handling

3. **Performance Considerations**
   - Timezone conversions are performed at the application level, not in the database
   - Client-side conversions reduce server load for display formatting

## Troubleshooting

1. **Incorrect Timezone Display**
   - Verify the business has the correct timezone selected
   - Check that the datetime is properly stored in UTC in the database
   - Ensure the middleware is properly activated in settings

2. **Form Submission Issues**
   - Ensure datetimes from forms are converted to UTC before saving
   - Check that date and time fields are properly combined for timezone conversion

3. **JavaScript Formatting Issues**
   - Verify that the `data-business-timezone` attribute is correctly set on the body element
   - Check that the datetime string in `data-utc-datetime` is in a valid format

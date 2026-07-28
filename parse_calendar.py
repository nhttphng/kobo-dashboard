#!/usr/bin/env python3
"""
Reliable iCal parser that handles RECURRENCE-ID events properly.
Outputs clean JSON for the dashboard.
"""

import sys
import json
import os
import urllib.request
from datetime import datetime, date, timezone
import pytz
from icalendar import Calendar, Event
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

def parse_ical_url(url, calendar_name, timezone_obj):
    """Parse iCal from URL and return today's events."""
    try:
        # Fetch iCal data
        with urllib.request.urlopen(url) as response:
            ical_data = response.read()
        
        # Parse calendar
        cal = Calendar.from_ical(ical_data)
        
        # Get today in configured timezone
        today = datetime.now(timezone_obj).date()
        tomorrow = today + timedelta(days=1);
        
        events = []
        
        # Process all events
        for component in cal.walk():
            if component.name == "VEVENT":
                event = component
                
                # Get start date
                dtstart = event.get('dtstart')
                if not dtstart:
                    continue
                    
                # Convert to date for comparison
                if hasattr(dtstart.dt, 'date'):
                    event_date = dtstart.dt.date()
                else:
                    event_date = dtstart.dt
                
                # Convert to configured timezone if it's a datetime
                if hasattr(dtstart.dt, 'astimezone'):
                    event_datetime_tz = dtstart.dt.astimezone(timezone_obj)
                    event_date = event_datetime_tz.date()
                
                # Check if event is today
                if event_date == today or event_date == tomorrow:
                    # Get event details
                    summary = str(event.get('summary', 'Untitled Event'))
                    
                    # Format start time
                    if hasattr(dtstart.dt, 'astimezone'):
                        start_time = dtstart.dt.astimezone(timezone_obj)
                        start_iso = start_time.isoformat()
                    else:
                        start_iso = dtstart.dt.isoformat()
                    
                    # Get end time if available
                    dtend = event.get('dtend')
                    end_iso = None
                    if dtend:
                        if hasattr(dtend.dt, 'astimezone'):
                            end_time = dtend.dt.astimezone(timezone_obj)
                            end_iso = end_time.isoformat()
                        else:
                            end_iso = dtend.dt.isoformat()
                    
                    # Create event object
                    event_obj = {
                        'summary': summary,
                        'start': {
                            'dateTime': start_iso
                        },
                        'end': {
                            'dateTime': end_iso
                        } if end_iso else {'dateTime': start_iso},
                        'description': str(event.get('description', '')),
                        'location': str(event.get('location', '')),
                        'calendarSource': calendar_name
                    }
                    
                    events.append(event_obj)
        
        return events
        
    except Exception as e:
        print(f"Error parsing calendar {calendar_name}: {e}", file=sys.stderr)
        return []

def main():
    """Main function to parse calendars and output JSON."""
    
    # Load calendar configuration from environment variables
    timezone_name = os.getenv('TIMEZONE', 'Europe/London')
    timezone_obj = pytz.timezone(timezone_name)
    
    ical_urls = os.getenv('ICAL_URLS', '').split(',')
    calendar_names = os.getenv('CALENDAR_NAMES', '').split(',')
    
    if not ical_urls or not calendar_names:
        print("Error: ICAL_URLS and CALENDAR_NAMES must be set in .env file", file=sys.stderr)
        return
    
    if len(ical_urls) != len(calendar_names):
        print("Error: ICAL_URLS and CALENDAR_NAMES must have the same number of entries", file=sys.stderr)
        return
    
    calendars = []
    for i, url in enumerate(ical_urls):
        if url.strip() and i < len(calendar_names):
            calendars.append({
                'name': calendar_names[i].strip(),
                'url': url.strip()
            })
    
    all_events = []
    
    for calendar in calendars:
        print(f"Processing {calendar['name']} calendar...", file=sys.stderr)
        events = parse_ical_url(calendar['url'], calendar['name'], timezone_obj)
        print(f"Found {len(events)} events for today/tomorrow from {calendar['name']}", file=sys.stderr)
        all_events.extend(events)
    
    # Sort events by start time
    all_events.sort(key=lambda x: x['start']['dateTime'])
    
    # Output JSON
    print(json.dumps(all_events, indent=2))

if __name__ == '__main__':
    main()

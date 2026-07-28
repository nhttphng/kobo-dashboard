#!/usr/bin/env python3
"""
Calendar Processing Service
Fetches iCal data, processes recurring events, and generates calendar.json
"""

import os
import sys
import json
import time
import urllib.request
from datetime import datetime, date, timezone, timedelta
import pytz
from icalendar import Calendar, Event
from dotenv import load_dotenv
import schedule
import logging

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s | %(levelname)s | %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger(__name__)

class CalendarProcessor:
    def __init__(self):
        load_dotenv()
        
        # Get timezone from environment variable
        timezone_name = os.getenv('TIMEZONE', 'Europe/London')
        self.timezone = pytz.timezone(timezone_name)
        logger.info(f"Using timezone: {timezone_name}")
        
        self.output_file = os.getenv('CALENDAR_JSON_PATH', './calendar.json')
        self.calendars = self._load_calendar_config()
        
    def _load_calendar_config(self):
        """Load calendar configuration from environment variables."""
        ical_urls = os.getenv('ICAL_URLS', '').split(',')
        calendar_names = os.getenv('CALENDAR_NAMES', '').split(',')
        
        if not ical_urls or not calendar_names:
            logger.error("ICAL_URLS and CALENDAR_NAMES must be set in .env file")
            return []
            
        if len(ical_urls) != len(calendar_names):
            logger.error("ICAL_URLS and CALENDAR_NAMES must have the same number of entries")
            return []
            
        calendars = []
        for i, url in enumerate(ical_urls):
            if url.strip() and i < len(calendar_names):
                calendars.append({
                    'name': calendar_names[i].strip(),
                    'url': url.strip()
                })
                
        logger.info(f"Loaded {len(calendars)} calendar configurations")
        return calendars
    
    def _fetch_ical_data(self, url):
        """Fetch iCal data from URL."""
        try:
            logger.info(f"Fetching iCal data from: {url}")
            with urllib.request.urlopen(url) as response:
                return response.read()
        except Exception as e:
            logger.error(f"Error fetching iCal from {url}: {e}")
            return None
    
    def _parse_calendar_events(self, ical_data, calendar_name):
        """Parse iCal data and return today's events."""
        try:
            cal = Calendar.from_ical(ical_data)
            
            # Get today in configured timezone
            today = datetime.now(self.timezone).date()
            tomorrow = today + timedelta(days=1)
            logger.info(f"Processing events for date: {today} ({calendar_name})")
            
            events = []
            total_components = 0
            
            # Process all VEVENT components
            for component in cal.walk():
                if component.name == "VEVENT":
                    total_components += 1
                    event = self._process_event(component, today, calendar_name) or self._process_event(component, tomorrow, calendar_name)
                    if event:
                        events.append(event)
            
            logger.info(f"Processed {total_components} total events, found {len(events)} for today and tomorrow ({calendar_name})")
            
            # Log each found event
            for event in events:
                start_time = event['start']['dateTime']
                logger.info(f"Event: '{event['summary']}' at {start_time} ({calendar_name})")
            
            return events
            
        except Exception as e:
            logger.error(f"Error parsing calendar {calendar_name}: {e}")
            return []
    
    def _process_event(self, event_component, target_date, calendar_name):
        """Process a single VEVENT component."""
        try:
            # Get start date/time
            dtstart = event_component.get('dtstart')
            if not dtstart:
                return None
            
            # Convert to date for comparison
            event_date = self._get_event_date(dtstart.dt)
            
            # Check if event is on target date
            if event_date != target_date:
                return None
            
            # Extract event details
            summary = str(event_component.get('summary', 'Untitled Event'))
            
            # Format start and end times
            start_iso = self._format_datetime(dtstart.dt)
            
            dtend = event_component.get('dtend')
            if dtend:
                end_iso = self._format_datetime(dtend.dt)
            else:
                # If no end time, assume 30 minutes duration
                if hasattr(dtstart.dt, 'astimezone'):
                    end_dt = dtstart.dt + timedelta(minutes=30)
                    end_iso = self._format_datetime(end_dt)
                else:
                    end_iso = start_iso
            
            # Create event object compatible with existing frontend
            return {
                'summary': summary,
                'start': {
                    'dateTime': start_iso
                },
                'end': {
                    'dateTime': end_iso
                },
                'description': str(event_component.get('description', '')),
                'location': str(event_component.get('location', '')),
                'calendarSource': calendar_name,
                "isAllDay": not hasattr(dtstart.dt, 'hour')
            }
            
        except Exception as e:
            logger.warning(f"Error processing event: {e}")
            return None
    
    def _get_event_date(self, dt):
        """Get the date of an event, handling timezone conversion."""
        if hasattr(dt, 'date'):
            # It's a datetime object
            if hasattr(dt, 'astimezone'):
                # Convert to configured timezone
                tz_dt = dt.astimezone(self.timezone)
                return tz_dt.date()
            else:
                # Naive datetime, assume UTC
                utc_dt = dt.replace(tzinfo=timezone.utc)
                tz_dt = utc_dt.astimezone(self.timezone)
                return tz_dt.date()
        else:
            # It's already a date object
            return dt
    
    def _format_datetime(self, dt):
        """Format datetime to ISO string in configured timezone."""
        if hasattr(dt, 'astimezone'):
            # It's a datetime object
            tz_dt = dt.astimezone(self.timezone)
            return tz_dt.isoformat()
        else:
            # It's a date object, assume start of day
            tz_dt = self.timezone.localize(datetime.combine(dt, datetime.min.time()))
            return tz_dt.isoformat()
    
    def process_calendars(self):
        """Main function to process all calendars and generate JSON."""
        logger.info("Starting calendar processing...")
        
        all_events = []
        
        for calendar in self.calendars:
            try:
                # Fetch iCal data
                ical_data = self._fetch_ical_data(calendar['url'])
                if not ical_data:
                    continue
                
                # Parse events
                events = self._parse_calendar_events(ical_data, calendar['name'])
                all_events.extend(events)
                
            except Exception as e:
                logger.error(f"Error processing calendar {calendar['name']}: {e}")
        
        # Sort all events by start time
        all_events.sort(key=lambda x: x['start']['dateTime'])
        
        # Write to JSON file
        try:
            with open(self.output_file, 'w', encoding='utf-8') as f:
                json.dump(all_events, f, indent=2, ensure_ascii=False)
            
            logger.info(f"Successfully saved {len(all_events)} total events to {self.output_file}")
            
            # Log summary by calendar
            calendar_counts = {}
            for event in all_events:
                cal_name = event['calendarSource']
                calendar_counts[cal_name] = calendar_counts.get(cal_name, 0) + 1
            
            for cal_name, count in calendar_counts.items():
                logger.info(f"  {cal_name}: {count} events")
                
        except Exception as e:
            logger.error(f"Error writing to {self.output_file}: {e}")

def main():
    """Main function to run the calendar processing service."""
    processor = CalendarProcessor()
    
    # Get interval from environment (default: 5 minutes)
    interval_minutes = int(os.getenv('CALENDAR_FETCH_INTERVAL_MINUTES', '5'))
    
    logger.info(f"Calendar Processing Service starting...")
    logger.info(f"Processing interval: {interval_minutes} minutes")
    logger.info(f"Output file: {processor.output_file}")
    
    # Schedule the processing
    schedule.every(interval_minutes).minutes.do(processor.process_calendars)
    
    # Run once immediately
    processor.process_calendars()
    
    # Keep running
    logger.info("Service started. Press Ctrl+C to stop.")
    try:
        while True:
            schedule.run_pending()
            time.sleep(10)  # Check every 10 seconds
    except KeyboardInterrupt:
        logger.info("Service stopped by user")
    except Exception as e:
        logger.error(f"Service error: {e}")

if __name__ == '__main__':
    main()

#!/usr/bin/env python3
"""
Performance Optimization Module
Implements fast data access without deleting historical data
"""

import logging
import time
from datetime import datetime, timedelta
from collections import defaultdict
import pytz
from .database import db
from .utils import parse_timestamp

logger = logging.getLogger(__name__)

class DataIndexer:
    """Creates and manages data indexes for fast lookups."""
    
    def __init__(self):
        self._indexes = {}
        self._index_timestamps = {}
        self._cache_ttl = 300  # 5 minutes
    
    def get_monitors_index(self, force_refresh=False):
        """Get optimized monitor data with pre-computed values."""
        cache_key = 'monitors_index'
        
        if not force_refresh and self._is_index_valid(cache_key):
            return self._indexes[cache_key]
        
        logger.debug("Building monitors index...")
        start_time = time.time()
        
        # Load all data once
        all_monitors = db.get_all('monitor')
        all_checks = db.get_all('check')
        all_tags = db.get_all('tag')
        all_monitor_tags = db.get_all('monitor_tag')
        
        # Create lookup dictionaries
        checks_by_monitor = defaultdict(list)
        for check in all_checks:
            checks_by_monitor[check['monitor_id']].append(check)
        
        tags_by_id = {tag['id']: tag for tag in all_tags}
        monitor_tags_lookup = defaultdict(list)
        for mt in all_monitor_tags:
            monitor_tags_lookup[mt['monitor_id']].append(mt['tag_id'])
        
        # Build optimized monitor objects
        monitor_index = {}
        for monitor_data in all_monitors:
            monitor_id = monitor_data['id']
            
            # Get latest check for status
            monitor_checks = checks_by_monitor[monitor_id]
            latest_check = None
            if monitor_checks:
                latest_check = max(monitor_checks, key=lambda c: c['checked_at'])
            
            # Pre-compute expensive operations
            monitor_summary = {
                'id': monitor_id,
                'name': monitor_data['name'],
                'url': monitor_data['url'],
                'monitor_type': monitor_data.get('monitor_type', 'http'),
                'is_active': monitor_data.get('is_active', True),
                'interval': monitor_data.get('interval', 60),
                'created_at': monitor_data.get('created_at'),
                
                # Pre-computed status info
                'status': 'up' if latest_check and latest_check['is_up'] else ('down' if latest_check else 'unknown'),
                'response_time': latest_check.get('response_time') if latest_check else None,
                'cert_expires_in_days': latest_check.get('cert_expires_in_days') if latest_check else None,
                'latest_check_at': latest_check.get('checked_at') if latest_check else None,
                
                # Pre-computed uptime percentage (last 7 days)
                'uptime_7d': self._calculate_uptime_percentage(monitor_checks, days=7),
                'uptime_24h': self._calculate_uptime_percentage(monitor_checks, days=1),
                
                # Check counts for performance metrics
                'total_checks_7d': len([c for c in monitor_checks if self._is_within_days(c.get('checked_at'), 7)]),
                'failed_checks_7d': len([c for c in monitor_checks if not c['is_up'] and self._is_within_days(c.get('checked_at'), 7)]),
                
                # Tag information
                'tag_ids': monitor_tags_lookup[monitor_id],
                'tags': [tags_by_id[tag_id] for tag_id in monitor_tags_lookup[monitor_id] if tag_id in tags_by_id],
                
                # Raw data for detailed views
                '_raw_data': monitor_data,
                '_recent_checks': monitor_checks[-50:] if monitor_checks else []  # Keep last 50 checks for details
            }
            
            monitor_index[monitor_id] = monitor_summary
        
        # Cache the index
        self._indexes[cache_key] = monitor_index
        self._index_timestamps[cache_key] = time.time()
        
        build_time = (time.time() - start_time) * 1000
        logger.info(f"Built monitors index for {len(monitor_index)} monitors in {build_time:.1f}ms")
        
        return monitor_index
    
    def get_dashboard_summary(self, force_refresh=False):
        """Get pre-computed dashboard summary data."""
        cache_key = 'dashboard_summary'
        
        if not force_refresh and self._is_index_valid(cache_key):
            return self._indexes[cache_key]
        
        logger.debug("Building dashboard summary...")
        monitors_index = self.get_monitors_index(force_refresh)
        
        # Calculate summary statistics
        active_monitors = [m for m in monitors_index.values() if m['is_active']]
        
        total_monitors = len(active_monitors)
        up_monitors = sum(1 for m in active_monitors if m['status'] == 'up')
        down_monitors = sum(1 for m in active_monitors if m['status'] == 'down')
        unknown_monitors = total_monitors - up_monitors - down_monitors
        
        # Performance metrics
        avg_response_time = None
        response_times = [m['response_time'] for m in active_monitors if m['response_time'] is not None]
        if response_times:
            avg_response_time = sum(response_times) / len(response_times)
        
        # Get recent incidents (without loading all incidents)
        recent_incidents = self._get_recent_incidents()
        
        summary = {
            'total_monitors': total_monitors,
            'up_monitors': up_monitors,
            'down_monitors': down_monitors,
            'unknown_monitors': unknown_monitors,
            'uptime_percentage': (up_monitors / total_monitors * 100) if total_monitors > 0 else 100,
            'avg_response_time': round(avg_response_time, 2) if avg_response_time else None,
            'recent_incidents': recent_incidents,
            'active_monitors': active_monitors,
            'last_updated': datetime.now(pytz.utc).isoformat()
        }
        
        # Cache the summary
        self._indexes[cache_key] = summary
        self._index_timestamps[cache_key] = time.time()
        
        return summary
    
    def get_monitor_details(self, monitor_id, force_refresh=False):
        """Get detailed monitor information with history."""
        cache_key = f'monitor_details_{monitor_id}'
        
        if not force_refresh and self._is_index_valid(cache_key):
            return self._indexes[cache_key]
        
        monitors_index = self.get_monitors_index()
        if monitor_id not in monitors_index:
            return None
        
        monitor_summary = monitors_index[monitor_id]
        
        # Load additional details
        all_checks = db.get_all('check')
        all_incidents = db.get_all('incident')
        
        # Filter for this monitor
        monitor_checks = [c for c in all_checks if c['monitor_id'] == monitor_id]
        monitor_incidents = [i for i in all_incidents if i['monitor_id'] == monitor_id]
        
        # Sort by date
        monitor_checks.sort(key=lambda c: c['checked_at'], reverse=True)
        monitor_incidents.sort(key=lambda i: i['started_at'], reverse=True)
        
        details = {
            **monitor_summary,
            'all_checks': monitor_checks,
            'all_incidents': monitor_incidents[:10],  # Last 10 incidents
            'check_history_24h': [c for c in monitor_checks if self._is_within_days(c.get('checked_at'), 1)],
            'check_history_7d': [c for c in monitor_checks if self._is_within_days(c.get('checked_at'), 7)],
        }
        
        # Cache the details
        self._indexes[cache_key] = details
        self._index_timestamps[cache_key] = time.time()
        
        return details
    
    def invalidate_cache(self, monitor_id=None):
        """Invalidate cache for specific monitor or all caches."""
        if monitor_id:
            # Invalidate specific monitor caches
            keys_to_remove = [k for k in self._indexes.keys() if k.endswith(f'_{monitor_id}')]
            for key in keys_to_remove:
                self._indexes.pop(key, None)
                self._index_timestamps.pop(key, None)
        else:
            # Invalidate all caches
            self._indexes.clear()
            self._index_timestamps.clear()
        
        logger.debug(f"Cache invalidated for monitor_id={monitor_id}")
    
    def _is_index_valid(self, cache_key):
        """Check if cached index is still valid."""
        if cache_key not in self._indexes:
            return False
        
        cache_time = self._index_timestamps.get(cache_key, 0)
        return (time.time() - cache_time) < self._cache_ttl
    
    def _calculate_uptime_percentage(self, checks, days=7):
        """Calculate uptime percentage for given period."""
        if not checks:
            return 100.0
        
        cutoff = datetime.now(pytz.utc) - timedelta(days=days)
        recent_checks = [c for c in checks if self._is_within_days(c.get('checked_at'), days)]
        
        if not recent_checks:
            return 100.0
        
        up_checks = sum(1 for c in recent_checks if c['is_up'])
        return (up_checks / len(recent_checks)) * 100
    
    def _is_within_days(self, timestamp_str, days):
        """Check if timestamp is within the last N days."""
        if not timestamp_str:
            return False
        
        try:
            timestamp = parse_timestamp(timestamp_str)
            if timestamp:
                cutoff = datetime.now(pytz.utc) - timedelta(days=days)
                return timestamp >= cutoff
        except:
            pass
        
        return False
    
    def _get_recent_incidents(self):
        """Get recent incidents efficiently."""
        all_incidents = db.get_all('incident')
        
        # Only load incidents from last 24 hours or unresolved ones
        recent_incidents = []
        cutoff = datetime.now(pytz.utc) - timedelta(hours=24)
        
        for incident_data in all_incidents:
            try:
                started_at = parse_timestamp(incident_data.get('started_at'))
                is_resolved = incident_data.get('is_resolved', False)
                
                if not is_resolved or (started_at and started_at >= cutoff):
                    recent_incidents.append(incident_data)
            except:
                continue
        
        # Sort by start time, most recent first
        recent_incidents.sort(key=lambda i: i.get('started_at', ''), reverse=True)
        
        return recent_incidents[:5]  # Return top 5

# Global indexer instance
data_indexer = DataIndexer()

def get_optimized_dashboard_data(force_refresh=False):
    """Get optimized dashboard data using indexes."""
    return data_indexer.get_dashboard_summary(force_refresh)

def get_optimized_monitor_data(monitor_id, force_refresh=False):
    """Get optimized monitor data using indexes."""
    return data_indexer.get_monitor_details(monitor_id, force_refresh)

def invalidate_monitor_cache(monitor_id=None):
    """Invalidate cached data for monitor or all monitors."""
    data_indexer.invalidate_cache(monitor_id)

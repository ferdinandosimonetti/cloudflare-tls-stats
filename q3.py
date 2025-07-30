#!/usr/bin/env python3
"""
Cloudflare Multi-Zone GraphQL TLS Versions Query Script

This script queries Cloudflare's GraphQL API to fetch TLS version statistics
for all zones accessible with the provided API token.
"""

import requests
import json
from datetime import datetime, timezone, timedelta
import argparse
import sys
from typing import Dict, Any, Optional, List, Tuple
import time


def get_datetime_range(days_ago: int) -> tuple[str, str]:
    """
    Generate datetime range from X days ago to now.
    
    Args:
        days_ago: Number of days to go back from now
        
    Returns:
        Tuple of (start_datetime, end_datetime) in ISO format
    """
    now = datetime.now(timezone.utc)
    start_date = now - timedelta(days=days_ago)
    
    return start_date.isoformat(), now.isoformat()


def chunk_time_range(start_datetime: str, end_datetime: str, max_chunk_seconds: int = 259200) -> List[Tuple[str, str]]:
    """
    Break a time range into chunks that respect Cloudflare's API limits.
    
    Args:
        start_datetime: Start datetime in ISO format
        end_datetime: End datetime in ISO format
        max_chunk_seconds: Maximum seconds per chunk (default: 259200 = 3 days)
        
    Returns:
        List of (start, end) datetime tuples
    """
    # Parse datetime strings
    start_dt = datetime.fromisoformat(start_datetime.replace('Z', '+00:00'))
    end_dt = datetime.fromisoformat(end_datetime.replace('Z', '+00:00'))
    
    chunks = []
    current_start = start_dt
    
    while current_start < end_dt:
        # Calculate chunk end (either max chunk size or the final end time)
        chunk_end = min(current_start + timedelta(seconds=max_chunk_seconds), end_dt)
        
        # Add chunk
        chunks.append((current_start.isoformat(), chunk_end.isoformat()))
        
        # Move to next chunk
        current_start = chunk_end
    
    return chunks


def get_zones_query() -> str:
    """Build the GraphQL query to get all zones."""
    return """
    query GetZones {
        viewer {
            zones {
                zoneTag
                __typename
            }
            __typename
        }
    }
    """


def build_tls_graphql_query() -> str:
    """Build the GraphQL query string for TLS data."""
    return """
    query GetTLSVersions($zoneTag: string, $filter: ZoneHttpRequests1hGroupsFilter_InputObject!, $limit: uint64!) {
        viewer {
            zones(filter: {zoneTag: $zoneTag}) {
                httpRequests1hGroups(limit: $limit, filter: $filter) {
                    sum {
                        clientSSLMap {
                            clientSSLProtocol
                            requests
                            __typename
                        }
                        __typename
                    }
                    __typename
                }
                __typename
            }
            __typename
        }
    }
    """


def build_tls_variables(zone_tag: str, start_datetime: str, end_datetime: str, limit: int = 1000) -> Dict[str, Any]:
    """
    Build GraphQL variables for the TLS query.
    
    Args:
        zone_tag: Cloudflare zone identifier
        start_datetime: Start datetime in ISO format
        end_datetime: End datetime in ISO format
        limit: Maximum number of records to return
        
    Returns:
        Dictionary containing GraphQL variables
    """
    return {
        "zoneTag": zone_tag,
        "filter": {
            "AND": [
                {
                    "datetime_geq": start_datetime,
                    "datetime_lt": end_datetime
                }
            ]
        },
        "limit": limit
    }


def execute_graphql_query(api_token: str, query: str, variables: Dict[str, Any] = None, verbose: bool = False) -> Optional[Dict[str, Any]]:
    """
    Execute GraphQL query against Cloudflare API.
    
    Args:
        api_token: Cloudflare API token
        query: GraphQL query string
        variables: Query variables (optional)
        verbose: Enable verbose output
        
    Returns:
        API response data or None if error
    """
    url = "https://api.cloudflare.com/client/v4/graphql"
    
    headers = {
        "Authorization": f"Bearer {api_token}",
        "Content-Type": "application/json"
    }
    
    payload = {
        "query": query
    }
    
    if variables:
        payload["variables"] = variables
    
    try:
        if verbose:
            print(f"Making request to: {url}")
            print(f"Payload: {json.dumps(payload, indent=2)}")
        
        response = requests.post(url, headers=headers, json=payload, timeout=30)
        
        if verbose:
            print(f"Response status: {response.status_code}")
        
        response.raise_for_status()
        
        data = response.json()
        
        if verbose:
            print(f"Full response: {json.dumps(data, indent=2)}")
        
        if "errors" in data and data["errors"] is not None:
            print(f"GraphQL errors: {json.dumps(data['errors'], indent=2)}", file=sys.stderr)
            return None
            
        return data
        
    except requests.exceptions.RequestException as e:
        print(f"Request error: {e}", file=sys.stderr)
        return None
    except json.JSONDecodeError as e:
        print(f"JSON decode error: {e}", file=sys.stderr)
        return None


def get_all_zones_rest_api(api_token: str, verbose: bool = False) -> List[Dict[str, str]]:
    """
    Get all zones using Cloudflare REST API to get zone names.
    
    Args:
        api_token: Cloudflare API token
        verbose: Enable verbose output
        
    Returns:
        List of zone dictionaries with 'zoneTag' and 'name' keys
    """
    url = "https://api.cloudflare.com/client/v4/zones"
    headers = {
        "Authorization": f"Bearer {api_token}",
        "Content-Type": "application/json"
    }
    
    zones = []
    page = 1
    per_page = 50  # Max allowed by Cloudflare
    
    try:
        while True:
            params = {
                "page": page,
                "per_page": per_page
            }
            
            if verbose:
                print(f"Fetching zones page {page}...")
            
            response = requests.get(url, headers=headers, params=params, timeout=30)
            response.raise_for_status()
            
            data = response.json()
            
            if not data.get("success", False):
                print(f"REST API error: {data.get('errors', 'Unknown error')}", file=sys.stderr)
                return []
            
            page_zones = data.get("result", [])
            
            if not page_zones:
                break
            
            for zone in page_zones:
                zones.append({
                    "zoneTag": zone["id"],
                    "name": zone["name"]
                })
            
            # Check if there are more pages
            result_info = data.get("result_info", {})
            if page >= result_info.get("total_pages", 1):
                break
            
            page += 1
        
        if verbose:
            print(f"Found {len(zones)} zones total")
        
        return zones
        
    except requests.exceptions.RequestException as e:
        print(f"REST API request error: {e}", file=sys.stderr)
        return []
    except json.JSONDecodeError as e:
        print(f"REST API JSON decode error: {e}", file=sys.stderr)
        return []


def get_all_zones(api_token: str, verbose: bool = False) -> List[Dict[str, str]]:
    """
    Get all zones accessible with the API token.
    First tries REST API to get zone names, falls back to GraphQL if needed.
    
    Args:
        api_token: Cloudflare API token
        verbose: Enable verbose output
        
    Returns:
        List of zone dictionaries with 'zoneTag' and 'name' keys
    """
    # Try REST API first to get zone names
    zones = get_all_zones_rest_api(api_token, verbose)
    
    if zones:
        return zones
    
    # Fallback to GraphQL if REST API fails
    if verbose:
        print("REST API failed, falling back to GraphQL...")
    
    query = get_zones_query()
    response_data = execute_graphql_query(api_token, query, verbose=verbose)
    
    if not response_data:
        return []
    
    try:
        gql_zones = response_data["data"]["viewer"]["zones"]
        zone_list = []
        
        for zone in gql_zones:
            zone_list.append({
                "zoneTag": zone["zoneTag"],
                "name": zone["zoneTag"]  # Use zoneTag as name since name field doesn't exist
            })
        
        return zone_list
        
    except KeyError as e:
        print(f"Unexpected response structure when fetching zones: missing key {e}", file=sys.stderr)
        return []


def process_tls_data_for_zone(data: Dict[str, Any], zone_name: str) -> Dict[str, int]:
    """
    Process TLS version data from the API response for a single zone.
    
    Args:
        data: API response data
        zone_name: Name of the zone for display
        
    Returns:
        Dictionary with TLS protocol as key and request count as value
    """
    tls_stats = {}
    total_requests = 0
    
    try:
        zones = data["data"]["viewer"]["zones"]
        
        if not zones:
            return {}
        
        for zone in zones:
            http_requests = zone.get("httpRequests1hGroups", [])
            
            for group in http_requests:
                sum_data = group.get("sum", {})
                client_ssl_map = sum_data.get("clientSSLMap", [])
                
                for ssl_data in client_ssl_map:
                    protocol = ssl_data.get("clientSSLProtocol", "Unknown")
                    requests = ssl_data.get("requests", 0)
                    
                    if protocol in tls_stats:
                        tls_stats[protocol] += requests
                    else:
                        tls_stats[protocol] = requests
                    
                    total_requests += requests
        
        return tls_stats
        
    except KeyError as e:
        print(f"Unexpected data structure for zone {zone_name}: missing key {e}", file=sys.stderr)
        return {}


def aggregate_tls_stats(stats_list: List[Dict[str, int]]) -> Dict[str, int]:
    """
    Aggregate multiple TLS statistics dictionaries into one.
    
    Args:
        stats_list: List of TLS statistics dictionaries
        
    Returns:
        Aggregated dictionary with TLS protocol as key and total request count as value
    """
    aggregated = {}
    
    for stats in stats_list:
        for protocol, requests in stats.items():
            if protocol in aggregated:
                aggregated[protocol] += requests
            else:
                aggregated[protocol] = requests
    
    return aggregated


def fetch_zone_tls_stats_chunked(api_token: str, zone_name: str, zone_tag: str, 
                                start_datetime: str, end_datetime: str, 
                                limit: int, delay: float, verbose: bool = False) -> Dict[str, int]:
    """
    Fetch TLS statistics for a zone, handling time range chunking.
    
    Args:
        api_token: Cloudflare API token
        zone_name: Name of the zone
        zone_tag: Zone tag identifier
        start_datetime: Start datetime in ISO format
        end_datetime: End datetime in ISO format
        limit: Maximum number of records per query
        verbose: Enable verbose output
        
    Returns:
        Aggregated TLS statistics dictionary
    """
    # Get time chunks
    time_chunks = chunk_time_range(start_datetime, end_datetime)
    
    if verbose:
        print(f"   Splitting time range into {len(time_chunks)} chunks")
    
    # Build TLS query
    tls_query = build_tls_graphql_query()
    
    # Fetch data for each chunk
    chunk_stats = []
    
    for i, (chunk_start, chunk_end) in enumerate(time_chunks, 1):
        if verbose:
            print(f"   Fetching chunk {i}/{len(time_chunks)}: {chunk_start} to {chunk_end}")
        
        # Build variables for this chunk
        variables = build_tls_variables(zone_tag, chunk_start, chunk_end, limit)
        
        # Execute query
        response_data = execute_graphql_query(api_token, tls_query, variables, verbose)
        if delay > 0:
            time.sleep(delay)
        if response_data:
            chunk_tls_stats = process_tls_data_for_zone(response_data, zone_name)
            chunk_stats.append(chunk_tls_stats)
        else:
            print(f"   ⚠️  Failed to get data for chunk {i}")
    
    # Aggregate all chunks
    return aggregate_tls_stats(chunk_stats)


def display_zone_tls_stats(zone_name: str, zone_tag: str, tls_stats: Dict[str, int]) -> None:
    """
    Display TLS statistics for a single zone.
    
    Args:
        zone_name: Name of the zone (domain name)
        zone_tag: Zone tag identifier
        tls_stats: Dictionary of TLS protocol statistics
    """
    if not tls_stats:
        print(f"\n🔒 {zone_name} ({zone_tag})")
        print("   No TLS data available for this time period")
        return
    
    total_requests = sum(tls_stats.values())
    sorted_stats = sorted(tls_stats.items(), key=lambda x: x[1], reverse=True)
    
    print(f"\n🔒 {zone_name} ({zone_tag})")
    print(f"   Total requests: {total_requests:,}")
    
    for protocol, requests in sorted_stats:
        percentage = (requests / total_requests * 100) if total_requests > 0 else 0
        print(f"   {protocol:<15}: {requests:>10,} requests ({percentage:>6.2f}%)")


def export_zone_tls_stats(zone_name: str, zone_tag: str, tls_stats: Dict[str, int], export_file: str) -> None:
    """
    Export TLS statistics for a single zone to a file
    
    Args:
        zone_name: Name of the zone (domain name)
        zone_tag: Zone tag identifier
        tls_stats: Dictionary of TLS protocol statistics
        export_file: File path to export the statistics
    """
    if not tls_stats:
        print(f"\n🔒 {zone_name} ({zone_tag})")
        print("   No TLS data available for this time period")
        return
    
    total_requests = sum(tls_stats.values())
    sorted_stats = sorted(tls_stats.items(), key=lambda x: x[1], reverse=True)

    try:
        with open(export_file, 'a') as f:
            for protocol, requests in sorted_stats:
                f.write(f"{zone_name};{zone_tag};{protocol};{requests}\n")
    except IOError as e:
        print(f"Error writing to export file {export_file}: {e}", file=sys.stderr)


def main():
    """Main function to orchestrate the multi-zone TLS version query."""
    parser = argparse.ArgumentParser(description="Query Cloudflare TLS version statistics for all zones")
    parser.add_argument("--api-token", required=True, help="Cloudflare API token")
    parser.add_argument("--days-ago", type=int, default=30, help="Number of days ago to start query from (default: 3)")
    parser.add_argument("--limit", type=int, default=1000, help="Maximum number of records to return per zone (default: 1000)")
    parser.add_argument("--start-date", help="Custom start date (ISO format, overrides --days-ago)")
    parser.add_argument("--end-date", help="Custom end date (ISO format, defaults to now)")
    parser.add_argument("--verbose", action="store_true", help="Enable verbose output")
    parser.add_argument("--delay", type=float, default=0.5, help="Delay between zone queries in seconds (default: 0.5)")
    parser.add_argument("--zone-filter", help="Filter zones by name (case-insensitive substring match)")
    parser.add_argument("--summary", action="store_true", help="Show summary statistics across all zones")
    parser.add_argument("--export-file", type=str, help="Semicolon-separated file to export TLS stats (optional)")
    
    args = parser.parse_args()
    
    # Determine datetime range
    if args.start_date:
        start_datetime = args.start_date
        end_datetime = args.end_date or datetime.now(timezone.utc).isoformat()
    else:
        start_datetime, end_datetime = get_datetime_range(args.days_ago)
    
    # Calculate total time range for display
    start_dt = datetime.fromisoformat(start_datetime.replace('Z', '+00:00'))
    end_dt = datetime.fromisoformat(end_datetime.replace('Z', '+00:00'))
    total_days = (end_dt - start_dt).total_seconds() / 86400
    
    print("=" * 80)
    print("🌐 Cloudflare Multi-Zone TLS Statistics")
    print("=" * 80)
    print(f"📅 Time range: {start_datetime} to {end_datetime}")
    print(f"📊 Total days: {total_days:.1f}")
    print(f"📊 Limit per zone: {args.limit}")
    if args.zone_filter:
        print(f"🔍 Zone filter: {args.zone_filter}")
    print()
    
    # Get all zones
    print("🔍 Fetching accessible zones...")
    zones = get_all_zones(args.api_token, args.verbose)
    
    if not zones:
        print("❌ No zones found or unable to fetch zones. Check your API token permissions.")
        sys.exit(1)
    
    # Apply zone filter if specified
    if args.zone_filter:
        zones = [z for z in zones if args.zone_filter.lower() in z["name"].lower()]
        if not zones:
            print(f"❌ No zones match the filter '{args.zone_filter}'")
            sys.exit(1)
    
    print(f"✅ Found {len(zones)} zone(s) to process")
    
    # Process each zone
    all_zone_stats = {}
    global_tls_stats = {}

    for i, zone in enumerate(zones, 1):
        zone_name = zone["name"]
        zone_tag = zone["zoneTag"]
        
        print(f"\n⏳ Processing zone {i}/{len(zones)}: {zone_name}")
        
        if args.verbose:
            print(f"   Zone tag: {zone_tag}")
        
        # Fetch TLS stats with chunking
        zone_tls_stats = fetch_zone_tls_stats_chunked(
            args.api_token, zone_name, zone_tag, 
            start_datetime, end_datetime, 
            args.limit, args.delay, args.verbose
        )
        
        if zone_tls_stats:
            all_zone_stats[zone_name] = zone_tls_stats
            
            # Aggregate global stats
            for protocol, requests in zone_tls_stats.items():
                if protocol in global_tls_stats:
                    global_tls_stats[protocol] += requests
                else:
                    global_tls_stats[protocol] = requests
            
            display_zone_tls_stats(zone_name, zone_tag, zone_tls_stats)
            if args.export_file:
                export_zone_tls_stats(zone_name, zone_tag, zone_tls_stats, args.export_file)
        else:
            print(f"   ❌ Failed to get data for {zone_name}")
            all_zone_stats[zone_name] = {}
        
        # Add delay between zones to be respectful to the API
        if i < len(zones) and args.delay > 0:
            time.sleep(args.delay)
    
    # Show summary if requested
    if args.summary and global_tls_stats:
        print("\n" + "=" * 80)
        print("📊 GLOBAL SUMMARY ACROSS ALL ZONES")
        print("=" * 80)
        
        total_global_requests = sum(global_tls_stats.values())
        sorted_global_stats = sorted(global_tls_stats.items(), key=lambda x: x[1], reverse=True)
        
        print(f"Total requests across all zones: {total_global_requests:,}")
        print()
        
        for protocol, requests in sorted_global_stats:
            percentage = (requests / total_global_requests * 100) if total_global_requests > 0 else 0
            print(f"{protocol:<15}: {requests:>12,} requests ({percentage:>6.2f}%)")
    
    print("\n" + "=" * 80)
    print("✅ Processing complete!")
    print("=" * 80)


if __name__ == "__main__":
    main()
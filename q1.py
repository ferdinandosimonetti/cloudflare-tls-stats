#!/usr/bin/env python3
"""
Cloudflare GraphQL TLS Versions Query Script

This script queries Cloudflare's GraphQL API to fetch TLS version statistics
for a specified zone and time period.
"""

import requests
import json
from datetime import datetime, timezone, timedelta
import argparse
import sys
from typing import Dict, Any, Optional


def get_datetime_range(months_ago: int) -> tuple[str, str]:
    """
    Generate datetime range from X months ago to now.
    
    Args:
        months_ago: Number of months to go back from now
        
    Returns:
        Tuple of (start_datetime, end_datetime) in ISO format
    """
    now = datetime.now(timezone.utc)
    # Approximate months by using 30 days per month
    start_date = now - timedelta(days=months_ago * 30)
    
    return start_date.isoformat(), now.isoformat()


def build_graphql_query() -> str:
    """Build the GraphQL query string."""
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


def build_variables(zone_tag: str, start_datetime: str, end_datetime: str, limit: int = 1000) -> Dict[str, Any]:
    """
    Build GraphQL variables for the query.
    
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


def execute_graphql_query(api_token: str, query: str, variables: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """
    Execute GraphQL query against Cloudflare API.
    
    Args:
        api_token: Cloudflare API token
        query: GraphQL query string
        variables: Query variables
        
    Returns:
        API response data or None if error
    """
    url = "https://api.cloudflare.com/client/v4/graphql"
    
    headers = {
        "Authorization": f"Bearer {api_token}",
        "Content-Type": "application/json"
    }
    
    payload = {
        "query": query,
        "variables": variables
    }
    
    try:
        print(f"Making request to: {url}")
        print(f"Headers: {headers}")
        print(f"Payload: {json.dumps(payload, indent=2)}")
        
        response = requests.post(url, headers=headers, json=payload, timeout=30)
        
        print(f"Response status: {response.status_code}")
        print(f"Response headers: {dict(response.headers)}")
        
        response.raise_for_status()
        
        data = response.json()
        print(f"Full response: {json.dumps(data, indent=2)}")
        
        if "errors" in data and data["errors"] is not None:
            print(f"GraphQL errors: {json.dumps(data['errors'], indent=2)}", file=sys.stderr)
            return None
        
        if "errors" in data and data["errors"] is None:
            print("Response contains 'errors': null - this might indicate an authentication or permission issue")
            
        return data
        
    except requests.exceptions.RequestException as e:
        print(f"Request error: {e}", file=sys.stderr)
        return None
    except json.JSONDecodeError as e:
        print(f"JSON decode error: {e}", file=sys.stderr)
        print(f"Raw response text: {response.text}")
        return None


def process_tls_data(data: Dict[str, Any]) -> None:
    """
    Process and display TLS version data from the API response.
    
    Args:
        data: API response data
    """
    try:
        zones = data["data"]["viewer"]["zones"]
        
        if not zones:
            print("No zones found or no data available for the specified time period.")
            return
        
        for zone in zones:
            http_requests = zone.get("httpRequests1hGroups", [])
            
            if not http_requests:
                print("No HTTP request data found for this zone.")
                continue
            
            print("\nTLS Version Statistics:")
            print("-" * 50)
            
            total_requests = 0
            tls_stats = {}
            
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
            
            # Sort by request count (descending)
            sorted_stats = sorted(tls_stats.items(), key=lambda x: x[1], reverse=True)
            
            for protocol, requests in sorted_stats:
                percentage = (requests / total_requests * 100) if total_requests > 0 else 0
                print(f"{protocol:<15}: {requests:>10,} requests ({percentage:>6.2f}%)")
            
            print("-" * 50)
            print(f"{'Total':<15}: {total_requests:>10,} requests")
            
    except KeyError as e:
        print(f"Unexpected data structure: missing key {e}", file=sys.stderr)
    except Exception as e:
        print(f"Error processing data: {e}", file=sys.stderr)


def main():
    """Main function to orchestrate the TLS version query."""
    parser = argparse.ArgumentParser(description="Query Cloudflare TLS version statistics")
    parser.add_argument("--api-token", required=True, help="Cloudflare API token")
    parser.add_argument("--zone-tag", required=True, help="Cloudflare zone tag")
    parser.add_argument("--months-ago", type=int, default=1, help="Number of months ago to start query from (default: 1)")
    parser.add_argument("--limit", type=int, default=1000, help="Maximum number of records to return (default: 1000)")
    parser.add_argument("--start-date", help="Custom start date (ISO format, overrides --months-ago)")
    parser.add_argument("--end-date", help="Custom end date (ISO format, defaults to now)")
    parser.add_argument("--verbose", action="store_true", help="Enable verbose output")
    
    args = parser.parse_args()
    
    # Determine datetime range
    if args.start_date:
        start_datetime = args.start_date
        end_datetime = args.end_date or datetime.now(timezone.utc).isoformat()
    else:
        start_datetime, end_datetime = get_datetime_range(args.months_ago)
    
    if args.verbose:
        print(f"Querying zone: {args.zone_tag}")
        print(f"Time range: {start_datetime} to {end_datetime}")
        print(f"Limit: {args.limit}")
        print()
    
    # Build and execute query
    query = build_graphql_query()
    variables = build_variables(args.zone_tag, start_datetime, end_datetime, args.limit)
    
    if args.verbose:
        print("GraphQL Variables:")
        print(json.dumps(variables, indent=2))
        print()
    
    # Execute query
    response_data = execute_graphql_query(args.api_token, query, variables)
    
    if response_data is None:
        sys.exit(1)
    
    if args.verbose:
        print("Raw API Response:")
        print(json.dumps(response_data, indent=2))
        print()
    
    # Process and display results
    process_tls_data(response_data)


if __name__ == "__main__":
    main()
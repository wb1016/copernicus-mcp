import asyncio
import json
import os
import time
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Sequence, Union

import httpx
import shapely.geometry
from mcp.server import Server
from mcp.server.models import InitializationOptions
from pydantic import BaseModel, Field

# Import version
from . import __version__

# Create MCP server
mcp = Server("copernicus-mcp")

# Configuration
COPERNICUS_USERNAME = os.environ.get("COPERNICUS_USERNAME", "")
COPERNICUS_PASSWORD = os.environ.get("COPERNICUS_PASSWORD", "")

# API Configuration
COPERNICUS_API_BASE = "https://catalogue.dataspace.copernicus.eu/resto/api/collections"
COPERNICUS_NEW_API_BASE = "https://catalogue.dataspace.copernicus.eu/odata/v1"
COPERNICUS_AUTH_URL = "https://identity.dataspace.copernicus.eu/auth/realms/CDSE/protocol/openid-connect/token"

# API Limits
MAX_DATE_RANGE_DAYS = 90  # Maximum date range to prevent timeouts
DEFAULT_DATE_RANGE_DAYS = 30  # Default date range if not specified
API_TIMEOUT = 30.0  # seconds
MAX_RESULTS_PER_REQUEST = 50  # OData API limit

# Debug flag for authentication
DEBUG_AUTH = os.environ.get("DEBUG_AUTH", "false").lower() == "true"

# Cache for authentication token
_auth_token = None
_auth_token_expiry = 0

# Mission collections mapping
COPERNICUS_COLLECTIONS = {
    "sentinel-1": "Sentinel1",
    "sentinel-2": "Sentinel2",
    "sentinel-3": "Sentinel3",
    "sentinel-5p": "Sentinel5P",
    "sentinel-6": "Sentinel6",
}


class GeometryType(str):
    POINT = "point"
    POLYGON = "polygon"
    BBOX = "bbox"


class CloudCoverFilter(BaseModel):
    """Cloud cover filter for optical missions"""

    min: Optional[float] = None
    max: Optional[float] = None


class DateRange(BaseModel):
    """Date range for search"""

    start: Optional[datetime] = None
    end: Optional[datetime] = None

    def validate_date_range(self):
        """Validate date range is not too broad"""
        if self.start and self.end:
            days_diff = (self.end - self.start).days
            if days_diff > MAX_DATE_RANGE_DAYS:
                raise ValueError(
                    f"Date range too broad ({days_diff} days). "
                    f"Maximum allowed is {MAX_DATE_RANGE_DAYS} days."
                )


class MissionParameters(BaseModel):
    """Mission-specific parameters"""

    mission: str = Field(..., description="Mission name")
    processing_level: Optional[str] = Field(None, description="Processing level")
    product_type: Optional[str] = Field(None, description="Product type")
    satellite: Optional[str] = Field(None, description="Specific satellite")


class SearchParameters(BaseModel):
    """Search parameters for Copernicus API"""

    geometry: Union[Sequence[Sequence[float]], Dict[str, Any], Sequence[float]]
    geometry_type: GeometryType
    mission_params: MissionParameters
    date_range: Optional[DateRange] = None
    cloud_cover: Optional[CloudCoverFilter] = None
    max_results: int = 50


class ImageMetadata(BaseModel):
    """Metadata for a single satellite image"""

    id: str = Field(description="Image ID")
    title: str = Field(description="Image title")
    mission: str = Field(description="Mission name")
    collection: str = Field(description="Collection name")
    platform: str = Field(description="Satellite platform")
    acquisition_date: datetime = Field(description="Acquisition date and time (UTC)")
    cloud_cover_percentage: Optional[float] = Field(
        None, description="Cloud cover percentage"
    )
    processing_level: str = Field(description="Processing level")
    product_type: Optional[str] = Field(None, description="Product type")
    geometry: Optional[Dict[str, Any]] = Field(
        None, description="Image footprint geometry"
    )
    download_url: Optional[str] = Field(
        None,
        description="Direct download URL (requires authentication with Bearer token)",
    )
    thumbnail_url: Optional[str] = Field(None, description="Thumbnail URL")
    size_mb: Optional[float] = Field(None, description="File size in MB")
    additional_metadata: Dict[str, Any] = Field(
        default_factory=dict, description="Additional mission-specific metadata"
    )


class SearchResult(BaseModel):
    """Search results container"""

    total_results: int = Field(description="Total number of matching images")
    returned_results: int = Field(description="Number of results returned")
    images: List[ImageMetadata] = Field(description="List of image metadata")
    search_parameters: Dict[str, Any] = Field(description="Search parameters used")
    download_authentication_note: Optional[str] = Field(
        None,
        description="Note about download authentication requirements",
    )


def create_bbox_from_point(lat: float, lon: float, size_km: float = 1.0):
    """Create a bounding box around a point"""
    # Approximate conversion: 1 degree ≈ 111 km
    delta = size_km / 111.0

    bbox = [
        [lon - delta, lat - delta],
        [lon + delta, lat - delta],
        [lon + delta, lat + delta],
        [lon - delta, lat + delta],
        [lon - delta, lat - delta],
    ]

    return bbox


def validate_geometry(geometry, geometry_type: GeometryType):
    """Validate and normalize geometry"""
    if geometry_type == GeometryType.POINT:
        if isinstance(geometry, list) and len(geometry) == 2:
            # Convert point to bbox
            lat, lon = geometry[1], geometry[0]
            return create_bbox_from_point(lat, lon)
        elif isinstance(geometry, list) and len(geometry) == 2:
            # Already [lon, lat]
            lat, lon = geometry[1], geometry[0]
            return create_bbox_from_point(lat, lon)
        else:
            raise ValueError("Point geometry must be [lon, lat] or [lat, lon]")

    elif geometry_type == GeometryType.BBOX:
        if isinstance(geometry, list) and len(geometry) == 4:
            # Convert bbox coordinates to polygon
            min_lon, min_lat, max_lon, max_lat = geometry
            return [
                [min_lon, min_lat],
                [max_lon, min_lat],
                [max_lon, max_lat],
                [min_lon, max_lat],
                [min_lon, min_lat],
            ]
        else:
            raise ValueError(
                "Bounding box must be [min_lon, min_lat, max_lon, max_lat]"
            )

    elif geometry_type == GeometryType.POLYGON:
        if isinstance(geometry, list):
            # Check if it's a valid polygon
            if len(geometry) < 3:
                raise ValueError("Polygon must have at least 3 points")
            # Check if first and last points are the same (closed polygon)
            if geometry[0] != geometry[-1]:
                # Close the polygon
                geometry = geometry + [geometry[0]]
            return geometry
        elif isinstance(geometry, dict) and geometry.get("type") == "Polygon":
            # GeoJSON polygon
            coordinates = geometry.get("coordinates", [])
            if coordinates and len(coordinates) > 0:
                # Convert to simple coordinate list
                return coordinates[0]
            else:
                raise ValueError("Invalid GeoJSON polygon coordinates")
        else:
            raise ValueError("Polygon must be a list of coordinates or GeoJSON Polygon")

    else:
        raise ValueError(f"Unknown geometry type: {geometry_type}")


def get_collection_name(mission: str) -> str:
    """Get collection name for mission"""
    return COPERNICUS_COLLECTIONS.get(mission, mission)


def get_mission_name_pattern(mission: str) -> str:
    """Get mission name pattern for search"""
    if mission == "sentinel-1":
        return "S1%"
    elif mission == "sentinel-2":
        return "S2%"
    elif mission == "sentinel-3":
        return "S3%"
    elif mission == "sentinel-5p":
        return "S5P%"
    elif mission == "sentinel-6":
        return "S6%"
    else:
        return f"{mission.upper()}%"


def get_approximate_tiles(lat: float, lon: float, max_tiles: int = 2):
    """Get approximate Sentinel-2 tile IDs for a location"""
    # This is a simplified approximation
    # In production, you would use a proper tile grid system

    # Sentinel-2 uses MGRS grid
    # Simplified: Use UTM zone and rough grid position
    try:
        # Calculate UTM zone
        utm_zone = int((lon + 180) / 6) + 1

        # Simplified tile calculation (this is approximate)
        # Real tile calculation would use proper MGRS formulas
        lat_band = chr(ord("C") + int((80 - lat) / 8))  # Approximate lat band
        grid_square = "VQ"  # Default for testing

        tiles = []
        for i in range(max_tiles):
            # Generate variations for nearby tiles
            grid_num = str((int(lon) % 10) + i).zfill(2)
            tile_id = f"{utm_zone:02d}{lat_band}{grid_square}{grid_num}"
            tiles.append(tile_id)

        return tiles
    except:
        return None


async def get_auth_token():
    """Get authentication token for Copernicus Data Space API"""
    global _auth_token, _auth_token_expiry

    # Check if we have a valid cached token
    if _auth_token and time.time() < _auth_token_expiry:
        if DEBUG_AUTH:
            print(
                f"[DEBUG] Using cached auth token (expires in {_auth_token_expiry - time.time():.0f}s)"
            )
        return _auth_token

    if not COPERNICUS_USERNAME or not COPERNICUS_PASSWORD:
        if DEBUG_AUTH:
            print("[DEBUG] No credentials provided, attempting unauthenticated access")
        return None

    try:
        auth_data = {
            "client_id": "cdse-public",
            "username": COPERNICUS_USERNAME,
            "password": COPERNICUS_PASSWORD,
            "grant_type": "password",
        }

        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(COPERNICUS_AUTH_URL, data=auth_data)
            response.raise_for_status()
            token_data = response.json()

        _auth_token = token_data.get("access_token")
        expires_in = token_data.get("expires_in", 300)  # Default 5 minutes
        _auth_token_expiry = time.time() + expires_in - 60  # Subtract 1 minute buffer

        if DEBUG_AUTH:
            print(f"[DEBUG] Got new auth token (expires in {expires_in}s)")

        return _auth_token

    except httpx.HTTPStatusError as e:
        if DEBUG_AUTH:
            print(f"[DEBUG] Authentication failed: {e.response.status_code}")
            print(f"[DEBUG] Response: {e.response.text[:200]}")
        raise Exception(f"Authentication failed: {e.response.status_code}")
    except Exception as e:
        if DEBUG_AUTH:
            print(f"[DEBUG] Authentication error: {e}")
        raise Exception(f"Authentication error: {str(e)}")


async def search_copernicus_images(params: SearchParameters) -> SearchResult:
    """
    Search for Copernicus satellite images using Copernicus Data Space API

    Args:
        params: Search parameters

    Returns:
        SearchResult containing matching images
    """
    # Validate and normalize geometry
    try:
        geometry = validate_geometry(params.geometry, params.geometry_type)
    except ValueError as e:
        raise ValueError(f"Invalid geometry: {e}")

    # Get collection name
    collection_name = get_collection_name(params.mission_params.mission)

    # Prepare search parameters for Copernicus API
    search_params = {
        "collection": collection_name,
        "maxRecords": params.max_results,
        "sortParam": "startDate",
        "sortOrder": "descending",
    }

    # Add date range (required for API performance)
    if params.date_range:
        if params.date_range.start:
            search_params["startDate"] = params.date_range.start.isoformat() + "Z"
        if params.date_range.end:
            search_params["completionDate"] = params.date_range.end.isoformat() + "Z"
    else:
        # Set default date range if not provided
        end_date = datetime.now()
        start_date = end_date - timedelta(days=DEFAULT_DATE_RANGE_DAYS)
        search_params["startDate"] = start_date.isoformat() + "Z"
        search_params["completionDate"] = end_date.isoformat() + "Z"

    # Validate date range is not too broad
    if params.date_range and params.date_range.start and params.date_range.end:
        date_range_days = (params.date_range.end - params.date_range.start).days
        if date_range_days > MAX_DATE_RANGE_DAYS:
            raise ValueError(
                f"Date range too broad ({date_range_days} days). "
                f"Maximum allowed is {MAX_DATE_RANGE_DAYS} days. "
                "Please specify a narrower date range."
            )

    # Add cloud cover filter (only for optical missions)
    if params.cloud_cover and params.mission_params.mission in [
        "sentinel-2",
        "sentinel-3",
    ]:
        if params.cloud_cover.min is not None:
            search_params["cloudCover"] = f"[{params.cloud_cover.min},100]"
        elif params.cloud_cover.max is not None:
            search_params["cloudCover"] = f"[0,{params.cloud_cover.max}]"

    # Add satellite filter
    if params.mission_params.satellite:
        search_params["platform"] = params.mission_params.satellite

    # Add processing level filter
    if params.mission_params.processing_level:
        search_params["processingLevel"] = params.mission_params.processing_level

    # Add product type filter
    if params.mission_params.product_type:
        search_params["productType"] = params.mission_params.product_type

    # Convert geometry to WKT for API
    try:
        polygon = shapely.geometry.shape(geometry)
        search_params["geometry"] = polygon.wkt
    except Exception as e:
        raise ValueError(f"Failed to process geometry: {e}")

    # Make API request - using the new API endpoint
    # Note: The old /resto/api/collections/ endpoint is deprecated
    # Using the new OData v1 API endpoint
    api_url = f"{COPERNICUS_NEW_API_BASE}/Products"

    # Build OData query parameters following OData documentation best practices
    # Use Collection/Name filter for better performance as recommended in documentation
    collection_name = get_collection_name(params.mission_params.mission)

    # Build filter query following OData syntax
    filter_parts = [f"Collection/Name eq '{collection_name}'"]

    # Add date range filter (required for API performance as per documentation)
    if "startDate" in search_params or "completionDate" in search_params:
        date_filter = ""
        if "startDate" in search_params:
            date_filter += f"ContentDate/Start ge {search_params['startDate']}"
        if "completionDate" in search_params:
            if date_filter:
                date_filter += " and "
            date_filter += f"ContentDate/Start le {search_params['completionDate']}"

        if date_filter:
            filter_parts.append(f"({date_filter})")

    # For Sentinel-2, we can add tile filtering if geometry is a point
    if (
        params.mission_params.mission == "sentinel-2"
        and params.geometry_type == GeometryType.POINT
    ):
        try:
            # Get approximate tiles for the search area
            polygon = shapely.geometry.shape(geometry)
            center = polygon.centroid
            approximate_tiles = get_approximate_tiles(center.y, center.x)

            if approximate_tiles:
                # Create OR condition for multiple tiles (limit to first 2 tiles)
                tile_filters = []
                for tile in approximate_tiles[:2]:
                    tile_filters.append(f"contains(Name, '{tile}')")

                if tile_filters:
                    tile_filter = " or ".join(tile_filters)
                    filter_parts.append(f"({tile_filter})")
        except:
            pass

    odata_params = {
        "$top": min(
            params.max_results * 2, 50
        ),  # Get more results for client-side filtering
        "$orderby": "ContentDate/Start desc",
        "$filter": " and ".join(filter_parts),
    }

    # Cloud cover filtering will be done client-side to avoid complex OData queries
    # This follows the pattern from working scripts and documentation examples
    pass

    # Use odata_params for the API request
    search_params = odata_params

    # Store original max_results for client-side filtering
    original_max_results = params.max_results

    if DEBUG_AUTH:
        print(
            f"[DEBUG] OData query strategy: Get {search_params['$top']} results, filter client-side"
        )
        print(f"[DEBUG] OData filter: {search_params.get('$filter', 'No filter')}")
        print(f"[DEBUG] Collection name: {collection_name}")
        print(f"[DEBUG] Mission: {params.mission_params.mission}")

    if DEBUG_AUTH:
        print(f"[DEBUG] Search API URL: {api_url}")
        print(f"[DEBUG] Search params: {search_params}")

    # Try to get authentication token, but don't fail if not available

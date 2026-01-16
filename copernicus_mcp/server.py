"""
Copernicus MCP Server for Earth Observation Data

This MCP server provides tools for searching and retrieving satellite images
from the Copernicus Data Space ecosystem, supporting multiple missions including:
- Sentinel-1 (SAR)
- Sentinel-2 (Multispectral)
- Sentinel-3 (Ocean and Land)
- Sentinel-5P (Atmospheric)
- Sentinel-6 (Ocean topography)

Authentication:
This server requires Copernicus Data Space credentials for some operations.
Set the following environment variables:
- COPERNICUS_USERNAME: Your Copernicus Data Space email
- COPERNICUS_PASSWORD: Your Copernicus Data Space password

Register for free at: https://dataspace.copernicus.eu/

Note: The Copernicus Data Space API has performance limitations.
For efficient queries, always specify:
1. A date range (start_date and end_date)
2. A reasonably sized geographic area
3. Mission-specific filters when possible
"""

__version__ = "0.1.0"

import asyncio
import json
import os
import sys
import time
from datetime import datetime, timedelta
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Union

import httpx
import shapely.geometry
from fastmcp import FastMCP
from pydantic import BaseModel, Field

# Initialize FastMCP server
mcp = FastMCP("copernicus-eo")

# Configuration
COPERNICUS_API_BASE = "https://catalogue.dataspace.copernicus.eu"
COPERNICUS_AUTH_URL = "https://identity.dataspace.copernicus.eu/auth/realms/CDSE/protocol/openid-connect/token"
COPERNICUS_NEW_API_BASE = "https://catalogue.dataspace.copernicus.eu/odata/v1"

# Mission information
COPERNICUS_MISSIONS = {
    "sentinel-1": {
        "name": "Sentinel-1",
        "description": "Synthetic Aperture Radar (SAR) mission for land and ocean monitoring",
        "launch_date": "2014-04-03",
        "operational": True,
        "applications": [
            "Marine surveillance",
            "Land monitoring",
            "Emergency response",
        ],
        "sensors": ["C-band SAR"],
        "resolution": "5-40m",
        "revisit_time": "6-12 days",
        "data_access": "Free and open",
    },
    "sentinel-2": {
        "name": "Sentinel-2",
        "description": "Multispectral imaging mission for land monitoring",
        "launch_date": "2015-06-23",
        "operational": True,
        "applications": ["Vegetation monitoring", "Land cover mapping", "Agriculture"],
        "sensors": ["MSI (Multispectral Imager)"],
        "resolution": "10-60m",
        "revisit_time": "5 days",
        "data_access": "Free and open",
    },
    "sentinel-3": {
        "name": "Sentinel-3",
        "description": "Ocean and land monitoring mission",
        "launch_date": "2016-02-16",
        "operational": True,
        "applications": [
            "Ocean color",
            "Sea surface temperature",
            "Land surface temperature",
        ],
        "sensors": ["OLCI", "SLSTR", "SRAL"],
        "resolution": "300-1200m",
        "revisit_time": "1-2 days",
        "data_access": "Free and open",
    },
    "sentinel-5p": {
        "name": "Sentinel-5P",
        "description": "Atmospheric monitoring mission",
        "launch_date": "2017-10-13",
        "operational": True,
        "applications": ["Air quality", "Ozone monitoring", "Climate research"],
        "sensors": ["TROPOMI"],
        "resolution": "7x3.5km",
        "revisit_time": "1 day",
        "data_access": "Free and open",
    },
    "sentinel-6": {
        "name": "Sentinel-6",
        "description": "Ocean topography mission",
        "launch_date": "2020-11-21",
        "operational": True,
        "applications": ["Sea level rise", "Ocean circulation", "Climate monitoring"],
        "sensors": ["Poseidon-4", "AMR-C", "GNSS", "LRA"],
        "resolution": "N/A",
        "revisit_time": "10 days",
        "data_access": "Free and open",
    },
}

# Environment variables for authentication
COPERNICUS_USERNAME = os.environ.get("COPERNICUS_USERNAME", "")
COPERNICUS_PASSWORD = os.environ.get("COPERNICUS_PASSWORD", "")

# API Limits
MAX_DATE_RANGE_DAYS = 90  # Maximum date range to prevent timeouts
DEFAULT_DATE_RANGE_DAYS = 30  # Default date range if not specified
API_TIMEOUT = 60.0  # seconds - increased for large search results
MAX_RESULTS_PER_REQUEST = 50  # OData API limit

# Debug flag for authentication
DEBUG_AUTH = os.environ.get("DEBUG_AUTH", "false").lower() == "true"

# Cache for authentication token
_auth_token = None
_auth_token_expiry = 0

# Mission collections mapping
COPERNICUS_COLLECTIONS = {
    "sentinel-1": "SENTINEL-1",
    "sentinel-2": "SENTINEL-2",
    "sentinel-3": "SENTINEL-3",
    "sentinel-5p": "SENTINEL-5P",
    "sentinel-6": "SENTINEL-6",
}


# Models for request/response
class GeometryType(str, Enum):
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


class MissionParameters(BaseModel):
    """Mission-specific parameters"""

    mission: str = Field(..., description="Mission name")
    processing_level: Optional[str] = Field(None, description="Processing level")
    product_type: Optional[str] = Field(None, description="Product type")
    satellite: Optional[str] = Field(None, description="Specific satellite")


class SearchParameters(BaseModel):
    """Search parameters for Copernicus API"""

    geometry: Any
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


# Helper functions
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
    # First, try to parse the geometry as JSON string if it's a string
    if isinstance(geometry, str):
        try:
            geometry = json.loads(geometry)
        except json.JSONDecodeError:
            raise ValueError("Geometry string must be valid JSON")

    if geometry_type == GeometryType.POINT:
        if isinstance(geometry, list) and len(geometry) == 2:
            # Check if both elements are numbers
            if not all(isinstance(coord, (int, float)) for coord in geometry):
                raise ValueError("Point coordinates must be numbers")

            # Validate coordinate ranges
            lon, lat = geometry[0], geometry[1]
            if not (-180 <= lon <= 180):
                raise ValueError(f"Longitude must be between -180 and 180, got {lon}")
            if not (-90 <= lat <= 90):
                raise ValueError(f"Latitude must be between -90 and 90, got {lat}")

            # Convert point to bbox
            return create_bbox_from_point(lat, lon)
        else:
            raise ValueError("Point geometry must be [lon, lat]")

    elif geometry_type == GeometryType.BBOX:
        if isinstance(geometry, list) and len(geometry) == 4:
            # Check if all elements are numbers
            if not all(isinstance(coord, (int, float)) for coord in geometry):
                raise ValueError("Bounding box coordinates must be numbers")

            # Validate coordinate ranges
            min_lon, min_lat, max_lon, max_lat = geometry
            if not (-180 <= min_lon <= 180):
                raise ValueError(
                    f"Min longitude must be between -180 and 180, got {min_lon}"
                )
            if not (-90 <= min_lat <= 90):
                raise ValueError(
                    f"Min latitude must be between -90 and 90, got {min_lat}"
                )
            if not (-180 <= max_lon <= 180):
                raise ValueError(
                    f"Max longitude must be between -180 and 180, got {max_lon}"
                )
            if not (-90 <= max_lat <= 90):
                raise ValueError(
                    f"Max latitude must be between -90 and 90, got {max_lat}"
                )

            if min_lon >= max_lon:
                raise ValueError(
                    f"Min longitude ({min_lon}) must be less than max longitude ({max_lon})"
                )
            if min_lat >= max_lat:
                raise ValueError(
                    f"Min latitude ({min_lat}) must be less than max latitude ({max_lat})"
                )

            # Convert bbox coordinates to polygon
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
            # Handle nested coordinate lists (GeoJSON format)
            if geometry and isinstance(geometry[0], list):
                # Check if it's a list of coordinate pairs
                if geometry[0] and isinstance(geometry[0][0], (int, float)):
                    # This is a simple polygon: [[lon, lat], [lon, lat], ...]
                    # Validate all coordinates are numbers and within valid ranges
                    for i, coord_pair in enumerate(geometry):
                        if not (
                            isinstance(coord_pair, list)
                            and len(coord_pair) == 2
                            and all(
                                isinstance(coord, (int, float)) for coord in coord_pair
                            )
                        ):
                            raise ValueError(
                                f"Invalid coordinate pair at position {i}: {coord_pair}"
                            )

                        lon, lat = coord_pair[0], coord_pair[1]
                        if not (-180 <= lon <= 180):
                            raise ValueError(
                                f"Longitude at position {i} must be between -180 and 180, got {lon}"
                            )
                        if not (-90 <= lat <= 90):
                            raise ValueError(
                                f"Latitude at position {i} must be between -90 and 90, got {lat}"
                            )

                    if len(geometry) < 3:
                        raise ValueError("Polygon must have at least 3 points")
                    # Check if first and last points are the same (closed polygon)
                    if geometry[0] != geometry[-1]:
                        # Close the polygon
                        geometry = geometry + [geometry[0]]
                    return geometry
                else:
                    # This is a nested polygon: [[[lon, lat], [lon, lat], ...]]
                    # Extract the first ring (outer boundary)
                    polygon_ring = geometry[0]
                    if not polygon_ring:
                        raise ValueError("Polygon ring cannot be empty")

                    # Validate all coordinates are numbers and within valid ranges
                    for i, coord_pair in enumerate(polygon_ring):
                        if not (
                            isinstance(coord_pair, list)
                            and len(coord_pair) == 2
                            and all(
                                isinstance(coord, (int, float)) for coord in coord_pair
                            )
                        ):
                            raise ValueError(
                                f"Invalid coordinate pair at position {i}: {coord_pair}"
                            )

                        lon, lat = coord_pair[0], coord_pair[1]
                        if not (-180 <= lon <= 180):
                            raise ValueError(
                                f"Longitude at position {i} must be between -180 and 180, got {lon}"
                            )
                        if not (-90 <= lat <= 90):
                            raise ValueError(
                                f"Latitude at position {i} must be between -90 and 90, got {lat}"
                            )

                    if len(polygon_ring) < 3:
                        raise ValueError("Polygon must have at least 3 points")
                    # Check if first and last points are the same (closed polygon)
                    if polygon_ring[0] != polygon_ring[-1]:
                        # Close the polygon
                        polygon_ring = polygon_ring + [polygon_ring[0]]
                    return polygon_ring
            else:
                raise ValueError("Polygon must be a list of coordinate pairs")
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


async def get_auth_token(
    username: Optional[str] = None, password: Optional[str] = None
):
    """Get authentication token for Copernicus Data Space API"""
    global _auth_token, _auth_token_expiry

    # Use provided credentials or fall back to environment variables
    auth_username = username or COPERNICUS_USERNAME
    auth_password = password or COPERNICUS_PASSWORD

    # Check if we have a valid cached token (only if using default credentials)
    if (
        not username
        and not password
        and _auth_token
        and time.time() < _auth_token_expiry
    ):
        return _auth_token

    if not auth_username or not auth_password:
        return {
            "error": "Authentication required",
            "message": "Please provide username and password or set COPERNICUS_USERNAME and COPERNICUS_PASSWORD environment variables",
        }

    try:
        auth_data = {
            "client_id": "cdse-public",
            "username": auth_username,
            "password": auth_password,
            "grant_type": "password",
        }

        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(COPERNICUS_AUTH_URL, data=auth_data)
            response.raise_for_status()
            token_data = response.json()

        access_token = token_data.get("access_token")
        expires_in = token_data.get("expires_in", 300)

        # Only cache if using default credentials
        if not username and not password:
            _auth_token = access_token
            _auth_token_expiry = (
                time.time() + expires_in - 60
            )  # Subtract 1 minute buffer

        return {
            "access_token": access_token,
            "expires_in": expires_in,
            "token_type": token_data.get("token_type", "Bearer"),
            "scope": token_data.get("scope", ""),
        }

    except httpx.HTTPStatusError as e:
        return {
            "error": "Authentication failed",
            "status_code": e.response.status_code,
            "message": str(e),
        }
    except Exception as e:
        return {"error": "Authentication error", "message": str(e)}


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

    # Prepare OData query parameters
    filter_parts = [f"Collection/Name eq '{collection_name}'"]

    # Add date range filter
    if params.date_range and params.date_range.start and params.date_range.end:
        start_str = params.date_range.start.isoformat() + "Z"
        end_str = params.date_range.end.isoformat() + "Z"
        filter_parts.append(f"ContentDate/Start ge {start_str}")
        filter_parts.append(f"ContentDate/Start le {end_str}")

    # Add spatial filter using geo.intersects
    # Convert geometry to WKT (Well-Known Text) format for OData
    try:
        if geometry and len(geometry) > 0:
            wkt_geometry = ""

            # Handle different geometry types
            if params.geometry_type == GeometryType.POLYGON:
                # Create WKT polygon string
                # OData expects coordinates in [lon lat] order (no comma between coordinates)
                wkt_coords = []
                for coord in geometry:
                    if len(coord) == 2:
                        lon, lat = coord[0], coord[1]
                        wkt_coords.append(f"{lon} {lat}")

                if wkt_coords:
                    # Close the polygon if not already closed
                    if wkt_coords[0] != wkt_coords[-1]:
                        wkt_coords.append(wkt_coords[0])

                    wkt_geometry = f"POLYGON(({','.join(wkt_coords)}))"

            elif params.geometry_type == GeometryType.BBOX:
                # For bbox, create polygon from bbox coordinates
                # geometry is already a polygon from validate_geometry
                wkt_coords = []
                for coord in geometry:
                    if len(coord) == 2:
                        lon, lat = coord[0], coord[1]
                        wkt_coords.append(f"{lon} {lat}")

                if wkt_coords:
                    # Close the polygon if not already closed
                    if wkt_coords[0] != wkt_coords[-1]:
                        wkt_coords.append(wkt_coords[0])

                    wkt_geometry = f"POLYGON(({','.join(wkt_coords)}))"

            elif params.geometry_type == GeometryType.POINT:
                # For point, create a small buffer around the point
                # geometry is a polygon (bbox) from validate_geometry
                wkt_coords = []
                for coord in geometry:
                    if len(coord) == 2:
                        lon, lat = coord[0], coord[1]
                        wkt_coords.append(f"{lon} {lat}")

                if wkt_coords:
                    # Close the polygon if not already closed
                    if wkt_coords[0] != wkt_coords[-1]:
                        wkt_coords.append(wkt_coords[0])

                    wkt_geometry = f"POLYGON(({','.join(wkt_coords)}))"

            if wkt_geometry:
                spatial_filter = f"geo.intersects(Footprint, geography'{wkt_geometry}')"
                filter_parts.append(spatial_filter)
                print(
                    f"Debug: Added spatial filter: {spatial_filter[:100]}...",
                    file=sys.stderr,
                )

    except Exception as e:
        # If spatial filter fails, continue without it (better than failing completely)
        print(f"Warning: Could not create spatial filter: {e}", file=sys.stderr)

    odata_params = {
        "$top": min(params.max_results, MAX_RESULTS_PER_REQUEST),
        "$orderby": "ContentDate/Start desc",
        "$filter": " and ".join(filter_parts),
        "$count": "true",  # Get total count
    }

    api_url = f"{COPERNICUS_NEW_API_BASE}/Products"

    # Get authentication token
    auth_token = None
    try:
        auth_token_response = await get_auth_token()
        if (
            isinstance(auth_token_response, dict)
            and "access_token" in auth_token_response
        ):
            auth_token = auth_token_response["access_token"]
        else:
            auth_token = None
    except Exception as e:
        auth_token = None  # Continue without authentication

    # Make API request
    headers = {"Accept": "application/json"}
    if auth_token:
        headers["Authorization"] = f"Bearer {auth_token}"

    async with httpx.AsyncClient(timeout=API_TIMEOUT) as client:
        try:
            print(f"Debug: API URL: {api_url}", file=sys.stderr)
            print(
                f"Debug: OData filter: {odata_params.get('$filter', 'No filter')}",
                file=sys.stderr,
            )
            response = await client.get(api_url, params=odata_params, headers=headers)
            response.raise_for_status()
            data = response.json()
            print(
                f"Debug: API response count: {data.get('@odata.count', 'Unknown')}",
                file=sys.stderr,
            )
        except Exception as e:
            raise Exception(f"API request failed: {str(e)}")

    # Parse results
    images = []
    products = data.get("value", [])

    for product in products[: params.max_results]:
        image_id = product.get("Id", "")
        title = product.get("Name", "")

        # Parse acquisition date
        content_date = product.get("ContentDate", {})
        acquisition_date_str = content_date.get("Start", "")
        try:
            acquisition_date = datetime.fromisoformat(
                acquisition_date_str.replace("Z", "+00:00")
            )
        except:
            acquisition_date = datetime.now()

        # Get cloud cover from attributes
        cloud_cover = None
        if params.mission_params.mission in ["sentinel-2", "sentinel-3"]:
            attributes = product.get("Attributes", [])
            for attr in attributes:
                if attr.get("Name") == "cloudCover":
                    cloud_cover = attr.get("Value", 0)
                    if isinstance(cloud_cover, str):
                        try:
                            cloud_cover = float(cloud_cover)
                        except:
                            cloud_cover = None
                    break

        # Apply cloud cover filter
        if params.cloud_cover:
            if params.cloud_cover.min is not None and cloud_cover is not None:
                if cloud_cover < params.cloud_cover.min:
                    continue
            if params.cloud_cover.max is not None and cloud_cover is not None:
                if cloud_cover > params.cloud_cover.max:
                    continue

        # Get processing level
        processing_level = ""
        if "L1C" in title:
            processing_level = "L1C"
        elif "L2A" in title:
            processing_level = "L2A"
        elif "GRD" in title:
            processing_level = "GRD"
        elif "SLC" in title:
            processing_level = "SLC"

        # Get platform
        platform = ""
        if title.startswith("S1"):
            platform = "Sentinel-1" + title[2]
        elif title.startswith("S2"):
            platform = "Sentinel-2" + title[2]
        elif title.startswith("S3"):
            platform = "Sentinel-3" + title[2]
        elif title.startswith("S5P"):
            platform = "Sentinel-5P"
        elif title.startswith("S6"):
            platform = "Sentinel-6" + title[2]

        # Get product type
        product_type = ""
        if "MSIL1C" in title:
            product_type = "MSIL1C"
        elif "MSIL2A" in title:
            product_type = "MSIL2A"
        elif "GRD" in title:
            product_type = "GRD"
        elif "SLC" in title:
            product_type = "SLC"

        # Construct download URL - using correct download endpoint
        download_url = None
        if image_id:
            # According to OData documentation, the correct download endpoint is download.dataspace.copernicus.eu
            download_url = f"https://download.dataspace.copernicus.eu/odata/v1/Products({image_id})/$value"

        thumbnail_url = product.get("QuicklookUrl", "")

        # Get file size
        size_mb = (
            product.get("ContentLength", 0) / (1024 * 1024)
            if product.get("ContentLength")
            else None
        )

        # Collect additional metadata
        additional_metadata = {}
        attributes = product.get("Attributes", [])
        for attr in attributes:
            name = attr.get("Name", "")
            value = attr.get("Value", "")
            if name and value is not None:
                additional_metadata[name] = value

        # Get collection
        collection = ""
        s3path = product.get("S3Path", "")
        if "Sentinel-1" in s3path:
            collection = "Sentinel1"
        elif "Sentinel-2" in s3path:
            collection = "Sentinel2"
        elif "Sentinel-3" in s3path:
            collection = "Sentinel3"
        elif "Sentinel-5P" in s3path:
            collection = "Sentinel5P"
        elif "Sentinel-6" in s3path:
            collection = "Sentinel6"

        image_metadata = ImageMetadata(
            id=image_id,
            title=title,
            mission=params.mission_params.mission,
            collection=collection,
            platform=platform,
            acquisition_date=acquisition_date,
            cloud_cover_percentage=cloud_cover,
            processing_level=processing_level,
            product_type=product_type,
            geometry={},
            download_url=download_url,
            thumbnail_url=thumbnail_url,
            size_mb=size_mb,
            additional_metadata=additional_metadata,
        )

        images.append(image_metadata)

    # Get total count
    total_results = data.get("@odata.count", len(products))

    return SearchResult(
        total_results=total_results,
        returned_results=len(images),
        images=images,
        search_parameters=params.model_dump(),
        download_authentication_note="Download URLs require authentication with Bearer token. Use the MCP server's authentication token or your own Copernicus Data Space credentials.",
    )


# MCP Tools
@mcp.tool(
    name="search_copernicus_images",
    description="Search for Copernicus satellite images for a given region",
)
async def search_copernicus(
    geometry: Any = Field(
        ...,
        description="Geometry as polygon coordinates [[lon, lat], ...] or GeoJSON polygon [[[lon, lat], ...]] or point [lon, lat] or bbox [min_lon, min_lat, max_lon, max_lat]",
    ),
    geometry_type: GeometryType = Field(
        GeometryType.POLYGON,
        description="Type of geometry: 'point', 'polygon', or 'bbox'",
    ),
    mission: str = Field(
        "sentinel-2",
        description="Mission name: 'sentinel-1', 'sentinel-2', 'sentinel-3', 'sentinel-5p', 'sentinel-6'",
    ),
    processing_level: Optional[str] = Field(
        None,
        description="Processing level (e.g., 'L2A' for Sentinel-2, 'GRD' for Sentinel-1)",
    ),
    product_type: Optional[str] = Field(
        None,
        description="Product type (e.g., 'MSI' for Sentinel-2, 'IW' for Sentinel-1)",
    ),
    satellite: Optional[str] = Field(
        None, description="Specific satellite (e.g., 'Sentinel-2A', 'Sentinel-1A')"
    ),
    start_date: Optional[str] = Field(
        None, description="Start date (YYYY-MM-DD or YYYY-MM-DDTHH:MM:SS)"
    ),
    end_date: Optional[str] = Field(
        None, description="End date (YYYY-MM-DD or YYYY-MM-DDTHH:MM:SS)"
    ),
    min_cloud_cover: Optional[float] = Field(
        None,
        ge=0,
        le=100,
        description="Minimum cloud cover percentage (for optical missions)",
    ),
    max_cloud_cover: Optional[float] = Field(
        None,
        ge=0,
        le=100,
        description="Maximum cloud cover percentage (for optical missions)",
    ),
    max_results: int = Field(
        50, ge=1, le=1000, description="Maximum number of results to return"
    ),
) -> Dict[str, Any]:
    """
    Search for Copernicus satellite images.

    This tool searches the Copernicus Data Space for satellite images
    from various missions including Sentinel-1, Sentinel-2, Sentinel-3,
    Sentinel-5P, and Sentinel-6.

    Examples:
    - Search for Sentinel-2 images over Paris with <20% cloud cover
    - Find Sentinel-1 SAR images for flood monitoring
    - Get Sentinel-5P atmospheric data for air quality analysis
    - Retrieve Sentinel-3 ocean temperature data
    """
    try:
        # Validate mission
        if mission not in COPERNICUS_COLLECTIONS:
            return {
                "error": f"Unknown mission: {mission}",
                "available_missions": list(COPERNICUS_COLLECTIONS.keys()),
            }

        # Parse date range
        date_range = None
        if start_date or end_date:
            start = None
            end = None

            if start_date:
                try:
                    start = datetime.fromisoformat(start_date.replace("Z", "+00:00"))
                except:
                    start = datetime.fromisoformat(start_date + "T00:00:00+00:00")

            if end_date:
                try:
                    end = datetime.fromisoformat(end_date.replace("Z", "+00:00"))
                except:
                    end = datetime.fromisoformat(end_date + "T23:59:59+00:00")

            date_range = DateRange(start=start, end=end)

        # Create cloud cover filter
        cloud_filter = None
        if min_cloud_cover is not None or max_cloud_cover is not None:
            cloud_filter = CloudCoverFilter(min=min_cloud_cover, max=max_cloud_cover)

        # Create mission parameters
        mission_params = MissionParameters(
            mission=mission,
            processing_level=processing_level,
            product_type=product_type,
            satellite=satellite,
        )

        # Create search parameters
        search_params = SearchParameters(
            geometry=geometry,
            geometry_type=geometry_type,
            mission_params=mission_params,
            date_range=date_range,
            cloud_cover=cloud_filter,
            max_results=max_results,
        )

        # Perform search
        result = await search_copernicus_images(search_params)

        # Format response
        response = {
            "total_results": result.total_results,
            "returned_results": result.returned_results,
            "images": [img.dict() for img in result.images],
            "search_summary": {
                "mission": mission,
                "geometry_type": geometry_type.value,
                "date_range": {"start": start_date, "end": end_date},
                "cloud_cover_filter": {"min": min_cloud_cover, "max": max_cloud_cover},
                "processing_level": processing_level,
                "product_type": product_type,
                "satellite": satellite,
            },
            "download_authentication_note": result.download_authentication_note,
        }

        return response

    except Exception as e:
        error_msg = str(e)
        if "Authentication failed" in error_msg:
            return {
                "error": error_msg,
                "message": "Authentication failed. Please check your Copernicus Data Space credentials in your MCP client settings.",
                "help": "Set COPERNICUS_USERNAME and COPERNICUS_PASSWORD environment variables in your code editor's MCP configuration.",
            }
        elif "Cannot connect" in error_msg or "timed out" in error_msg:
            return {
                "error": error_msg,
                "message": "Network connection issue. Please check your internet connection.",
            }
        else:
            return {
                "error": error_msg,
                "message": f"Failed to search for {mission} images",
            }


@mcp.tool(
    name="get_image_details",
    description="Get comprehensive metadata for a specific satellite image including download URL",
)
async def get_image_details(
    image_id: str,
    mission: str = "sentinel-2",
) -> Dict[str, Any]:
    """
    Get detailed metadata for a specific satellite image.

    Args:
        image_id: The unique identifier of the satellite image
        mission: Mission name (e.g., 'sentinel-2', 'sentinel-1')

    Returns:
        Dictionary containing:
        - image: Detailed image metadata including download URL
        - authentication_note: Instructions for downloading the image
        - python_example: Example Python code for downloading with authentication
    """
    try:
        # Get authentication token
        auth_token_response = await get_auth_token()
        if (
            isinstance(auth_token_response, dict)
            and "access_token" in auth_token_response
        ):
            auth_token = auth_token_response["access_token"]
        else:
            auth_token = None

        # Build API URL for the specific product
        api_url = f"{COPERNICUS_NEW_API_BASE}/Products({image_id})"

        async with httpx.AsyncClient(timeout=API_TIMEOUT) as client:
            response = await client.get(
                api_url,
                headers={
                    "Accept": "application/json",
                    "Authorization": f"Bearer {auth_token}",
                },
            )

            if response.status_code != 200:
                return {
                    "error": f"Failed to get image details: {response.status_code}",
                    "message": f"API returned: {response.text[:200]}",
                }

            product = response.json()

            # Extract basic metadata
            title = product.get("Name", "")
            collection = product.get("Collection", {}).get("Name", "")
            platform = product.get("Platform", {}).get("Name", "")

            # Parse acquisition date
            content_date = product.get("ContentDate", {})
            acquisition_date_str = content_date.get("Start", "")
            acquisition_date = datetime.fromisoformat(
                acquisition_date_str.replace("Z", "+00:00")
            )

            # Get cloud cover from attributes
            cloud_cover = None
            attributes = product.get("Attributes", [])
            for attr in attributes:
                if attr.get("Name") == "cloudCover":
                    cloud_cover = attr.get("Value", 0)
                    try:
                        cloud_cover = float(cloud_cover)
                    except:
                        cloud_cover = None
                    break

            # Get processing level and product type
            processing_level = ""
            product_type = ""
            for attr in attributes:
                if attr.get("Name") == "processingLevel":
                    processing_level = attr.get("Value", "")
                elif attr.get("Name") == "productType":
                    product_type = attr.get("Value", "")

            # Get file size
            size_bytes = product.get("ContentLength", 0)
            size_mb = size_bytes / (1024 * 1024) if size_bytes else None

            # Get S3 path for thumbnail
            s3path = product.get("S3Path", "")
            thumbnail_url = (
                f"https://catalogue.dataspace.copernicus.eu/odata/v1/Products({image_id})/Products('quicklook')/$value"
                if s3path
                else None
            )

            # Create download URL (requires authentication)
            download_url = f"https://download.dataspace.copernicus.eu/odata/v1/Products({image_id})/$value"

            # Build image metadata
            image_metadata = {
                "id": image_id,
                "title": title,
                "mission": mission,
                "collection": collection,
                "platform": platform,
                "acquisition_date": acquisition_date.isoformat(),
                "cloud_cover_percentage": cloud_cover,
                "processing_level": processing_level,
                "product_type": product_type,
                "geometry": {},
                "download_url": download_url,
                "thumbnail_url": thumbnail_url,
                "size_mb": size_mb,
                "additional_metadata": {
                    "s3_path": s3path,
                    "content_length": size_bytes,
                    "attributes": attributes,
                },
            }

            # Python example for downloading
            python_example = f'''import requests

# Get your access token first (using Copernicus credentials)
access_token = "your_access_token_here"

url = "{download_url}"
headers = {{"Authorization": f"Bearer {{access_token}}"}}

response = requests.get(url, headers=headers, stream=True)
if response.status_code == 200:
    with open("image.zip", "wb") as f:
        for chunk in response.iter_content(chunk_size=8192):
            f.write(chunk)
    print("Download completed successfully!")
else:
    print(f"Download failed: {{response.status_code}} - {{response.text}}")'''

            return {
                "image": image_metadata,
                "authentication_note": "Download requires Bearer token authentication. Use your Copernicus Data Space credentials to obtain an access token.",
                "python_example": python_example,
                "note": "The download URL follows OData API format and requires authentication. Search operations may work without authentication, but downloads always require valid credentials.",
            }

    except Exception as e:
        error_msg = str(e)
        if "Authentication failed" in error_msg:
            return {
                "error": error_msg,
                "message": "Authentication required. Please set COPERNICUS_USERNAME and COPERNICUS_PASSWORD environment variables.",
                "note": "You can register for free at https://dataspace.copernicus.eu/",
            }
        elif "Cannot connect" in error_msg or "timed out" in error_msg:
            return {
                "error": error_msg,
                "message": "Network connection issue. Please check your internet connection.",
            }
        else:
            return {
                "error": error_msg,
                "message": f"Failed to get details for image {image_id}",
            }


@mcp.tool(
    name="get_mission_info",
    description="Get detailed information about Copernicus satellite missions",
)
async def get_mission_info(
    mission: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Get information about available Copernicus missions and their capabilities.

    Args:
        mission: Optional specific mission name. If not provided, returns info for all missions.

    Returns:
        Dictionary containing mission information including:
        - name: Mission name
        - description: Mission description
        - launch_date: Launch date
        - operational: Whether mission is operational
        - applications: List of applications
        - sensors: List of sensors
        - resolution: Spatial resolution
        - revisit_time: Temporal revisit time
        - data_access: Data access policy
    """
    try:
        if mission:
            mission_lower = mission.lower()
            if mission_lower not in COPERNICUS_MISSIONS:
                return {
                    "error": f"Mission '{mission}' not found",
                    "available_missions": list(COPERNICUS_MISSIONS.keys()),
                }

            return {
                "mission": COPERNICUS_MISSIONS[mission_lower],
                "note": "For detailed API documentation and data access, visit https://dataspace.copernicus.eu/",
            }
        else:
            return {
                "missions": COPERNICUS_MISSIONS,
                "total_missions": len(COPERNICUS_MISSIONS),
                "note": "For detailed API documentation and data access, visit https://dataspace.copernicus.eu/",
            }
    except Exception as e:
        return {
            "error": str(e),
            "message": "Failed to get mission information",
        }


@mcp.tool(
    name="get_recent_images",
    description="Get the most recent satellite images for a region",
)
async def get_recent_images(
    geometry: Any,
    geometry_type: GeometryType = GeometryType.POINT,
    mission: str = "sentinel-2",
    days_back: int = 7,
    max_results: int = 10,
) -> Dict[str, Any]:
    """
    Get the most recent satellite images for a region.

    Args:
        geometry: Geometry as polygon coordinates [[lon, lat], ...] or GeoJSON polygon [[[lon, lat], ...]] or point [lon, lat] or bbox [min_lon, min_lat, max_lon, max_lat]
        geometry_type: Type of geometry: 'point', 'polygon', or 'bbox'
        mission: Mission name: 'sentinel-1', 'sentinel-2', 'sentinel-3', 'sentinel-5p', 'sentinel-6'
        days_back: Number of days to look back from current date (1-365)
        max_results: Maximum number of recent images to return (1-100)

    Returns:
        Dictionary containing recent images with metadata including download URLs
    """
    try:
        # Validate days_back
        if days_back < 1 or days_back > 365:
            return {
                "error": f"days_back must be between 1 and 365, got {days_back}",
                "message": "Please specify a valid date range",
            }

        # Validate max_results
        if max_results < 1 or max_results > 100:
            return {
                "error": f"max_results must be between 1 and 100, got {max_results}",
                "message": "Please specify a valid number of results",
            }

        # Calculate date range
        end_date = datetime.now()
        start_date = end_date - timedelta(days=days_back)

        # Create mission parameters
        mission_params = MissionParameters(
            mission=mission,
            processing_level=None,
            product_type=None,
            satellite=None,
        )

        # Create search parameters
        search_params = SearchParameters(
            geometry=geometry,
            geometry_type=geometry_type,
            mission_params=mission_params,
            date_range=DateRange(start=start_date, end=end_date),
            max_results=max_results,
        )

        # Use the existing search function
        try:
            search_result = await search_copernicus_images(search_params)

            # Convert SearchResult to dictionary
            result = {
                "total_results": search_result.total_results,
                "returned_results": search_result.returned_results,
                "images": [img.dict() for img in search_result.images],
                "search_parameters": search_result.search_parameters,
                "download_authentication_note": search_result.download_authentication_note,
            }

            # Add context about the date range
            result["date_range"] = {
                "start_date": start_date.isoformat(),
                "end_date": end_date.isoformat(),
                "days_back": days_back,
            }
            result["note"] = (
                f"Showing most recent {len(result.get('images', []))} images from the last {days_back} days"
            )

            return result

        except Exception as e:
            error_msg = str(e)
            if "Authentication failed" in error_msg:
                return {
                    "error": error_msg,
                    "message": "Authentication required. Please set COPERNICUS_USERNAME and COPERNICUS_PASSWORD environment variables.",
                    "note": "You can register for free at https://dataspace.copernicus.eu/",
                }
            elif "Cannot connect" in error_msg or "timed out" in error_msg:
                return {
                    "error": error_msg,
                    "message": "Network connection issue. Please check your internet connection.",
                }
            else:
                return {
                    "error": error_msg,
                    "message": f"Failed to search for recent {mission} images",
                }

    except Exception as e:
        error_msg = str(e)
        return {
            "error": error_msg,
            "message": f"Failed to get recent images for {mission}",
        }


@mcp.tool(
    name="check_coverage",
    description="Check satellite image coverage for a region over time",
)
async def check_coverage(
    geometry: Any,
    start_date: str,
    end_date: str,
    geometry_type: GeometryType = GeometryType.POLYGON,
    mission: str = "sentinel-2",
    group_by: str = "month",
) -> Dict[str, Any]:
    """
    Check satellite image coverage for a region over time.

    Args:
        geometry: Geometry as polygon coordinates [[lon, lat], ...] or GeoJSON polygon [[[lon, lat], ...]] or point [lon, lat] or bbox [min_lon, min_lat, max_lon, max_lat]
        start_date: Start date (YYYY-MM-DD or YYYY-MM-DDTHH:MM:SS)
        end_date: End date (YYYY-MM-DD or YYYY-MM-DDTHH:MM:SS)
        geometry_type: Type of geometry: 'point', 'polygon', or 'bbox'
        mission: Mission name: 'sentinel-1', 'sentinel-2', 'sentinel-3', 'sentinel-5p', 'sentinel-6'
        group_by: Group results by: 'day', 'week', 'month', 'year'

    Returns:
        Dictionary containing coverage analysis with temporal distribution
    """
    try:
        # Parse dates
        try:
            start_dt = datetime.fromisoformat(start_date.replace("Z", "+00:00"))
            end_dt = datetime.fromisoformat(end_date.replace("Z", "+00:00"))
        except ValueError:
            return {
                "error": "Invalid date format",
                "message": "Dates must be in ISO format (YYYY-MM-DD or YYYY-MM-DDTHH:MM:SS)",
            }

        # Validate date range
        if start_dt >= end_dt:
            return {
                "error": "Invalid date range",
                "message": "Start date must be before end date",
            }

        # Validate group_by
        valid_group_by = ["day", "week", "month", "year"]
        if group_by not in valid_group_by:
            return {
                "error": f"Invalid group_by value: {group_by}",
                "message": f"Valid values are: {', '.join(valid_group_by)}",
            }

        # Create mission parameters
        mission_params = MissionParameters(
            mission=mission,
            processing_level=None,
            product_type=None,
            satellite=None,
        )

        # Create search parameters for the entire date range
        search_params = SearchParameters(
            geometry=geometry,
            geometry_type=geometry_type,
            mission_params=mission_params,
            date_range=DateRange(start=start_dt, end=end_dt),
            max_results=1000,  # Large limit to get comprehensive coverage
        )

        # Search for all images in the date range
        try:
            search_result = await search_copernicus_images(search_params)

            # Convert SearchResult to dictionary
            result = {
                "total_results": search_result.total_results,
                "returned_results": search_result.returned_results,
                "images": [img.dict() for img in search_result.images],
                "search_parameters": search_result.search_parameters,
                "download_authentication_note": search_result.download_authentication_note,
            }

        except Exception as e:
            error_msg = str(e)
            if "Authentication failed" in error_msg:
                return {
                    "error": error_msg,
                    "message": "Authentication required. Please set COPERNICUS_USERNAME and COPERNICUS_PASSWORD environment variables.",
                    "note": "You can register for free at https://dataspace.copernicus.eu/",
                }
            elif "Cannot connect" in error_msg or "timed out" in error_msg:
                return {
                    "error": error_msg,
                    "message": "Network connection issue. Please check your internet connection.",
                }
            else:
                return {
                    "error": error_msg,
                    "message": f"Failed to search for {mission} images for coverage analysis",
                }

        # Analyze coverage
        images = result.get("images", [])
        total_images = len(images)

        # Group images by time period
        coverage_by_period = {}
        for image in images:
            try:
                acquisition_date = datetime.fromisoformat(
                    image.get("acquisition_date", "").replace("Z", "+00:00")
                )

                # Determine period key based on group_by
                if group_by == "day":
                    period_key = acquisition_date.strftime("%Y-%m-%d")
                elif group_by == "week":
                    # ISO week year and week number
                    year, week, _ = acquisition_date.isocalendar()
                    period_key = f"{year}-W{week:02d}"
                elif group_by == "month":
                    period_key = acquisition_date.strftime("%Y-%m")
                elif group_by == "year":
                    period_key = acquisition_date.strftime("%Y")
                else:
                    period_key = acquisition_date.strftime("%Y-%m")

                if period_key not in coverage_by_period:
                    coverage_by_period[period_key] = {
                        "count": 0,
                        "images": [],
                        "cloud_cover_sum": 0,
                        "cloud_cover_count": 0,
                    }

                coverage_by_period[period_key]["count"] += 1
                coverage_by_period[period_key]["images"].append(
                    {
                        "id": image.get("id"),
                        "title": image.get("title"),
                        "acquisition_date": image.get("acquisition_date"),
                        "cloud_cover_percentage": image.get("cloud_cover_percentage"),
                        "download_url": image.get("download_url"),
                    }
                )

                # Track cloud cover statistics
                cloud_cover = image.get("cloud_cover_percentage")
                if cloud_cover is not None:
                    coverage_by_period[period_key]["cloud_cover_sum"] += cloud_cover
                    coverage_by_period[period_key]["cloud_cover_count"] += 1

            except Exception as e:
                # Skip images with invalid dates
                continue

        # Calculate statistics for each period
        coverage_analysis = []
        for period_key, period_data in coverage_by_period.items():
            avg_cloud_cover = None
            if period_data["cloud_cover_count"] > 0:
                avg_cloud_cover = (
                    period_data["cloud_cover_sum"] / period_data["cloud_cover_count"]
                )

            coverage_analysis.append(
                {
                    "period": period_key,
                    "image_count": period_data["count"],
                    "average_cloud_cover": avg_cloud_cover,
                    "sample_images": period_data["images"][
                        :3
                    ],  # Include first 3 images as samples
                }
            )

        # Sort by period
        coverage_analysis.sort(key=lambda x: x["period"])

        return {
            "coverage_analysis": coverage_analysis,
            "summary": {
                "total_images": total_images,
                "date_range": {
                    "start_date": start_dt.isoformat(),
                    "end_date": end_dt.isoformat(),
                    "total_days": (end_dt - start_dt).days,
                },
                "group_by": group_by,
                "periods_covered": len(coverage_analysis),
                "images_per_period_avg": total_images / len(coverage_analysis)
                if coverage_analysis
                else 0,
            },
            "note": "Coverage analysis shows temporal distribution of available images. Use this to identify gaps or dense periods of data collection.",
            "download_authentication_note": "Download URLs require authentication with Bearer token. Use the MCP server's authentication token or your own Copernicus Data Space credentials.",
        }

    except Exception as e:
        error_msg = str(e)
        return {
            "error": error_msg,
            "message": f"Failed to analyze coverage for {mission}",
        }


@mcp.tool(
    name="download_image",
    description="Download a Copernicus satellite image by ID. Requires COPERNICUS_USERNAME and COPERNICUS_PASSWORD environment variables. WARNING: Full product downloads can take hours. Use download_type='quicklook' for testing.",
)
async def download_image(
    image_id: str,
    mission: str = "sentinel-2",
    download_type: str = "full",
    output_dir: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Download a Copernicus satellite image.

    Args:
        image_id: The ID of the image to download (from search results)
        mission: Mission name (e.g., 'sentinel-2', 'sentinel-1')
        download_type: Type of download - 'full', 'quicklook', or 'compressed'
        output_dir: Optional output directory (default: 'downloads')

    Returns:
        Dictionary with download status and file information

    WARNING:
    - Full product downloads can be several GB and take HOURS to complete
    - MCP clients may timeout during long downloads
    - Use download_type='quicklook' for testing (small files, fast downloads)
    - Progress is reported to stderr every 5 seconds during download
    """
    return await _download_image_helper(image_id, mission, download_type, output_dir)


async def _download_image_helper(
    image_id: str,
    mission: str = "sentinel-2",
    download_type: str = "full",
    output_dir: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Helper function to download a Copernicus satellite image.

    Args:
        image_id: The ID of the image to download (from search results)
        mission: Mission name (e.g., 'sentinel-2', 'sentinel-1')
        download_type: Type of download - 'full', 'quicklook', or 'compressed'
        output_dir: Optional output directory (default: 'downloads')

    Returns:
        Dictionary with download status and file information

    WARNING:
    - Full product downloads can be several GB and take HOURS to complete
    - MCP clients may timeout during long downloads
    - Use download_type='quicklook' for testing (small files, fast downloads)
    - Progress is reported to stderr every 5 seconds during download
    """
    import os
    import sys
    import time
    from pathlib import Path

    import httpx

    # Check for authentication
    username = os.environ.get("COPERNICUS_USERNAME")
    password = os.environ.get("COPERNICUS_PASSWORD")

    if not username or not password:
        return {
            "error": "Authentication required",
            "message": "Please set COPERNICUS_USERNAME and COPERNICUS_PASSWORD environment variables",
            "instructions": {
                "bash": "export COPERNICUS_USERNAME='your-email@example.com'\nexport COPERNICUS_PASSWORD='your-password'",
                "python": "import os\nos.environ['COPERNICUS_USERNAME'] = 'your-email@example.com'\nos.environ['COPERNICUS_PASSWORD'] = 'your-password'",
            },
            "register_url": "https://dataspace.copernicus.eu/",
        }

    try:
        # Get access token
        token_response = await get_auth_token(username, password)
        if isinstance(token_response, dict) and "error" in token_response:
            return token_response

        access_token = token_response.get("access_token")
        if not access_token:
            return {
                "error": "Authentication failed",
                "message": "No access token received",
                "response": token_response,
            }

        # Set up output directory
        if output_dir:
            download_dir = Path(output_dir)
        else:
            download_dir = Path("downloads")

        download_dir.mkdir(exist_ok=True, parents=True)

        # Generate filename
        safe_mission = mission.replace("-", "_")
        timestamp = int(time.time())
        filename = f"{safe_mission}_{image_id}_{timestamp}"

        # Download based on type
        if download_type == "full":
            print(
                f"WARNING: Full product download started. This can take HOURS to complete.",
                file=sys.stderr,
            )
            print(
                f"Progress will be reported every 5 seconds. MCP clients may timeout.",
                file=sys.stderr,
            )
            print(
                f"For testing, use download_type='quicklook' instead.",
                file=sys.stderr,
            )
            sys.stderr.flush()
            return await _download_full_product(
                image_id, filename, download_dir, access_token
            )
        elif download_type == "quicklook":
            print(
                f"Quicklook download started (fast, small file)",
                file=sys.stderr,
            )
            sys.stderr.flush()
            return await _download_quicklook(
                image_id, filename, download_dir, access_token
            )
        elif download_type == "compressed":
            print(
                f"Compressed download started. This may take several minutes.",
                file=sys.stderr,
            )
            print(
                f"Progress will be reported every 5 seconds.",
                file=sys.stderr,
            )
            sys.stderr.flush()
            return await _download_compressed(
                image_id, filename, download_dir, access_token
            )
        else:
            return {
                "error": "Invalid download type",
                "message": "download_type must be 'full', 'quicklook', or 'compressed'",
                "received": download_type,
            }

    except Exception as e:
        return {
            "error": "Download failed",
            "exception": str(e),
            "type": type(e).__name__,
        }


async def _download_full_product(
    product_id: str, filename: str, download_dir: Path, access_token: str
) -> Dict[str, Any]:
    """Download full satellite image product"""
    import os
    import sys
    import time

    import httpx

    # Try different download endpoints
    download_urls = [
        f"https://download.dataspace.copernicus.eu/odata/v1/Products({product_id})/$value",
        f"https://catalogue.dataspace.copernicus.eu/odata/v1/Products({product_id})/$value",
    ]

    output_path = download_dir / f"{filename}.zip"

    headers = {
        "Authorization": f"Bearer {access_token}",
        "Accept": "application/octet-stream",
    }

    # Increase timeout for large downloads - up to 2 hours for very large files
    timeout = httpx.Timeout(
        7200.0, connect=60.0, read=7200.0, write=60.0
    )  # 2 hours for download, 1 minute for connect

    for url in download_urls:
        try:
            async with httpx.AsyncClient(timeout=timeout) as client:
                async with client.stream("GET", url, headers=headers) as response:
                    if response.status_code == 200:
                        total_size = int(response.headers.get("content-length", 0))

                        # Log start of download
                        print(
                            f"Starting download of product {product_id}",
                            file=sys.stderr,
                        )
                        if total_size > 0:
                            print(
                                f"Total size: {total_size / (1024 * 1024 * 1024):.2f} GB ({total_size / (1024 * 1024):.1f} MB)",
                                file=sys.stderr,
                            )
                        print(f"Download URL: {url}", file=sys.stderr)
                        print(
                            f"Download started at {time.strftime('%Y-%m-%d %H:%M:%S')}",
                            file=sys.stderr,
                        )
                        print(
                            f"Progress will be reported every 5 seconds or 50MB",
                            file=sys.stderr,
                        )
                        sys.stderr.flush()

                        # Download the file with progress reporting
                        downloaded = 0
                        chunk_size = 1024 * 1024  # 1MB chunks for better performance
                        last_progress_time = time.time()
                        last_progress_size = 0

                        with open(output_path, "wb") as f:
                            async for chunk in response.aiter_bytes(
                                chunk_size=chunk_size
                            ):
                                if chunk:
                                    f.write(chunk)
                                    downloaded += len(chunk)

                                    # Report progress every 5 seconds or every 50MB
                                    current_time = time.time()
                                    if (current_time - last_progress_time >= 5) or (
                                        downloaded - last_progress_size
                                        >= 50 * 1024 * 1024
                                    ):
                                        if total_size > 0:
                                            percent = (downloaded / total_size) * 100
                                            print(
                                                f"Download progress: {downloaded / (1024 * 1024):.1f} MB / {total_size / (1024 * 1024):.1f} MB ({percent:.1f}%)",
                                                file=sys.stderr,
                                            )
                                        else:
                                            print(
                                                f"Download progress: {downloaded / (1024 * 1024):.1f} MB downloaded",
                                                file=sys.stderr,
                                            )
                                        sys.stderr.flush()
                                        last_progress_time = current_time
                                        last_progress_size = downloaded

                                    # Always flush after each chunk to ensure output
                                    sys.stderr.flush()

                        # Final progress report
                        print(
                            f"Download complete: {downloaded / (1024 * 1024):.1f} MB downloaded",
                            file=sys.stderr,
                        )
                        sys.stderr.flush()

                        # Verify download
                        if output_path.exists():
                            file_size = output_path.stat().st_size

                            # Verify file size matches expected if we have total_size
                            if (
                                total_size > 0 and abs(file_size - total_size) > 1024
                            ):  # Allow 1KB difference
                                print(
                                    f"Warning: Downloaded file size ({file_size} bytes) differs from expected ({total_size} bytes)",
                                    file=sys.stderr,
                                )
                                sys.stderr.flush()

                            return {
                                "success": True,
                                "download_type": "full",
                                "product_id": product_id,
                                "filename": output_path.name,
                                "filepath": str(output_path),
                                "file_size_bytes": file_size,
                                "file_size_mb": file_size / (1024 * 1024),
                                "file_size_gb": file_size / (1024 * 1024 * 1024),
                                "download_url": url,
                                "message": f"Successfully downloaded full product ({file_size / (1024 * 1024):.1f} MB)",
                            }

        except httpx.TimeoutException as e:
            print(f"Timeout during download from {url}: {e}", file=sys.stderr)
            sys.stderr.flush()
            continue
        except Exception as e:
            print(f"Error during download from {url}: {e}", file=sys.stderr)
            sys.stderr.flush()
            continue

    return {
        "error": "Download failed",
        "message": "Failed to download from all available endpoints",
        "product_id": product_id,
        "tried_urls": download_urls,
    }


async def _download_quicklook(
    product_id: str, filename: str, download_dir: Path, access_token: str
) -> Dict[str, Any]:
    """Download quicklook/preview image"""
    import sys

    import httpx

    # First get product details to find quicklook asset
    product_url = f"https://catalogue.dataspace.copernicus.eu/odata/v1/Products({product_id})?$expand=Assets"

    headers = {
        "Authorization": f"Bearer {access_token}",
        "Accept": "application/json",
    }

    timeout = httpx.Timeout(
        120.0, connect=30.0
    )  # 2 minutes for download, 30 seconds for connect

    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            print(f"Fetching product details for {product_id}", file=sys.stderr)
            sys.stderr.flush()

            response = await client.get(product_url, headers=headers)
            response.raise_for_status()

            product_data = response.json()
            assets = product_data.get("Assets", [])

            # Find quicklook assets
            quicklook_assets = [
                asset
                for asset in assets
                if asset.get("ContentType") == "image/jpeg"
                or "quicklook" in asset.get("Name", "").lower()
                or "preview" in asset.get("Name", "").lower()
            ]

            if not quicklook_assets:
                return {
                    "error": "Quicklook not available",
                    "message": "No quicklook/preview assets found for this product",
                    "product_id": product_id,
                }

            # Use first quicklook asset
            quicklook_id = quicklook_assets[0].get("Id")
            if not quicklook_id:
                return {
                    "error": "Quicklook ID not found",
                    "message": "Quicklook asset has no ID",
                    "product_id": product_id,
                }

            # Download quicklook
            quicklook_url = f"https://catalogue.dataspace.copernicus.eu/odata/v1/Assets({quicklook_id})/$value"
            output_path = download_dir / f"{filename}_quicklook.jpg"

            headers = {
                "Authorization": f"Bearer {access_token}",
                "Accept": "image/jpeg",
            }

            print(f"Downloading quicklook from {quicklook_url}", file=sys.stderr)
            sys.stderr.flush()

            async with client.stream(
                "GET", quicklook_url, headers=headers
            ) as stream_response:
                stream_response.raise_for_status()

                with open(output_path, "wb") as f:
                    async for chunk in stream_response.aiter_bytes(chunk_size=8192):
                        if chunk:
                            f.write(chunk)

            if output_path.exists():
                file_size = output_path.stat().st_size
                print(
                    f"Quicklook download complete: {file_size / 1024:.1f} KB",
                    file=sys.stderr,
                )
                sys.stderr.flush()

                return {
                    "success": True,
                    "download_type": "quicklook",
                    "product_id": product_id,
                    "quicklook_id": quicklook_id,
                    "filename": output_path.name,
                    "filepath": str(output_path),
                    "file_size_bytes": file_size,
                    "file_size_kb": file_size / 1024,
                    "download_url": quicklook_url,
                    "message": f"Successfully downloaded quicklook ({file_size / 1024:.1f} KB)",
                }
            else:
                return {
                    "error": "Quicklook download failed",
                    "message": "File was not created",
                    "product_id": product_id,
                }

    except Exception as e:
        print(f"Error downloading quicklook: {e}", file=sys.stderr)
        sys.stderr.flush()
        return {
            "error": "Quicklook download failed",
            "exception": str(e),
            "product_id": product_id,
        }


async def _download_compressed(
    product_id: str, filename: str, download_dir: Path, access_token: str
) -> Dict[str, Any]:
    """Download compressed version of satellite image"""
    import os
    import sys
    import time

    import httpx

    # For compressed downloads, we'll use a different endpoint
    # Note: This might not be available for all products
    compressed_url = f"https://catalogue.dataspace.copernicus.eu/odata/v1/Products({product_id})/Compressed/$value"

    output_path = download_dir / f"{filename}_compressed.zip"

    headers = {
        "Authorization": f"Bearer {access_token}",
        "Accept": "application/octet-stream",
    }

    # Increase timeout for compressed downloads
    timeout = httpx.Timeout(
        3600.0, connect=60.0, read=3600.0, write=60.0
    )  # 1 hour for download, 1 minute for connect

    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            async with client.stream(
                "GET", compressed_url, headers=headers
            ) as response:
                if response.status_code == 200:
                    total_size = int(response.headers.get("content-length", 0))

                    # Log start of download
                    print(
                        f"Starting compressed download of product {product_id}",
                        file=sys.stderr,
                    )
                    if total_size > 0:
                        print(
                            f"Total size: {total_size / (1024 * 1024):.1f} MB",
                            file=sys.stderr,
                        )
                    print(f"Download URL: {compressed_url}", file=sys.stderr)
                    sys.stderr.flush()

                    # Download the file with progress reporting
                    downloaded = 0
                    chunk_size = 1024 * 1024  # 1MB chunks for better performance
                    last_progress_time = time.time()
                    last_progress_size = 0

                    with open(output_path, "wb") as f:
                        async for chunk in response.aiter_bytes(chunk_size=chunk_size):
                            if chunk:
                                f.write(chunk)
                                downloaded += len(chunk)

                                # Report progress every 5 seconds or every 50MB
                                current_time = time.time()
                                if (current_time - last_progress_time >= 5) or (
                                    downloaded - last_progress_size >= 50 * 1024 * 1024
                                ):
                                    if total_size > 0:
                                        percent = (downloaded / total_size) * 100
                                        print(
                                            f"Compressed download progress: {downloaded / (1024 * 1024):.1f} MB / {total_size / (1024 * 1024):.1f} MB ({percent:.1f}%)",
                                            file=sys.stderr,
                                        )
                                    else:
                                        print(
                                            f"Compressed download progress: {downloaded / (1024 * 1024):.1f} MB downloaded",
                                            file=sys.stderr,
                                        )
                                    sys.stderr.flush()
                                    last_progress_time = current_time
                                    last_progress_size = downloaded

                                # Always flush after each chunk to ensure output
                                sys.stderr.flush()

                    # Final progress report
                    print(
                        f"Compressed download complete: {downloaded / (1024 * 1024):.1f} MB downloaded",
                        file=sys.stderr,
                    )
                    sys.stderr.flush()

                    if output_path.exists():
                        file_size = output_path.stat().st_size

                        # Verify file size matches expected if we have total_size
                        if total_size > 0 and abs(file_size - total_size) > 1024:
                            print(
                                f"Warning: Downloaded compressed file size ({file_size} bytes) differs from expected ({total_size} bytes)",
                                file=sys.stderr,
                            )
                            sys.stderr.flush()

                        return {
                            "success": True,
                            "download_type": "compressed",
                            "product_id": product_id,
                            "filename": output_path.name,
                            "filepath": str(output_path),
                            "file_size_bytes": file_size,
                            "file_size_mb": file_size / (1024 * 1024),
                            "download_url": compressed_url,
                            "message": f"Successfully downloaded compressed product ({file_size / (1024 * 1024):.1f} MB)",
                        }
                else:
                    print(
                        f"Compressed download failed: HTTP {response.status_code}: {response.reason_phrase}",
                        file=sys.stderr,
                    )
                    sys.stderr.flush()
                    return {
                        "error": "Compressed download failed",
                        "message": f"HTTP {response.status_code}: {response.reason_phrase}",
                        "product_id": product_id,
                        "url": compressed_url,
                    }

        # If we get here, the compressed download endpoint didn't work
        # Try the regular download endpoint as fallback
        print(
            f"Compressed endpoint failed, trying regular download as fallback",
            file=sys.stderr,
        )
        sys.stderr.flush()
        return await _download_full_product(
            product_id, filename, download_dir, access_token
        )

    except httpx.TimeoutException as e:
        print(f"Timeout during compressed download: {e}", file=sys.stderr)
        sys.stderr.flush()
        return {
            "error": "Compressed download timeout",
            "exception": str(e),
            "product_id": product_id,
            "message": "Download timed out. The file may be too large or the connection too slow.",
        }
    except Exception as e:
        print(f"Error during compressed download: {e}", file=sys.stderr)
        sys.stderr.flush()
        return {
            "error": "Compressed download failed",
            "exception": str(e),
            "product_id": product_id,
        }


@mcp.tool(
    name="batch_download_images",
    description="Download multiple Copernicus satellite images concurrently. Requires authentication. WARNING: Full product batch downloads can take HOURS. Use download_type='quicklook' for testing.",
)
async def batch_download_images(
    image_ids: List[str],
    mission: str = "sentinel-2",
    download_type: str = "full",
    output_dir: Optional[str] = None,
    max_concurrent: int = 3,
) -> Dict[str, Any]:
    """
    Download multiple Copernicus satellite images concurrently.

    Args:
        image_ids: List of image IDs to download
        mission: Mission name (e.g., 'sentinel-2', 'sentinel-1')
        output_dir: Optional output directory (default: 'downloads')
        max_concurrent: Maximum number of concurrent downloads

    Returns:
        Dictionary with batch download results

    WARNING:
    - Full product batch downloads can take HOURS to complete
    - MCP clients may timeout during long downloads
    - Use download_type='quicklook' for testing (small files, fast downloads)
    - Progress is reported to stderr every 5 seconds during each download
    """
    import asyncio
    import os
    import sys
    from pathlib import Path

    # Check for authentication
    username = os.environ.get("COPERNICUS_USERNAME")
    password = os.environ.get("COPERNICUS_PASSWORD")

    if not username or not password:
        return {
            "error": "Authentication required",
            "message": "Please set COPERNICUS_USERNAME and COPERNICUS_PASSWORD environment variables",
        }

    # Get access token once for all downloads
    token_response = await get_auth_token(username, password)
    if isinstance(token_response, dict) and "error" in token_response:
        return token_response

    access_token = token_response.get("access_token")
    if not access_token:
        return {
            "error": "Authentication failed",
            "message": "No access token received",
        }

    # Set up output directory
    import os
    from pathlib import Path

    if output_dir:
        download_dir = Path(output_dir)
    else:
        download_dir = Path("batch_downloads")

    download_dir.mkdir(exist_ok=True, parents=True)

    # Create semaphore for concurrent downloads
    semaphore = asyncio.Semaphore(max_concurrent)

    async def download_with_semaphore(image_id: str) -> Dict[str, Any]:
        async with semaphore:
            print(f"Starting download of image {image_id}", file=sys.stderr)
            sys.stderr.flush()

            try:
                if download_type == "full":
                    return await _download_full_product(
                        image_id, f"{mission}_{image_id}", download_dir, access_token
                    )
                elif download_type == "quicklook":
                    return await _download_quicklook(
                        image_id, f"{mission}_{image_id}", download_dir, access_token
                    )
                elif download_type == "compressed":
                    return await _download_compressed(
                        image_id, f"{mission}_{image_id}", download_dir, access_token
                    )
                else:
                    return {
                        "error": "Invalid download type",
                        "image_id": image_id,
                        "message": f"Unknown download type: {download_type}",
                    }
            except Exception as e:
                print(
                    f"Error in download_with_semaphore for {image_id}: {e}",
                    file=sys.stderr,
                )
                sys.stderr.flush()
                return {
                    "error": "Download failed",
                    "exception": str(e),
                    "image_id": image_id,
                }

    # Start all downloads
    print(
        f"Starting batch download of {len(image_ids)} images with max {max_concurrent} concurrent downloads",
        file=sys.stderr,
    )
    if download_type == "full":
        print(
            f"WARNING: Full product batch download. This can take HOURS to complete.",
            file=sys.stderr,
        )
        print(
            f"MCP clients may timeout. Use download_type='quicklook' for testing.",
            file=sys.stderr,
        )
    elif download_type == "compressed":
        print(
            f"Note: Compressed downloads may take several minutes per image.",
            file=sys.stderr,
        )
    else:
        print(
            f"Quicklook downloads are fast and suitable for testing.",
            file=sys.stderr,
        )
    print(
        f"Progress will be reported every 5 seconds during each download.",
        file=sys.stderr,
    )
    sys.stderr.flush()

    tasks = [download_with_semaphore(image_id) for image_id in image_ids]
    results = await asyncio.gather(*tasks, return_exceptions=True)

    # Process results
    successful = []
    failed = []
    total_size = 0

    for i, result in enumerate(results):
        image_id = image_ids[i]

        if isinstance(result, Exception):
            print(f"Download failed for {image_id}: {result}", file=sys.stderr)
            sys.stderr.flush()
            failed.append(
                {
                    "image_id": image_id,
                    "error": str(result),
                    "type": type(result).__name__,
                }
            )
        elif isinstance(result, dict) and result.get("success"):
            print(
                f"Download successful for {image_id}: {result.get('message', '')}",
                file=sys.stderr,
            )
            sys.stderr.flush()
            successful.append(result)
            total_size += result.get("file_size_bytes", 0)
        else:
            print(f"Download failed for {image_id}: {result}", file=sys.stderr)
            sys.stderr.flush()
            failed.append({"image_id": image_id, "result": result})

    # Final batch summary
    print(
        f"Batch download complete: {len(successful)} successful, {len(failed)} failed",
        file=sys.stderr,
    )
    print(
        f"Total downloaded size: {total_size / (1024 * 1024 * 1024):.2f} GB ({total_size / (1024 * 1024):.1f} MB)",
        file=sys.stderr,
    )
    sys.stderr.flush()

    return {
        "batch_summary": {
            "total_images": len(image_ids),
            "successful": len(successful),
            "failed": len(failed),
            "total_size_bytes": total_size,
            "total_size_mb": total_size / (1024 * 1024),
            "total_size_gb": total_size / (1024 * 1024 * 1024),
            "download_type": download_type,
            "mission": mission,
            "output_dir": str(download_dir),
        },
        "successful_downloads": successful,
        "failed_downloads": failed,
    }


@mcp.tool(
    name="check_download_availability",
    description="Check if Copernicus satellite images are available for download",
)
async def check_download_availability(
    image_ids: List[str],
) -> Dict[str, Any]:
    """
    Check download availability for multiple Copernicus satellite images.

    Args:
        image_ids: List of image IDs to check

    Returns:
        Dictionary with availability status for each image
    """
    import httpx

    # Check for authentication
    username = os.environ.get("COPERNICUS_USERNAME")
    password = os.environ.get("COPERNICUS_PASSWORD")

    if not username or not password:
        return {
            "error": "Authentication required",
            "message": "Please set COPERNICUS_USERNAME and COPERNICUS_PASSWORD environment variables",
        }

    # Get access token
    token_response = await get_auth_token(username, password)
    if isinstance(token_response, dict) and "error" in token_response:
        return token_response

    access_token = token_response.get("access_token")
    if not access_token:
        return {
            "error": "Authentication failed",
            "message": "No access token received",
        }

    headers = {
        "Authorization": f"Bearer {access_token}",
        "Accept": "application/json",
    }

    availability_results = []

    for image_id in image_ids:
        try:
            # Check product details
            product_url = f"https://catalogue.dataspace.copernicus.eu/odata/v1/Products({image_id})?$expand=Assets"
            async with httpx.AsyncClient(timeout=60.0) as client:
                response = await client.get(product_url, headers=headers)

            if response.status_code == 200:
                product_data = response.json()

                # Check for quicklook availability
                assets = product_data.get("Assets", [])
                quicklook_available = any(
                    asset.get("ContentType") == "image/jpeg"
                    or "quicklook" in asset.get("Name", "").lower()
                    or "preview" in asset.get("Name", "").lower()
                    for asset in assets
                )

                # Check product size
                size_bytes = product_data.get("ContentLength", 0)

                availability_results.append(
                    {
                        "image_id": image_id,
                        "available": True,
                        "status_code": 200,
                        "quicklook_available": quicklook_available,
                        "size_bytes": size_bytes,
                        "size_mb": size_bytes / (1024 * 1024),
                        "name": product_data.get("Name", "Unknown"),
                        "content_date": product_data.get("ContentDate", {}),
                    }
                )
            else:
                availability_results.append(
                    {
                        "image_id": image_id,
                        "available": False,
                        "status_code": response.status_code,
                        "error": response.text[:200]
                        if response.text
                        else "Unknown error",
                    }
                )

        except Exception as e:
            availability_results.append(
                {
                    "image_id": image_id,
                    "available": False,
                    "error": str(e),
                    "type": type(e).__name__,
                }
            )

    # Summary
    available_count = sum(1 for r in availability_results if r.get("available"))
    total_size = sum(
        r.get("size_bytes", 0) for r in availability_results if r.get("available")
    )

    return {
        "summary": {
            "total_checked": len(image_ids),
            "available": available_count,
            "unavailable": len(image_ids) - available_count,
            "total_available_size_mb": total_size / (1024 * 1024),
        },
        "availability_details": availability_results,
    }


@mcp.tool(
    name="get_product_download_links",
    description="Get all available download links for a Copernicus satellite image",
)
async def get_product_download_links(
    image_id: str,
) -> Dict[str, Any]:
    """
    Get all available download links for a Copernicus satellite image.

    Args:
        image_id: The ID of the image

    Returns:
        Dictionary with all available download links and metadata
    """
    import httpx

    # Check for authentication
    username = os.environ.get("COPERNICUS_USERNAME")
    password = os.environ.get("COPERNICUS_PASSWORD")

    if not username or not password:
        return {
            "error": "Authentication required",
            "message": "Please set COPERNICUS_USERNAME and COPERNICUS_PASSWORD environment variables",
        }

    # Get access token
    token_response = await get_auth_token(username, password)
    if isinstance(token_response, dict) and "error" in token_response:
        return token_response

    access_token = token_response.get("access_token")
    if not access_token:
        return {
            "error": "Authentication failed",
            "message": "No access token received",
        }

    headers = {
        "Authorization": f"Bearer {access_token}",
        "Accept": "application/json",
    }

    try:
        # Get product details with assets
        product_url = f"https://catalogue.dataspace.copernicus.eu/odata/v1/Products({image_id})?$expand=Assets"
        async with httpx.AsyncClient(timeout=60.0) as client:
            response = await client.get(product_url, headers=headers)
            response.raise_for_status()

            product_data = response.json()

            # Extract download links
            download_links = {
                "full_product": [
                    f"https://download.dataspace.copernicus.eu/odata/v1/Products({image_id})/$value",
                    f"https://catalogue.dataspace.copernicus.eu/odata/v1/Products({image_id})/$value",
                ],
                "quicklook": [],
                "compressed": [
                    f"https://catalogue.dataspace.copernicus.eu/odata/v1/Products({image_id})/Compressed/$value",
                ],
            }

        # Find quicklook assets
        assets = product_data.get("Assets", [])
        for asset in assets:
            if (
                asset.get("ContentType") == "image/jpeg"
                or "quicklook" in asset.get("Name", "").lower()
                or "preview" in asset.get("Name", "").lower()
            ):
                quicklook_id = asset.get("Id")
                if quicklook_id:
                    download_links["quicklooks"].append(
                        {
                            "id": quicklook_id,
                            "name": asset.get("Name", "Unknown"),
                            "content_type": asset.get("ContentType", "Unknown"),
                            "url": f"https://catalogue.dataspace.copernicus.eu/odata/v1/Assets({quicklook_id})/$value",
                        }
                    )

        return {
            "success": True,
            "image_id": image_id,
            "product_name": product_data.get("Name", "Unknown"),
            "content_date": product_data.get("ContentDate", {}),
            "size_bytes": product_data.get("ContentLength", 0),
            "size_mb": product_data.get("ContentLength", 0) / (1024 * 1024),
            "download_links": download_links,
            "metadata": {
                "platform": product_data.get("Platform", "Unknown"),
                "instrument": product_data.get("Instrument", "Unknown"),
                "processing_level": product_data.get("ProcessingLevel", "Unknown"),
                "cloud_cover": product_data.get("CloudCover", "Unknown"),
                "footprint": product_data.get("Footprint", "Unknown"),
            },
        }

    except Exception as e:
        return {
            "error": "Failed to get download links",
            "image_id": image_id,
            "exception": str(e),
            "type": type(e).__name__,
        }


@mcp.tool(
    name="list_downloaded_files",
    description="List downloaded Copernicus satellite image files",
)
async def list_downloaded_files(
    download_dir: Optional[str] = None,
    file_type: Optional[str] = None,
    limit: int = 50,
) -> Dict[str, Any]:
    """
    List downloaded Copernicus satellite image files.

    Args:
        download_dir: Directory to scan (default: 'downloads')
        file_type: Filter by file type - 'full', 'quicklook', 'compressed', or None for all
        limit: Maximum number of files to return

    Returns:
        Dictionary with file listing and statistics
    """
    import os
    import time
    from pathlib import Path

    if download_dir:
        base_dir = Path(download_dir)
    else:
        base_dir = Path("downloads")

    if not base_dir.exists():
        return {
            "error": "Directory not found",
            "directory": str(base_dir),
            "message": "No downloads directory found. Run download_image first.",
        }

    files = []
    total_size = 0

    # Scan directory
    for file_path in base_dir.rglob("*"):
        if file_path.is_file():
            # Check file type
            filename = file_path.name.lower()
            if file_type == "full" and not filename.endswith(".zip"):
                continue
            elif file_type == "quicklook" and not (
                "quicklook" in filename or filename.endswith(".jpg")
            ):
                continue
            elif file_type == "compressed" and not (
                "compressed" in filename or filename.endswith(".zip")
            ):
                continue

            stat = file_path.stat()
            files.append(
                {
                    "filename": file_path.name,
                    "filepath": str(file_path),
                    "size_bytes": stat.st_size,
                    "size_mb": stat.st_size / (1024 * 1024),
                    "modified_time": time.ctime(stat.st_mtime),
                    "modified_timestamp": stat.st_mtime,
                    "file_type": "quicklook"
                    if "quicklook" in filename
                    else "compressed"
                    if "compressed" in filename
                    else "full"
                    if filename.endswith(".zip")
                    else "other",
                }
            )
            total_size += stat.st_size

    # Sort by modification time (newest first)
    files.sort(key=lambda x: x["modified_timestamp"], reverse=True)

    # Apply limit
    if limit > 0:
        files = files[:limit]

    return {
        "directory": str(base_dir),
        "total_files": len(files),
        "total_size_bytes": total_size,
        "total_size_gb": total_size / (1024 * 1024 * 1024),
        "file_type_filter": file_type,
        "files": files,
    }


@mcp.tool(
    name="cleanup_downloads",
    description="Clean up downloaded files based on criteria",
)
async def cleanup_downloads(
    download_dir: Optional[str] = None,
    older_than_days: Optional[int] = None,
    max_size_mb: Optional[float] = None,
    file_type: Optional[str] = None,
    dry_run: bool = True,
) -> Dict[str, Any]:
    """
    Clean up downloaded files based on criteria.

    Args:
        download_dir: Directory to clean (default: 'downloads')
        older_than_days: Remove files older than X days
        max_size_mb: Keep total size under X MB (remove oldest first)
        file_type: Filter by file type - 'full', 'quicklook', 'compressed'
        dry_run: If True, only show what would be deleted

    Returns:
        Dictionary with cleanup results
    """
    import os
    import time
    from pathlib import Path

    if download_dir:
        base_dir = Path(download_dir)
    else:
        base_dir = Path("downloads")

    if not base_dir.exists():
        return {
            "error": "Directory not found",
            "directory": str(base_dir),
        }

    current_time = time.time()
    files_to_delete = []
    total_size_to_free = 0

    # Scan all files
    all_files = []
    for file_path in base_dir.rglob("*"):
        if file_path.is_file():
            stat = file_path.stat()
            filename = file_path.name.lower()

            # Check file type filter
            file_type_match = True
            if file_type:
                if file_type == "full" and not filename.endswith(".zip"):
                    file_type_match = False
                elif file_type == "quicklook" and not (
                    "quicklook" in filename or filename.endswith(".jpg")
                ):
                    file_type_match = False
                elif file_type == "compressed" and not (
                    "compressed" in filename or filename.endswith(".zip")
                ):
                    file_type_match = False

            if file_type_match:
                all_files.append(
                    {
                        "path": file_path,
                        "stat": stat,
                        "filename": file_path.name,
                        "size_bytes": stat.st_size,
                        "age_days": (current_time - stat.st_mtime) / (24 * 3600),
                    }
                )

    # Apply older_than_days filter
    if older_than_days is not None:
        for file_info in all_files:
            if file_info["age_days"] > older_than_days:
                files_to_delete.append(file_info)
                total_size_to_free += file_info["size_bytes"]

    # Apply max_size_mb filter (remove oldest first)
    elif max_size_mb is not None:
        # Sort by age (oldest first)
        all_files.sort(key=lambda x: x["age_days"], reverse=True)

        total_size_mb = sum(f["size_bytes"] for f in all_files) / (1024 * 1024)
        target_size_mb = max_size_mb

        if total_size_mb > target_size_mb:
            current_size_mb = total_size_mb
            for file_info in all_files:
                if current_size_mb <= target_size_mb:
                    break
                files_to_delete.append(file_info)
                total_size_to_free += file_info["size_bytes"]
                current_size_mb -= file_info["size_bytes"] / (1024 * 1024)

    # Perform deletion (or dry run)
    deleted_files = []
    deletion_errors = []

    for file_info in files_to_delete:
        try:
            if not dry_run:
                file_info["path"].unlink()
                deleted_files.append(
                    {
                        "filename": file_info["filename"],
                        "size_bytes": file_info["size_bytes"],
                        "age_days": file_info["age_days"],
                    }
                )
            else:
                deleted_files.append(
                    {
                        "filename": file_info["filename"],
                        "size_bytes": file_info["size_bytes"],
                        "age_days": file_info["age_days"],
                        "would_delete": True,
                    }
                )
        except Exception as e:
            deletion_errors.append(
                {
                    "filename": file_info["filename"],
                    "error": str(e),
                }
            )

    return {
        "directory": str(base_dir),
        "dry_run": dry_run,
        "criteria": {
            "older_than_days": older_than_days,
            "max_size_mb": max_size_mb,
            "file_type": file_type,
        },
        "summary": {
            "total_files_scanned": len(all_files),
            "files_to_delete": len(files_to_delete),
            "files_deleted": len(deleted_files) if not dry_run else 0,
            "size_to_free_bytes": total_size_to_free,
            "size_to_free_mb": total_size_to_free / (1024 * 1024),
            "deletion_errors": len(deletion_errors),
        },
        "deleted_files": deleted_files,
        "deletion_errors": deletion_errors,
    }


@mcp.tool(
    name="get_download_statistics",
    description="Get statistics about downloaded Copernicus satellite images",
)
async def get_download_statistics(
    download_dir: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Get statistics about downloaded Copernicus satellite images.

    Args:
        download_dir: Directory to analyze (default: 'downloads')

    Returns:
        Dictionary with download statistics
    """
    import os
    import time
    from collections import defaultdict
    from pathlib import Path

    if download_dir:
        base_dir = Path(download_dir)
    else:
        base_dir = Path("downloads")

    if not base_dir.exists():
        return {
            "error": "Directory not found",
            "directory": str(base_dir),
        }

    statistics = {
        "total_files": 0,
        "total_size_bytes": 0,
        "by_file_type": defaultdict(lambda: {"count": 0, "size_bytes": 0}),
        "by_mission": defaultdict(lambda: {"count": 0, "size_bytes": 0}),
        "by_month": defaultdict(lambda: {"count": 0, "size_bytes": 0}),
        "oldest_file": None,
        "newest_file": None,
    }

    # Scan directory
    for file_path in base_dir.rglob("*"):
        if file_path.is_file():
            stat = file_path.stat()
            filename = file_path.name

            # Determine file type
            if "quicklook" in filename.lower():
                file_type = "quicklook"
            elif "compressed" in filename.lower():
                file_type = "compressed"
            elif filename.endswith(".zip"):
                file_type = "full"
            else:
                file_type = "other"

            # Try to extract mission from filename
            mission = "unknown"
            for m in [
                "sentinel_1",
                "sentinel_2",
                "sentinel_3",
                "sentinel_5p",
                "sentinel_6",
            ]:
                if m in filename.lower():
                    mission = m.replace("_", "-")
                    break

            # Get month
            month_key = time.strftime("%Y-%m", time.localtime(stat.st_mtime))

            # Update statistics
            statistics["total_files"] += 1
            statistics["total_size_bytes"] += stat.st_size

            statistics["by_file_type"][file_type]["count"] += 1
            statistics["by_file_type"][file_type]["size_bytes"] += stat.st_size

            statistics["by_mission"][mission]["count"] += 1
            statistics["by_mission"][mission]["size_bytes"] += stat.st_size

            statistics["by_month"][month_key]["count"] += 1
            statistics["by_month"][month_key]["size_bytes"] += stat.st_size

            # Track oldest/newest
            file_info = {
                "filename": filename,
                "size_bytes": stat.st_size,
                "modified_time": time.ctime(stat.st_mtime),
                "modified_timestamp": stat.st_mtime,
            }

            if (
                statistics["oldest_file"] is None
                or stat.st_mtime < statistics["oldest_file"]["modified_timestamp"]
            ):
                statistics["oldest_file"] = file_info

            if (
                statistics["newest_file"] is None
                or stat.st_mtime > statistics["newest_file"]["modified_timestamp"]
            ):
                statistics["newest_file"] = file_info

    # Convert defaultdict to regular dict for JSON serialization
    statistics["by_file_type"] = dict(statistics["by_file_type"])
    statistics["by_mission"] = dict(statistics["by_mission"])
    statistics["by_month"] = dict(statistics["by_month"])

    # Add calculated fields
    statistics["total_size_gb"] = statistics["total_size_bytes"] / (1024 * 1024 * 1024)
    statistics["average_file_size_mb"] = (
        statistics["total_size_bytes"] / max(statistics["total_files"], 1)
    ) / (1024 * 1024)

    return {
        "directory": str(base_dir),
        "statistics": statistics,
    }


@mcp.tool(
    name="search_and_download",
    description="Search for Copernicus satellite images and download the best match. WARNING: Full product downloads can take HOURS. Use download_type='quicklook' for testing.",
)
async def search_and_download(
    geometry: Any,
    geometry_type: str = "point",
    mission: str = "sentinel-2",
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    max_cloud_cover: Optional[float] = None,
    download_type: str = "quicklook",
    output_dir: Optional[str] = None,
    limit: int = 5,
) -> Dict[str, Any]:
    """
    Search for Copernicus satellite images and download the best match.

    Args:
        geometry: Geometry as polygon coordinates [[lon, lat], ...] or GeoJSON polygon [[[lon, lat], ...]] or point [lon, lat] or bbox [min_lon, min_lat, max_lon, max_lat]
        geometry_type: Type of geometry - 'point', 'bbox', or 'polygon'
        mission: Mission name (e.g., 'sentinel-2', 'sentinel-1')
        start_date: Start date (YYYY-MM-DD)
        end_date: End date (YYYY-MM-DD)
        max_cloud_cover: Maximum cloud cover percentage (0-100)
        download_type: Type of download - 'full', 'quicklook', or 'compressed'
        output_dir: Optional output directory
        limit: Maximum number of search results to consider

    Returns:
        Dictionary with search results and download status
    """
    import sys
    import time
    from datetime import datetime

    # Step 1: Create SearchParameters object
    # Create MissionParameters
    mission_params = MissionParameters(
        mission=mission, processing_level=None, product_type=None, satellite=None
    )

    # Create DateRange if dates are provided
    date_range = None
    if start_date or end_date:
        try:
            start_dt = datetime.fromisoformat(start_date) if start_date else None
            end_dt = datetime.fromisoformat(end_date) if end_date else None
            date_range = DateRange(start=start_dt, end=end_dt)
        except ValueError:
            # If date parsing fails, continue without date filter
            pass

    # Create CloudCoverFilter if max_cloud_cover is provided
    cloud_cover_filter = None
    if max_cloud_cover is not None:
        cloud_cover_filter = CloudCoverFilter(max=max_cloud_cover)

    # Create SearchParameters
    search_params = SearchParameters(
        geometry=geometry,
        geometry_type=GeometryType(geometry_type),
        mission_params=mission_params,
        date_range=date_range,
        cloud_cover=cloud_cover_filter,
        max_results=limit,
    )

    try:
        print(f"Searching for {mission} images...", file=sys.stderr)
        sys.stderr.flush()

        # Get the actual function from the module
        search_results = await search_copernicus_images(search_params)

        print(f"Found {len(search_results.images)} images", file=sys.stderr)
        sys.stderr.flush()
    except Exception as e:
        print(f"Search failed: {e}", file=sys.stderr)
        sys.stderr.flush()
        return {
            "error": "Search failed",
            "search_error": str(e),
            "message": "Failed to search for images",
        }

    products = search_results.images
    if not products:
        return {
            "error": "No images found",
            "search_params": search_params,
            "message": "No satellite images found matching the search criteria",
        }

    # Step 2: Select the best image (lowest cloud cover, most recent)
    print(f"Selecting best image from {len(products)} results...", file=sys.stderr)
    sys.stderr.flush()

    best_product = None
    best_score = float("-inf")

    for product in products:
        # Calculate score
        score = 0

        # Prefer recent images
        acquisition_date = product.acquisition_date
        if acquisition_date:
            try:
                # Give higher score to more recent images
                days_ago = (datetime.now() - acquisition_date).days
                score += max(0, 30 - days_ago)  # Higher score for images within 30 days
            except:
                pass

        # Prefer low cloud cover
        cloud_cover = product.cloud_cover_percentage
        if cloud_cover is not None:
            score += (100 - cloud_cover) * 0.5  # Higher score for lower cloud cover

        # Prefer higher processing level
        processing_level = product.processing_level
        if "L2A" in processing_level:
            score += 20
        elif "L1C" in processing_level:
            score += 10

        if score > best_score:
            best_score = score
            best_product = product

    if not best_product:
        return {
            "error": "No suitable image found",
            "search_results": len(products),
            "message": "Could not select a suitable image from search results",
        }

    # Step 3: Download the selected image
    image_id = best_product.id
    if not image_id:
        return {
            "error": "No image ID found",
            "best_product": best_product,
            "message": "Selected product has no ID",
        }

    print(f"Downloading selected image: {image_id}", file=sys.stderr)
    print(f"Download type: {download_type}", file=sys.stderr)
    sys.stderr.flush()

    download_result = await _download_image_helper(
        image_id=image_id,
        mission=mission,
        download_type=download_type,
        output_dir=output_dir,
    )

    print(f"Download completed for image: {image_id}", file=sys.stderr)
    sys.stderr.flush()

    return {
        "search_summary": {
            "total_results": len(products),
            "search_params": search_params.model_dump(),
            "selected_image_id": image_id,
            "selection_score": best_score,
        },
        "selected_image": {
            "id": image_id,
            "title": best_product.title,
            "acquisition_date": best_product.acquisition_date,
            "cloud_cover_percentage": best_product.cloud_cover_percentage,
            "processing_level": best_product.processing_level,
            "platform": best_product.platform,
            "mission": best_product.mission,
        },
        "download_result": download_result,
    }


def main():
    """Main entry point for running the MCP server"""
    import argparse
    import sys

    # Parse command line arguments
    parser = argparse.ArgumentParser(
        description="Copernicus MCP Server - Access Earth Observation data from Copernicus Sentinel missions",
        add_help=False,
    )
    parser.add_argument(
        "-h", "--help", action="store_true", help="Show this help message and exit"
    )
    parser.add_argument(
        "-v", "--version", action="store_true", help="Show version information and exit"
    )

    # Try to parse known arguments only
    args, unknown = parser.parse_known_args()

    # Handle --help
    if args.help:
        parser.print_help()
        sys.exit(0)

    # Handle --version
    if args.version:
        print(f"Copernicus MCP Server v{__version__}")
        print("Access Earth Observation data from Copernicus Sentinel missions")
        sys.exit(0)

    # If there are unknown arguments, print warning to stderr
    if unknown:
        print(f"Warning: Ignoring unknown arguments: {unknown}", file=sys.stderr)

    # Minimal startup message for MCP protocol compatibility
    print(f"Starting Copernicus MCP Server v{__version__}", file=sys.stderr)

    # Run the MCP server
    mcp.run()


if __name__ == "__main__":
    main()

# Copernicus Earth Observation MCP Server

A comprehensive Model Context Protocol (MCP) server for accessing Copernicus Earth Observation data from the Copernicus Data Space ecosystem. This server provides a complete suite of tools for searching, downloading, and managing satellite imagery from all Copernicus Sentinel missions.

## 📋 Table of Contents
- [Features](#-features)
- [Available Missions](#-available-missions)
- [Quick Start](#-quick-start)
- [Running the Server](#-running-the-server)
- [Available Tools](#-available-tools)
- [Complete Workflow Example](#-complete-workflow-example)
- [Configuration](#-configuration)
- [Testing](#-testing)
- [Architecture](#-architecture)
- [Authentication Model](#-authentication-model)
- [Error Handling](#-error-handling)
- [Performance Considerations](#-performance-considerations)
- [Security Notes](#-security-notes)
- [Troubleshooting](#-troubleshooting)
- [Contributing](#-contributing)
- [License](#-license)
- [Acknowledgments](#-acknowledgments)

## 🌟 Features

### **Search & Discovery**
- **Multi-Mission Support**: Access data from Sentinel-1, Sentinel-2, Sentinel-3, Sentinel-5P, and Sentinel-6 missions
- **Advanced Search**: Search by location (point, polygon, bounding box), date range, cloud cover, and mission-specific parameters
- **Coverage Analysis**: Analyze temporal coverage and availability of satellite data for specific regions
- **Recent Images**: Get the most recent satellite images for monitoring and change detection
- **Comprehensive Metadata**: Retrieve detailed image metadata including acquisition details, processing levels, and technical specifications

### **Download & Data Management**
- **Image Download**: Download full products, quicklook previews, and compressed versions of satellite images
- **Batch Operations**: Download multiple images concurrently with configurable concurrency limits
- **Intelligent Selection**: Automatic best-image selection based on recency, cloud cover, and processing level
- **Availability Checking**: Verify download availability and get file size information before downloading
- **Download Links**: Get all available download URLs for any satellite image

### **File Management**
- **File Listing**: List and analyze downloaded files with filtering by type, size, and date
- **Statistics**: Get comprehensive statistics about downloaded files (by mission, file type, time period)
- **Automated Cleanup**: Clean up old or large downloads with age-based and size-based strategies
- **Dry Run Mode**: Safety-first approach with preview of cleanup actions before execution

## 🛰️ Available Missions

| Mission | Type | Primary Applications | Resolution | Revisit Time |
|---------|------|---------------------|------------|--------------|
| **Sentinel-1** | Synthetic Aperture Radar (SAR) | Disaster monitoring, sea ice tracking, land subsidence | 5-40m | 6-12 days |
| **Sentinel-2** | Multispectral Imaging | Agriculture, vegetation monitoring, urban planning | 10-60m | 5 days |
| **Sentinel-3** | Ocean & Land Monitoring | Ocean color, sea surface temperature, fire detection | 300-1200m | <2 days |
| **Sentinel-5P** | Atmospheric Monitoring | Air quality, ozone layer, greenhouse gas tracking | 7.5×3.5km | Daily |
| **Sentinel-6** | Ocean Topography | Sea level rise, ocean circulation, climate research | 300m | 10 days |

## 🚀 Quick Start

### Prerequisites
- Python 3.11 or higher
- pip package manager
- Copernicus Data Space account (free registration required)

### Installation

1. **Clone the repository:**
   ```bash
   git clone <repository-url>
   cd copernicus-mcp
   ```

2. **Install dependencies:**
   ```bash
   pip install -r requirements.txt
   ```

3. **Install in development mode:**
   ```bash
   pip install -e .
   ```

4. **Set up authentication:**
   ```bash
   # Linux/Mac
   export COPERNICUS_USERNAME="your-email@example.com"
   export COPERNICUS_PASSWORD="your-password"
   
   # Windows (Command Prompt)
   set COPERNICUS_USERNAME=your-email@example.com
   set COPERNICUS_PASSWORD=your-password
   
   # Windows (PowerShell)
   $env:COPERNICUS_USERNAME="your-email@example.com"
   $env:COPERNICUS_PASSWORD="your-password"
   ```

   **Register for free at:** https://dataspace.copernicus.eu/

### Authentication Test
Verify your credentials work:
```bash
python -c "
import asyncio
import os
from copernicus_mcp.server import get_auth_token

async def test():
    result = await get_auth_token()
    if isinstance(result, dict) and 'access_token' in result:
        print('✅ Authentication successful!')
        print(f'Token length: {len(result[\"access_token\"])} characters')
    else:
        print(f'❌ Authentication failed: {result.get(\"error\", \"Unknown error\")}')

asyncio.run(test())
"
```

## 📡 Running the Server

### Basic Usage
```bash
# Run the MCP server
python -m copernicus_mcp

# Or using the module directly
python -m copernicus_mcp.server
```

### Command Line Options
```bash
# Show version
python -m copernicus_mcp --version

# Show help
python -m copernicus_mcp --help
```

### MCP Client Integration
Add to your MCP client configuration (e.g., Claude Desktop, Zed):

```json
{
  "mcpServers": {
    "copernicus-eo": {
      "command": "copernicus-mcp",
      "args": [],
      "env": {
        "COPERNICUS_DEBUG_AUTH": "true"
      },
      "description": "Access Copernicus Earth Observation satellite data"
    }
  }
}
```

## 🛠️ Available Tools

### **Search & Discovery Tools**

#### 1. `search_copernicus_images`
Search for satellite images from Copernicus missions.

**Parameters:**
- `geometry`: GeoJSON polygon coordinates, point [lon, lat], or bbox [min_lon, min_lat, max_lon, max_lat]
- `geometry_type`: 'point', 'polygon', or 'bbox'
- `mission`: Mission name ('sentinel-1', 'sentinel-2', 'sentinel-3', 'sentinel-5p', 'sentinel-6')
- `start_date`, `end_date`: Date range (YYYY-MM-DD)
- `max_cloud_cover`: Maximum cloud cover percentage (0-100, optical missions only)
- `max_results`: Maximum number of results (1-1000)

**Example:**
```python
# Search for Sentinel-2 images over Paris
search_copernicus_images(
    geometry=[[2.2945, 48.8584], [2.2945, 48.8604], [2.2965, 48.8604], [2.2965, 48.8584]],
    geometry_type="polygon",
    mission="sentinel-2",
    start_date="2024-01-01",
    end_date="2024-01-31",
    max_cloud_cover=20,
    max_results=10
)
```

#### 2. `get_image_details`
Get comprehensive metadata for a specific satellite image.

**Parameters:**
- `image_id`: Satellite image ID (from search results)
- `mission`: Optional mission name

**Returns:** Detailed metadata including download URLs, processing level, cloud cover, footprint, and authentication guidance.

#### 3. `get_mission_info`
Get detailed information about Copernicus satellite missions.

**Parameters:**
- `mission`: Optional specific mission name

**Returns:** Mission capabilities, sensors, applications, resolution, and revisit time.

#### 4. `get_recent_images`
Get the most recent satellite images for a region.

**Parameters:**
- `geometry`: Location coordinates
- `geometry_type`: 'point', 'polygon', or 'bbox'
- `mission`: Mission name
- `days_back`: Number of days to look back (default: 7)
- `max_results`: Maximum results (default: 10)

#### 5. `check_coverage`
Analyze satellite image coverage for a region over time.

**Parameters:**
- `geometry`: Location coordinates
- `geometry_type`: 'point', 'polygon', or 'bbox'
- `mission`: Mission name
- `start_date`, `end_date`: Analysis period
- `group_by`: Group results by 'day', 'week', 'month', or 'year'

### **Download Tools**

#### 6. `download_image`
Download a Copernicus satellite image by ID.

**Parameters:**
- `image_id`: Image ID from search results (required)
- `mission`: Mission name (default: 'sentinel-2')
- `download_type`: 'full', 'quicklook', or 'compressed' (default: 'full')
- `output_dir`: Custom output directory (default: 'downloads')

**Example:**
```python
# Download a quicklook preview
download_image(
    image_id="S2B_MSIL2A_20240115T105629_N0510_R094_T31UCS_20240115T130259",
    mission="sentinel-2",
    download_type="quicklook"
)

# Download full product
download_image(
    image_id="S2B_MSIL2A_20240115T105629_N0510_R094_T31UCS_20240115T130259",
    mission="sentinel-2",
    download_type="full"
)
```

#### 7. `batch_download_images`
Download multiple images concurrently.

**Parameters:**
- `image_ids`: List of image IDs to download
- `mission`: Mission name (default: 'sentinel-2')
- `download_type`: 'full', 'quicklook', or 'compressed' (default: 'full')
- `output_dir`: Output directory (default: 'batch_downloads')
- `max_concurrent`: Maximum concurrent downloads (default: 3)

**Example:**
```python
batch_download_images(
    image_ids=["id1", "id2", "id3"],
    mission="sentinel-2",
    download_type="quicklook",
    max_concurrent=2
)
```

#### 8. `search_and_download`
Search for images and automatically download the best match.

**Parameters:**
- `geometry`: Location coordinates
- `geometry_type`: 'point', 'polygon', or 'bbox' (default: 'point')
- `mission`: Mission name (default: 'sentinel-2')
- `start_date`, `end_date`: Search date range
- `max_cloud_cover`: Maximum cloud cover percentage
- `download_type`: 'full', 'quicklook', or 'compressed' (default: 'quicklook')
- `output_dir`: Output directory
- `limit`: Maximum search results to consider (default: 5)

**Example:**
```python
# Search and download best image
search_and_download(
    geometry=[-122.4194, 37.7749],  # San Francisco
    geometry_type="point",
    mission="sentinel-2",
    start_date="2024-01-01",
    end_date="2024-01-31",
    download_type="quicklook"
)
```

#### 9. `check_download_availability`
Check if images are available for download.

**Parameters:**
- `image_ids`: List of image IDs to check

**Returns:** Availability status, file sizes, and quicklook availability for each image.

#### 10. `get_product_download_links`
Get all available download links for an image.

**Parameters:**
- `image_id`: Image ID

**Returns:** All download URLs (full, compressed, quicklooks) with metadata.

### **File Management Tools**

#### 11. `list_downloaded_files`
List downloaded satellite image files.

**Parameters:**
- `download_dir`: Directory to scan (default: 'downloads')
- `file_type`: Filter by 'full', 'quicklook', 'compressed', or None for all
- `limit`: Maximum files to return (default: 50)

**Example:**
```python
list_downloaded_files(
    download_dir="my_downloads",
    file_type="quicklook",
    limit=10
)
```

#### 12. `cleanup_downloads`
Clean up downloaded files based on criteria.

**Parameters:**
- `download_dir`: Directory to clean (default: 'downloads')
- `older_than_days`: Remove files older than X days
- `max_size_mb`: Keep total size under X MB (removes oldest first)
- `file_type`: Filter by file type
- `dry_run`: Only show what would be deleted (default: True)

**Example:**
```python
# Dry run - see what would be deleted
cleanup_downloads(
    download_dir="downloads",
    older_than_days=30,
    dry_run=True
)

# Actually delete files older than 30 days
cleanup_downloads(
    download_dir="downloads",
    older_than_days=30,
    dry_run=False
)

# Keep total size under 10GB
cleanup_downloads(
    download_dir="downloads",
    max_size_mb=10240,
    dry_run=False
)
```

#### 13. `get_download_statistics`
Get statistics about downloaded files.

**Parameters:**
- `download_dir`: Directory to analyze (default: 'downloads')

**Returns:** Comprehensive statistics including total files, size, breakdown by mission/file type/month, and oldest/newest files.

## 📊 Complete Workflow Example

```python
# 1. Search for images
search_results = search_copernicus_images(
    geometry=[-122.4194, 37.7749],  # San Francisco
    geometry_type="point",
    mission="sentinel-2",
    start_date="2024-01-01",
    end_date="2024-01-31",
    max_cloud_cover=30,
    max_results=5
)

# 2. Extract image IDs
image_ids = [img["Id"] for img in search_results.get("products", [])]

# 3. Check availability
availability = check_download_availability(image_ids[:2])

# 4. Download quicklooks for available images
for image_id in image_ids[:2]:
    download_image(
        image_id=image_id,
        mission="sentinel-2",
        download_type="quicklook"
    )

# 5. List downloaded files
files = list_downloaded_files(
    download_dir="downloads",
    file_type="quicklook"
)

# 6. Get statistics
stats = get_download_statistics()
```

## 🔧 Configuration

### Environment Variables

| Variable | Description | Required For |
|----------|-------------|--------------|
| `COPERNICUS_USERNAME` | Copernicus Data Space email | Download operations |
| `COPERNICUS_PASSWORD` | Copernicus Data Space password | Download operations |
| `COPERNICUS_DEBUG_AUTH` | Enable authentication debugging | Debugging |
| `COPERNICUS_TEST_REAL_DOWNLOAD` | Enable real download tests | Testing |

### Default Directories
- **Downloads**: `downloads/` (individual downloads)
- **Batch Downloads**: `batch_downloads/` (batch operations)
- **Search Results**: `search_downloads/` (search_and_download)

### Performance Settings
- **Max Concurrent Downloads**: 3 (configurable in `batch_download_images`)
- **API Timeout**: 60 seconds
- **Download Chunk Size**: 8KB
- **Token Cache**: 4 minutes (with 1-minute buffer)

## 🧪 Testing

### Test Scripts
```bash
# Test authentication and basic functionality
python test_simple_download.py

# Test end-to-end workflow (requires credentials)
python test_download_e2e.py

# Test with real credentials
export COPERNICUS_USERNAME="your-email@example.com"
export COPERNICUS_PASSWORD="your-password"
python test_download_e2e.py
```

### Example Scripts
```bash
# Run complete examples
python example_download_usage.py

# Test specific functionality
python test_fix.py
```

## 🏗️ Architecture

### Server Structure
```
copernicus-mcp/
├── copernicus_mcp/          # Main package
│   ├── server.py           # Complete server implementation
│   ├── __init__.py         # Package exports
│   └── server_corrupted_backup.py  # Backup
├── tests/                  # Test scripts
│   ├── test_simple_download.py
│   ├── test_download_e2e.py
│   ├── test_fix.py
│   └── test_download_tools.py
├── examples/               # Usage examples
│   └── example_download_usage.py
├── requirements.txt        # Python dependencies
├── pyproject.toml         # Project configuration
├── README.md              # This file
├── DOWNLOAD_FUNCTIONS_SUMMARY.md  # Detailed docs
├── mcp_config.json        # MCP client configuration
└── INSTALL.md             # Installation guide
```

### Key Components
1. **Authentication Manager**: Handles token acquisition, caching, and refresh
2. **Search Engine**: Advanced query builder for Copernicus Data Space API
3. **Download Manager**: Concurrent downloads with progress tracking
4. **File Manager**: Disk space management and cleanup
5. **MCP Interface**: FastMCP-based tool registration and protocol handling

## 🔒 Authentication Model

### Public Access (No Authentication Required)
- Mission information
- Basic search operations
- Metadata retrieval

### Authenticated Access (Credentials Required)
- Image downloads (full, quicklook, compressed)
- Batch downloads
- Availability checks
- Download link retrieval

### Token Management
- Automatic token acquisition from Copernicus Identity Service
- Token caching with expiration handling
- Graceful error handling for invalid credentials
- Support for both environment variables and parameter-based authentication

## ⚠️ Error Handling

The server includes comprehensive error handling for:

### Authentication Errors
- Missing credentials
- Invalid credentials
- Token expiration
- Rate limiting

### API Errors
- Invalid image IDs
- Unavailable products
- Network timeouts
- API quota exceeded

### File System Errors
- Insufficient disk space
- Permission denied
- Invalid file paths
- Corrupted downloads

### User Input Errors
- Invalid geometry formats
- Unsupported mission parameters
- Date range errors
- Invalid download types

## 📈 Performance Considerations

### Download Sizes
- **Quicklooks**: 100KB - 1MB (recommended for testing)
- **Compressed Products**: 100MB - 1GB
- **Full Products**: 1GB - 10GB+ (varies by mission)

### Network Usage
- Start with quicklook downloads for testing
- Use `max_concurrent` to control bandwidth usage
- Monitor disk space for large downloads

### API Limits
- Respect Copernicus Data Space API rate limits
- Use appropriate date ranges and geographic extents
- Cache search results when possible

## 🚨 Security Notes

### Credential Safety
- Never hardcode credentials in code
- Use environment variables or secure credential stores
- Tokens are automatically refreshed and never stored permanently
- All authentication errors are logged without exposing sensitive information

### Network Security
- All API calls use HTTPS with proper certificate validation
- Download URLs are validated before use
- Timeout settings prevent hanging connections

### File Security
- Downloaded files use standard file permissions
- No automatic execution of downloaded content
- Cleanup operations require explicit confirmation (dry-run mode by default)

## 🔧 Troubleshooting

### Common Issues and Solutions

#### Authentication Failures
```bash
# Check if credentials are set
echo $COPERNICUS_USERNAME
echo $COPERNICUS_PASSWORD

# Test authentication directly
python -c "
import asyncio
from copernicus_mcp.server import get_auth_token
async def test():
    result = await get_auth_token()
    print('Result:', result)
asyncio.run(test())
"
```

#### Download Failures
1. **Check disk space**: Ensure you have sufficient space for downloads
2. **Verify image ID**: Use valid IDs from search results
3. **Try quicklook first**: Test with smaller files before downloading full products
4. **Check network**: Ensure stable internet connection

#### Search Issues
1. **Date range**: Use reasonable date ranges (e.g., last 30 days)
2. **Geometry size**: Keep search areas manageable
3. **Cloud cover**: Adjust cloud cover filters for optical missions

### Debug Mode
Enable debug logging for detailed information:
```bash
export COPERNICUS_DEBUG_AUTH=true
python -m copernicus_mcp
```

### Log Files
- Check application logs for detailed error messages
- Monitor download progress in real-time
- Review cleanup operations before execution

## 🙏 Acknowledgments

### Data Providers
- **European Space Agency (ESA)** for the Copernicus program
- **Copernicus Data Space Ecosystem** for providing API access
- **European Commission** for funding and support

### Technical Dependencies
- **FastMCP** framework for MCP server implementation
- **httpx** for async HTTP client functionality
- **pydantic** for data validation and serialization
- **shapely** for geometric operations

## 📚 Additional Resources

### Documentation
- [Copernicus Data Space Documentation](https://documentation.dataspace.copernicus.eu/)
- [MCP Protocol Specification](https://spec.modelcontextprotocol.io/)
- [FastMCP Documentation](https://fastmcp.readthedocs.io/)

### Tutorials and Examples
- Complete workflow examples in `example_download_usage.py`
- Test scripts for different scenarios
- Configuration examples in `mcp_config.json`

---

**Note**: This server is actively maintained. For the latest updates, check the GitHub repository and release notes.

**Happy Earth Observation!** 🌍🛰️

# Copernicus MCP Server - Installation Guide

## Overview

The Copernicus MCP Server provides access to Earth Observation data from the Copernicus Sentinel missions through the Model Context Protocol (MCP). This guide covers installation, setup, and basic usage.

## Prerequisites

### Required Tools
- Python package manager (pip)
- Git (optional, for cloning the repository)
- Terminal/Command Prompt

### Authentication Requirements
This server requires authentication with the Copernicus Data Space API. You need:

1. **Register for a free account** at: https://dataspace.copernicus.eu/
2. **Set environment variables** for your credentials:
   ```bash
   # On Linux/Mac
   export COPERNICUS_USERNAME="your-email@example.com"
   export COPERNICUS_PASSWORD="your-password"
   
   # On Windows (Command Prompt)
   set COPERNICUS_USERNAME=your-email@example.com
   set COPERNICUS_PASSWORD=your-password
   
   # On Windows (PowerShell)
   $env:COPERNICUS_USERNAME="your-email@example.com"
   $env:COPERNICUS_PASSWORD="your-password"
   ```

## Installation Methods

### Install from Local Directory (Recommended)

1. **Clone or download the repository**
   ```bash
   # Clone the repository
   git clone <repository-url>
   cd copernicus-mcp
   
   # Or if you already have the files
   cd /path/to/copernicus-mcp
   ```

2. **Create a virtual environment (optional but recommended)**
   ```bash
   # Create virtual environment
   python -m venv venv
   
   # Activate virtual environment
   # On Windows:
   venv\Scripts\activate
   # On macOS/Linux:
   source venv/bin/activate
   ```

3. **Install dependencies**
   ```bash
   pip install -r requirements.txt
   ```

4. **Install the package in development mode**
   ```bash
   pip install -e .
   ```

5. **Set up your Copernicus Data Space credentials** as environment variables (see Authentication Requirements above)


## Verification

### Test the Installation

1. **Check if the server can be imported**
   ```python
   python -c "from src.server import mcp; print('Server imported successfully')"
   ```

2. **Run basic tests**
   ```bash
   python -m pytest tests/test_server.py -v
   ```

3. **Test the server directly**
   ```bash
   python -m copernicus_mcp --help
   ```

### Verify Dependencies

Check installed packages:
```bash
pip list | grep -E "(fastmcp|httpx|pydantic|shapely|geojson)"
```

Expected output should show versions similar to:
```
fastmcp          1.0.0
httpx            0.25.0
pydantic         2.0.0
shapely          2.0.0
geojson          3.0.0
```

## Configuration

### Environment Variables

The server can be configured using environment variables:

| Variable | Description | Default | Required |
|----------|-------------|---------|----------|
| `COPERNICUS_USERNAME` | Your Copernicus Data Space email | - | **Yes** |
| `COPERNICUS_PASSWORD` | Your Copernicus Data Space password | - | **Yes** |
| `COPERNICUS_API_BASE` | Base URL for Copernicus API | `https://catalogue.dataspace.copernicus.eu` | No |
| `MCP_SERVER_NAME` | Server name for MCP clients | `copernicus-eo` | No |
| `HTTP_TIMEOUT` | HTTP request timeout in seconds | `30` | No |
| `MAX_RESULTS` | Default maximum search results | `50` | No |

Example:
```bash
# Required authentication variables
export COPERNICUS_USERNAME="your-email@example.com"
export COPERNICUS_PASSWORD="your-password"

# Optional configuration variables
export COPERNICUS_API_BASE="https://catalogue.dataspace.copernicus.eu"
export HTTP_TIMEOUT=60
```

### MCP Client Configuration

For use with MCP clients like Claude Desktop:

1. **Create or edit your MCP configuration file**
   - **Claude Desktop**: `~/Library/Application Support/Claude/claude_desktop_config.json` (macOS) or `%APPDATA%\Claude\claude_desktop_config.json` (Windows)
   - **Cursor**: `.cursor/mcp.json`
   - **Other clients**: Refer to their documentation

2. **Add the Copernicus server configuration**

   For local installation:
   ```json
   {
     "mcpServers": {
       "copernicus": {
         "command": "python",
         "args": ["-m", "copernicus_mcp"],
         "env": {
           "PYTHONPATH": "/full/path/to/copernicus-mcp/src",
           "COPERNICUS_USERNAME": "your-email@example.com",
           "COPERNICUS_PASSWORD": "your-password"
         }
       }
     }
   }
   ```

   For global installation:
   ```json
   {
     "mcpServers": {
       "copernicus": {
         "command": "copernicus-mcp",
         "env": {
           "COPERNICUS_USERNAME": "your-email@example.com",
           "COPERNICUS_PASSWORD": "your-password"
         }
       }
     }
   }
   ```

## Running the Server

### Basic Usage

1. **Start the server directly**
   ```bash
   python -m copernicus_mcp
   ```

2. **Run with specific options**
   ```bash
   # Run with debug logging
   python -m copernicus_mcp --verbose
   
   # Run on specific transport (stdio, http, etc.)
   python -m copernicus_mcp --transport stdio
   ```

### Integration with MCP Clients

Once configured in your MCP client, the server will automatically start when the client connects. You can verify the connection by:

1. Opening your MCP client
2. Checking for available tools (should include `search_copernicus_images`, `get_mission_info`, etc.)
3. Testing a simple query

## Testing the Connection

### Authentication Test

Before running the server, test your credentials:
```bash
python -c "
import os
from src.server import get_auth_token
import asyncio

async def test_auth():
    try:
        token = await get_auth_token()
        print('✅ Authentication successful!')
        print(f'Token length: {len(token)} characters')
    except Exception as e:
        print(f'❌ Authentication failed: {e}')
        print('Please check your COPERNICUS_USERNAME and COPERNICUS_PASSWORD environment variables')

asyncio.run(test_auth())
"
```

## Troubleshooting

### Debug Mode

Run the server in debug mode for more information:
```bash
python -m copernicus_mcp --verbose --debug
```

### Authentication Debugging

If authentication fails, you can test it directly:
```bash
# Test authentication only
python -c "
import asyncio
import httpx
import os

async def test_auth_direct():
    auth_data = {
        'client_id': 'cdse-public',
        'username': os.environ.get('COPERNICUS_USERNAME', ''),
        'password': os.environ.get('COPERNICUS_PASSWORD', ''),
        'grant_type': 'password',
    }
    
    async with httpx.AsyncClient() as client:
        try:
            response = await client.post(
                'https://identity.dataspace.copernicus.eu/auth/realms/CDSE/protocol/openid-connect/token',
                data=auth_data,
                headers={'Content-Type': 'application/x-www-form-urlencoded'}
            )
            print(f'Status: {response.status_code}')
            print(f'Response: {response.text[:200]}')
        except Exception as e:
            print(f'Error: {e}')

asyncio.run(test_auth_direct())
"
```

### Logs

Check server logs for:
- Connection attempts
- API responses
- Error messages
- Tool execution details

## Updating

### Update from Source
```bash
# Pull latest changes
git pull origin main

# Reinstall dependencies
pip install -r requirements.txt --upgrade

# Reinstall the package
pip install -e . --upgrade
```

### Update Dependencies
```bash
pip install --upgrade fastmcp httpx pydantic shapely geojson
```

## Uninstallation

### Remove the Package
```bash
pip uninstall copernicus-mcp
```

### Remove Dependencies
```bash
pip uninstall fastmcp httpx pydantic shapely geojson python-dateutil typing-extensions
```

### Clean Up
- Remove virtual environment: `rm -rf venv`
- Remove configuration from MCP clients
- Delete the repository folder

## Support
**Common resources**
- [Copernicus Data Space Documentation](https://documentation.dataspace.copernicus.eu/)
- [FastMCP Documentation](https://github.com/modelcontextprotocol/python-sdk)
- [MCP Specification](https://spec.modelcontextprotocol.io/)

## Next Steps

After successful installation:

1. **Try the examples**: Run `python examples/basic_usage.py`
2. **Explore available tools**: Check what tools are available through your MCP client
3. **Integrate with workflows**: Use the server in your data analysis pipelines
4. **Extend functionality**: Add support for additional missions or features


**Note**: This server provides search and metadata capabilities. Full image downloads may require additional authentication with the Copernicus Data Space.

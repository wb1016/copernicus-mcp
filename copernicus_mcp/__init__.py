"""
Copernicus MCP Server Package

A Model Context Protocol (MCP) server for accessing Copernicus Earth Observation data
from the Copernicus Data Space ecosystem.
"""

__version__ = "0.1.0"
__author__ = "Copernicus MCP Team"
__description__ = "MCP server for accessing Copernicus Earth Observation data"

from .server import mcp

__all__ = ["mcp"]

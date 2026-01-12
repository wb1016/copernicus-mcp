#!/usr/bin/env python3
"""
Run script for Copernicus MCP Server

This script provides an easy way to start the Copernicus MCP Server
with various configuration options.
"""

import argparse
import asyncio
import logging
import os
import sys
from pathlib import Path

try:
    from copernicus_mcp.server import __version__
    from copernicus_mcp.server import main as server_main
except ImportError as e:
    print(f"Error importing server module: {e}")
    print("Make sure you have installed the dependencies:")
    print("  pip install -r requirements.txt")
    sys.exit(1)


def setup_logging(verbose: bool = False, debug: bool = False):
    """Configure logging based on verbosity level"""
    log_level = logging.WARNING
    if verbose:
        log_level = logging.INFO
    if debug:
        log_level = logging.DEBUG

    logging.basicConfig(
        level=log_level,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    # Suppress noisy logs from dependencies
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)


def parse_arguments():
    """Parse command line arguments"""
    parser = argparse.ArgumentParser(
        description="Copernicus MCP Server - Access Earth Observation data from Copernicus Sentinel missions",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s                    # Start server with default settings
  %(prog)s --verbose          # Enable verbose logging
  %(prog)s --debug            # Enable debug logging
  %(prog)s --version          # Show version information
  %(prog)s --check            # Check dependencies and configuration
        """,
    )

    parser.add_argument(
        "-v", "--verbose", action="store_true", help="Enable verbose output"
    )

    parser.add_argument(
        "-d", "--debug", action="store_true", help="Enable debug logging"
    )

    parser.add_argument(
        "--version", action="store_true", help="Show version information and exit"
    )

    parser.add_argument(
        "--check",
        action="store_true",
        help="Check dependencies and configuration without starting server",
    )

    parser.add_argument(
        "--transport",
        choices=["stdio", "http", "sse"],
        default="stdio",
        help="MCP transport protocol (default: stdio)",
    )

    parser.add_argument(
        "--host",
        default="127.0.0.1",
        help="Host for HTTP/SSE transport (default: 127.0.0.1)",
    )

    parser.add_argument(
        "--port",
        type=int,
        default=3000,
        help="Port for HTTP/SSE transport (default: 3000)",
    )

    return parser.parse_args()


def check_dependencies():
    """Check if all required dependencies are available"""
    print("Checking dependencies...")

    dependencies = [
        ("fastmcp", "FastMCP framework"),
        ("httpx", "HTTP client"),
        ("pydantic", "Data validation"),
        ("shapely", "Geometry operations"),
        ("geojson", "GeoJSON handling"),
    ]

    all_ok = True
    for package, description in dependencies:
        try:
            __import__(package)
            print(f"  ✓ {package} ({description})")
        except ImportError:
            print(f"  ✗ {package} ({description}) - NOT FOUND")
            all_ok = False

    return all_ok


def check_configuration():
    """Check server configuration"""
    print("\nChecking configuration...")

    # Check environment variables
    env_vars = {
        "COPERNICUS_API_BASE": "https://catalogue.dataspace.copernicus.eu",
    }

    for var, default in env_vars.items():
        value = os.environ.get(var, default)
        if value != default:
            print(f"  ⚠ {var}: {value} (custom)")
        else:
            print(f"  ✓ {var}: {value} (default)")

    # Check Python path
    print(f"\nPython path:")
    for path in sys.path[:3]:  # Show first 3 entries
        print(f"  {path}")

    return True


def show_version():
    """Display version information"""
    print(f"Copernicus MCP Server v{__version__}")
    print("Access Earth Observation data from Copernicus Sentinel missions")
    print("")
    print("Available missions:")
    print("  • Sentinel-1: Synthetic Aperture Radar (SAR)")
    print("  • Sentinel-2: Multispectral Imaging")
    print("  • Sentinel-3: Ocean & Land Monitoring")
    print("  • Sentinel-5P: Atmospheric Monitoring")
    print("  • Sentinel-6: Ocean Topography")
    print("")
    print("Tools:")
    print("  • search_copernicus_images: Search for satellite images")
    print("  • get_mission_info: Get mission details")
    print("  • get_image_details: Get image metadata")
    print("  • get_recent_images: Get recent images")
    print("  • check_coverage: Analyze temporal coverage")
    print("")
    print("Configuration:")
    print(
        f"  API Base URL: {os.environ.get('COPERNICUS_API_BASE', 'https://catalogue.dataspace.copernicus.eu')}"
    )
    print(f"  Python: {sys.version}")


def main():
    """Main entry point"""
    args = parse_arguments()

    # Show version and exit if requested
    if args.version:
        show_version()
        sys.exit(0)

    # Setup logging
    setup_logging(args.verbose, args.debug)

    # Check dependencies if requested
    if args.check:
        deps_ok = check_dependencies()
        config_ok = check_configuration()

        if deps_ok and config_ok:
            print("\n✓ All checks passed!")
            sys.exit(0)
        else:
            print("\n✗ Some checks failed")
            sys.exit(1)

    # Start the server
    try:
        print(f"Starting Copernicus MCP Server v{__version__}")
        print(f"Transport: {args.transport}")

        if args.transport in ["http", "sse"]:
            print(f"Host: {args.host}")
            print(f"Port: {args.port}")

        print(
            "Available missions: Sentinel-1, Sentinel-2, Sentinel-3, Sentinel-5P, Sentinel-6"
        )
        print("Use Ctrl+C to stop the server\n")

        # Run the server
        server_main()

    except KeyboardInterrupt:
        print("\nServer stopped by user")
        sys.exit(0)
    except Exception as e:
        print(f"\nError starting server: {e}")
        if args.debug:
            import traceback

            traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()

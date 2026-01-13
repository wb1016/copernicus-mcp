#!/usr/bin/env python3
"""
Example Usage of Copernicus MCP Server Download Functionality

This script demonstrates how to use the new download tools in the Copernicus MCP server.
It shows various download scenarios and file management operations.

Prerequisites:
1. Install the Copernicus MCP server: pip install -e .
2. Set environment variables:
   export COPERNICUS_USERNAME='your-email@example.com'
   export COPERNICUS_PASSWORD='your-password'
3. Get valid image IDs from search results

Usage:
    python example_download_usage.py
"""

import asyncio
import json
import os
import sys
from pathlib import Path
from typing import Dict, List

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent))

try:
    from copernicus_mcp.server import (
        batch_download_images,
        check_download_availability,
        cleanup_downloads,
        download_image,
        get_download_statistics,
        get_product_download_links,
        list_downloaded_files,
        search_and_download,
        search_copernicus,
    )
except ImportError as e:
    print(f"Error importing server modules: {e}")
    print("Make sure you've installed the server: pip install -e .")
    sys.exit(1)


class DownloadExamples:
    """Example class demonstrating download functionality"""

    def __init__(self):
        self.has_credentials = False
        self.username = os.environ.get("COPERNICUS_USERNAME")
        self.password = os.environ.get("COPERNICUS_PASSWORD")

        if self.username and self.password:
            self.has_credentials = True
            print("✓ Copernicus credentials found")
        else:
            print("Warning: No Copernicus credentials found")
            print("  Set environment variables:")
            print("    export COPERNICUS_USERNAME='your-email@example.com'")
            print("    export COPERNICUS_PASSWORD='your-password'")

        # Example image IDs (replace with real IDs from search results)
        self.example_image_ids = [
            "01234567-89ab-cdef-0123-456789abcdef",  # Example ID 1
            "fedcba98-7654-3210-fedc-ba9876543210",  # Example ID 2
        ]

        # Create example directories
        self.example_dir = Path("example_downloads")
        self.example_dir.mkdir(exist_ok=True)

    def print_header(self, title: str):
        """Print section header"""
        print("\n" + "=" * 60)
        print(title)
        print("=" * 60)

    def print_result(self, title: str, result: Dict):
        """Print result with formatting"""
        print(f"\n{title}:")
        print(json.dumps(result, indent=2, default=str))

    async def example_1_check_availability(self):
        """Example 1: Check download availability"""
        self.print_header("EXAMPLE 1: Check Download Availability")

        if not self.has_credentials:
            print("Skipping - requires credentials")
            return

        print("Checking availability for example image IDs...")
        result = await check_download_availability(self.example_image_ids[:1])

        if "error" in result:
            print(f"Error: {result.get('error')}")
            print("Note: Example IDs are not real - use IDs from search results")
        else:
            self.print_result("Availability Result", result)

    async def example_2_get_download_links(self):
        """Example 2: Get download links for an image"""
        self.print_header("EXAMPLE 2: Get Download Links")

        if not self.has_credentials:
            print("Skipping - requires credentials")
            return

        print("Getting download links for an example image...")
        result = await get_product_download_links(self.example_image_ids[0])

        if "error" in result:
            print(f"Error: {result.get('error')}")
            print("Note: Example IDs are not real - use IDs from search results")
        else:
            self.print_result("Download Links", result)

    async def example_3_download_quicklook(self):
        """Example 3: Download a quicklook image"""
        self.print_header("EXAMPLE 3: Download Quicklook")

        if not self.has_credentials:
            print("Skipping - requires credentials")
            return

        print("Attempting to download quicklook for example image...")
        result = await download_image(
            image_id=self.example_image_ids[0],
            mission="sentinel-2",
            download_type="quicklook",
            output_dir=str(self.example_dir),
        )

        if "error" in result:
            print(f"Error: {result.get('error')}")
            print("Note: Example IDs are not real - use IDs from search results")
        else:
            self.print_result("Download Result", result)

    async def example_4_batch_download(self):
        """Example 4: Batch download multiple images"""
        self.print_header("EXAMPLE 4: Batch Download")

        if not self.has_credentials:
            print("Skipping - requires credentials")
            return

        print("Attempting batch download of example images...")
        result = await batch_download_images(
            image_ids=self.example_image_ids,
            mission="sentinel-2",
            download_type="quicklook",
            output_dir=str(self.example_dir / "batch"),
            max_concurrent=2,
        )

        if "error" in result:
            print(f"Error: {result.get('error')}")
            print("Note: Example IDs are not real - use IDs from search results")
        else:
            self.print_result("Batch Download Result", result)

    async def example_5_search_and_download(self):
        """Example 5: Search and download best match"""
        self.print_header("EXAMPLE 5: Search and Download")

        if not self.has_credentials:
            print("Skipping - requires credentials")
            return

        print("Searching for Sentinel-2 images near San Francisco...")
        result = await search_and_download(
            geometry=[-122.4194, 37.7749],  # San Francisco coordinates
            geometry_type="point",
            mission="sentinel-2",
            start_date="2024-01-01",
            end_date="2024-01-31",
            download_type="quicklook",
            output_dir=str(self.example_dir / "search_results"),
            limit=3,
        )

        if "error" in result:
            print(f"Error: {result.get('error')}")
            if "No images found" in str(result.get("error", "")):
                print("Note: No images found for the search criteria")
                print("Try different dates or location")
        else:
            self.print_result("Search and Download Result", result)

    async def example_6_file_management(self):
        """Example 6: File management operations"""
        self.print_header("EXAMPLE 6: File Management")

        # Create some test files for demonstration
        test_files = [
            self.example_dir / "test_quicklook_1.jpg",
            self.example_dir / "test_quicklook_2.jpg",
            self.example_dir / "test_full_1.zip",
        ]

        for file_path in test_files:
            file_path.write_text("Test content")

        print("1. Listing downloaded files...")
        list_result = await list_downloaded_files(
            download_dir=str(self.example_dir),
            file_type=None,
            limit=10,
        )
        self.print_result("File List", list_result)

        print("\n2. Getting download statistics...")
        stats_result = await get_download_statistics(
            download_dir=str(self.example_dir),
        )
        self.print_result("Download Statistics", stats_result)

        print("\n3. Dry run cleanup (would delete files older than 0 days)...")
        cleanup_result = await cleanup_downloads(
            download_dir=str(self.example_dir),
            older_than_days=0,
            dry_run=True,
        )
        self.print_result("Cleanup Dry Run", cleanup_result)

        # Clean up test files
        for file_path in test_files:
            file_path.unlink(missing_ok=True)

    async def example_7_real_workflow(self):
        """Example 7: Complete real workflow"""
        self.print_header("EXAMPLE 7: Complete Workflow")

        if not self.has_credentials:
            print("Skipping - requires credentials")
            return

        print("This example shows a complete workflow:")
        print("1. Search for images")
        print("2. Check availability")
        print("3. Download quicklooks")
        print("4. Manage downloaded files")

        # Step 1: Search for images
        print("\nStep 1: Searching for Sentinel-2 images...")
        search_result = await search_copernicus(
            geometry=[-122.4194, 37.7749],  # San Francisco
            geometry_type="point",
            mission="sentinel-2",
            start_date="2024-01-01",
            end_date="2024-01-07",  # One week
            max_cloud_cover=20,
            max_results=3,
        )

        if "error" in search_result:
            print(f"Search error: {search_result.get('error')}")
            return

        products = search_result.get("products", [])
        if not products:
            print("No images found for the search criteria")
            print("Try different dates or increase cloud cover tolerance")
            return

        print(f"Found {len(products)} image(s)")

        # Step 2: Extract image IDs
        image_ids = [p.get("Id") for p in products if p.get("Id")]
        if not image_ids:
            print("No valid image IDs found in search results")
            return

        print(f"Extracted {len(image_ids)} image ID(s)")

        # Step 3: Check availability
        print("\nStep 2: Checking download availability...")
        availability_result = await check_download_availability(image_ids[:2])

        if "error" in availability_result:
            print(f"Availability check error: {availability_result.get('error')}")
        else:
            available = availability_result.get("summary", {}).get("available", 0)
            print(f"{available} image(s) available for download")

        # Step 4: Download quicklook for first available image
        if image_ids:
            print(f"\nStep 3: Downloading quicklook for image {image_ids[0]}...")
            download_result = await download_image(
                image_id=image_ids[0],
                mission="sentinel-2",
                download_type="quicklook",
                output_dir=str(self.example_dir / "workflow"),
            )

            if "error" in download_result:
                print(f"Download error: {download_result.get('error')}")
            else:
                print(f"Download successful: {download_result.get('message', '')}")

        # Step 5: List downloaded files
        print("\nStep 4: Listing downloaded files...")
        list_result = await list_downloaded_files(
            download_dir=str(self.example_dir),
            limit=5,
        )

        if "error" in list_result:
            print(f"List error: {list_result.get('error')}")
        else:
            total_files = list_result.get("total_files", 0)
            print(f"Total files in directory: {total_files}")

    async def run_all_examples(self):
        """Run all examples"""
        print("COPENICUS MCP SERVER - DOWNLOAD EXAMPLES")
        print("=" * 60)

        await self.example_1_check_availability()
        await self.example_2_get_download_links()
        await self.example_3_download_quicklook()
        await self.example_4_batch_download()
        await self.example_5_search_and_download()
        await self.example_6_file_management()
        await self.example_7_real_workflow()

        # Clean up example directory
        try:
            import shutil

            if self.example_dir.exists():
                shutil.rmtree(self.example_dir)
        except:
            pass

        print("\n" + "=" * 60)
        print("EXAMPLES COMPLETE")
        print("=" * 60)
        print("\nNext steps:")
        print("1. Get real image IDs using search_copernicus")
        print("2. Test with your own coordinates and date ranges")
        print("3. Adjust download_type based on your needs:")
        print("   - 'quicklook' for previews (fast, small files)")
        print("   - 'full' for complete datasets (slow, large files)")
        print("   - 'compressed' for compressed versions")
        print("\nRemember to set your credentials:")
        print("export COPERNICUS_USERNAME='your-email@example.com'")
        print("export COPERNICUS_PASSWORD='your-password'")


async def main():
    """Main async function"""
    examples = DownloadExamples()
    await examples.run_all_examples()


if __name__ == "__main__":
    # Run async examples
    asyncio.run(main())

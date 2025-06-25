#!/usr/bin/env python3

# Run this command: python run.py fileName.json --max-images 5
"""
Google Maps Image Scraper Runner
Reads countries and locations from JSON file and extracts images using the scraper module.
"""

import json
import sys
from datetime import datetime
import logging

# Import the scraper module
try:
    from google_maps_image_scraper import scrape_locations_list
except ImportError:
    print("Error: google_maps_image_scraper.py not found in the same directory")
    sys.exit(1)

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

def load_countries_data(json_file="countries_locations.json"):
    """
    Load countries and locations from JSON file.
    
    Args:
        json_file (str): Path to JSON file containing countries and famousLocations
        
    Returns:
        list: List of country objects with famousLocations
    """
    try:
        with open(json_file, 'r', encoding='utf-8') as f:
            return json.load(f)
    except FileNotFoundError:
        logger.error(f"JSON file not found: {json_file}")
        sys.exit(1)
    except json.JSONDecodeError as e:
        logger.error(f"Invalid JSON format in {json_file}: {str(e)}")
        sys.exit(1)

def transform_scraper_output(scraper_results, country_name):
    """
    Transform the scraper output to match the desired format.
    
    Args:
        scraper_results (dict): Results from scrape_locations_list
        country_name (str): Name of the country
        
    Returns:
        dict: Formatted country object
    """
    country_data = {
        "country": country_name,
        "locations": []
    }
    
    for location_result in scraper_results.get("locations", []):
        location_name = location_result.get("location_name", "")
        image_urls = location_result.get("image_urls", [])
        
        if image_urls:
            location_data = {
                "Location Name": location_name,
                "images": image_urls
            }
            country_data["locations"].append(location_data)
        else:
            logger.warning(f"No images found for location: {location_name}")
    
    return country_data

def process_country(country_data, max_images=20):
    """
    Process a single country and its locations.
    
    Args:
        country_data (dict): Country object with name and famousLocations
        max_images (int): Maximum images per location
        
    Returns:
        dict: Country data with locations and images
    """
    country_name = country_data.get("country", "Unknown")
    locations = country_data.get("famousLocations", [])
    
    print(f"\nProcessing Country: {country_name}")
    print(f"Locations to process: {len(locations)}")
    print("-" * 80)
    
    try:
        scraper_results = scrape_locations_list(
            locations_list=locations,
            output_file=None,
            max_images=max_images,
            headless=True,
            timeout=30,
            show_progress=True
        )
        
        result = transform_scraper_output(scraper_results, country_name)
        
        successful_locations = len(result["locations"])
        total_images = sum(len(loc["images"]) for loc in result["locations"])
        
        print(f"\n{country_name} Summary:")
        print(f"  Successful locations: {successful_locations}/{len(locations)}")
        print(f"  Total images found: {total_images}")
        
        return result
        
    except Exception as e:
        logger.error(f"Error processing country {country_name}: {str(e)}")
        return {
            "country": country_name,
            "locations": []
        }

def process_all_countries(countries_data, max_images=20, output_file=None):
    """
    Process all countries from the JSON data.
    
    Args:
        countries_data (list): List of country objects
        max_images (int): Maximum images per location
        output_file (str, optional): Output JSON file path
        
    Returns:
        list: List of processed country objects with images
    """
    print(f"Starting Image Extraction")
    print(f"Countries to process: {len(countries_data)}")
    print(f"Max images per location: {max_images}")
    print(f"Mode: Headless")
    print("=" * 80)
    
    results = []
    
    for i, country_data in enumerate(countries_data, 1):
        country_name = country_data.get("country", "Unknown")
        print(f"\n[{i}/{len(countries_data)}] Processing: {country_name}")
        
        try:
            result = process_country(country_data, max_images)
            results.append(result)
        except Exception as e:
            logger.error(f"Failed to process country {country_name}: {str(e)}")
            results.append({
                "country": country_name,
                "locations": []
            })
        
        # Delay between countries to avoid being blocked
        if i < len(countries_data):
            print(f"\nWaiting 5 seconds before next country...")
            import time
            time.sleep(5)
    
    # Save results if output file specified
    if output_file:
        try:
            with open(output_file, 'w', encoding='utf-8') as f:
                json.dump(results, f, indent=2, ensure_ascii=False)
            print(f"\nResults saved to: {output_file}")
        except Exception as e:
            logger.error(f"Failed to save results to {output_file}: {str(e)}")
    
    print_summary(results)
    return results

def print_summary(results):
    """
    Print final summary of all results.
    
    Args:
        results (list): List of country results
    """
    print("\n" + "=" * 80)
    print("FINAL SUMMARY")
    print("=" * 80)
    
    total_countries = len(results)
    successful_countries = len([r for r in results if r["locations"]])
    total_locations = sum(len(r["locations"]) for r in results)
    total_images = sum(sum(len(loc["images"]) for loc in r["locations"]) for r in results)
    
    print(f"Total countries processed: {total_countries}")
    print(f"Countries with images: {successful_countries}")
    print(f"Total locations with images: {total_locations}")
    print(f"Total images extracted: {total_images}")
    
    if total_locations > 0:
        avg_images_per_location = round(total_images / total_locations, 2)
        print(f"Average images per location: {avg_images_per_location}")
    
    failed_countries = [r["country"] for r in results if not r["locations"]]
    if failed_countries:
        print(f"\nCountries with no images found:")
        for country in failed_countries:
            print(f"  • {country}")

def main():
    """Main function to run the image extraction process."""
    import argparse
    
    parser = argparse.ArgumentParser(description='Google Maps Image Scraper for Countries')
    parser.add_argument('input_file', help='JSON file containing countries and famousLocations')
    parser.add_argument('--max-images', type=int, default=20, help='Maximum number of images per location (default: 20)')
    
    args = parser.parse_args()
    
    # Load countries data from JSON file
    countries_data = load_countries_data(args.input_file)
    
    # Generate output filename with timestamp
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    input_name = args.input_file.replace('.json', '').replace('countries_locations_', '').replace('countries_', '')
    output_file = f"images_{input_name}_{timestamp}.json"
    
    # Process all countries
    results = process_all_countries(
        countries_data=countries_data,
        max_images=args.max_images,
        output_file=output_file
    )
    
    return results

if __name__ == "__main__":
    try:
        results = main()
        print(f"\nProcess completed successfully!")
        
    except KeyboardInterrupt:
        print("\nProcess interrupted by user")
        sys.exit(1)
    except Exception as e:
        print(f"\nAn error occurred: {str(e)}")
        logger.exception("Unhandled exception in main")
        sys.exit(1)
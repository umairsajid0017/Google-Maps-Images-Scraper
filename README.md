# Google Maps Images Scraper

A comprehensive Selenium-based scraper for extracting images from Google Maps location galleries. This project includes two main components: a core scraper module and a batch processing runner for multiple countries and locations.

## Features

- **Location Search**: Automatically searches Google Maps for specified locations
- **Gallery Navigation**: Opens photos sections and navigates through all available images
- **High-Resolution Images**: Extracts high-resolution versions of images (w0-h0 format)
- **Parallel Downloads**: Uses multi-threading for efficient image downloads
- **Batch Processing**: Process multiple countries and locations from JSON input
- **CSV Export**: Real-time URL saving to CSV files with timestamps
- **JSON Output**: Structured output format for integration with other tools
- **Error Handling**: Comprehensive error handling and retry mechanisms
- **Logging**: Detailed logging to track the scraping process

## Components

### 1. Core Scraper (`google_maps_image_scraper.py`)

The main scraper module that handles individual locations or batch processing.

### 2. Batch Runner (`run.py`)

A specialized runner for processing multiple countries and locations from JSON input files.

## Installation

Install the required dependencies:

```bash
pip install selenium webdriver-manager requests
```

## Usage

### Single Location Scraping

Extract images from a single location:

```bash
python google_maps_image_scraper.py "Empire State Building" --max-images 20
```

### Batch Location Processing

Process multiple locations from a comma-separated list:

```bash
python google_maps_image_scraper.py --list-input "Eiffel Tower,Big Ben,Statue of Liberty" --output-json results.json --max-images 10
```

### Country-Based Batch Processing

Process multiple countries and locations from a structured JSON file:

```bash
python run.py test.json --max-images 15
```

## Command Line Arguments

### Core Scraper (`google_maps_image_scraper.py`)

**Single Location Mode:**
- `location`: Name of the location to search for (required for single mode)

**Batch Mode:**
- `--list-input`: Comma-separated list of locations for batch processing
- `--output-json`: Output JSON file for batch results

**General Options:**
- `--max-images`: Maximum number of images to extract per location (default: unlimited)
- `--headless`: Run browser in headless mode
- `--download-dir`: Directory to save downloaded images (default: 'downloaded_images')
- `--max-workers`: Maximum number of threads for downloading (default: 5)
- `--timeout`: Timeout in seconds for WebDriverWait (default: 30)

**Output Control:**
- `--no-csv`: Disable saving URLs to CSV files
- `--only-csv`: Only save URLs to CSV, skip downloading images
- `--urls-only`: Only extract URLs to JSON, skip downloading images

**Debug & Advanced:**
- `--debug`: Enable debug mode with detailed logs
- `--no-headless`: Force browser to run in visible mode
- `--retry-attempts`: Number of retry attempts for each step (default: 3)

### Batch Runner (`run.py`)

- `input_file`: JSON file containing countries and famousLocations (required)
- `--max-images`: Maximum number of images per location (default: 20)

## Input Formats

### JSON Format for Batch Runner

The `run.py` script expects a JSON file with the following structure:

```json
[
    {
        "country": "Afghanistan",
        "famousLocations": [
            "Babur Gardens",
            "Band-e Amir National Park",
            "Herat Citadel"
        ]
    },
    {
        "country": "Albania",
        "famousLocations": [
            "Butrint National Park",
            "Skanderbeg Square",
            "Blue Eye Spring"
        ]
    }
]
```

## Output Formats

### CSV Output

Real-time CSV files with three columns:
- `index`: Sequential number for each image
- `image_url`: Full URL to the high-resolution image
- `timestamp`: When the URL was discovered

### JSON Output

Structured JSON format for batch processing:

```json
[
    {
        "country": "Afghanistan",
        "locations": [
            {
                "Location Name": "Babur Gardens",
                "images": [
                    "https://lh3.googleusercontent.com/...",
                    "https://lh3.googleusercontent.com/..."
                ]
            }
        ]
    }
]
```

## Example Usage Scenarios

### Extract URLs Only (No Downloads)

```bash
# Single location - URLs only
python google_maps_image_scraper.py "Taj Mahal" --urls-only --max-images 50

# Batch processing - URLs only
python google_maps_image_scraper.py --list-input "Colosseum,Machu Picchu" --urls-only --output-json urls_only.json
```

### CSV Only Mode

```bash
# Save only CSV files without downloading images
python google_maps_image_scraper.py "Sydney Opera House" --only-csv --max-images 30
```

### Country Batch Processing

```bash
# Process from JSON file
python run.py countries_data.json --max-images 25
```

## Customizing for Your Data

### Adapting the Batch Runner

The `run.py` script can be easily modified to work with different JSON input formats. Key areas to customize:

1. **Input Structure**: Modify the `load_countries_data()` function to match your JSON schema
2. **Output Format**: Adjust the `transform_scraper_output()` function for different output requirements
3. **Processing Logic**: Update the `process_country()` function for custom processing workflows

### Example Customization

If your JSON has a different structure, modify the relevant functions:

```python
# For a different input format like:
# {"regions": [{"name": "Europe", "places": ["Paris", "Rome"]}]}

def load_countries_data(json_file):
    # Adapt loading logic for your format
    pass

def process_country(region_data, max_images):
    # Adapt processing for your data structure
    pass
```

## File Organization

```
project/
├── google_maps_image_scraper.py    # Core scraper module
├── run.py                          # Batch processing runner
├── test.json                       # Sample input file
├── downloaded_images/              # Default download directory
├── countries_images_YYYYMMDD_HHMMSS.json  # Output files
└── gmaps_scraper.log              # Log files
```

## Error Handling

The scraper includes comprehensive error handling for:
- WebDriver initialization failures
- Network timeouts and connection issues
- Missing or changed page elements
- File I/O operations
- Malformed input data

## Performance Considerations

- Use `--headless` mode for better performance
- Adjust `--max-workers` based on your system capabilities
- Consider using `--only-csv` for large-scale URL extraction
- Implement delays between requests to avoid being blocked

## Legal and Ethical Usage

- Respect Google's Terms of Service
- Implement appropriate delays between requests
- Use scraped images responsibly and in accordance with copyright laws
- Consider the impact on Google's servers and other users
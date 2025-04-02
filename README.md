# Atlas14GridMiner

A powerful tool for efficiently downloading, processing, and visualizing NOAA Atlas 14 precipitation frequency grids.

## Overview

Atlas14GridMiner automates the retrieval and processing of precipitation frequency estimates from NOAA's Atlas 14 database. This tool helps hydrologists, civil engineers, and water resource professionals obtain critical rainfall data for flood studies, stormwater design, and hydrologic modeling.

### Key Features

- **Automated Grid Retrieval**: Downloads precipitation grids directly from NOAA servers
- **Smart Zone Detection**: Automatically identifies which NOAA Atlas 14 zones intersect with your project area
- **Grid Mosaicking**: Seamlessly combines grids across zone boundaries
- **Confidence Intervals**: Generates 90% confidence interval grids for 100-year events
- **User-Friendly Interface**: Simple Streamlit-based UI for easy configuration
- **Built-in Shapefile Support**: Works with included shapefiles or your own custom project area

## Installation

### Prerequisites

- Python 3.9+
- Required packages (automatically installed with pixi):
  - streamlit
  - geopandas
  - rasterio
  - numpy
  - tqdm
  - scipy
  - requests

### Setup with Pixi

Atlas14GridMiner uses pixi for environment management:

```bash
# Initialize the pixi environment
pixi install

# Run the application
pixi run python run_noaa_app_alt.py
```

## Usage

1. **Launch the application**: Run `python run_noaa_app_alt.py`
2. **Configure inputs**:
   - Enter a base directory for outputs
   - Select or upload required shapefiles
   - Choose recurrence intervals (1, 2, 5, 10, 25, 50, 100, 200, 500, 1000 years)
   - Select precipitation durations (5min to 24hr)
   - Toggle confidence interval generation
3. **Start processing**: Click "Process NOAA Grids" to begin
4. **View results**: Check your specified output directory for downloaded and processed grids

## Output Files

The tool generates several directories:

- **NOAA_grids/**: Contains all downloaded grids from NOAA servers
- **NOAA_grids_mosaic/**: Contains mosaicked grids (when multiple zones are involved)

File naming follows this pattern:
- `comb100yr24ha.asc` - Combined 100-year, 24-hour precipitation depth grid
- `comb100yr24ha_plus.asc` - Upper confidence bound (84th percentile)
- `comb100yr24ha_minus.asc` - Lower confidence bound (16th percentile)

## Technical Background

NOAA Atlas 14 provides precipitation frequency estimates with 90% confidence intervals for various durations and recurrence intervals. This data is essential for designing infrastructure that can withstand specific storm events.

This tool automates the process of:
1. Determining which NOAA zones intersect with your area of interest
2. Downloading relevant precipitation grids from NOAA servers
3. Mosaicking grids when a project area spans multiple zones
4. Generating confidence interval grids for statistical analysis

## Troubleshooting

If you encounter socket permission errors when running the Streamlit app:

1. Try the alternate port version: `python run_noaa_app_alt.py`
2. Run with administrator privileges if prompted
3. Ensure no other applications are using port 8502

## License

[MIT License](LICENSE)

## Acknowledgments

- Data provided by NOAA's [Precipitation Frequency Data Server](https://hdsc.nws.noaa.gov/hdsc/pfds/index.html)
- Developed using Streamlit, GeoPandas, and Rasterio libraries

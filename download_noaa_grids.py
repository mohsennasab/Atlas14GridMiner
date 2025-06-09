# Version: 2.0
# Description: Automates downloading and processing of NOAA Atlas 14 precipitation grids

import time
import os
import requests
import shutil
from zipfile import ZipFile
import geopandas as gpd
import glob
import rasterio
from rasterio.merge import merge
from rasterio.io import MemoryFile
import numpy as np
from tqdm import tqdm
from concurrent.futures import ThreadPoolExecutor
import logging
from typing import List, Tuple, Optional, Dict
import re
from scipy import special
import sys
from pathlib import Path
from dataclasses import dataclass
import warnings

warnings.filterwarnings('ignore', category=RuntimeWarning, message='invalid value encountered in cast')

# Configuration
@dataclass
class Config:
    """Configuration for NOAA grid processing"""
    CHUNK_SIZE: int = 1024 * 1024  # 1MB chunks for download
    MAX_RETRIES: int = 3
    TIMEOUT: int = 30
    VALID_EVENTS: set = frozenset({'1', '2', '5', '10', '25', '50', '100', '200', '500', '1000'})
    VALID_DURATIONS: set = frozenset({'05m', '10m', '15m', '30m', '60m', '02h', '03h', '06h', '12h', '24h'})

# Configure logging
def setup_logging(log_file: Optional[str] = None) -> None:
    """Configure logging with both file and console handlers"""
    handlers = [logging.StreamHandler()]
    if log_file:
        handlers.append(logging.FileHandler(log_file))
    
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(levelname)s - %(message)s',
        handlers=handlers
    )

class NOAADownloader:
    def __init__(self, config: Optional[Config] = None):
        self.config = config or Config()
        self._session = requests.Session()

    def download_and_unzip_noaa_grid(self, args: Tuple[str, str, str]) -> None:
        """Enhanced download function with retries and better error handling"""
        zone, fname, target_folder = args
        zipurl = f'https://hdsc.nws.noaa.gov/pub/hdsc/data/{zone}/{fname}'
        downloaded_file = Path(target_folder) / fname

        for attempt in range(self.config.MAX_RETRIES):
            try:
                with self._session.get(zipurl, stream=True, timeout=self.config.TIMEOUT) as r:
                    r.raise_for_status()
                    downloaded_file.parent.mkdir(parents=True, exist_ok=True)
                    with open(downloaded_file, "wb") as f:
                        for chunk in r.iter_content(chunk_size=self.config.CHUNK_SIZE):
                            f.write(chunk)

                with ZipFile(downloaded_file) as zf:
                    zf.extractall(path=target_folder)
                downloaded_file.unlink()
                return

            except Exception as e:
                if attempt == self.config.MAX_RETRIES - 1:
                    logging.error(f"Failed to process {fname} after {self.config.MAX_RETRIES} attempts: {str(e)}")
                    if downloaded_file.exists():
                        downloaded_file.unlink()
                    raise
                time.sleep(2 ** attempt)

class NOAAProcessor:
    """Handles NOAA grid processing operations"""
    
    @staticmethod
    def find_noaa_zones(prj_area_shp_path: str, states_shp_path: str) -> List[str]:
        """Find intersecting NOAA zones with improved error handling and CRS standardization"""
        try:
            with warnings.catch_warnings():
                warnings.filterwarnings('ignore', category=UserWarning)
                states_shp = gpd.read_file(states_shp_path)
                prj_area_shp = gpd.read_file(prj_area_shp_path)
        except Exception as e:
            logging.error(f"Error reading shapefiles: {e}")
            raise

        # Target CRS: NAD83 (EPSG:4269) to match NOAA rasters and zones
        target_crs = "EPSG:4269"
        
        # Log original CRS information
        logging.info(f"NOAA Zones shapefile CRS: {states_shp.crs}")
        logging.info(f"Project Area shapefile original CRS: {prj_area_shp.crs}")
        
        # Ensure NOAA zones shapefile is in target CRS
        if states_shp.crs != target_crs:
            logging.info(f"Converting NOAA zones from {states_shp.crs} to {target_crs}")
            states_shp = states_shp.to_crs(target_crs)
        
        # Convert project area to target CRS (NAD83 EPSG:4269)
        if prj_area_shp.crs != target_crs:
            logging.info(f"Converting Project Area shapefile from {prj_area_shp.crs} to {target_crs}")
            prj_area_shp = prj_area_shp.to_crs(target_crs)
        else:
            logging.info(f"Project Area shapefile already in target CRS: {target_crs}")
        
        # Create union of project area geometries
        prj_area_union = prj_area_shp.geometry.unary_union
        
        # Find intersecting NOAA zones
        qry = states_shp.sindex.query(prj_area_union, predicate="intersects")
        zone_list = states_shp.iloc[qry]['NOAA14_cd'].unique().tolist()
        
        logging.info(f"Found intersecting NOAA zones: {zone_list}")
        
        return [z for z in zone_list if z != "Atlas2"]

    @staticmethod
    def mosaic_list_of_rasters(raster_list: List[str], event: str, dur: str, CI: str = '') -> None:
        """Mosaic rasters with improved memory handling"""
        mosaic_folder = Path(os.path.dirname(raster_list[0])) / '..' / 'NOAA_grids_mosaic'
        mosaic_folder.mkdir(parents=True, exist_ok=True)

        # Future-proof pattern: Allow any number of letters for the zone prefix
        if not all(re.match(rf"^[a-zA-Z]+{event}yr{dur}a[ul]?\.asc$", Path(f).name) for f in raster_list):
            raise ValueError(
                f"Unexpected file pattern in raster list for event={event}, duration={dur}. Files: {raster_list}"
            )

        with rasterio.Env():
            sources = [rasterio.open(f) for f in raster_list]
            try:
                mosaic, transform = merge(sources, method='max')
                
                meta = sources[0].meta.copy()
                meta.update({
                    "height": mosaic.shape[1],
                    "width": mosaic.shape[2],
                    "transform": transform
                })

                output_name = f"comb{event}yr{dur}a{CI}.asc"
                with rasterio.open(mosaic_folder / output_name, 'w', **meta) as dst:
                    dst.write(mosaic)

            finally:
                for src in sources:
                    src.close()

    @staticmethod
    def compute_1pct_plus_and_minus(path_to_100yr: str, path_to_100yr_upper: str, 
                                  path_to_100yr_lower: str) -> None:
        """Compute confidence intervals with improved error handling"""
        try:
            with rasterio.Env():
                with rasterio.open(path_to_100yr) as rast:
                    p_100yr_arr = rast.read(1, out_dtype='float32')
                    out_meta = rast.meta.copy()
                with rasterio.open(path_to_100yr_lower) as rast:
                    p_lower_arr = rast.read(1, out_dtype='float32')
                with rasterio.open(path_to_100yr_upper) as rast:
                    p_upper_arr = rast.read(1, out_dtype='float32')

                # Process arrays
                for arr in [p_100yr_arr, p_lower_arr, p_upper_arr]:
                    arr[arr <= 0] = np.nan
                    arr /= 1000.0

                # Calculate confidence intervals
                mu = np.log(p_100yr_arr)
                sigma_lower = (mu - np.log(p_lower_arr)) / 1.645
                sigma_upper = (np.log(p_upper_arr) - mu) / 1.645
                sigma_max = np.maximum(sigma_lower, sigma_upper)
                
                p_1pct_minus = np.exp(mu + (sigma_max * np.sqrt(2) * special.erfinv(2 * 0.16 - 1)))
                p_1pct_plus = np.exp(mu + (sigma_max * np.sqrt(2) * special.erfinv(2 * 0.84 - 1)))

                # Save results
                filename_100yr = Path(path_to_100yr).stem
                folder = Path(path_to_100yr).parent
                out_meta.update({"nodata": np.nan})

                for suffix, data in [("_plus", p_1pct_plus), ("_minus", p_1pct_minus)]:
                    output_path = folder / f"{filename_100yr}{suffix}.asc"
                    with rasterio.open(output_path, "w", **out_meta) as dest:
                        dest.write(np.around(data * 1000, 0).astype(np.float32), 1)

        except Exception as e:
            logging.error(f"Error in confidence interval computation: {e}")
            raise

class NOAAGrids:
    """Main class for NOAA grid operations"""
    
    def __init__(self, config: Optional[Config] = None):
        self.config = config or Config()
        self.downloader = NOAADownloader(self.config)
        self.processor = NOAAProcessor()

    def process_grids(self, base_dir: str, prj_area_shp_path: str, 
                     states_shp_path: str, event_list: List[str], 
                     dur_list: List[str], CI_100yr: bool = True) -> None:
        """Main processing function"""
        try:
            # Validate inputs
            if not set(event_list).issubset(self.config.VALID_EVENTS):
                raise ValueError(f"Invalid events. Valid options are: {self.config.VALID_EVENTS}")
            if not set(dur_list).issubset(self.config.VALID_DURATIONS):
                raise ValueError(f"Invalid durations. Valid options are: {self.config.VALID_DURATIONS}")

            base_dir = Path(base_dir)
            zones = self.get_noaa_grids(base_dir, prj_area_shp_path, event_list, 
                                      dur_list, states_shp_path, CI_100yr)
            
            if len(zones) > 1:
                self.combine_multiple_zones(base_dir, event_list, dur_list)
                grids_folder = base_dir / 'NOAA_grids_mosaic'
            else:
                grids_folder = base_dir / 'NOAA_grids'

            if '100' in event_list and CI_100yr:
                self.process_confidence_intervals(grids_folder, dur_list)

        except Exception as e:
            logging.error(f"Error in grid processing: {e}")
            raise

    def get_noaa_grids(self, base_dir: Path, prj_area_shp_path: str, 
                       event_list: List[str], dur_list: List[str], 
                       states_shp_path: str, CI_100yr: bool = True) -> List[str]:
        """Download NOAA grids with parallel processing"""
        grids_folder = base_dir / 'NOAA_grids'
        grids_folder.mkdir(parents=True, exist_ok=True)

        zone_list = self.processor.find_noaa_zones(prj_area_shp_path, states_shp_path)
        logging.info(f"Processing zones: {zone_list}")

        file_tasks = []
        for zone in zone_list:
            for event in event_list:
                for duration in dur_list:
                    base_pattern = f"{zone}{event}yr{duration}a"
                    file_tasks.append((zone, f"{base_pattern}.zip", str(grids_folder)))
                    
                    if event == '100' and CI_100yr:
                        file_tasks.extend([
                            (zone, f"{base_pattern}u.zip", str(grids_folder)),
                            (zone, f"{base_pattern}l.zip", str(grids_folder))
                        ])

        with ThreadPoolExecutor(max_workers=4) as executor:
            list(tqdm(executor.map(self.downloader.download_and_unzip_noaa_grid, file_tasks), 
                     total=len(file_tasks), desc="Downloading grids"))

        return zone_list

    def combine_multiple_zones(self, base_dir: Path, event_list: List[str], dur_list: List[str]) -> None:
        """Combine multiple zones with parallel processing"""
        tasks = []
        grids_folder = base_dir / 'NOAA_grids'

        for e in event_list:
            for d in dur_list:
                # Exact match for event and duration
                rasters = [
                    f for f in grids_folder.glob(f"*{e}yr{d}a.asc")
                    if re.search(rf"^[a-zA-Z]+{e}yr{d}a\.asc$", f.name)
                ]

                if len(rasters) > 1:
                    tasks.append(([str(r) for r in rasters], e, d, ''))

                # Confidence intervals (u and l)
                if e == '100':
                    for ci in ['u', 'l']:
                        ci_rasters = [
                            f for f in grids_folder.glob(f"*{e}yr{d}a{ci}.asc")
                            if re.search(rf"^[a-zA-Z]+{e}yr{d}a{ci}\.asc$", f.name)
                        ]

                        if len(ci_rasters) > 1:
                            tasks.append(([str(r) for r in ci_rasters], e, d, ci))

        with ThreadPoolExecutor(max_workers=os.cpu_count()) as executor:
            futures = []
            for rasters, e, d, ci in tasks:
                futures.append(
                    executor.submit(self.processor.mosaic_list_of_rasters, rasters, e, d, ci)
                )

            for future in tqdm(futures, desc="Mosaicking grids"):
                future.result()


    def process_confidence_intervals(self, grids_folder: Path, dur_list: List[str]) -> None:
        """Process confidence intervals for all durations"""
        logging.info("Computing 1% plus/minus grids")
        for dur in tqdm(dur_list, desc="Processing durations"):
            try:
                base = next(grids_folder.glob(f"*100yr{dur}a.asc"))
                upper = next(grids_folder.glob(f"*100yr{dur}au.asc"))
                lower = next(grids_folder.glob(f"*100yr{dur}al.asc"))
                
                self.processor.compute_1pct_plus_and_minus(
                    str(base), str(upper), str(lower))
            except StopIteration:
                logging.warning(f"Missing files for duration {dur}")
            except Exception as e:
                logging.error(f"Error processing duration {dur}: {e}")

def get_user_input() -> Dict[str, any]:
    """Get and validate user inputs in an organized manner"""
    print("\n" + "="*80)
    print("Welcome to the NOAA Grids Automation Script!")
    print("="*80 + "\n")

    # 1. Base Directory
    print("\n--- Step 1: Base Directory Configuration ---")
    base_dir = Path(input(
        "Enter the Base Directory where all data will be stored:\n"
        "Example: D:/Projects/NOAA/Precipitation\n"
        "> "
    ).strip('"').strip("'"))
    base_dir.mkdir(parents=True, exist_ok=True)

    # 2. Shapefile Paths
    print("\n--- Step 2: Shapefile Paths ---")
    states_shp_path = Path(input(
        "Enter the path to the NOAA Atlas 14 Zones Shapefile (.shp):\n"
        "Example: C:/Data/NOAA_Zones/atl14_zones.shp\n"
        "> "
    ).strip('"').strip("'"))
    if not states_shp_path.is_file():
        raise FileNotFoundError(f"NOAA Atlas 14 Zones Shapefile not found at '{states_shp_path}'")

    prj_area_shp_path = Path(input(
        "Enter the path to your Project Area Shapefile (.shp):\n"
        "Example: D:/Projects/NOAA/project_area.shp\n"
        "> "
    ).strip('"').strip("'"))
    if not prj_area_shp_path.is_file():
        raise FileNotFoundError(f"Project Area Shapefile not found at '{prj_area_shp_path}'")

    # 3. Event Selection
    print("\n--- Step 3: Event Selection ---")
    print("Available Recurrence Intervals (years):")
    events_display = "all, " + ', '.join(sorted(Config.VALID_EVENTS, key=int))
    print(f"  {events_display}")
    event_input = input("Enter desired intervals separated by spaces (or 'all'):\n> ").strip().lower()
    event_list = list(Config.VALID_EVENTS) if event_input == 'all' else event_input.split()
    if not set(event_list).issubset(Config.VALID_EVENTS):
        raise ValueError(f"Invalid recurrence intervals. Valid options: {Config.VALID_EVENTS}")

    # 4. Duration Selection
    print("\n--- Step 4: Duration Selection ---")
    print("Available Precipitation Durations:")
    durations_display = "all, " + ', '.join(sorted(Config.VALID_DURATIONS))
    print(f"  {durations_display}")
    dur_input = input("Enter desired durations separated by spaces (or 'all'):\n> ").strip().lower()
    dur_list = list(Config.VALID_DURATIONS) if dur_input == 'all' else dur_input.split()
    if not set(dur_list).issubset(Config.VALID_DURATIONS):
        raise ValueError(f"Invalid durations. Valid options: {Config.VALID_DURATIONS}")

    # 5. Confidence Interval Option
    print("\n--- Step 5: Confidence Interval Configuration ---")
    ci_input = input(
        "Download 90% confidence interval grids for 100-year event? (yes/no)\n"
        "Default is 'yes'\n"
        "> "
    ).strip().lower()
    CI_100yr = ci_input not in {'no', 'n'}

    return {
        "base_dir": base_dir,
        "states_shp_path": states_shp_path,
        "prj_area_shp_path": prj_area_shp_path,
        "event_list": event_list,
        "dur_list": dur_list,
        "CI_100yr": CI_100yr
    }

def main():
    """Main entry point with improved error handling and input validation"""
    setup_logging("noaa_processing.log")
    start_time = time.time()
    
    try:
        # Get user inputs
        inputs = get_user_input()
        
        # Initialize and run processor
        processor = NOAAGrids()
        processor.process_grids(
            base_dir=str(inputs["base_dir"]),
            prj_area_shp_path=str(inputs["prj_area_shp_path"]),
            states_shp_path=str(inputs["states_shp_path"]),
            event_list=inputs["event_list"],
            dur_list=inputs["dur_list"],
            CI_100yr=inputs["CI_100yr"]
        )
        
        # Log completion time
        elapsed_time = time.time() - start_time
        hours, rem = divmod(elapsed_time, 3600)
        minutes, seconds = divmod(rem, 60)
        logging.info(f"Processing completed in {int(hours)}h {int(minutes)}m {round(seconds, 2)}s")
        
    except Exception as e:
        logging.error(f"Fatal error: {str(e)}", exc_info=True)
        sys.exit(1)

if __name__ == '__main__':
    print("Script starting...")  # Debug print
    logging.info("Script initialized")  # Debug log
    main()
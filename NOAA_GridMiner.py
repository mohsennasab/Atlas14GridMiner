"""
NOAA Atlas 14 Grid Processor - Streamlined Version
Author: Tahmasebi Nasab, Mohsen
Last Modified: June 2025
Modified by: Daniel Kang; Version: 2.3 (detailed version)
"""

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
import json

warnings.filterwarnings('ignore', category=RuntimeWarning, message='invalid value encountered in cast')

# Configuration
@dataclass
class Config:
    """Enhanced configuration for NOAA grid processing"""
    CHUNK_SIZE: int = 1024 * 1024  # 1MB chunks for download
    MAX_RETRIES: int = 3
    TIMEOUT: int = 30
    VALID_EVENTS: set = frozenset({'1', '2', '5', '10', '25', '50', '100', '200', '500', '1000'})
    VALID_DURATIONS: set = frozenset({'05m', '10m', '15m', '30m', '60m', '02h', '03h', '06h', '12h', '24h'})
    
    # NOAA Atlas 14 Volume definitions
    ATLAS14_VOLUMES = {
        'sw1': {'name': 'Semiarid Southwest', 'volume': 1, 'description': 'Arizona, Nevada, Utah', 'code': 'sw'},
        'orb': {'name': 'Ohio River Basin and Surrounding States', 'volume': 2, 'description': 'Indiana, Kentucky, Ohio, Tennessee, West Virginia', 'code': 'orb'},
        'pr': {'name': 'Puerto Rico and U.S. Virgin Islands', 'volume': 3, 'description': 'Puerto Rico, U.S. Virgin Islands', 'code': 'pr'},
        'hi': {'name': 'Hawaiian Islands', 'volume': 4, 'description': 'Hawaii', 'code': 'hi'},
        'sw6': {'name': 'California', 'volume': 6, 'description': 'California', 'code': 'sw'},
        'ak': {'name': 'Alaska', 'volume': 7, 'description': 'Alaska', 'code': 'ak'},
        'mw': {'name': 'Midwestern States', 'volume': 8, 'description': 'Illinois, Iowa, Michigan, Minnesota, Missouri, Wisconsin', 'code': 'mw'},
        'se': {'name': 'Southeastern States', 'volume': 9, 'description': 'Alabama, Florida, Georgia, Mississippi, South Carolina', 'code': 'se'},
        'ne': {'name': 'Northeastern States', 'volume': 10, 'description': 'Connecticut, Maine, Massachusetts, New Hampshire, Rhode Island, Vermont', 'code': 'ne'},
        'tx': {'name': 'Texas', 'volume': 11, 'description': 'Texas', 'code': 'tx'},
        'inw': {'name': 'Interior Northwest', 'volume': 12, 'description': 'Idaho, Montana, Oregon, Washington', 'code': 'inw'}
    }
    
    # Duration series types
    SERIES_TYPES = ['PDS', 'AMS', 'BOTH']

def setup_logging(log_file: Optional[str] = None, verbose: bool = True) -> None:
    """Enhanced logging configuration with detailed processing log"""
    log_level = logging.INFO if verbose else logging.WARNING
    handlers = [logging.StreamHandler()]
    if log_file:
        handlers.append(logging.FileHandler(log_file))
    
    logging.basicConfig(
        level=log_level,
        format='%(asctime)s - %(levelname)s - %(message)s',
        handlers=handlers,
        force=True  # Override any existing configuration
    )

class ProcessingLogger:
    """Enhanced processing logger for detailed operation tracking"""
    
    def __init__(self, log_file: Optional[str] = None):
        self.log_file = log_file
        self.start_time = time.time()
        self.operations = []
        self.downloaded_urls = []
        
    def log_config(self, config_dict: Dict):
        """Log user configuration details"""
        logging.info("="*80)
        logging.info("NOAA ATLAS 14 GRID PROCESSOR - CONFIGURATION SUMMARY")
        logging.info("="*80)
        
        for key, value in config_dict.items():
            if isinstance(value, list):
                logging.info(f"{key}: {', '.join(map(str, value))}")
            else:
                logging.info(f"{key}: {value}")
        
        logging.info("="*80)
        
    def log_operation(self, operation: str, status: str, details: str = ""):
        """Log individual operations with timestamp"""
        elapsed = time.time() - self.start_time
        log_entry = {
            'timestamp': time.strftime('%H:%M:%S'),
            'elapsed': f"{elapsed:.1f}s",
            'operation': operation,
            'status': status,
            'details': details
        }
        self.operations.append(log_entry)
        
        log_msg = f"[{log_entry['elapsed']}] {operation}: {status}"
        if details:
            log_msg += f" - {details}"
        logging.info(log_msg)
    
    def log_download_url(self, url: str, status: str):
        """Log downloaded URLs for QA/QC tracking"""
        self.downloaded_urls.append({'url': url, 'status': status})
        logging.info(f"Downloaded: {url} - {status}")
    
    def generate_summary(self):
        """Generate processing summary"""
        total_time = time.time() - self.start_time
        hours, rem = divmod(total_time, 3600)
        minutes, seconds = divmod(rem, 60)
        
        logging.info("="*80)
        logging.info("PROCESSING SUMMARY")
        logging.info("="*80)
        logging.info(f"Total Processing Time: {int(hours)}h {int(minutes)}m {round(seconds, 2)}s")
        logging.info(f"Total Operations: {len(self.operations)}")
        
        # Count operation types
        success_ops = len([op for op in self.operations if op['status'] == 'SUCCESS'])
        error_ops = len([op for op in self.operations if op['status'] == 'ERROR'])
        
        logging.info(f"Successful Operations: {success_ops}")
        if error_ops > 0:
            logging.warning(f"Failed Operations: {error_ops}")
        
        # Log download summary
        success_downloads = len([url for url in self.downloaded_urls if url['status'] == 'SUCCESS'])
        total_downloads = len(self.downloaded_urls)
        logging.info(f"Successful Downloads: {success_downloads}/{total_downloads}")
        
        # Log failed URLs for troubleshooting
        failed_urls = [url['url'] for url in self.downloaded_urls if url['status'] != 'SUCCESS']
        if failed_urls:
            logging.warning("Failed Downloads:")
            for url in failed_urls:
                logging.warning(f"  - {url}")
        
        logging.info("="*80)
    
    def write_qa_summary(self, base_dir: Path, config_dict: Dict, calculate_stats: bool = False):
        """Write QA/QC summary to text file in base directory"""
        qa_file = base_dir / "noaa_processing.txt"
        
        total_time = time.time() - self.start_time
        hours, rem = divmod(total_time, 3600)
        minutes, seconds = divmod(rem, 60)
        
        with open(qa_file, 'w') as f:
            f.write("NOAA ATLAS 14 GRID PROCESSOR - QA/QC SUMMARY\n")
            f.write("=" * 60 + "\n\n")
            
            # Configuration Summary
            f.write("USER CONFIGURATION:\n")
            f.write("-" * 30 + "\n")
            for key, value in config_dict.items():
                if isinstance(value, list):
                    f.write(f"{key}: {', '.join(map(str, value))}\n")
                else:
                    f.write(f"{key}: {value}\n")
            f.write("\n")
            
            # Processing Summary
            f.write("PROCESSING SUMMARY:\n")
            f.write("-" * 30 + "\n")
            f.write(f"Total Processing Time: {int(hours)}h {int(minutes)}m {round(seconds, 2)}s\n")
            f.write(f"Total Operations: {len(self.operations)}\n")
            
            success_ops = len([op for op in self.operations if op['status'] == 'SUCCESS'])
            error_ops = len([op for op in self.operations if op['status'] == 'ERROR'])
            f.write(f"Successful Operations: {success_ops}\n")
            f.write(f"Failed Operations: {error_ops}\n\n")
            
            # Download Summary
            f.write("DOWNLOAD SUMMARY:\n")
            f.write("-" * 30 + "\n")
            success_downloads = len([url for url in self.downloaded_urls if url['status'] == 'SUCCESS'])
            total_downloads = len(self.downloaded_urls)
            f.write(f"Total Downloads: {total_downloads}\n")
            f.write(f"Successful Downloads: {success_downloads}\n")
            f.write(f"Failed Downloads: {total_downloads - success_downloads}\n\n")
            
            # Data Sources (URLs)
            f.write("DATA SOURCES:\n")
            f.write("-" * 30 + "\n")
            unique_urls = list(set([url['url'] for url in self.downloaded_urls]))
            for url in sorted(unique_urls):
                status = next((u['status'] for u in self.downloaded_urls if u['url'] == url), 'UNKNOWN')
                f.write(f"{status}: {url}\n")
            f.write("\n")
            
            # Output Locations
            f.write("OUTPUT LOCATIONS:\n")
            f.write("-" * 30 + "\n")
            f.write(f"Base Directory: {base_dir}\n")
            
            # Calculate and report basic statistics for output files if requested
            if calculate_stats:
                f.write("\nBASIC STATISTICS:\n")
                f.write("-" * 30 + "\n")
                
                for series in ['PDS', 'AMS']:
                    grids_folder = base_dir / f'NOAA_grids_{series}'
                    mosaic_folder = base_dir / f'NOAA_grids_mosaic_{series}'
                    
                    if grids_folder.exists():
                        f.write(f"{series} Grids: {grids_folder}\n")
                        
                    if mosaic_folder.exists():
                        f.write(f"{series} Mosaic: {mosaic_folder}\n")
                        
                        # Calculate statistics for all ASC files in mosaic folder
                        asc_files = list(mosaic_folder.glob("*.asc"))
                        
                        if asc_files:
                            f.write(f"\n{series} MOSAIC STATISTICS:\n")
                            for asc_file in sorted(asc_files):
                                try:
                                    with rasterio.open(asc_file) as src:
                                        data = src.read(1, masked=True)
                                        if data.compressed().size > 0:  # Check if there's valid data
                                            f.write(f"  {asc_file.name}:\n")
                                            f.write(f"    Min: {np.min(data.compressed()):.2f}\n")
                                            f.write(f"    Max: {np.max(data.compressed()):.2f}\n")
                                            f.write(f"    Mean: {np.mean(data.compressed()):.2f}\n")
                                            f.write(f"    Std Dev: {np.std(data.compressed()):.2f}\n\n")
                                        else:
                                            f.write(f"  {asc_file.name}: No valid data\n")
                                except Exception as e:
                                    f.write(f"  {asc_file.name}: Error reading file - {e}\n")
                    else:
                        # If no mosaic folder, check individual grids folder
                        if grids_folder.exists():
                            asc_files = list(grids_folder.glob("*.asc"))
                            if asc_files:
                                f.write(f"\n{series} INDIVIDUAL GRID STATISTICS:\n")
                                for asc_file in sorted(asc_files):
                                    try:
                                        with rasterio.open(asc_file) as src:
                                            data = src.read(1, masked=True)
                                            if data.compressed().size > 0:
                                                f.write(f"  {asc_file.name}:\n")
                                                f.write(f"    Min: {np.min(data.compressed()):.2f}\n")
                                                f.write(f"    Max: {np.max(data.compressed()):.2f}\n")
                                                f.write(f"    Mean: {np.mean(data.compressed()):.2f}\n")
                                                f.write(f"    Std Dev: {np.std(data.compressed()):.2f}\n\n")
                                    except Exception as e:
                                        f.write(f"  {asc_file.name}: Error reading file - {e}\n")
            else:
                # Just list output locations without statistics
                for series in ['PDS', 'AMS']:
                    grids_folder = base_dir / f'NOAA_grids_{series}'
                    mosaic_folder = base_dir / f'NOAA_grids_mosaic_{series}'
                    if grids_folder.exists():
                        f.write(f"{series} Grids: {grids_folder}\n")
                    if mosaic_folder.exists():
                        f.write(f"{series} Mosaic: {mosaic_folder}\n")
        
        logging.info(f"QA/QC summary written to: {qa_file}")

class EnhancedNOAADownloader:
    """Enhanced downloader with better error handling and progress tracking"""
    
    def __init__(self, config: Optional[Config] = None, logger: Optional[ProcessingLogger] = None):
        self.config = config or Config()
        self.logger = logger
        self._session = requests.Session()

    def download_and_unzip_noaa_grid(self, args: Tuple[str, str, str, str]) -> None:
        """Enhanced download function with series type support"""
        zone, fname, target_folder, series_type = args
        
        # Modify filename for AMS if needed
        if series_type == 'AMS':
            # Convert PDS filename to AMS (add '_ams' suffix before .zip)
            fname_ams = fname.replace('.zip', '_ams.zip')
            zipurl = f'https://hdsc.nws.noaa.gov/pub/hdsc/data/{zone}/{fname_ams}'
            downloaded_file = Path(target_folder) / fname_ams
        else:
            zipurl = f'https://hdsc.nws.noaa.gov/pub/hdsc/data/{zone}/{fname}'
            downloaded_file = Path(target_folder) / fname

        for attempt in range(self.config.MAX_RETRIES):
            try:
                if self.logger:
                    self.logger.log_operation(
                        f"Download {fname}", 
                        f"Attempt {attempt + 1}", 
                        f"Zone: {zone}, Series: {series_type}"
                    )
                
                with self._session.get(zipurl, stream=True, timeout=self.config.TIMEOUT) as r:
                    r.raise_for_status()
                    downloaded_file.parent.mkdir(parents=True, exist_ok=True)
                    with open(downloaded_file, "wb") as f:
                        for chunk in r.iter_content(chunk_size=self.config.CHUNK_SIZE):
                            f.write(chunk)

                with ZipFile(downloaded_file) as zf:
                    zf.extractall(path=target_folder)
                downloaded_file.unlink()
                
                if self.logger:
                    self.logger.log_operation(f"Download {fname}", "SUCCESS", f"Series: {series_type}")
                    self.logger.log_download_url(zipurl, "SUCCESS")
                return

            except Exception as e:
                if attempt == self.config.MAX_RETRIES - 1:
                    error_msg = f"Failed to process {fname} after {self.config.MAX_RETRIES} attempts: {str(e)}"
                    logging.error(error_msg)
                    if self.logger:
                        self.logger.log_operation(f"Download {fname}", "ERROR", error_msg)
                        self.logger.log_download_url(zipurl, "ERROR")
                    if downloaded_file.exists():
                        downloaded_file.unlink()
                    raise
                time.sleep(2 ** attempt)

class EnhancedNOAAProcessor:
    """Enhanced processor with volume selection and series type support"""
    
    def __init__(self, logger: Optional[ProcessingLogger] = None):
        self.logger = logger
    
    def find_noaa_zones_by_volume(self, volume_codes: List[str], states_shp_path: str) -> List[str]:
        """Find zones by specific volume codes or numbers"""
        if self.logger:
            self.logger.log_operation("Zone Detection", "START", f"Volumes: {volume_codes}")
        
        try:
            with warnings.catch_warnings():
                warnings.filterwarnings('ignore', category=UserWarning)
                states_shp = gpd.read_file(states_shp_path)
            
            # Convert volume codes/numbers to actual NOAA zone codes
            zone_list = []
            for volume_input in volume_codes:
                # Check if input is a volume number
                try:
                    volume_num = int(volume_input)
                    # Find volume by number
                    matching_volumes = [k for k, v in Config.ATLAS14_VOLUMES.items() if v['volume'] == volume_num]
                    if matching_volumes:
                        volume_key = matching_volumes[0]
                        actual_zone_code = Config.ATLAS14_VOLUMES[volume_key]['code']
                        zone_list.append(actual_zone_code)
                    else:
                        logging.warning(f"Volume number {volume_num} not found")
                except ValueError:
                    # Input is a volume code, convert to actual zone code
                    if volume_input in Config.ATLAS14_VOLUMES:
                        actual_zone_code = Config.ATLAS14_VOLUMES[volume_input]['code']
                        zone_list.append(actual_zone_code)
                    else:
                        logging.warning(f"Volume code {volume_input} not found")
            
            # Remove duplicates
            zone_list = list(set([z for z in zone_list if z != "Atlas2"]))
            
            if self.logger:
                self.logger.log_operation("Zone Detection", "SUCCESS", f"Found zones: {zone_list}")
            
            return zone_list
            
        except Exception as e:
            error_msg = f"Error in volume-based zone detection: {e}"
            logging.error(error_msg)
            if self.logger:
                self.logger.log_operation("Zone Detection", "ERROR", error_msg)
            raise
    
    @staticmethod
    def find_noaa_zones_by_aoi(prj_area_shp_path: str, states_shp_path: str, logger: Optional[ProcessingLogger] = None) -> List[str]:
        """Find intersecting NOAA zones with improved error handling and CRS standardization"""
        if logger:
            logger.log_operation("AOI Zone Detection", "START", f"Project area: {Path(prj_area_shp_path).name}")
        
        try:
            with warnings.catch_warnings():
                warnings.filterwarnings('ignore', category=UserWarning)
                states_shp = gpd.read_file(states_shp_path)
                prj_area_shp = gpd.read_file(prj_area_shp_path)
        except Exception as e:
            error_msg = f"Error reading shapefiles: {e}"
            logging.error(error_msg)
            if logger:
                logger.log_operation("AOI Zone Detection", "ERROR", error_msg)
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
        zone_list = [z for z in zone_list if z != "Atlas2"]
        
        logging.info(f"Found intersecting NOAA zones: {zone_list}")
        
        if logger:
            logger.log_operation("AOI Zone Detection", "SUCCESS", f"Found zones: {zone_list}")
        
        return zone_list

    @staticmethod
    def mosaic_list_of_rasters(raster_list: List[str], event: str, dur: str, series_type: str = 'PDS', CI: str = '') -> None:
        """Enhanced mosaic function with series type support"""
        # AMS files use '_ams' suffix, PDS files use standard 'a'
        mosaic_folder = Path(os.path.dirname(raster_list[0])) / '..' / f'NOAA_grids_mosaic_{series_type}'
        mosaic_folder.mkdir(parents=True, exist_ok=True)

        # Enhanced pattern matching for both PDS and AMS
        if series_type == 'AMS':
            if CI:  # Confidence interval files
                expected_pattern = rf"^[a-zA-Z]+{event}yr{dur}a{CI}_ams\.asc$"
            else:  # Main files
                expected_pattern = rf"^[a-zA-Z]+{event}yr{dur}a_ams\.asc$"
        else:  # PDS
            expected_pattern = rf"^[a-zA-Z]+{event}yr{dur}a{CI}\.asc$"
        
        # Log the pattern being used for debugging
        logging.info(f"Mosaic validation pattern for {series_type} (CI='{CI}'): {expected_pattern}")
        logging.info(f"Files being validated: {[Path(f).name for f in raster_list]}")
            
        if not all(re.match(expected_pattern, Path(f).name) for f in raster_list):
            failed_files = [Path(f).name for f in raster_list if not re.match(expected_pattern, Path(f).name)]
            raise ValueError(
                f"Unexpected file pattern in raster list for event={event}, duration={dur}, series={series_type}, CI={CI}. "
                f"Expected pattern: {expected_pattern}. Failed files: {failed_files}"
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

                # Output naming: add '_ams' suffix for AMS, keep standard for PDS
                if series_type == 'AMS':
                    if CI:  # Confidence interval files
                        output_name = f"comb{event}yr{dur}a{CI}_ams.asc"
                    else:  # Main files
                        output_name = f"comb{event}yr{dur}a_ams.asc"
                else:  # PDS
                    output_name = f"comb{event}yr{dur}a{CI}.asc"
                    
                logging.info(f"Creating mosaic output: {output_name}")
                    
                with rasterio.open(mosaic_folder / output_name, 'w', **meta) as dst:
                    dst.write(mosaic)

            finally:
                for src in sources:
                    src.close()

    @staticmethod
    def compute_1pct_plus_and_minus(path_to_100yr: str, path_to_100yr_upper: str, 
                                  path_to_100yr_lower: str, series_type: str = 'PDS') -> None:
        """Enhanced confidence interval computation with series type support"""
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

                # Save results with proper naming for series type
                filename_100yr = Path(path_to_100yr).stem
                folder = Path(path_to_100yr).parent
                out_meta.update({"nodata": np.nan})

                # Generate proper output names based on series type
                if series_type == 'AMS' and '_ams' in filename_100yr:
                    # For AMS: comb100yr24ha_ams -> comb100yr24ha_ams_plus.asc
                    base_name = filename_100yr  # Already contains _ams
                    plus_name = f"{base_name}_plus.asc"
                    minus_name = f"{base_name}_minus.asc"
                elif series_type == 'PDS':
                    # For PDS: comb100yr24ha -> comb100yr24ha_plus.asc
                    plus_name = f"{filename_100yr}_plus.asc"
                    minus_name = f"{filename_100yr}_minus.asc"
                else:
                    # Fallback
                    plus_name = f"{filename_100yr}_plus.asc"
                    minus_name = f"{filename_100yr}_minus.asc"

                # Write output files
                plus_path = folder / plus_name
                minus_path = folder / minus_name
                
                with rasterio.open(plus_path, "w", **out_meta) as dest:
                    dest.write(np.around(p_1pct_plus * 1000, 0).astype(np.float32), 1)
                
                with rasterio.open(minus_path, "w", **out_meta) as dest:
                    dest.write(np.around(p_1pct_minus * 1000, 0).astype(np.float32), 1)

        except Exception as e:
            logging.error(f"Error in confidence interval computation for {series_type}: {e}")
            raise

class EnhancedNOAAGrids:
    """Main enhanced class for NOAA grid operations"""
    
    def __init__(self, config: Optional[Config] = None):
        self.config = config or Config()
        self.logger = ProcessingLogger()
        self.downloader = EnhancedNOAADownloader(self.config, self.logger)
        self.processor = EnhancedNOAAProcessor(self.logger)

    def process_grids(self, base_dir: str, prj_area_shp_path: Optional[str] = None, 
                     states_shp_path: str = None, volume_codes: Optional[List[str]] = None,
                     event_list: List[str] = None, dur_list: List[str] = None, 
                     series_types: List[str] = ['PDS'], CI_100yr: bool = True, inputs: Dict = None) -> None:
        """Enhanced main processing function with volume selection and series types"""
        try:
            # Log configuration
            config_dict = {
                'Base Directory': base_dir,
                'Project Area Shapefile': prj_area_shp_path or 'Volume-based selection',
                'Volume Codes': volume_codes or 'AOI-based detection',
                'Series Types': series_types,
                'Events': event_list,
                'Durations': dur_list,
                'Confidence Intervals (100-yr)': CI_100yr
            }
            self.logger.log_config(config_dict)
            
            # Validate inputs
            if not set(event_list).issubset(self.config.VALID_EVENTS):
                raise ValueError(f"Invalid events. Valid options are: {self.config.VALID_EVENTS}")
            if not set(dur_list).issubset(self.config.VALID_DURATIONS):
                raise ValueError(f"Invalid durations. Valid options are: {self.config.VALID_DURATIONS}")
            if not set(series_types).issubset(self.config.SERIES_TYPES):
                raise ValueError(f"Invalid series types. Valid options are: {self.config.SERIES_TYPES}")

            base_dir = Path(base_dir)
            
            # Determine zones based on input method
            if volume_codes:
                zones = self.processor.find_noaa_zones_by_volume(volume_codes, states_shp_path)
            elif prj_area_shp_path:
                zones = self.processor.find_noaa_zones_by_aoi(prj_area_shp_path, states_shp_path, self.logger)
            else:
                raise ValueError("Either volume_codes or prj_area_shp_path must be provided")
            
            # Process each series type
            for series_type in series_types:
                if series_type == 'BOTH':
                    actual_series = ['PDS', 'AMS']
                else:
                    actual_series = [series_type]
                
                for series in actual_series:
                    self.logger.log_operation(f"Processing {series} Series", "START", f"Zones: {zones}")
                    
                    self.get_noaa_grids(base_dir, zones, event_list, dur_list, series, CI_100yr)
                    
                    if len(zones) > 1:
                        self.combine_multiple_zones(base_dir, event_list, dur_list, series)
                        grids_folder = base_dir / f'NOAA_grids_mosaic_{series}'
                    else:
                        grids_folder = base_dir / f'NOAA_grids_{series}'

                    if '100' in event_list and CI_100yr:
                        self.process_confidence_intervals(grids_folder, dur_list, series)
                    
                    self.logger.log_operation(f"Processing {series} Series", "SUCCESS", f"Output: {grids_folder}")

        except Exception as e:
            error_msg = f"Error in grid processing: {e}"
            logging.error(error_msg)
            self.logger.log_operation("Grid Processing", "ERROR", error_msg)
            raise
        finally:
            self.logger.generate_summary()
            # Write QA/QC summary to base directory
            config_dict['Base Directory'] = str(base_dir)  # Ensure base_dir is string for logging
            self.logger.write_qa_summary(base_dir, config_dict, inputs.get("calculate_stats", False))

    def get_noaa_grids(self, base_dir: Path, zone_list: List[str], 
                       event_list: List[str], dur_list: List[str], 
                       series_type: str = 'PDS', CI_100yr: bool = True) -> List[str]:
        """Enhanced grid download with series type support"""
        grids_folder = base_dir / f'NOAA_grids_{series_type}'
        grids_folder.mkdir(parents=True, exist_ok=True)

        self.logger.log_operation(f"Download {series_type} Grids", "START", f"Zones: {zone_list}")

        file_tasks = []
        
        for zone in zone_list:
            for event in event_list:
                for duration in dur_list:
                    base_pattern = f"{zone}{event}yr{duration}a"
                    file_tasks.append((zone, f"{base_pattern}.zip", str(grids_folder), series_type))
                    
                    if event == '100' and CI_100yr:
                        file_tasks.extend([
                            (zone, f"{base_pattern}u.zip", str(grids_folder), series_type),
                            (zone, f"{base_pattern}l.zip", str(grids_folder), series_type)
                        ])

        with ThreadPoolExecutor(max_workers=4) as executor:
            list(tqdm(executor.map(self.downloader.download_and_unzip_noaa_grid, file_tasks), 
                     total=len(file_tasks), desc=f"Downloading {series_type} grids"))

        self.logger.log_operation(f"Download {series_type} Grids", "SUCCESS", f"Files: {len(file_tasks)}")
        return zone_list

    def combine_multiple_zones(self, base_dir: Path, event_list: List[str], dur_list: List[str], series_type: str = 'PDS') -> None:
        """Enhanced zone combination with series type support"""
        tasks = []
        grids_folder = base_dir / f'NOAA_grids_{series_type}'

        self.logger.log_operation(f"Mosaic {series_type} Grids", "START", "Combining multiple zones")

        for e in event_list:
            for d in dur_list:
                # Pattern matching for PDS vs AMS files
                if series_type == 'AMS':
                    pattern = f"*{e}yr{d}a_ams.asc"
                    pattern_regex = rf"^[a-zA-Z]+{e}yr{d}a_ams\.asc$"
                else:
                    pattern = f"*{e}yr{d}a.asc"
                    pattern_regex = rf"^[a-zA-Z]+{e}yr{d}a\.asc$"
                
                rasters = [
                    f for f in grids_folder.glob(pattern)
                    if re.search(pattern_regex, f.name)
                ]

                if len(rasters) > 1:
                    tasks.append(([str(r) for r in rasters], e, d, series_type, ''))

                # Confidence intervals (u and l)
                if e == '100':
                    for ci in ['u', 'l']:
                        if series_type == 'AMS':
                            # AMS confidence intervals: mw100yr24hal_ams.asc, mw100yr24hau_ams.asc
                            ci_pattern = f"*{e}yr{d}a{ci}_ams.asc"
                            ci_regex = rf"^[a-zA-Z]+{e}yr{d}a{ci}_ams\.asc$"
                        else:
                            # PDS confidence intervals: mw100yr24hal.asc, mw100yr24hau.asc
                            ci_pattern = f"*{e}yr{d}a{ci}.asc"
                            ci_regex = rf"^[a-zA-Z]+{e}yr{d}a{ci}\.asc$"
                        
                        ci_rasters = [
                            f for f in grids_folder.glob(ci_pattern)
                            if re.search(ci_regex, f.name)
                        ]

                        logging.info(f"Looking for {series_type} CI files with pattern: {ci_pattern}")
                        logging.info(f"Found {len(ci_rasters)} CI files: {[f.name for f in ci_rasters]}")

                        if len(ci_rasters) > 1:
                            tasks.append(([str(r) for r in ci_rasters], e, d, series_type, ci))
                            logging.info(f"Added {series_type} CI mosaic task for {ci}: {len(ci_rasters)} files")
                        else:
                            logging.warning(f"Not enough {series_type} CI files for {ci} (found {len(ci_rasters)}, need >1)")

        with ThreadPoolExecutor(max_workers=os.cpu_count()) as executor:
            futures = []
            for rasters, e, d, series, ci in tasks:
                futures.append(
                    executor.submit(self.processor.mosaic_list_of_rasters, rasters, e, d, series, ci)
                )

            for future in tqdm(futures, desc=f"Mosaicking {series_type} grids"):
                future.result()

        self.logger.log_operation(f"Mosaic {series_type} Grids", "SUCCESS", f"Tasks: {len(tasks)}")

    def process_confidence_intervals(self, grids_folder: Path, dur_list: List[str], series_type: str = 'PDS') -> None:
        """Enhanced confidence interval processing with series type support"""
        self.logger.log_operation(f"Confidence Intervals ({series_type})", "START", "Computing 1% plus/minus grids")
        
        for dur in tqdm(dur_list, desc=f"Processing {series_type} confidence intervals"):
            try:
                if series_type == 'AMS':
                    # For AMS files: look for comb100yr24ha_ams.asc, comb100yr24hal_ams.asc, comb100yr24hau_ams.asc
                    base_pattern = f"*100yr{dur}a_ams.asc"
                    upper_pattern = f"*100yr{dur}au_ams.asc"
                    lower_pattern = f"*100yr{dur}al_ams.asc"
                    
                    # Debug: List all files to see what's actually there
                    all_files = list(grids_folder.glob("*.asc"))
                    logging.info(f"Available files in {grids_folder}: {[f.name for f in all_files]}")
                    
                else:
                    # For PDS files: look for comb100yr24ha.asc, comb100yr24hal.asc, comb100yr24hau.asc
                    base_pattern = f"*100yr{dur}a.asc"
                    upper_pattern = f"*100yr{dur}au.asc"
                    lower_pattern = f"*100yr{dur}al.asc"
                
                logging.info(f"Looking for {series_type} confidence interval files:")
                logging.info(f"  Base pattern: {base_pattern}")
                logging.info(f"  Upper pattern: {upper_pattern}")
                logging.info(f"  Lower pattern: {lower_pattern}")
                
                base_files = list(grids_folder.glob(base_pattern))
                upper_files = list(grids_folder.glob(upper_pattern))
                lower_files = list(grids_folder.glob(lower_pattern))
                
                logging.info(f"Found files - Base: {base_files}, Upper: {upper_files}, Lower: {lower_files}")
                
                if not base_files:
                    logging.warning(f"No base file found for pattern {base_pattern}")
                    continue
                if not upper_files:
                    logging.warning(f"No upper file found for pattern {upper_pattern}")
                    continue
                if not lower_files:
                    logging.warning(f"No lower file found for pattern {lower_pattern}")
                    continue
                
                base = base_files[0]
                upper = upper_files[0]
                lower = lower_files[0]
                
                logging.info(f"Processing confidence intervals for {series_type}:")
                logging.info(f"  Base: {base.name}")
                logging.info(f"  Upper: {upper.name}")
                logging.info(f"  Lower: {lower.name}")
                
                self.processor.compute_1pct_plus_and_minus(
                    str(base), str(upper), str(lower), series_type)
                    
                self.logger.log_operation(f"CI Processing {dur}", "SUCCESS", f"{series_type} confidence intervals calculated")
                    
            except StopIteration:
                warning_msg = f"Missing confidence interval files for duration {dur} in {series_type}"
                logging.warning(warning_msg)
                self.logger.log_operation(f"CI Processing {dur}", "WARNING", warning_msg)
            except IndexError:
                warning_msg = f"Missing confidence interval files for duration {dur} in {series_type}"
                logging.warning(warning_msg)
                self.logger.log_operation(f"CI Processing {dur}", "WARNING", warning_msg)
            except Exception as e:
                error_msg = f"Error processing confidence intervals for duration {dur} in {series_type}: {e}"
                logging.error(error_msg)
                self.logger.log_operation(f"CI Processing {dur}", "ERROR", error_msg)

def get_enhanced_user_input() -> Dict[str, any]:
    """Enhanced user input collection with new options"""
    print("\n" + "="*80)
    print("ENHANCED NOAA GRIDS AUTOMATION SCRIPT!")
    print("="*80 + "\n")

    # 1. Base Directory
    print("--- Step 1: Base Directory Configuration ---")
    base_dir = Path(input(
        "Enter the Base Directory where all data will be stored:\n"
        "Example: D:/Projects/NOAA/Precipitation\n"
        "> "
    ).strip('"').strip("'"))
    base_dir.mkdir(parents=True, exist_ok=True)

    # 2. AOI Input Method Selection
    print("\n--- Step 2: Area of Interest (AOI) Definition ---")
    print("Choose AOI definition method:")
    print("1. Upload custom project area shapefile")
    print("2. Select specific NOAA Atlas 14 volume(s)")
    
    aoi_method = input("Enter choice (1 or 2): ").strip()
    
    prj_area_shp_path = None
    volume_codes = None
    
    if aoi_method == "1":
        # Custom shapefile method
        prj_area_shp_path = Path(input(
            "Enter the path to your Project Area Shapefile (.shp):\n"
            "Example: D:/Projects/NOAA/project_area.shp\n"
            "> "
        ).strip('"').strip("'"))
        if not prj_area_shp_path.is_file():
            raise FileNotFoundError(f"Project Area Shapefile not found at '{prj_area_shp_path}'")
    
    elif aoi_method == "2":
        # Volume selection method
        print("\nAvailable NOAA Atlas 14 Volumes:")
        print("Volume | Code | Name                                    | Coverage")
        print("-" * 80)
        for code, info in Config.ATLAS14_VOLUMES.items():
            print(f"  {info['volume']:2d}   | {code:4s} | {info['name']:38s} | {info['description']}")
        
        volume_input = input(
            "\nEnter volume codes or numbers separated by spaces (e.g., 'se ne' or '9 10' or 'se 10'):\n"
            "> "
        ).strip().split()
        
        # Validate volume codes and numbers
        invalid_inputs = []
        for vol_input in volume_input:
            try:
                # Check if it's a valid volume number
                vol_num = int(vol_input)
                if not any(info['volume'] == vol_num for info in Config.ATLAS14_VOLUMES.values()):
                    invalid_inputs.append(vol_input)
            except ValueError:
                # Check if it's a valid volume code
                if vol_input not in Config.ATLAS14_VOLUMES:
                    invalid_inputs.append(vol_input)
        
        if invalid_inputs:
            raise ValueError(f"Invalid volume codes/numbers: {invalid_inputs}")
        volume_codes = volume_input
    
    else:
        raise ValueError("Invalid choice. Please enter 1 or 2.")

    # 3. NOAA Zones Shapefile
    print("\n--- Step 3: NOAA Atlas 14 Zones Shapefile ---")
    use_builtin = input("Use built-in NOAA zones shapefile? (y/n) [default: y]: ").strip().lower()
    
    if use_builtin in ['', 'y', 'yes']:
        # Use built-in shapefile
        current_dir = Path(__file__).parent
        states_shp_path = current_dir / "support_data" / "US_States" / "tl_2021_us_state.shp"
        if not states_shp_path.exists():
            raise FileNotFoundError(f"Built-in NOAA zones shapefile not found at: {states_shp_path}")
    else:
        states_shp_path = Path(input(
            "Enter the path to the NOAA Atlas 14 Zones Shapefile (.shp):\n"
            "Example: C:/Data/NOAA_Zones/tl_2021_us_state.shp\n"
            "> "
        ).strip('"').strip("'"))
        if not states_shp_path.is_file():
            raise FileNotFoundError(f"NOAA Atlas 14 Zones Shapefile not found at '{states_shp_path}'")

    # 4. Duration Series Selection
    print("\n--- Step 4: Duration Series Selection ---")
    print("Available series types:")
    print("  PDS: Partial Duration Series")
    print("  AMS: Annual Maximum Series")
    print("  BOTH: Both PDS and AMS")
    
    series_input = input("Enter series type (PDS/AMS/BOTH) [default: PDS]: ").strip().upper()
    if series_input == '':
        series_input = 'PDS'
    
    if series_input not in Config.SERIES_TYPES:
        raise ValueError(f"Invalid series type. Valid options: {Config.SERIES_TYPES}")
    
    series_types = [series_input]

    # 5. Event Selection
    print("\n--- Step 5: Average Recurrence Interval (ARI) Selection ---")
    print("Available Recurrence Intervals (years):")
    events_display = "all, " + ', '.join(sorted(Config.VALID_EVENTS, key=int))
    print(f"  {events_display}")
    event_input = input("Enter desired intervals separated by spaces (or 'all') [default: all]: ").strip().lower()
    if event_input == '' or event_input == 'all':
        event_list = list(Config.VALID_EVENTS)
    else:
        event_list = event_input.split()
        if not set(event_list).issubset(Config.VALID_EVENTS):
            raise ValueError(f"Invalid recurrence intervals. Valid options: {Config.VALID_EVENTS}")

    # 6. Duration Selection
    print("\n--- Step 6: Storm Duration Selection ---")
    print("Available Precipitation Durations:")
    durations_display = "all, " + ', '.join(sorted(Config.VALID_DURATIONS))
    print(f"  {durations_display}")
    dur_input = input("Enter desired durations separated by spaces (or 'all') [default: all]: ").strip().lower()
    if dur_input == '' or dur_input == 'all':
        dur_list = list(Config.VALID_DURATIONS)
    else:
        dur_list = dur_input.split()
        if not set(dur_list).issubset(Config.VALID_DURATIONS):
            raise ValueError(f"Invalid durations. Valid options: {Config.VALID_DURATIONS}")

    # 7. Confidence Interval Option
    print("\n--- Step 7: Confidence Interval Configuration ---")
    ci_input = input(
        "Download 90% confidence interval grids for 100-year event? (y/n) [default: y]: "
    ).strip().lower()
    CI_100yr = ci_input in ['', 'y', 'yes']

    # 8. Logging and Statistics Options
    print("\n--- Step 8: Processing Options ---")
    verbose = input("Enable detailed logging? (y/n) [default: y]: ").strip().lower()
    verbose = verbose in ['', 'y', 'yes']
    
    calculate_stats = input("Calculate basic statistics for all output rasters? (y/n) [default: n]: ").strip().lower()
    calculate_stats = calculate_stats in ['y', 'yes']

    return {
        "base_dir": base_dir,
        "prj_area_shp_path": prj_area_shp_path,
        "volume_codes": volume_codes,
        "states_shp_path": states_shp_path,
        "series_types": series_types,
        "event_list": event_list,
        "dur_list": dur_list,
        "CI_100yr": CI_100yr,
        "verbose": verbose,
        "calculate_stats": calculate_stats
    }

def display_volume_diagram():
    """Display NOAA Atlas 14 volume information"""
    print("\n" + "="*80)
    print("NOAA ATLAS 14 PRECIPITATION FREQUENCY VOLUMES")
    print("="*80)
    print("Volume | Code | Name                                    | Coverage")
    print("-" * 80)
    for code, info in Config.ATLAS14_VOLUMES.items():
        print(f"  {info['volume']:2d}   | {code:4s} | {info['name']:38s} | {info['description']}")
    print("="*80)

def validate_ascii_availability(base_dir: Path, zones: List[str], events: List[str], 
                               durations: List[str], series_types: List[str]) -> Dict[str, bool]:
    """Check if ASCII files are already available to skip processing"""
    availability = {}
    
    for series_type in series_types:
        if series_type == 'BOTH':
            check_series = ['PDS', 'AMS']
        else:
            check_series = [series_type]
        
        for series in check_series:
            grids_folder = base_dir / f'NOAA_grids_{series}'
            
            all_files_exist = True
            for zone in zones:
                for event in events:
                    for duration in durations:
                        if series == 'AMS':
                            expected_file = grids_folder / f"{zone}{event}yr{duration}a_ams.asc"
                        else:
                            expected_file = grids_folder / f"{zone}{event}yr{duration}a.asc"
                        
                        if not expected_file.exists():
                            all_files_exist = False
                            break
                    if not all_files_exist:
                        break
                if not all_files_exist:
                    break
            
            availability[f"{series}_complete"] = all_files_exist
    
    return availability

def main():
    """Enhanced main entry point with improved error handling and new features"""
    try:
        # Display volume information
        display_volume_diagram()
        
        # Setup logging first
        setup_logging("noaa_processing.log", verbose=True)
        start_time = time.time()
        
        # Get user inputs
        inputs = get_enhanced_user_input()
        
        # Setup detailed logging based on user preference
        log_file_path = inputs["base_dir"] / "noaa_processing.log"
        setup_logging(str(log_file_path), verbose=inputs["verbose"])
        
        # Check for existing ASCII files
        if inputs.get("prj_area_shp_path"):
            # For AOI-based processing, we need to detect zones first
            temp_processor = EnhancedNOAAProcessor()
            zones = temp_processor.find_noaa_zones_by_aoi(
                str(inputs["prj_area_shp_path"]), 
                str(inputs["states_shp_path"])
            )
        else:
            # For volume-based processing, we know the zones
            temp_processor = EnhancedNOAAProcessor()
            zones = temp_processor.find_noaa_zones_by_volume(
                inputs["volume_codes"], 
                str(inputs["states_shp_path"])
            )
        
        # Check ASCII availability
        ascii_status = validate_ascii_availability(
            inputs["base_dir"], zones, inputs["event_list"], 
            inputs["dur_list"], inputs["series_types"]
        )
        
        # Report ASCII availability
        print("\n--- ASCII File Availability Check ---")
        for series_key, available in ascii_status.items():
            series_name = series_key.replace('_complete', '')
            status = "✓ Available" if available else "✗ Need to download"
            print(f"{series_name}: {status}")
        
        # Ask user if they want to skip download for available files
        skip_available = False
        if any(ascii_status.values()):
            skip_input = input("\nSkip processing for available ASCII files? (y/n) [default: n]: ").strip().lower()
            skip_available = skip_input in ['y', 'yes']
        
        if skip_available:
            print("Skipping download for available files...")
            # Filter series types to only process missing ones
            filtered_series = []
            for series_type in inputs["series_types"]:
                if series_type == 'BOTH':
                    if not ascii_status.get('PDS_complete', False):
                        filtered_series.append('PDS')
                    if not ascii_status.get('AMS_complete', False):
                        filtered_series.append('AMS')
                else:
                    if not ascii_status.get(f'{series_type}_complete', False):
                        filtered_series.append(series_type)
            
            if not filtered_series:
                print("All requested files are available. Processing complete!")
                return
            
            inputs["series_types"] = filtered_series
        
        # Initialize and run enhanced processor
        processor = EnhancedNOAAGrids()
        processor.process_grids(
            base_dir=str(inputs["base_dir"]),
            prj_area_shp_path=str(inputs["prj_area_shp_path"]) if inputs["prj_area_shp_path"] else None,
            states_shp_path=str(inputs["states_shp_path"]),
            volume_codes=inputs["volume_codes"],
            event_list=inputs["event_list"],
            dur_list=inputs["dur_list"],
            series_types=inputs["series_types"],
            CI_100yr=inputs["CI_100yr"],
            inputs=inputs  # Pass the full inputs dict for access to calculate_stats
        )
        
        # Final summary
        elapsed_time = time.time() - start_time
        hours, rem = divmod(elapsed_time, 3600)
        minutes, seconds = divmod(rem, 60)
        
        print("\n" + "="*80)
        print("PROCESSING COMPLETED SUCCESSFULLY!")
        print("="*80)
        print(f"Total Processing Time: {int(hours)}h {int(minutes)}m {round(seconds, 2)}s")
        print(f"Output Location: {inputs['base_dir']}")
        
        # List output folders
        print("\nOutput Folders Created:")
        for series_type in inputs["series_types"]:
            if series_type == 'BOTH':
                for series in ['PDS', 'AMS']:
                    grids_folder = inputs["base_dir"] / f'NOAA_grids_{series}'
                    mosaic_folder = inputs["base_dir"] / f'NOAA_grids_mosaic_{series}'
                    if grids_folder.exists():
                        print(f"  - {grids_folder}")
                    if mosaic_folder.exists():
                        print(f"  - {mosaic_folder}")
            else:
                grids_folder = inputs["base_dir"] / f'NOAA_grids_{series_type}'
                mosaic_folder = inputs["base_dir"] / f'NOAA_grids_mosaic_{series_type}'
                if grids_folder.exists():
                    print(f"  - {grids_folder}")
                if mosaic_folder.exists():
                    print(f"  - {mosaic_folder}")
        
        print("="*80)
        
    except KeyboardInterrupt:
        print("\n\nProcessing interrupted by user.")
        logging.info("Processing interrupted by user.")
    except Exception as e:
        error_msg = f"Fatal error: {str(e)}"
        print(f"\nERROR: {error_msg}")
        logging.error(error_msg, exc_info=True)
        sys.exit(1)

if __name__ == '__main__':
    print("Enhanced NOAA Atlas 14 Grid Processor starting...")
    logging.info("Enhanced script initialized")
    main()
# Enhanced NOAA Atlas 14 GUI - With Proper Directory Structure
# Integrates with GridPrecipProcessor project structure
# Features enhanced volume coverage map and organized support files

import streamlit as st
from pathlib import Path
import os
import tempfile
import shutil
import logging
from typing import List, Optional, Dict, Any
import time
import json
import folium
from streamlit_folium import folium_static, st_folium
import plotly.express as px
import pandas as pd
from PIL import Image
import io
import base64

# Project Configuration
class ProjectConfig:
    """Centralized configuration for GridPrecipProcessor project"""
    
    def __init__(self):
        # Base paths
        self.PROJECT_ROOT = Path(__file__).parent
        self.SUPPORT_INFO = self.PROJECT_ROOT / "SupportInfo"
        
        # Part 1 paths
        self.PART1_SUPPORT = self.SUPPORT_INFO / "part1_supp"
        self.US_STATES_PATH = self.PART1_SUPPORT / "US_States" / "tl_2021_us_state.shp"
        self.PROJECT_AREA_PATH = self.PART1_SUPPORT / "Project_Area"
        self.VOLUME_MAP_IMAGE = self.PART1_SUPPORT / "noaa_atlas14_volumes.png"
        
        # Part 2 paths  
        self.PART2_SUPPORT = self.SUPPORT_INFO / "part2_supp"
        self.NRCS_DISTROS_PATH = self.PART2_SUPPORT / "NRCS_Distros.xlsx"
        self.WORK_AREA_PATH = self.PART2_SUPPORT / "WorkArea"
        self.CUSTOM_TEMPLATES = self.PART2_SUPPORT / "custom_templates"
        
        # Default output paths
        self.DEFAULT_LOGS = self.PROJECT_ROOT / "logs"
        self.DEFAULT_OUTPUT = self.PROJECT_ROOT / "output"
        
        # Create directories if they don't exist
        self._create_directories()
    
    def _create_directories(self):
        """Create necessary directories if they don't exist"""
        directories = [
            self.SUPPORT_INFO, self.PART1_SUPPORT, self.PART2_SUPPORT,
            self.PROJECT_AREA_PATH, self.CUSTOM_TEMPLATES,
            self.DEFAULT_LOGS, self.DEFAULT_OUTPUT
        ]
        
        for directory in directories:
            directory.mkdir(parents=True, exist_ok=True)

# Initialize project configuration
config = ProjectConfig()

# Import the enhanced NOAA processor
try:
    from NOAA_GridMiner import EnhancedNOAAGrids, Config
except ImportError as e:
    st.error("❌ Enhanced NOAA GridMiner script not found!")
    st.error("Please ensure NOAA_GridMiner.py is in the project root directory.")
    st.code(f"Import error details: {str(e)}", language="text")
    st.info(f"""
    **Expected project structure:**
    ```
    {config.PROJECT_ROOT}/
    ├── NOAA_GridMiner.py (Part 1)
    ├── ASCtoTimeSeriesTIFF.py (Part 2) 
    ├── TIFFtoDSS.py (Part 3)
    ├── enhanced_streamlit_noaa_ui.py (this GUI)
    └── SupportInfo/
        ├── part1_supp/
        └── part2_supp/
    ```
    """)
    st.stop()

# Configure logging for Streamlit
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def setup_page():
    """Configure Streamlit page with enhanced settings"""
    st.set_page_config(
        page_title="GridPrecipProcessor - NOAA Atlas 14 Toolkit",
        page_icon="🌧️",
        layout="wide",
        initial_sidebar_state="expanded"
    )
    
    # Custom CSS for better styling
    st.markdown("""
    <style>
    .main-header {
        font-size: 2.5rem;
        font-weight: bold;
        color: #1f77b4;
        text-align: center;
        margin-bottom: 1rem;
    }
    .sub-header {
        font-size: 1.2rem;
        color: #666;
        text-align: center;
        margin-bottom: 2rem;
    }
    .expandable-section {
        border: 1px solid #ddd;
        border-radius: 5px;
        padding: 10px;
        margin: 10px 0;
    }
    .log-section {
        background-color: #f8f9fa;
        border-left: 4px solid #007bff;
        padding: 10px;
        font-family: monospace;
        font-size: 12px;
        max-height: 400px;
        overflow-y: auto;
    }
    .volume-info {
        background-color: #f0f8ff;
        border: 1px solid #b0d4f1;
        border-radius: 5px;
        padding: 10px;
        margin: 5px 0;
    }
    </style>
    """, unsafe_allow_html=True)

class SessionManager:
    """Manage session state for multi-part workflow"""
    
    @staticmethod
    def initialize_session():
        """Initialize session state variables"""
        if 'current_tab' not in st.session_state:
            st.session_state.current_tab = 'Part 1: Grid Miner'
        if 'processing_logs' not in st.session_state:
            st.session_state.processing_logs = []
        if 'part1_completed' not in st.session_state:
            st.session_state.part1_completed = False
        if 'part1_output_dir' not in st.session_state:
            st.session_state.part1_output_dir = None
        if 'part2_completed' not in st.session_state:
            st.session_state.part2_completed = False
        if 'part2_output_dir' not in st.session_state:
            st.session_state.part2_output_dir = None
        if 'advanced_mode' not in st.session_state:
            st.session_state.advanced_mode = False
        if 'selected_volumes' not in st.session_state:
            st.session_state.selected_volumes = []
        if 'ref_img_expanded' not in st.session_state:
            st.session_state.ref_img_expanded = False

class LogHandler:
    """Handle real-time logging for GUI display"""
    
    def __init__(self):
        self.logs = []
    
    def add_log(self, level: str, message: str):
        """Add log entry with timestamp"""
        timestamp = time.strftime("%H:%M:%S")
        self.logs.append({
            'timestamp': timestamp,
            'level': level,
            'message': message
        })
        
        # Add to session state for persistence
        if 'processing_logs' not in st.session_state:
            st.session_state.processing_logs = []
        st.session_state.processing_logs.append({
            'timestamp': timestamp,
            'level': level,
            'message': message
        })
    
    def display_logs(self, container):
        """Display logs in a container"""
        if st.session_state.processing_logs:
            log_text = ""
            for log in st.session_state.processing_logs[-50:]:  # Show last 50 entries
                level_color = {
                    'INFO': '🔵',
                    'WARNING': '🟡', 
                    'ERROR': '🔴',
                    'SUCCESS': '🟢'
                }.get(log['level'], '⚪')
                log_text += f"{level_color} [{log['timestamp']}] {log['level']}: {log['message']}\n"
                
            container.text_area(
                "Processing Logs",
                value=log_text,
                height=300,
                key="log_display"
            )

class EnhancedMapVisualization:
    """Handle enhanced geospatial map visualizations with coverage areas"""
    
    @staticmethod
    def get_volume_boundaries():
        """Get approximate boundary coordinates for NOAA Atlas 14 volumes"""
        # These are approximate boundaries - in production, you'd use actual shapefiles
        volume_boundaries = {
            1: {  # Semiarid Southwest
                'name': 'Semiarid Southwest',
                'color': '#4285f4',
                'coordinates': [
                    [[31.0, -114.8], [37.0, -114.8], [42.0, -111.0], [42.0, -109.0], 
                     [37.0, -109.0], [31.0, -109.0], [31.0, -114.8]]
                ]
            },
            2: {  # Ohio River Basin
                'name': 'Ohio River Basin and Surrounding States',
                'color': '#34a853',
                'coordinates': [
                    [[36.5, -89.0], [42.0, -89.0], [42.0, -80.5], [36.5, -80.5], [36.5, -89.0]]
                ]
            },
            3: {  # Puerto Rico
                'name': 'Puerto Rico and U.S. Virgin Islands',
                'color': '#fbbc04',
                'coordinates': [
                    [[17.5, -67.5], [18.8, -67.5], [18.8, -64.5], [17.5, -64.5], [17.5, -67.5]]
                ]
            },
            4: {  # Hawaii
                'name': 'Hawaiian Islands',
                'color': '#ea4335',
                'coordinates': [
                    [[18.8, -161.0], [22.5, -161.0], [22.5, -154.5], [18.8, -154.5], [18.8, -161.0]]
                ]
            },
            6: {  # California
                'name': 'California',
                'color': '#9c27b0',
                'coordinates': [
                    [[32.5, -124.5], [42.0, -124.5], [42.0, -114.0], [32.5, -114.0], [32.5, -124.5]]
                ]
            },
            7: {  # Alaska
                'name': 'Alaska',
                'color': '#00bcd4',
                'coordinates': [
                    [[54.0, -165.0], [71.0, -165.0], [71.0, -130.0], [54.0, -130.0], [54.0, -165.0]]
                ]
            },
            8: {  # Midwestern States
                'name': 'Midwestern States',
                'color': '#795548',
                'coordinates': [
                    [[40.0, -97.5], [49.0, -97.5], [49.0, -82.0], [40.0, -82.0], [40.0, -97.5]]
                ]
            },
            9: {  # Southeastern States
                'name': 'Southeastern States',
                'color': '#ff9800',
                'coordinates': [
                    [[24.5, -87.5], [36.5, -87.5], [36.5, -75.5], [24.5, -75.5], [24.5, -87.5]]
                ]
            },
            10: {  # Northeastern States
                'name': 'Northeastern States',
                'color': '#607d8b',
                'coordinates': [
                    [[40.0, -80.0], [47.5, -80.0], [47.5, -66.9], [40.0, -66.9], [40.0, -80.0]]
                ]
            },
            11: {  # Texas
                'name': 'Texas',
                'color': '#e91e63',
                'coordinates': [
                    [[25.8, -106.6], [36.5, -106.6], [36.5, -93.5], [25.8, -93.5], [25.8, -106.6]]
                ]
            },
            12: {  # Interior Northwest
                'name': 'Interior Northwest',
                'color': '#8bc34a',
                'coordinates': [
                    [[42.0, -125.0], [49.0, -125.0], [49.0, -104.0], [42.0, -104.0], [42.0, -125.0]]
                ]
            }
        }
        return volume_boundaries
    
    @staticmethod
    def create_enhanced_volume_map():
        """Create interactive map showing NOAA Atlas 14 volume coverage areas"""
        # Create base map centered on continental US
        m = folium.Map(
            location=[39.8283, -98.5795],
            zoom_start=4,
            tiles='OpenStreetMap'
        )
        
        # Get volume boundaries
        volume_boundaries = EnhancedMapVisualization.get_volume_boundaries()
        
        # Add volume coverage areas
        for vol_num, vol_info in volume_boundaries.items():
            # Create polygon for volume coverage
            folium.Polygon(
                locations=[(coord[0], coord[1]) for coord in vol_info['coordinates'][0]],
                color=vol_info['color'],
                weight=2,
                fillColor=vol_info['color'],
                fillOpacity=0.3,
                popup=folium.Popup(
                    f"""
                    <div style='width:200px'>
                        <h4>Volume {vol_num}</h4>
                        <p><strong>{vol_info['name']}</strong></p>
                        <p>Click to select this volume for processing</p>
                    </div>
                    """,
                    max_width=250
                ),
                tooltip=f"Volume {vol_num}: {vol_info['name']}"
            ).add_to(m)
            
            # Add volume label at center
            center_lat = sum(coord[0] for coord in vol_info['coordinates'][0]) / len(vol_info['coordinates'][0])
            center_lon = sum(coord[1] for coord in vol_info['coordinates'][0]) / len(vol_info['coordinates'][0])
            
            folium.Marker(
                location=[center_lat, center_lon],
                popup=f"Volume {vol_num}",
                tooltip=f"Volume {vol_num}",
                icon=folium.DivIcon(
                    html=f"""
                    <div style='
                        background-color: white;
                        border: 2px solid {vol_info['color']};
                        border-radius: 50%;
                        width: 30px;
                        height: 30px;
                        display: flex;
                        justify-content: center;
                        align-items: center;
                        font-weight: bold;
                        font-size: 12px;
                        color: {vol_info['color']};
                    '>{vol_num}</div>
                    """,
                    icon_size=(30, 30),
                    icon_anchor=(15, 15)
                )
            ).add_to(m)
        
        # Add legend
        legend_html = """
        <div style='position: fixed; 
                    bottom: 50px; right: 50px; width: 200px; height: auto; 
                    background-color: white; border:2px solid grey; z-index:9999; 
                    font-size:14px; padding: 10px;
                    '>
        <h4>NOAA Atlas 14 Volumes</h4>
        """
        
        for vol_num, vol_info in volume_boundaries.items():
            legend_html += f"""
            <p><span style='color:{vol_info['color']}'>■</span> Volume {vol_num}: {vol_info['name'][:20]}...</p>
            """
        
        legend_html += "</div>"
        m.get_root().html.add_child(folium.Element(legend_html))
        
        return m
    
    @staticmethod
    def create_volume_map():
        """Create original interactive map with pin markers for NOAA Atlas 14 volumes"""
        # Create base map centered on continental US
        m = folium.Map(
            location=[39.8283, -98.5795],
            zoom_start=4,
            tiles='OpenStreetMap'
        )
        
        # Volume center coordinates and info (original pin-based approach)
        volume_info = {
            1: {'name': 'Semiarid Southwest', 'color': 'blue', 'coords': [34.0, -112.0]},
            2: {'name': 'Ohio River Basin and Surrounding States', 'color': 'lightblue', 'coords': [38.0, -85.0]},
            3: {'name': 'Puerto Rico and U.S. Virgin Islands', 'color': 'green', 'coords': [18.2, -66.4]},
            4: {'name': 'Hawaiian Islands', 'color': 'pink', 'coords': [20.0, -157.0]},
            6: {'name': 'California', 'color': 'purple', 'coords': [36.7, -119.7]},
            7: {'name': 'Alaska', 'color': 'darkblue', 'coords': [64.0, -153.0]},
            8: {'name': 'Midwestern States', 'color': 'brown', 'coords': [42.0, -93.0]},
            9: {'name': 'Southeastern States', 'color': 'orange', 'coords': [32.0, -83.0]},
            10: {'name': 'Northeastern States', 'color': 'yellow', 'coords': [44.0, -71.0]},
            11: {'name': 'Texas', 'color': 'red', 'coords': [31.0, -100.0]},
            12: {'name': 'Interior Northwest', 'color': 'lightgreen', 'coords': [46.0, -114.0]}
        }
        
        # Add volume markers (original pin approach)
        for vol_num, info in volume_info.items():
            folium.Marker(
                location=info['coords'],
                popup=f"Volume {vol_num}: {info['name']}",
                tooltip=f"Volume {vol_num}",
                icon=folium.Icon(color=info['color'], icon='info-sign')
            ).add_to(m)
        
        return m
    
    @staticmethod  
    def display_reference_image():
        """Display built-in reference image for NOAA volumes"""
        if config.VOLUME_MAP_IMAGE.exists():
            try:
                image = Image.open(config.VOLUME_MAP_IMAGE)
                st.image(image, caption="NOAA Atlas 14 Volume Coverage Map", use_column_width=True)
                return True
            except Exception as e:
                st.warning(f"Could not load reference image: {e}")
                return False
        else:
            # Create placeholder if image doesn't exist
            st.info("📷 Reference image not found. You can add 'noaa_atlas14_volumes.png' to SupportInfo/part1_supp/")
            return False
    
    @staticmethod
    def display_uploaded_reference(uploaded_image):
        """Display user-uploaded reference image"""
        if uploaded_image is not None:
            try:
                image = Image.open(uploaded_image)
                st.image(image, caption="Custom Reference Map/Image", use_container_width=True)
                
                # Option to save as default (future enhancement)
                with st.expander("🗺️ Image Information"):
                    st.write(f"**Filename:** {uploaded_image.name}")
                    st.write(f"**Size:** {image.size}")
                    st.write(f"**Format:** {image.format}")
                    
            except Exception as e:
                st.error(f"Error displaying image: {e}")

def find_builtin_shapefile(folder_path):
    """Find a shapefile in a built-in folder"""
    if not folder_path.exists():
        return None
    
    # Find shapefile in folder
    shp_files = list(folder_path.glob("*.shp"))
    if not shp_files:
        return None
        
    return str(shp_files[0])

def copy_files_to_single_dir(uploaded_files, label="shapefile") -> Optional[str]:
    """Copy all shapefile components to a single temporary directory"""
    if not uploaded_files:
        return None
    
    # Create a temporary directory
    temp_dir = tempfile.mkdtemp(prefix=f"{label}_")
    logger.info(f"Created temporary directory for {label}: {temp_dir}")
    
    # Copy files to temp directory
    for uploaded_file in uploaded_files:
        filename = uploaded_file.name
        file_path = os.path.join(temp_dir, filename)
        
        with open(file_path, "wb") as f:
            f.write(uploaded_file.getbuffer())
        logger.info(f"Saved {filename} to {file_path}")
    
    # Find .shp file
    shp_files = list(Path(temp_dir).glob("*.shp"))
    if not shp_files:
        shutil.rmtree(temp_dir)
        return None
    
    return str(shp_files[0])

def part1_grid_miner_tab():
    """Enhanced Part 1: NOAA Grid Miner interface with proper directory structure"""
    st.markdown('<div class="main-header">Part 1: NOAA Atlas 14 Grid Miner</div>', unsafe_allow_html=True)
    st.markdown('<div class="sub-header">Download and process NOAA precipitation grids for your project area</div>', unsafe_allow_html=True)
    
    # Initialize log handler
    log_handler = LogHandler()
    
    # Create columns for main content and logging
    main_col, log_col = st.columns([3, 2])
    
    with main_col:
        # Basic/Advanced mode toggle
        col1, col2 = st.columns([1, 4])
        with col1:
            st.session_state.advanced_mode = st.toggle(
                "Advanced Mode", 
                value=st.session_state.advanced_mode,
                help="Show advanced configuration options"
            )
        
        # Base Directory Configuration
        with st.expander("📁 **Base Directory Configuration**", expanded=True):
            # Default to project output directory
            default_base_dir = str(config.DEFAULT_OUTPUT)
            base_dir = st.text_input(
                "Base Directory",
                value=default_base_dir,
                help="Directory where all output data will be stored",
                placeholder="C:/Projects/NOAA/Precipitation"
            )
            
            if base_dir:
                try:
                    Path(base_dir).mkdir(parents=True, exist_ok=True)
                    st.success(f"✅ Directory ready: {base_dir}")
                except Exception as e:
                    st.error(f"❌ Cannot create directory: {e}")
        
        # Area of Interest Configuration
        with st.expander("🗺️ **Area of Interest Configuration**", expanded=True):
            aoi_method = st.radio(
                "Select method to define your area of interest:",
                ["Upload Project Area Shapefile", "Select NOAA Atlas 14 Volume(s)", "Use Sample Project Area"],
                help="Choose how you want to define the geographic area for analysis"
            )
            
            prj_area_shp_path = None
            volume_codes = None
            
            if aoi_method == "Upload Project Area Shapefile":
                col1, col2 = st.columns([3, 1])
                with col1:
                    prj_area_files = st.file_uploader(
                        "Upload ALL shapefile components (.shp, .shx, .dbf, .prj required)",
                        type=["shp", "shx", "dbf", "prj"],
                        accept_multiple_files=True,
                        help="Upload all components of your project area shapefile"
                    )
                
                with col2:
                    # Reference image upload
                    st.markdown("**Reference Map/Image**")
                    reference_image = st.file_uploader(
                        "Upload reference image",
                        type=["png", "jpg", "jpeg", "tiff", "pdf"],
                        help="Optional reference map or image for context"
                    )
                    
                if reference_image:
                    EnhancedMapVisualization.display_uploaded_reference(reference_image)
                
                if prj_area_files:
                    prj_area_shp_path = copy_files_to_single_dir(prj_area_files, "project_area")
                    if prj_area_shp_path:
                        st.success(f"✅ Project area shapefile ready: {Path(prj_area_shp_path).name}")
                    else:
                        st.error("❌ Missing .shp file in upload")
            
            elif aoi_method == "Select NOAA Atlas 14 Volume(s)":
                col1, col2 = st.columns([1, 1])
                
                with col1:
                    st.markdown("**Available NOAA Atlas 14 Volumes:**")
                    
                    # Create volume selection with enhanced info
                    volume_info_dict = EnhancedMapVisualization.get_volume_boundaries()
                    
                    selected_volumes = []
                    for vol_num, vol_info in volume_info_dict.items():
                        # Map volume number to config code
                        vol_code = None
                        for code, config_info in Config.ATLAS14_VOLUMES.items():
                            if config_info['volume'] == vol_num:
                                vol_code = code
                                break
                        
                        if vol_code:
                            checkbox_key = f"volume_{vol_num}"
                            is_selected = st.checkbox(
                                f"Volume {vol_num}: {vol_info['name']}",
                                key=checkbox_key,
                                help=f"Select Volume {vol_num} for processing"
                            )
                            if is_selected:
                                selected_volumes.append(vol_code)
                    
                    if selected_volumes:
                        volume_codes = selected_volumes
                        st.success(f"✅ Selected volumes: {', '.join(volume_codes)}")
                        
                        # Display volume information
                        with st.expander("📊 **Selected Volume Details**"):
                            for code in volume_codes:
                                if code in Config.ATLAS14_VOLUMES:
                                    info = Config.ATLAS14_VOLUMES[code]
                                    st.markdown(f"""
                                    <div class="volume-info">
                                        <strong>Volume {info['volume']} ({code}):</strong> {info['name']}<br>
                                        <small>{info.get('description', 'No description available')}</small>
                                    </div>
                                    """, unsafe_allow_html=True)
                
                with col2:
                    st.markdown("**📍 NOAA Atlas 14 Volume Coverage:**")
                    
                    # Interactive volume coverage map
                    enhanced_map = EnhancedMapVisualization.create_volume_map()
                    map_data = st_folium(enhanced_map, width=400, height=300, returned_objects=["last_object_clicked"])
                    
                    # Static reference image with helper icon
                    col_img, col_icon = st.columns([4, 1])
                    with col_img:
                        st.markdown("**Reference Volume Map:**")
                    with col_icon:
                        if st.button("🔍", help="Click to expand reference image", key="expand_ref_img"):
                            # Toggle expansion state
                            if 'ref_img_expanded' not in st.session_state:
                                st.session_state.ref_img_expanded = False
                            st.session_state.ref_img_expanded = not st.session_state.ref_img_expanded
                    
                    # Show reference image (expandable)
                    if st.session_state.get('ref_img_expanded', False):
                        if config.VOLUME_MAP_IMAGE.exists():
                            try:
                                ref_image = Image.open(config.VOLUME_MAP_IMAGE)
                                st.image(ref_image, caption="NOAA Atlas 14 Volume Coverage Map", use_container_width=True)
                            except Exception as e:
                                st.warning(f"Could not load reference image: {e}")
                        else:
                            st.info("📷 Add 'noaa_atlas14_volumes.png' to SupportInfo/part1_supp/ for reference image")
                    else:
                        # Show thumbnail when collapsed
                        if config.VOLUME_MAP_IMAGE.exists():
                            try:
                                ref_image = Image.open(config.VOLUME_MAP_IMAGE)
                                # Create thumbnail
                                ref_image.thumbnail((150, 100))
                                st.image(ref_image, caption="Click 🔍 to expand", width=150)
                            except Exception as e:
                                st.info("📷 Reference image available (click 🔍 to view)")
                        else:
                            st.info("📷 No reference image found")
                    
                    # Handle map interactions (future enhancement)
                    if map_data['last_object_clicked']:
                        clicked_data = map_data['last_object_clicked']
                        st.info(f"Map interaction: {clicked_data}")
            
            elif aoi_method == "Use Sample Project Area":
                # Use built-in sample project area
                sample_shp_path = find_builtin_shapefile(config.PROJECT_AREA_PATH)
                if sample_shp_path:
                    prj_area_shp_path = sample_shp_path
                    st.success(f"✅ Using sample project area: {Path(sample_shp_path).name}")
                    st.info(f"📁 Sample location: {config.PROJECT_AREA_PATH}")
                else:
                    st.warning("⚠️ Sample project area not found. Please add a sample shapefile to SupportInfo/part1_supp/Project_Area/")
        
        # NOAA Zones Shapefile Configuration
        with st.expander("🌍 **NOAA Atlas 14 Zones Shapefile**", expanded=not st.session_state.advanced_mode):
            use_builtin_states = st.checkbox(
                "Use built-in NOAA zones shapefile",
                value=True,
                help="Use the included NOAA Atlas 14 zones shapefile from SupportInfo"
            )
            
            states_shp_path = None
            if use_builtin_states:
                if config.US_STATES_PATH.exists():
                    states_shp_path = config.US_STATES_PATH
                    st.success(f"✅ Using built-in shapefile: {states_shp_path.name}")
                    st.info(f"📁 Location: {config.US_STATES_PATH}")
                else:
                    st.error(f"❌ Built-in shapefile not found: {config.US_STATES_PATH}")
                    st.info("Please ensure the US_States folder contains the NOAA zones shapefile")
            else:
                states_files = st.file_uploader(
                    "Upload NOAA zones shapefile components",
                    type=["shp", "shx", "dbf", "prj"],
                    accept_multiple_files=True,
                    help="Upload all components of the NOAA Atlas 14 zones shapefile"
                )
                
                if states_files:
                    states_shp_path = copy_files_to_single_dir(states_files, "noaa_zones")
        
        # Processing Configuration (keeping the same as before)
        with st.expander("⚙️ **Processing Configuration**", expanded=True):
            col1, col2 = st.columns(2)
            
            with col1:
                # Series Type Selection
                series_type = st.selectbox(
                    "Duration Series Type",
                    options=["PDS", "AMS", "BOTH"],
                    index=0,
                    help="PDS: Partial Duration Series, AMS: Annual Maximum Series, BOTH: Generate both types"
                )
                
                # Recurrence Intervals
                st.markdown("**Recurrence Intervals (Years):**")
                if st.session_state.advanced_mode:
                    interval_options = ["all"] + sorted(list(Config.VALID_EVENTS), key=int)
                    selected_intervals = st.multiselect(
                        "Select intervals:",
                        options=interval_options,
                        default=["all"],
                        help="Select specific recurrence intervals or 'all' for complete dataset"
                    )
                else:
                    # Simplified interface for basic mode
                    interval_preset = st.selectbox(
                        "Interval preset:",
                        options=[
                            "Standard (2, 5, 10, 25, 50, 100-year)",
                            "Extended (All intervals)",
                            "Regulatory (10, 25, 50, 100-year)",
                            "Custom selection"
                        ],
                        help="Choose a preset or custom selection"
                    )
                    
                    if interval_preset == "Standard (2, 5, 10, 25, 50, 100-year)":
                        selected_intervals = ["2", "5", "10", "25", "50", "100"]
                    elif interval_preset == "Extended (All intervals)":
                        selected_intervals = ["all"]
                    elif interval_preset == "Regulatory (10, 25, 50, 100-year)":
                        selected_intervals = ["10", "25", "50", "100"]
                    else:  # Custom
                        selected_intervals = st.multiselect(
                            "Select custom intervals:",
                            options=sorted(list(Config.VALID_EVENTS), key=int),
                            default=["10", "25", "50", "100"]
                        )
            
            with col2:
                # Durations (keeping same logic as before)
                st.markdown("**Storm Durations:**")
                if st.session_state.advanced_mode:
                    minutes = sorted([d for d in Config.VALID_DURATIONS if d.endswith('m')], key=lambda x: int(x[:-1]))
                    hours = sorted([d for d in Config.VALID_DURATIONS if d.endswith('h')], key=lambda x: int(x[:-1]))
                    duration_options = ["all"] + minutes + hours
                    
                    selected_durations = st.multiselect(
                        "Select durations:",
                        options=duration_options,
                        default=["all"],
                        help="Select specific durations or 'all' for complete dataset"
                    )
                else:
                    # Simplified interface for basic mode
                    duration_preset = st.selectbox(
                        "Duration preset:",
                        options=[
                            "Standard (15m, 30m, 1h, 2h, 3h, 6h, 12h, 24h)",
                            "Extended (All durations)",
                            "Short Duration (5m, 10m, 15m, 30m, 1h)",
                            "Long Duration (3h, 6h, 12h, 24h)",
                            "Custom selection"
                        ],
                        help="Choose a preset or custom selection"
                    )
                    
                    if duration_preset == "Standard (15m, 30m, 1h, 2h, 3h, 6h, 12h, 24h)":
                        selected_durations = ["15m", "30m", "60m", "02h", "03h", "06h", "12h", "24h"]
                    elif duration_preset == "Extended (All durations)":
                        selected_durations = ["all"]
                    elif duration_preset == "Short Duration (5m, 10m, 15m, 30m, 1h)":
                        selected_durations = ["05m", "10m", "15m", "30m", "60m"]
                    elif duration_preset == "Long Duration (3h, 6h, 12h, 24h)":
                        selected_durations = ["03h", "06h", "12h", "24h"]
                    else:  # Custom
                        selected_durations = st.multiselect(
                            "Select custom durations:",
                            options=sorted(list(Config.VALID_DURATIONS)),
                            default=["60m", "02h", "06h", "24h"]
                        )
                
                # Additional Options
                st.markdown("**Additional Options:**")
                ci_100yr = st.checkbox(
                    "Include 100-Year Confidence Intervals",
                    value=True,
                    help="Generate 90% confidence interval grids for 100-year events"
                )
                
                if st.session_state.advanced_mode:
                    calculate_stats = st.checkbox(
                        "Calculate detailed statistics",
                        value=False,
                        help="Generate detailed statistics for all output rasters (increases processing time)"
                    )
                else:
                    calculate_stats = False
    
    # Logging Section in right column
    with log_col:
        with st.expander("📋 **Processing Logs**", expanded=False):
            log_placeholder = st.empty()
            
            if st.button("Clear Logs"):
                st.session_state.processing_logs = []
                st.rerun()
            
            # Display logs
            log_handler.display_logs(log_placeholder)
    
    # Process Button (keeping same logic as before)
    st.markdown("---")
    col1, col2, col3 = st.columns([1, 1, 1])
    with col2:
        process_button = st.button(
            "🚀 Start Processing",
            type="primary",
            use_container_width=True,
            help="Begin NOAA grid download and processing"
        )
    
    # Processing Results (keeping same logic as before but using proper paths)
    if process_button:
        st.markdown("### 📊 Processing Results")
        
        # Validate inputs
        errors = validate_part1_inputs(
            base_dir, prj_area_shp_path, volume_codes, states_shp_path,
            selected_intervals, selected_durations, series_type
        )
        
        if errors:
            st.error("❌ Please correct the following errors:")
            for error in errors:
                st.warning(f"• {error}")
        else:
            # Show progress
            progress_bar = st.progress(0, text="Initializing processing...")
            status_placeholder = st.empty()
            
            try:
                # Process events and durations
                if "all" in selected_intervals:
                    event_list = list(Config.VALID_EVENTS)
                else:
                    event_list = selected_intervals
                
                if "all" in selected_durations:
                    dur_list = list(Config.VALID_DURATIONS)
                else:
                    dur_list = selected_durations
                
                # Initialize enhanced processor
                log_handler.add_log("INFO", "Initializing Enhanced NOAA Grid Processor...")
                processor = EnhancedNOAAGrids()
                
                # Create inputs dictionary for enhanced script
                inputs = {
                    "calculate_stats": calculate_stats if st.session_state.advanced_mode else False
                }
                
                # Start processing
                start_time = time.time()
                log_handler.add_log("INFO", f"Starting processing with {len(event_list)} events and {len(dur_list)} durations...")
                
                processor.process_grids(
                    base_dir=base_dir,
                    prj_area_shp_path=prj_area_shp_path,
                    states_shp_path=str(states_shp_path) if states_shp_path else None,
                    volume_codes=volume_codes,
                    event_list=event_list,
                    dur_list=dur_list,
                    series_types=[series_type],
                    CI_100yr=ci_100yr,
                    inputs=inputs
                )
                
                # Processing completed
                elapsed_time = time.time() - start_time
                hours, rem = divmod(elapsed_time, 3600)
                minutes, seconds = divmod(rem, 60)
                
                progress_bar.progress(100, text="Processing completed successfully!")
                
                # Update session state
                st.session_state.part1_completed = True
                st.session_state.part1_output_dir = base_dir
                
                # Display results
                st.success(f"✅ Processing completed successfully!")
                st.info(f"⏱️ Processing time: {int(hours)}h {int(minutes)}m {round(seconds, 2)}s")
                st.info(f"📁 Output location: {base_dir}")
                
                # Show output structure
                with st.expander("📂 **Output Structure**", expanded=True):
                    try:
                        base_path = Path(base_dir)
                        output_folders = []
                        
                        for series in ([series_type] if series_type != 'BOTH' else ['PDS', 'AMS']):
                            grids_folder = base_path / f'NOAA_grids_{series}'
                            mosaic_folder = base_path / f'NOAA_grids_mosaic_{series}'
                            
                            if grids_folder.exists():
                                file_count = len(list(grids_folder.glob("*.asc")))
                                output_folders.append(f"📁 {grids_folder.name} ({file_count} files)")
                            
                            if mosaic_folder.exists():
                                file_count = len(list(mosaic_folder.glob("*.asc")))
                                output_folders.append(f"📁 {mosaic_folder.name} ({file_count} files)")
                        
                        for folder in output_folders:
                            st.write(folder)
                            
                        # Show summary file
                        summary_file = base_path / "noaa_processing.txt"
                        if summary_file.exists():
                            st.write("📄 noaa_processing.txt (Processing summary)")
                            
                            with st.expander("📄 **View Processing Summary**"):
                                with open(summary_file, 'r') as f:
                                    st.text(f.read())
                    
                    except Exception as e:
                        st.warning(f"Could not analyze output structure: {e}")
                
                log_handler.add_log("SUCCESS", "Part 1 processing completed successfully!")
                
            except Exception as e:
                progress_bar.progress(0, text="Processing failed!")
                st.error(f"❌ Processing failed: {str(e)}")
                log_handler.add_log("ERROR", f"Processing failed: {str(e)}")
                
                # Show error details in advanced mode
                if st.session_state.advanced_mode:
                    with st.expander("🔍 **Error Details**"):
                        st.exception(e)

def validate_part1_inputs(base_dir, prj_area_shp_path, volume_codes, states_shp_path, 
                         selected_intervals, selected_durations, series_type):
    """Validate Part 1 inputs and return list of errors"""
    errors = []
    
    # Base directory validation
    if not base_dir:
        errors.append("Base directory is required")
    else:
        try:
            Path(base_dir).mkdir(parents=True, exist_ok=True)
        except Exception as e:
            errors.append(f"Cannot create base directory: {str(e)}")
    
    # AOI validation
    if not prj_area_shp_path and not volume_codes:
        errors.append("Either project area shapefile or volume selection is required")
    
    # States shapefile validation
    if not states_shp_path or not Path(states_shp_path).exists():
        errors.append("NOAA zones shapefile is required and must exist")
    
    # Events and durations validation
    if not selected_intervals:
        errors.append("At least one recurrence interval must be selected")
    
    if not selected_durations:
        errors.append("At least one duration must be selected")
    
    # Validate against config
    if "all" not in selected_intervals:
        if not set(selected_intervals).issubset(Config.VALID_EVENTS):
            errors.append(f"Invalid recurrence intervals. Valid options: {', '.join(sorted(Config.VALID_EVENTS, key=int))}")
    
    if "all" not in selected_durations:
        if not set(selected_durations).issubset(Config.VALID_DURATIONS):
            errors.append(f"Invalid durations. Valid options: {', '.join(sorted(Config.VALID_DURATIONS))}")
    
    return errors

def part2_placeholder_tab():
    """Enhanced placeholder for Part 2 with proper directory structure"""
    st.markdown('<div class="main-header">Part 2: ASC to Time-Series TIFF Processor</div>', unsafe_allow_html=True)
    st.markdown('<div class="sub-header">Convert gridded precipitation data to time-series TIFF rasters using temporal distribution patterns</div>', unsafe_allow_html=True)
    
    # Check if Part 1 is completed
    if not st.session_state.part1_completed:
        st.warning("⚠️ Please complete Part 1 first before proceeding to Part 2.")
        st.info("Part 2 requires the ASC precipitation grids from Part 1 to function properly.")
        return
    
    # Auto-detect Part 1 output
    if st.session_state.part1_output_dir:
        st.success(f"✅ Part 1 output detected: {st.session_state.part1_output_dir}")
        
        with st.expander("📁 **Input Configuration (Auto-detected)**", expanded=True):
            st.info(f"Input directory: {st.session_state.part1_output_dir}")
            st.write("Part 2 will automatically process the precipitation grids (.asc files) from Part 1.")
            
            # Show detected ASC files
            try:
                base_path = Path(st.session_state.part1_output_dir)
                asc_files = []
                
                # Look for ASC files in grid folders
                for pattern in ['NOAA_grids_*/', 'NOAA_grids_mosaic_*/']:
                    for folder in base_path.glob(pattern):
                        if folder.is_dir():
                            folder_files = list(folder.glob("*.asc"))
                            asc_files.extend(folder_files)
                
                if asc_files:
                    st.write(f"📊 Found {len(asc_files)} ASC precipitation grid files")
                    
                    with st.expander("📄 View detected files"):
                        for file in sorted(asc_files)[:10]:  # Show first 10 files
                            st.write(f"• {file.name}")
                        if len(asc_files) > 10:
                            st.write(f"... and {len(asc_files) - 10} more files")
                else:
                    st.warning("⚠️ No ASC files found in Part 1 output directory")
                    
            except Exception as e:
                st.warning(f"Could not analyze Part 1 output: {e}")
    
    # Show available NRCS distributions
    with st.expander("📊 **Available Temporal Distributions**", expanded=True):
        col1, col2 = st.columns(2)
        
        with col1:
            st.markdown("**Built-in NRCS Distributions:**")
            if config.NRCS_DISTROS_PATH.exists():
                st.success(f"✅ Default NRCS distributions available")
                st.info(f"📁 Location: {config.NRCS_DISTROS_PATH}")
                
                # Future: Preview distributions
                st.info("🔍 Distribution preview coming in Part 2 implementation")
            else:
                st.warning(f"⚠️ Default NRCS distributions not found")
                st.info("Please add NRCS_Distros.xlsx to SupportInfo/part2_supp/")
        
        with col2:
            st.markdown("**Custom Distributions:**")
            st.info("📁 Custom templates will be stored in:")
            st.code(str(config.CUSTOM_TEMPLATES))
            
            # Placeholder for custom upload
            custom_file = st.file_uploader(
                "Upload custom temporal distribution",
                type=["xlsx", "csv"],
                help="Upload your own temporal distribution data",
                disabled=True  # Disabled until Part 2 implementation
            )
            
            if custom_file:
                st.info("🚧 Custom distribution upload will be available in Part 2")
    
    # Placeholder content
    st.info("🚧 ASCtoTimeSeriesTIFF.py integration coming soon!")
    
    with st.expander("🔧 **Planned Part 2 Features**", expanded=True):
        st.markdown("""
        **ASC to Time-Series TIFF Processor will include:**
        
        📋 **Input Processing**
        - Automatic detection of ASC precipitation grids from Part 1
        - Support for both PDS and AMS series types
        - Validation of grid consistency and coverage
        
        ⏱️ **Temporal Distribution**
        - NRCS temporal distribution patterns (Type I, II, III, IV)
        - Custom temporal distribution import from Excel/CSV
        - Regional distribution selection based on geographic location
        - Storm duration and time step configuration
        
        🗂️ **Output Configuration**
        - Time-series TIFF raster generation
        - Customizable time intervals and resolution
        - Metadata preservation and documentation
        - Georeferenced output with proper CRS
        
        ⚡ **Processing Options**
        - Batch processing capabilities across multiple events
        - Progress tracking and detailed logging
        - Quality control and validation checks
        - Memory-efficient processing for large datasets
        """)

def part3_placeholder_tab():
    """Enhanced placeholder for Part 3 with proper directory structure"""
    st.markdown('<div class="main-header">Part 3: TIFF to HEC-DSS Converter</div>', unsafe_allow_html=True)
    st.markdown('<div class="sub-header">Convert time-series TIFF rasters to HEC-DSS format for HEC-RAS 2D rain-on-mesh modeling</div>', unsafe_allow_html=True)
    
    # Check if Part 2 is completed
    if not st.session_state.part2_completed:
        st.warning("⚠️ Please complete Parts 1 and 2 first before proceeding to Part 3.")
        st.info("Part 3 requires time-series TIFF files from Part 2 to convert to HEC-DSS format.")
        return
    
    # Auto-detect Part 2 output (placeholder for now)
    if st.session_state.part2_output_dir:
        st.success(f"✅ Part 2 output detected: {st.session_state.part2_output_dir}")
        
        with st.expander("📁 **Input Configuration (Auto-detected)**", expanded=True):
            st.info(f"Input directory: {st.session_state.part2_output_dir}")
            st.write("Part 3 will automatically process the time-series TIFF files from Part 2.")
            
            # Future: Show detected TIFF files
            st.info("🔍 TIFF file detection will be implemented when Part 2 is completed.")
    
    # Placeholder content for Part 3 functionality
    st.info("🚧 TIFFtoDSS.py integration coming soon!")
    
    with st.expander("🔧 **Planned Part 3 Features**", expanded=True):
        st.markdown("""
        **TIFF to HEC-DSS Converter will include:**
        
        📥 **Input Processing**
        - Automatic detection of time-series TIFF files from Part 2
        - Validation of temporal consistency and spatial coverage
        - Support for multiple storm events and durations
        - Batch processing across different scenarios
        
        🔄 **HEC-DSS Conversion**
        - Native HEC-DSS format generation (Version 6 & 7 support)
        - Proper time-series data structure and organization
        - Spatial reference system preservation and validation
        - Watershed and location metadata integration
        
        🎯 **HEC-RAS 2D Integration**
        - Rain-on-mesh compatibility verification
        - Grid alignment and resolution validation
        - Temporal resolution optimization for computational efficiency
        - Coordinate system alignment with HEC-RAS models
        
        📊 **Quality Control & Validation**
        - Data integrity verification and error checking
        - Missing data identification and handling options
        - Comprehensive metadata documentation
        - Output validation against HEC-RAS requirements
        
        ⚡ **Advanced Features**
        - Multiple event and duration processing
        - Progress tracking with detailed logging
        - Error handling and recovery mechanisms
        - Memory-efficient processing for large datasets
        """)

def main():
    """Main application entry point with enhanced directory structure"""
    setup_page()
    
    # Initialize session management
    SessionManager.initialize_session()
    
    # Display project header
    st.markdown("""
    <div style='text-align: center; padding: 20px; background: linear-gradient(90deg, #1f77b4, #4dabf7); color: white; border-radius: 10px; margin-bottom: 30px;'>
        <h1>🌧️ GridPrecipProcessor</h1>
        <h3>Enhanced NOAA Atlas 14 Precipitation Toolkit</h3>
        <p>A comprehensive three-part suite for precipitation analysis and hydrologic modeling preparation</p>
    </div>
    """, unsafe_allow_html=True)
    
    # Sidebar with enhanced navigation and project info
    with st.sidebar:
        # Project logo/header
        st.markdown("### 🏗️ GridPrecipProcessor v2.0")
        st.markdown("*A comprehensive three-part suite for precipitation analysis and hydrologic modeling preparation.*")
        
        st.markdown("---")
        
        # Project structure info
        with st.expander("📁 Project Structure"):
            st.code(f"""
GridPrecipProcessor/
├── SupportInfo/
│   ├── part1_supp/ (NOAA data)
│   └── part2_supp/ (Temporal patterns)
├── NOAA_GridMiner.py
├── ASCtoTimeSeriesTIFF.py
├── TIFFtoDSS.py
└── enhanced_streamlit_noaa_ui.py
            """)
        
        # Workflow status
        st.markdown("### 📋 Workflow Status")
        
        status_part1 = "✅ Completed" if st.session_state.part1_completed else "⏳ Pending"
        status_part2 = "✅ Completed" if st.session_state.part2_completed else "⏳ Pending"
        status_part3 = "🚧 Coming Soon"
        
        st.markdown(f"""
        **Part 1: NOAA Grid Miner** {status_part1}  
        **Part 2: ASC to Time-Series TIFF** {status_part2}  
        **Part 3: TIFF to HEC-DSS** {status_part3}
        """)
        
        # Progress indicator
        if st.session_state.part1_completed:
            progress_value = 0.33
            if st.session_state.part2_completed:
                progress_value = 0.67
        else:
            progress_value = 0.0
        
        st.progress(progress_value, text=f"Workflow Progress: {int(progress_value*100)}%")
        
        st.markdown("---")
        
        # Instructions
        st.markdown("### 📖 Quick Start Guide")
        st.markdown("""
        **Step 1: NOAA Grid Miner**
        - Define your area of interest (shapefile or volumes)
        - Select precipitation parameters (events, durations)
        - Download and process NOAA grids
        
        **Step 2: ASC to Time-Series TIFF**
        - Apply temporal distribution patterns (NRCS types)
        - Generate time-series TIFF rasters
        - Prepare data for hydrologic modeling
        
        **Step 3: TIFF to HEC-DSS**
        - Convert to HEC-DSS format
        - Ensure HEC-RAS 2D compatibility
        - Validate rain-on-mesh requirements
        """)
        
        st.markdown("---")
        
        # Repository and updates section
        with st.expander("🔗 Repository & Updates"):
            st.markdown("""
            **GitHub Repository:**  
            🔗 [GridPrecipProcessor](https://github.com/your-username/GridPrecipProcessor)
            
            *Visit the repository for:*
            - 📦 Latest releases and version history
            - 📖 Comprehensive documentation 
            - 🐛 Issue reporting and feature requests
            - 💾 Source code and development updates
            """)
        
        with st.expander("📚 References & Resources"):
            st.markdown("""
            **Technical References:**
            - [NOAA Atlas 14 Precipitation Frequency](https://hdsc.nws.noaa.gov/hdsc/pfds/)
            - [HEC-RAS 2D Modeling Documentation](https://www.hec.usace.army.mil/)
            - [NRCS Temporal Distribution Guidance](https://www.nrcs.usda.gov/)
            
            **Additional Resources:**
            - [USGS StreamStats](https://streamstats.usgs.gov/)
            - [FEMA Flood Risk Products](https://www.fema.gov/flood-maps)
            - [National Weather Service HDSC](https://hdsc.nws.noaa.gov/)
            """)
    
    # Main content area with enhanced tabs
    tab1, tab2, tab3 = st.tabs([
        "🌧️ Part 1: NOAA Grid Miner", 
        "⏱️ Part 2: ASC to Time-Series TIFF", 
        "📊 Part 3: TIFF to HEC-DSS"
    ])
    
    with tab1:
        part1_grid_miner_tab()
    
    with tab2:
        part2_placeholder_tab()
    
    with tab3:
        part3_placeholder_tab()
    
    # Footer
    st.markdown("---")
    st.markdown("""
    <div style='text-align: center; color: #666; font-size: 0.8em;'>
        GridPrecipProcessor v2.0 | Enhanced NOAA Atlas 14 Precipitation Toolkit<br>
        Built for professional hydrologic analysis and modeling preparation
    </div>
    """, unsafe_allow_html=True)

if __name__ == "__main__":
    main()
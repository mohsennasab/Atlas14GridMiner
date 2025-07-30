import streamlit as st
from pathlib import Path
import os
import tempfile
import shutil
import logging
from typing import List, Optional, Dict, Any
import time
import tkinter as tk
from tkinter import filedialog
import warnings

# Set GDAL environment variable for shapefile handling
os.environ['SHAPE_RESTORE_SHX'] = 'YES'
warnings.filterwarnings('ignore', category=RuntimeWarning, message='invalid value encountered in cast')

# Tool Configuration
class ToolConfig:
    """Simple configuration for standalone operation"""
    def __init__(self):
        self.TOOL_ROOT = Path(__file__).parent
        self.SUPPORT_DATA = self.TOOL_ROOT / "support_data"
        self.US_STATES_PATH = self.SUPPORT_DATA / "US_States" / "tl_2021_us_state.shp"
        self.DEFAULT_OUTPUT = self.TOOL_ROOT / "output"
        
        # Create directories
        for directory in [self.SUPPORT_DATA, self.DEFAULT_OUTPUT]:
            directory.mkdir(parents=True, exist_ok=True)

config = ToolConfig()

# Import core processing
try:
    from NOAA_GridMiner import EnhancedNOAAGrids, Config as NOAAConfig
    IMPORT_SUCCESS = True
    IMPORT_ERROR = None
except ImportError as e:
    IMPORT_SUCCESS = False
    IMPORT_ERROR = str(e)

def setup_page():
    """Clean page setup without excessive styling"""
    st.set_page_config(
        page_title="NOAA Atlas 14 Grid Miner",
        page_icon="🌧️",
        layout="wide",
        initial_sidebar_state="expanded"
    )
    
    # Minimal, clean styling
    st.markdown("""
    <style>
    .main-header {
        background: linear-gradient(90deg, #1f77b4, #4dabf7);
        color: white;
        padding: 25px;
        border-radius: 10px;
        text-align: center;
        margin-bottom: 25px;
    }
    .section-header {
        font-size: 1.3rem;
        font-weight: bold;
        color: #1f77b4;
        margin: 20px 0 10px 0;
        padding-bottom: 5px;
        border-bottom: 2px solid #e0e0e0;
    }
    .success-msg {
        background: #d4edda;
        border: 1px solid #c3e6cb;
        color: #155724;
        padding: 10px;
        border-radius: 5px;
        margin: 10px 0;
    }
    .error-msg {
        background: #f8d7da;
        border: 1px solid #f5c6cb;
        color: #721c24;
        padding: 10px;
        border-radius: 5px;
        margin: 10px 0;
    }
    .log-display {
        background: #f8f9fa;
        border-left: 4px solid #007bff;
        padding: 10px;
        font-family: monospace;
        font-size: 12px;
        max-height: 400px;
        overflow-y: auto;
        white-space: pre-wrap;
    }
    </style>
    """, unsafe_allow_html=True)

def initialize_session():
    """Initialize session state variables"""
    if 'processing_logs' not in st.session_state:
        st.session_state.processing_logs = []
    if 'processing_completed' not in st.session_state:
        st.session_state.processing_completed = False
    if 'output_directory' not in st.session_state:
        st.session_state.output_directory = None

def browse_folder(label, default_path=""):
    """Simple folder browser using tkinter"""
    if st.button(f"📁 Browse", key=f"browse_{label}", help="Browse for folder"):
        try:
            # Create a temporary tkinter root window (hidden)
            root = tk.Tk()
            root.withdraw()
            root.attributes('-topmost', True)
            
            # Open folder dialog
            folder_path = filedialog.askdirectory(
                title=f"Select {label}",
                initialdir=default_path if default_path and Path(default_path).exists() else str(Path.home())
            )
            
            root.destroy()
            
            if folder_path:
                return folder_path
        except Exception as e:
            st.error(f"Error opening folder browser: {e}")
    
    return None

def auto_detect_shapefile_components(shp_file_path):
    """Auto-detect and upload other shapefile components from same directory"""
    if not shp_file_path:
        return None
    
    base_path = Path(shp_file_path)
    base_name = base_path.stem
    directory = base_path.parent
    
    # Expected shapefile components
    extensions = ['.shp', '.shx', '.dbf', '.prj', '.cpg', '.qpj']
    found_components = []
    
    # Check for each component
    for ext in extensions:
        component_path = directory / f"{base_name}{ext}"
        if component_path.exists():
            found_components.append(ext)
    
    # Show found components
    if found_components:
        st.success(f"✅ Auto-detected components: {', '.join(found_components)}")
        
        # Check for required components
        required = ['.shp', '.shx', '.dbf']
        missing_required = [ext for ext in required if ext not in found_components]
        
        if missing_required:
            st.warning(f"⚠️ Missing required components: {', '.join(missing_required)} - GDAL will attempt to restore")
        
        return str(base_path)
    else:
        st.error("❌ No shapefile components found in selected directory")
        return None

def copy_shapefile_components(uploaded_files):
    """Enhanced shapefile handling with component validation"""
    if not uploaded_files:
        return None
    
    temp_dir = tempfile.mkdtemp(prefix="shapefile_")
    
    # Copy all uploaded files
    for uploaded_file in uploaded_files:
        file_path = os.path.join(temp_dir, uploaded_file.name)
        with open(file_path, "wb") as f:
            f.write(uploaded_file.getbuffer())
    
    # Find .shp file
    shp_files = list(Path(temp_dir).glob("*.shp"))
    if not shp_files:
        shutil.rmtree(temp_dir)
        return None
    
    shp_path = shp_files[0]
    base_name = shp_path.stem
    
    # Validate components
    required_extensions = ['.shp', '.shx', '.dbf']
    found_files = []
    missing_files = []
    
    for ext in required_extensions:
        if (shp_path.parent / f"{base_name}{ext}").exists():
            found_files.append(ext)
        else:
            missing_files.append(ext)
    
    if found_files:
        st.success(f"✅ Shapefile components: {', '.join(found_files)}")
    if missing_files:
        st.warning(f"⚠️ Missing components: {', '.join(missing_files)}")
    
    return str(shp_path)

def find_builtin_shapefile():
    """Find built-in NOAA zones shapefile"""
    if config.US_STATES_PATH.exists():
        return str(config.US_STATES_PATH)
    return None

class ProcessingLogger:
    """Simple processing logger for terminal-style output"""
    
    def __init__(self):
        self.logs = []
    
    def add_log(self, level, message):
        """Add log entry during processing"""
        timestamp = time.strftime("%H:%M:%S")
        log_entry = f"[{timestamp}] {level}: {message}"
        
        if 'processing_logs' not in st.session_state:
            st.session_state.processing_logs = []
        st.session_state.processing_logs.append(log_entry)
    
    def display_logs(self, container):
        """Display logs in terminal style"""
        if st.session_state.processing_logs:
            log_text = "\n".join(st.session_state.processing_logs)
            container.markdown(f'<div class="log-display">{log_text}</div>', unsafe_allow_html=True)
        else:
            container.info("Processing logs will appear here when processing starts...")

def main_interface():
    """Main interface with practical enhancements"""
    
    # Check import status
    if not IMPORT_SUCCESS:
        st.error(f"❌ Cannot import NOAA_GridMiner.py: {IMPORT_ERROR}")
        st.info("Please ensure NOAA_GridMiner.py is in the same directory as this GUI script.")
        st.stop()
    
    # Header
    st.markdown("""
    <div class="main-header">
        <h1>🌧️ NOAA Atlas 14 Grid Miner</h1>
        <h3>Enhanced Precipitation Grid Processing Tool</h3>
        <p>Download and process NOAA Atlas 14 precipitation frequency data for your project area</p>
    </div>
    """, unsafe_allow_html=True)
    
    # Initialize logger
    logger = ProcessingLogger()
    
    # Main layout
    main_col, sidebar_col = st.columns([3, 1])
    
    with main_col:
        # Output Configuration
        st.markdown('<div class="section-header">📁 Output Configuration</div>', unsafe_allow_html=True)
        
        # Output directory with browse functionality
        col1, col2 = st.columns([3, 1])
        
        with col1:
            # Show full default path for clarity
            default_output_full = str(config.DEFAULT_OUTPUT.resolve())
            base_dir = st.text_input(
                "Output Directory",
                value=default_output_full,
                help="Directory where all processed grids will be stored",
                placeholder="C:/Projects/NOAA/Output"
            )
        
        with col2:
            # Browse button
            browsed_dir = browse_folder("Output Directory", str(config.DEFAULT_OUTPUT.parent))
            if browsed_dir:
                base_dir = browsed_dir
                st.rerun()
        
        if base_dir:
            try:
                Path(base_dir).mkdir(parents=True, exist_ok=True)
                st.markdown(f'<div class="success-msg">✅ Output directory ready: {base_dir}</div>', unsafe_allow_html=True)
            except Exception as e:
                st.markdown(f'<div class="error-msg">❌ Cannot create directory: {e}</div>', unsafe_allow_html=True)
        
        # Area of Interest Definition
        st.markdown('<div class="section-header">🗺️ Area of Interest Definition</div>', unsafe_allow_html=True)
        
        aoi_method = st.radio(
            "Select method to define your area of interest:",
            ["Upload Project Area Shapefile", "Select NOAA Atlas 14 Volume(s)"],
            help="Choose the method that best fits your analysis needs"
        )
        
        prj_area_shp_path = None
        volume_codes = None
        
        if aoi_method == "Upload Project Area Shapefile":
            st.markdown("**📤 Shapefile Upload Options**")
            
            upload_method = st.radio(
                "Choose upload method:",
                ["Upload All Components", "Auto-Detect from .shp File"],
                help="Upload all files manually or let the system auto-detect components"
            )
            
            if upload_method == "Upload All Components":
                prj_area_files = st.file_uploader(
                    "Upload ALL shapefile components (.shp, .shx, .dbf, .prj required)",
                    type=["shp", "shx", "dbf", "prj", "cpg", "qpj"],
                    accept_multiple_files=True,
                    help="Upload all components for best compatibility"
                )
                
                if prj_area_files:
                    prj_area_shp_path = copy_shapefile_components(prj_area_files)
                    if prj_area_shp_path:
                        st.markdown(f'<div class="success-msg">✅ Project area shapefile ready: {Path(prj_area_shp_path).name}</div>', unsafe_allow_html=True)
            
            else:  # Auto-detect
                shp_file = st.file_uploader(
                    "Upload .shp file (other components will be auto-detected)",
                    type=["shp"],
                    help="Select the main .shp file, other components will be found automatically"
                )
                
                if shp_file:
                    # Save .shp file temporarily
                    temp_dir = tempfile.mkdtemp(prefix="shapefile_autodetect_")
                    shp_path = os.path.join(temp_dir, shp_file.name)
                    
                    with open(shp_path, "wb") as f:
                        f.write(shp_file.getbuffer())
                    
                    prj_area_shp_path = auto_detect_shapefile_components(shp_path)
                    if prj_area_shp_path:
                        st.markdown(f'<div class="success-msg">✅ Project area shapefile with auto-detected components ready</div>', unsafe_allow_html=True)
        
        elif aoi_method == "Select NOAA Atlas 14 Volume(s)":
            st.markdown("**📍 Available NOAA Atlas 14 Volumes**")
            
            # Simple volume selection without map
            selected_volumes = []
            volumes_sorted = sorted(NOAAConfig.ATLAS14_VOLUMES.items(), key=lambda x: x[1]['volume'])
            
            # Create organized volume selection
            col1, col2 = st.columns(2)
            
            for i, (code, info) in enumerate(volumes_sorted):
                target_col = col1 if i % 2 == 0 else col2
                
                with target_col:
                    is_selected = st.checkbox(
                        f"Volume {info['volume']}: {info['name']}", 
                        key=f"vol_{code}",
                        help=f"Coverage: {info.get('description', 'Multiple states/regions')}"
                    )
                    
                    if is_selected:
                        selected_volumes.append(code)
            
            if selected_volumes:
                volume_codes = selected_volumes
                st.markdown(f'<div class="success-msg">✅ Selected volumes: {", ".join(volume_codes)}</div>', unsafe_allow_html=True)
                
                # Show selected volume details
                with st.expander("📊 Selected Volume Details"):
                    for code in volume_codes:
                        info = NOAAConfig.ATLAS14_VOLUMES[code]
                        st.write(f"**Volume {info['volume']} ({code}):** {info['name']}")
                        if 'description' in info:
                            st.write(f"*Coverage: {info['description']}*")
        
        # NOAA Zones Shapefile
        st.markdown('<div class="section-header">🌍 NOAA Atlas 14 Zones Shapefile</div>', unsafe_allow_html=True)
        
        use_builtin_states = st.checkbox(
            "Use built-in NOAA zones shapefile",
            value=True,
            help="Use the included NOAA Atlas 14 zones shapefile"
        )
        
        states_shp_path = None
        if use_builtin_states:
            builtin_path = find_builtin_shapefile()
            if builtin_path:
                states_shp_path = builtin_path
                st.markdown(f'<div class="success-msg">✅ Using built-in shapefile: {Path(builtin_path).name}</div>', unsafe_allow_html=True)
                st.info(f"📁 Location: {config.US_STATES_PATH}")
            else:
                st.markdown(f'<div class="error-msg">❌ Built-in shapefile not found: {config.US_STATES_PATH}</div>', unsafe_allow_html=True)
        else:
            states_files = st.file_uploader(
                "Upload NOAA zones shapefile components",
                type=["shp", "shx", "dbf", "prj"],
                accept_multiple_files=True,
                help="Upload all components of the NOAA Atlas 14 zones shapefile"
            )
            
            if states_files:
                states_shp_path = copy_shapefile_components(states_files)
        
        # Processing Configuration
        st.markdown('<div class="section-header">⚙️ Processing Configuration</div>', unsafe_allow_html=True)
        
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
            interval_options = ["all"] + sorted(list(NOAAConfig.VALID_EVENTS), key=int)
            selected_intervals = st.multiselect(
                "Select intervals:",
                options=interval_options,
                default=["all"],
                help="Select specific recurrence intervals or 'all' for complete dataset"
            )
            
            # Quick presets
            preset_col1, preset_col2, preset_col3 = st.columns(3)
            with preset_col1:
                if st.button("Standard", help="2,5,10,25,50,100 year"):
                    selected_intervals = ["2", "5", "10", "25", "50", "100"]
                    st.rerun()
            with preset_col2:
                if st.button("Regulatory", help="10,25,50,100 year"):
                    selected_intervals = ["10", "25", "50", "100"]
                    st.rerun()
            with preset_col3:
                if st.button("All Events", help="All available intervals"):
                    selected_intervals = ["all"]
                    st.rerun()
        
        with col2:
            # Storm Durations
            st.markdown("**Storm Durations:**")
            minutes = sorted([d for d in NOAAConfig.VALID_DURATIONS if d.endswith('m')], key=lambda x: int(x[:-1]))
            hours = sorted([d for d in NOAAConfig.VALID_DURATIONS if d.endswith('h')], key=lambda x: int(x[:-1]))
            duration_options = ["all"] + minutes + hours
            
            selected_durations = st.multiselect(
                "Select durations:",
                options=duration_options,
                default=["all"],
                help="Select specific durations or 'all' for complete dataset"
            )
            
            # Duration presets
            preset_col1, preset_col2, preset_col3 = st.columns(3)
            with preset_col1:
                if st.button("Standard", help="15m,30m,1h,6h,24h", key="dur_standard"):
                    selected_durations = ["15m", "30m", "60m", "06h", "24h"]
                    st.rerun()
            with preset_col2:
                if st.button("Short", help="5m,10m,15m,30m,1h", key="dur_short"):
                    selected_durations = ["05m", "10m", "15m", "30m", "60m"]
                    st.rerun()
            with preset_col3:
                if st.button("All Durations", help="All available durations", key="dur_all"):
                    selected_durations = ["all"]
                    st.rerun()
            
            # Additional Options
            st.markdown("**Additional Options:**")
            ci_100yr = st.checkbox(
                "Include 100-Year Confidence Intervals",
                value=True,
                help="Generate 90% confidence interval grids for 100-year events"
            )
            
            calculate_stats = st.checkbox(
                "Calculate detailed statistics",
                value=False,
                help="Generate detailed statistics for all output rasters (increases processing time)"
            )
    
    # Sidebar
    with sidebar_col:
        st.markdown("### 🔧 Processing Controls")
        
        # Process button
        process_button = st.button(
            "🚀 Start Processing",
            type="primary",
            use_container_width=True,
            help="Begin NOAA grid download and processing"
        )
        
        # Processing status
        if st.session_state.processing_completed:
            st.markdown('<div class="success-msg">✅ Processing Completed!</div>', unsafe_allow_html=True)
        
        # Processing logs
        st.markdown("### 📋 Processing Logs")
        
        if st.button("Clear Logs", use_container_width=True):
            st.session_state.processing_logs = []
            st.rerun()
        
        log_container = st.container()
        logger.display_logs(log_container)
        
        # Tool Information
        with st.expander("ℹ️ Tool Information", expanded=False):
            st.markdown("""
            ### 🚀 Quick Start Guide
            
            **Step 1:** Configure output directory  
            **Step 2:** Define area of interest (shapefile or volumes)  
            **Step 3:** Configure processing parameters  
            **Step 4:** Click "Start Processing"  
            
            ### 🔗 Repository
            [GridMiner Repository](https://github.com/your-username/GridMiner)
            
            ### 📚 References
            - [NOAA Atlas 14](https://hdsc.nws.noaa.gov/hdsc/pfds/)
            - [HEC-RAS Documentation](https://www.hec.usace.army.mil/)
            - [USGS StreamStats](https://streamstats.usgs.gov/)
            """)
    
    # Processing execution
    if process_button:
        execute_processing(
            base_dir, prj_area_shp_path, volume_codes, states_shp_path,
            selected_intervals, selected_durations, series_type, ci_100yr,
            calculate_stats, logger
        )

def execute_processing(base_dir, prj_area_shp_path, volume_codes, states_shp_path,
                      selected_intervals, selected_durations, series_type, ci_100yr,
                      calculate_stats, logger):
    """Execute processing with terminal-style logging"""
    
    st.markdown("---")
    st.markdown("### 📊 Processing Results")
    
    # Validate inputs
    errors = validate_inputs(base_dir, prj_area_shp_path, volume_codes, states_shp_path,
                            selected_intervals, selected_durations)
    
    if errors:
        st.error("❌ Please correct the following issues:")
        for error in errors:
            st.write(f"• {error}")
        return
    
    # Display processing configuration
    with st.expander("📋 Processing Configuration", expanded=True):
        col1, col2 = st.columns(2)
        
        with col1:
            st.write(f"**Output Directory:** {base_dir}")
            if prj_area_shp_path:
                st.write(f"**AOI Method:** Shapefile ({Path(prj_area_shp_path).name})")
            if volume_codes:
                st.write(f"**AOI Method:** Volume Selection ({', '.join(volume_codes)})")
        
        with col2:
            event_list = list(NOAAConfig.VALID_EVENTS) if "all" in selected_intervals else selected_intervals
            dur_list = list(NOAAConfig.VALID_DURATIONS) if "all" in selected_durations else selected_durations
            
            st.write(f"**Events:** {len(event_list)} intervals")
            st.write(f"**Durations:** {len(dur_list)} periods")
            st.write(f"**Series Type:** {series_type}")
    
    # Execute processing
    progress_bar = st.progress(0, text="Initializing processing...")
    
    try:
        logger.add_log("INFO", "Starting NOAA grid processing")
        logger.add_log("INFO", f"Processing {len(event_list)} events × {len(dur_list)} durations")
        
        # Initialize processor
        processor = EnhancedNOAAGrids()
        inputs = {"calculate_stats": calculate_stats}
        
        start_time = time.time()
        progress_bar.progress(25, text="Processing grids...")
        
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
        progress_bar.progress(100, text="Processing completed!")
        
        # Update session state
        st.session_state.processing_completed = True
        st.session_state.output_directory = base_dir
        
        logger.add_log("SUCCESS", f"Processing completed in {elapsed_time:.1f} seconds")
        
        # Display results
        hours, rem = divmod(elapsed_time, 3600)
        minutes, seconds = divmod(rem, 60)
        
        st.markdown(f'<div class="success-msg">✅ Processing completed successfully!</div>', unsafe_allow_html=True)
        
        col1, col2 = st.columns(2)
        with col1:
            st.info(f"⏱️ Processing time: {int(hours)}h {int(minutes)}m {round(seconds, 2)}s")
        with col2:
            st.info(f"📁 Output location: {base_dir}")
        
        # Show output structure
        display_results(base_dir, series_type)
        
    except Exception as e:
        progress_bar.progress(0, text="Processing failed!")
        st.markdown(f'<div class="error-msg">❌ Processing failed: {str(e)}</div>', unsafe_allow_html=True)
        logger.add_log("ERROR", f"Processing failed: {str(e)}")
        
        with st.expander("🔍 Error Details"):
            st.exception(e)

def validate_inputs(base_dir, prj_area_shp_path, volume_codes, states_shp_path,
                   selected_intervals, selected_durations):
    """Validate processing inputs"""
    errors = []
    
    if not base_dir:
        errors.append("Output directory is required")
    
    if not prj_area_shp_path and not volume_codes:
        errors.append("Area of interest must be defined")
    
    if not states_shp_path:
        errors.append("NOAA zones shapefile is required")
    
    if not selected_intervals:
        errors.append("At least one recurrence interval must be selected")
    
    if not selected_durations:
        errors.append("At least one duration must be selected")
    
    return errors

def display_results(base_dir, series_type):
    """Display processing results"""
    with st.expander("📂 Output Structure", expanded=True):
        try:
            base_path = Path(base_dir)
            series_list = [series_type] if series_type != 'BOTH' else ['PDS', 'AMS']
            
            for series in series_list:
                st.markdown(f"**{series} Series:**")
                
                grids_folder = base_path / f'NOAA_grids_{series}'
                mosaic_folder = base_path / f'NOAA_grids_mosaic_{series}'
                
                if grids_folder.exists():
                    file_count = len(list(grids_folder.glob("*.asc")))
                    st.write(f"📁 {grids_folder.name}: {file_count} files")
                
                if mosaic_folder.exists():
                    file_count = len(list(mosaic_folder.glob("*.asc")))
                    st.write(f"📁 {mosaic_folder.name}: {file_count} files")
            
            # Summary file
            summary_file = base_path / "noaa_processing.txt"
            if summary_file.exists():
                st.write("📄 noaa_processing.txt (Processing summary)")
                
                if st.button("📖 View Summary"):
                    with st.expander("Processing Summary", expanded=True):
                        with open(summary_file, 'r') as f:
                            st.text(f.read())
        
        except Exception as e:
            st.warning(f"Could not analyze output structure: {e}")

def main():
    """Main application entry point"""
    setup_page()
    initialize_session()
    main_interface()

if __name__ == "__main__":
    main()
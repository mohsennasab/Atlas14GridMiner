import streamlit as st
from pathlib import Path
import os
import tempfile
import shutil
import logging
import time
import tkinter as tk
from tkinter import filedialog
import warnings
import sys
import io
import contextlib
import threading
from typing import Dict, List, Optional, Any, Callable
from abc import ABC, abstractmethod

# Set GDAL environment variable for shapefile handling
os.environ['SHAPE_RESTORE_SHX'] = 'YES'
warnings.filterwarnings('ignore', category=RuntimeWarning, message='invalid value encountered in cast')

# ==================================================================================
# LOGGING CAPTURE HELPERS
# ==================================================================================

class LogCaptureHandler(logging.Handler):
    """Custom logging handler to capture core engine logs"""
    
    def __init__(self, gui_framework):
        super().__init__()
        self.gui_framework = gui_framework
        
    def emit(self, record):
        try:
            msg = self.format(record)
            level_map = {
                logging.INFO: "INFO",
                logging.WARNING: "WARNING", 
                logging.ERROR: "ERROR",
                logging.DEBUG: "DEBUG"
            }
            level = level_map.get(record.levelno, "INFO")
            
            # Clean up the message (remove timestamp if already present)
            if "] [" in msg and msg.startswith("["):
                # Extract just the message part if it already has timestamp
                parts = msg.split("] ", 2)
                if len(parts) >= 3:
                    msg = parts[2]
            
            self.gui_framework.add_log(level, msg)
        except Exception:
            pass


class TeeOutput:
    """Tee-like output that writes to both original stream and captures for GUI"""
    
    def __init__(self, original, buffer, gui_framework, log_container, is_error=False):
        self.original = original
        self.buffer = buffer
        self.gui_framework = gui_framework
        self.log_container = log_container
        self.is_error = is_error
        
    def write(self, data):
        # Write to original stream (terminal)
        self.original.write(data)
        self.original.flush()
        
        # Write to buffer for later processing
        self.buffer.write(data)
        
        # If it's a complete line, add to GUI logs immediately
        if '\n' in data:
            lines = data.strip().split('\n')
            for line in lines:
                if line.strip():
                    # Clean up progress bar artifacts and other noise
                    clean_line = self._clean_line(line.strip())
                    if clean_line:
                        level = "ERROR" if self.is_error else "INFO"
                        self.gui_framework.add_log(level, clean_line)
                        
                        # Update log display in real time
                        try:
                            self.log_container.empty()
                            self.gui_framework.display_logs(self.log_container)
                        except:
                            pass
        
        return len(data)
    
    def _clean_line(self, line):
        """Clean up log line for GUI display"""
        # Skip progress bar artifacts
        if '█' in line or '100%|' in line or line.startswith('Downloading'):
            return None
            
        # Skip empty lines or just whitespace
        if not line or line.isspace():
            return None
            
        # Extract useful information from tqdm progress
        if '%|' in line and '/s]' in line:
            # Extract progress info from tqdm
            try:
                if 'it/s' in line or 'files/s' in line:
                    return f"Processing: {line.split('|')[0].strip()}"
            except:
                pass
            return None
            
        return line
    
    def flush(self):
        self.original.flush()


# ==================================================================================
# STANDARDIZED GUI FRAMEWORK - Template for All Parts
# ==================================================================================

class ToolGUIFramework(ABC):
    """Base framework class for standardized tool GUIs"""
    
    def __init__(self, tool_name: str, tool_version: str, tool_description: str):
        self.tool_name = tool_name
        self.tool_version = tool_version 
        self.tool_description = tool_description
        self.config = self.create_config_class()
        self.logger = None
        self.session_keys = self._define_session_keys()
        
    @abstractmethod
    def create_config_class(self):
        """Each tool implements its own configuration class"""
        pass
        
    @abstractmethod
    def _define_session_keys(self) -> Dict[str, Any]:
        """Define session state keys specific to each tool"""
        pass
        
    @abstractmethod
    def render_input_sections(self):
        """Render tool-specific input configuration sections"""
        pass
        
    @abstractmethod
    def validate_inputs(self) -> tuple[bool, List[str]]:
        """Validate tool-specific inputs"""
        pass
        
    @abstractmethod
    def execute_processing(self, **kwargs) -> bool:
        """Execute tool-specific processing"""
        pass
    
    def setup_page(self):
        """Standard page setup with consistent styling"""
        st.set_page_config(
            page_title=self.tool_name,
            page_icon="🌧️",
            layout="wide",
            initial_sidebar_state="expanded"
        )
        
        # Consistent styling across all tools
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

    def initialize_session(self):
        """Initialize session state with tool-specific keys"""
        for key, default_value in self.session_keys.items():
            if key not in st.session_state:
                st.session_state[key] = default_value

    def render_header(self):
        """Render standardized header"""
        st.markdown(f"""
        <div class="main-header">
            <h1>🌧️ {self.tool_name}</h1>
            <h3>Version {self.tool_version}</h3>
            <p>{self.tool_description}</p>
        </div>
        """, unsafe_allow_html=True)

    def render_sidebar_controls(self):
        """Render standardized sidebar processing controls"""
        st.sidebar.markdown("### 🔧 Processing Controls")
        
        # Process button
        process_button = st.sidebar.button(
            "🚀 Start Processing",
            type="primary",
            use_container_width=True,
            help="Begin processing with current configuration"
        )
        
        # Processing status
        if st.session_state.get('processing_completed', False):
            st.sidebar.markdown('<div class="success-msg">✅ Processing Completed!</div>', 
                              unsafe_allow_html=True)
        
        return process_button

    def render_logs_section(self):
        """Render standardized processing logs section"""
        st.sidebar.markdown("### 📋 Processing Logs")
        
        if st.sidebar.button("Clear Logs", use_container_width=True):
            st.session_state.processing_logs = []
            st.rerun()
        
        log_container = st.sidebar.container()
        self.display_logs(log_container)

    def display_logs(self, container):
        """Display logs in standardized terminal style"""
        logs = st.session_state.get('processing_logs', [])
        if logs:
            log_text = "\n".join(logs)
            container.markdown(f'<div class="log-display">{log_text}</div>', 
                             unsafe_allow_html=True)
        else:
            container.info("Processing logs will appear here...")

    def browse_folder(self, label: str, default_path: str = "") -> Optional[str]:
        """Standardized folder browser using tkinter"""
        if st.button(f"📁 Browse", key=f"browse_{label}", help="Browse for folder"):
            try:
                root = tk.Tk()
                root.withdraw()
                root.attributes('-topmost', True)
                
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

    def add_log(self, level: str, message: str):
        """Add log entry to session state"""
        timestamp = time.strftime("%H:%M:%S")
        log_entry = f"[{timestamp}] {level}: {message}"
        
        if 'processing_logs' not in st.session_state:
            st.session_state.processing_logs = []
        st.session_state.processing_logs.append(log_entry)

    @contextlib.contextmanager
    def capture_logs(self, log_container):
        """Context manager to capture stdout/stderr and core engine logs"""
        # Create string buffers to capture output
        stdout_buffer = io.StringIO()
        stderr_buffer = io.StringIO()
        
        # Setup logging handler to capture logging output
        log_capture_handler = LogCaptureHandler(self)
        logger = logging.getLogger()
        original_level = logger.level
        logger.setLevel(logging.INFO)
        logger.addHandler(log_capture_handler)
        
        # Redirect stdout and stderr
        original_stdout = sys.stdout
        original_stderr = sys.stderr
        
        try:
            # Use tee-like functionality to capture while still showing output
            sys.stdout = TeeOutput(original_stdout, stdout_buffer, self, log_container)
            sys.stderr = TeeOutput(original_stderr, stderr_buffer, self, log_container, is_error=True)
            
            yield
            
        finally:
            # Restore original streams
            sys.stdout = original_stdout
            sys.stderr = original_stderr
            
            # Remove log handler
            logger.removeHandler(log_capture_handler)
            logger.setLevel(original_level)
            
            # Capture any remaining output
            stdout_content = stdout_buffer.getvalue()
            stderr_content = stderr_buffer.getvalue()
            
            if stdout_content.strip():
                for line in stdout_content.strip().split('\n'):
                    if line.strip():
                        self.add_log("INFO", line.strip())
            
            if stderr_content.strip():
                for line in stderr_content.strip().split('\n'):
                    if line.strip():
                        self.add_log("ERROR", line.strip())

    def show_success_message(self, message: str):
        """Display standardized success message"""
        st.markdown(f'<div class="success-msg">✅ {message}</div>', unsafe_allow_html=True)

    def show_error_message(self, message: str):
        """Display standardized error message"""
        st.markdown(f'<div class="error-msg">❌ {message}</div>', unsafe_allow_html=True)

    def run(self):
        """Main execution method - template pattern"""
        self.setup_page()
        self.initialize_session()
        self.render_header()
        
        # Main layout
        main_col, sidebar_col = st.columns([3, 1])
        
        with main_col:
            # Tool-specific input sections
            self.render_input_sections()
        
        with sidebar_col:
            # Standardized sidebar controls
            process_button = self.render_sidebar_controls()
            self.render_logs_section()
            
            # Tool information section
            self.render_tool_info()
        
        # Handle processing execution
        if process_button:
            is_valid, errors = self.validate_inputs()
            if is_valid:
                success = self.execute_processing()
                if success:
                    st.session_state.processing_completed = True
                    self.show_success_message("Processing completed successfully!")
                else:
                    self.show_error_message("Processing failed. Check logs for details.")
            else:
                st.error("Please correct the following issues:")
                for error in errors:
                    st.write(f"• {error}")

    def render_tool_info(self):
        """Render standardized tool information section"""
        with st.expander("ℹ️ Tool Information", expanded=False):
            st.markdown(f"""
            ### 🚀 About {self.tool_name}
            
            **Version:** {self.tool_version}  
            **Description:** {self.tool_description}
            
            ### 📚 Quick Start Guide
            1. Configure output directory
            2. Define area of interest
            3. Set processing parameters
            4. Click "Start Processing"
            
            ### 🔗 Documentation
            For detailed documentation and examples, visit the project repository.
            """)


# ==================================================================================
# NOAA GRID MINER SPECIFIC IMPLEMENTATION
# ==================================================================================

class NOAAGridMinerConfig:
    """Configuration management for NOAA Grid Miner"""
    
    def __init__(self):
        self.TOOL_ROOT = Path(__file__).parent
        self.SUPPORT_DATA = self.TOOL_ROOT / "support_data"
        self.US_STATES_PATH = self.SUPPORT_DATA / "US_States" / "tl_2021_us_state.shp"
        self.DEFAULT_OUTPUT = self.TOOL_ROOT / "output"
        
        # Create directories
        for directory in [self.SUPPORT_DATA, self.DEFAULT_OUTPUT]:
            directory.mkdir(parents=True, exist_ok=True)


class NOAAGridMinerGUI(ToolGUIFramework):
    """NOAA Atlas 14 Grid Miner GUI - Part 1 of 3-part workflow"""
    
    def __init__(self):
        super().__init__(
            tool_name="NOAA Atlas 14 Grid Miner",
            tool_version="2.0.0",
            tool_description="Download and process NOAA precipitation grids for your project area"
        )
        
        # Import core processing module
        try:
            from NOAA_GridMiner import EnhancedNOAAGrids, Config as NOAAConfig
            self.processor_class = EnhancedNOAAGrids
            self.noaa_config = NOAAConfig
            self.import_success = True
            self.import_error = None
        except ImportError as e:
            self.import_success = False
            self.import_error = str(e)

    def create_config_class(self):
        """Create NOAA-specific configuration"""
        return NOAAGridMinerConfig()

    def _define_session_keys(self) -> Dict[str, Any]:
        """Define NOAA Grid Miner session state keys"""
        return {
            'processing_logs': [],
            'processing_completed': False,
            'output_directory': None
        }

    def check_import_status(self) -> bool:
        """Check if core processing module is available"""
        if not self.import_success:
            self.show_error_message(f"Cannot import NOAA_GridMiner.py: {self.import_error}")
            st.info("Please ensure NOAA_GridMiner.py is in the same directory as this GUI script.")
            return False
        return True

    def render_input_sections(self):
        """Render NOAA Grid Miner specific input sections"""
        if not self.check_import_status():
            return

        # Output Configuration
        self.render_output_configuration()
        
        # Area of Interest Definition
        self.render_aoi_configuration()
        
        # NOAA Zones Shapefile
        self.render_zones_configuration()
        
        # Processing Configuration
        self.render_processing_configuration()

    def render_output_configuration(self):
        """Render output directory configuration section"""
        st.markdown('<div class="section-header">📁 Output Configuration</div>', unsafe_allow_html=True)
        
        col1, col2 = st.columns([3, 1])
        
        with col1:
            default_output_full = str(self.config.DEFAULT_OUTPUT.resolve())
            base_dir = st.text_input(
                "Output Directory",
                value=default_output_full,
                help="Directory where all processed grids will be stored",
                placeholder="C:/Projects/NOAA/Output"
            )
        
        with col2:
            browsed_dir = self.browse_folder("Output Directory", str(self.config.DEFAULT_OUTPUT.parent))
            if browsed_dir:
                base_dir = browsed_dir
                st.rerun()
        
        if base_dir:
            try:
                Path(base_dir).mkdir(parents=True, exist_ok=True)
                self.show_success_message(f"Output directory ready: {base_dir}")
                st.session_state.output_directory = base_dir
            except Exception as e:
                self.show_error_message(f"Cannot create directory: {e}")

    def render_aoi_configuration(self):
        """Render area of interest configuration section"""
        st.markdown('<div class="section-header">🗺️ Area of Interest Definition</div>', unsafe_allow_html=True)
        
        aoi_method = st.radio(
            "Select method to define your area of interest:",
            ["Upload Project Area Shapefile", "Select NOAA Atlas 14 Volume(s)"],
            help="Choose the method that best fits your analysis needs"
        )
        
        if aoi_method == "Upload Project Area Shapefile":
            self.render_shapefile_upload()
        else:
            self.render_volume_selection()

    def render_shapefile_upload(self):
        """Render shapefile upload configuration"""
        st.markdown("**📤 Shapefile Upload**")
        
        prj_area_files = st.file_uploader(
            "Upload ALL shapefile components (.shp, .shx, .dbf, .prj required)",
            type=["shp", "shx", "dbf", "prj", "cpg", "qpj"],
            accept_multiple_files=True,
            help="Upload all components for best compatibility"
        )
        
        if prj_area_files:
            prj_area_shp_path = self.copy_shapefile_components(prj_area_files)
            if prj_area_shp_path:
                self.show_success_message(f"Project area shapefile ready: {Path(prj_area_shp_path).name}")
                st.session_state.prj_area_shp_path = prj_area_shp_path

    def render_volume_selection(self):
        """Render NOAA volume selection interface"""
        st.markdown("**📍 Available NOAA Atlas 14 Volumes**")
        
        selected_volumes = []
        volumes_sorted = sorted(self.noaa_config.ATLAS14_VOLUMES.items(), key=lambda x: x[1]['volume'])
        
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
            st.session_state.volume_codes = selected_volumes
            self.show_success_message(f"Selected volumes: {', '.join(selected_volumes)}")

    def render_zones_configuration(self):
        """Render NOAA zones shapefile configuration"""
        st.markdown('<div class="section-header">🌍 NOAA Atlas 14 Zones Shapefile</div>', unsafe_allow_html=True)
        
        use_builtin_states = st.checkbox(
            "Use built-in NOAA zones shapefile",
            value=True,
            help="Use the included NOAA Atlas 14 zones shapefile"
        )
        
        if use_builtin_states:
            builtin_path = self.find_builtin_shapefile()
            if builtin_path:
                st.session_state.states_shp_path = builtin_path
                self.show_success_message(f"Using built-in shapefile: {Path(builtin_path).name}")
                st.info(f"📁 Location: {self.config.US_STATES_PATH}")
            else:
                self.show_error_message(f"Built-in shapefile not found: {self.config.US_STATES_PATH}")
        else:
            states_files = st.file_uploader(
                "Upload NOAA zones shapefile components",
                type=["shp", "shx", "dbf", "prj"],
                accept_multiple_files=True,
                help="Upload all components of the NOAA Atlas 14 zones shapefile"
            )
            
            if states_files:
                states_shp_path = self.copy_shapefile_components(states_files)
                if states_shp_path:
                    st.session_state.states_shp_path = states_shp_path

    def render_processing_configuration(self):
        """Render processing parameters configuration"""
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
            st.session_state.series_type = series_type
            
            # Recurrence Intervals
            st.markdown("**Recurrence Intervals (Years):**")
            interval_options = ["all"] + sorted(list(self.noaa_config.VALID_EVENTS), key=int)
            selected_intervals = st.multiselect(
                "Select intervals:",
                options=interval_options,
                default=["all"],
                help="Select specific recurrence intervals or 'all' for complete dataset"
            )
            
        with col2:
            # Storm Durations
            st.markdown("**Storm Durations:**")
            minutes = sorted([d for d in self.noaa_config.VALID_DURATIONS if d.endswith('m')], key=lambda x: int(x[:-1]))
            hours = sorted([d for d in self.noaa_config.VALID_DURATIONS if d.endswith('h')], key=lambda x: int(x[:-1]))
            duration_options = ["all"] + minutes + hours
            
            selected_durations = st.multiselect(
                "Select durations:",
                options=duration_options,
                default=["all"],
                help="Select specific durations or 'all' for complete dataset"
            )
            
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
        
        # Store configuration in session state
        st.session_state.selected_intervals = selected_intervals
        st.session_state.selected_durations = selected_durations
        st.session_state.ci_100yr = ci_100yr
        st.session_state.calculate_stats = calculate_stats

    def validate_inputs(self) -> tuple[bool, List[str]]:
        """Validate NOAA Grid Miner inputs"""
        errors = []
        
        # Check output directory
        if not st.session_state.get('output_directory'):
            errors.append("Output directory is required")
        
        # Check AOI definition
        has_shapefile = st.session_state.get('prj_area_shp_path')
        has_volumes = st.session_state.get('volume_codes')
        if not has_shapefile and not has_volumes:
            errors.append("Area of interest must be defined (shapefile or volumes)")
        
        # Check NOAA zones shapefile
        if not st.session_state.get('states_shp_path'):
            errors.append("NOAA zones shapefile is required")
        
        # Check intervals and durations
        if not st.session_state.get('selected_intervals'):
            errors.append("At least one recurrence interval must be selected")
        if not st.session_state.get('selected_durations'):
            errors.append("At least one duration must be selected")
        
        return len(errors) == 0, errors

    def execute_processing(self) -> bool:
        """Execute NOAA Grid Miner processing with real-time log capture"""
        
        # Create a placeholder for real-time log updates
        st.markdown("---")
        st.markdown("### 📊 Processing Results")
        
        # Display processing configuration
        with st.expander("📋 Processing Configuration", expanded=True):
            col1, col2 = st.columns(2)
            
            with col1:
                st.write(f"**Output Directory:** {st.session_state['output_directory']}")
                if st.session_state.get('prj_area_shp_path'):
                    shp_name = Path(st.session_state['prj_area_shp_path']).name
                    st.write(f"**AOI Method:** Shapefile ({shp_name})")
                if st.session_state.get('volume_codes'):
                    st.write(f"**AOI Method:** Volume Selection ({', '.join(st.session_state['volume_codes'])})")
            
            with col2:
                selected_intervals = st.session_state.get('selected_intervals', [])
                selected_durations = st.session_state.get('selected_durations', [])
                event_list = list(self.noaa_config.VALID_EVENTS) if "all" in selected_intervals else selected_intervals
                dur_list = list(self.noaa_config.VALID_DURATIONS) if "all" in selected_durations else selected_durations
                
                st.write(f"**Events:** {len(event_list)} intervals")
                st.write(f"**Durations:** {len(dur_list)} periods")
                st.write(f"**Series Type:** {st.session_state.get('series_type', 'PDS')}")
        
        # Create progress bar and log container
        progress_bar = st.progress(0, text="Initializing processing...")
        log_display_container = st.container()
        
        try:
            # Initialize processing
            self.add_log("INFO", "Starting NOAA grid processing")
            self.add_log("INFO", f"Processing {len(event_list)} events × {len(dur_list)} durations")
            
            # Initialize processor
            processor = self.processor_class()
            inputs = {"calculate_stats": st.session_state.get('calculate_stats', False)}
            
            progress_bar.progress(10, text="Setting up processor...")
            
            # Execute processing with log capture
            start_time = time.time()
            success = False
            
            with self.capture_logs(log_display_container):
                progress_bar.progress(25, text="Processing grids...")
                
                try:
                    processor.process_grids(
                        base_dir=st.session_state['output_directory'],
                        prj_area_shp_path=st.session_state.get('prj_area_shp_path'),
                        states_shp_path=str(st.session_state['states_shp_path']),
                        volume_codes=st.session_state.get('volume_codes'),
                        event_list=event_list,
                        dur_list=dur_list,
                        series_types=[st.session_state.get('series_type', 'PDS')],
                        CI_100yr=st.session_state.get('ci_100yr', True),
                        inputs=inputs
                    )
                    # If we get here without exception, processing succeeded
                    success = True
                    progress_bar.progress(100, text="Processing completed!")
                    
                except Exception as e:
                    success = False
                    self.add_log("ERROR", f"Processing error: {str(e)}")
                    progress_bar.progress(0, text="Processing failed!")
            
            # Processing completed
            elapsed_time = time.time() - start_time
            hours, rem = divmod(elapsed_time, 3600)
            minutes, seconds = divmod(rem, 60)
            
            if success:
                self.add_log("SUCCESS", f"Processing completed in {elapsed_time:.1f} seconds")
                
                # Display timing and location info
                col1, col2 = st.columns(2)
                with col1:
                    st.info(f"⏱️ Processing time: {int(hours)}h {int(minutes)}m {round(seconds, 2)}s")
                with col2:
                    st.info(f"📁 Output location: {st.session_state['output_directory']}")
                
                # Display results
                self.display_results()
                
                return True
            else:
                self.add_log("ERROR", "Processing failed - check logs above for details")
                return False
                
        except Exception as e:
            progress_bar.progress(0, text="Processing failed!")
            self.add_log("ERROR", f"Critical error: {str(e)}")
            
            with st.expander("🔍 Error Details"):
                st.exception(e)
            
            return False

    def display_results(self):
        """Display processing results"""
        with st.expander("📂 Output Structure", expanded=True):
            try:
                base_path = Path(st.session_state['output_directory'])
                series_type = st.session_state.get('series_type', 'PDS')
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

    # Helper methods
    def copy_shapefile_components(self, uploaded_files):
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

    def find_builtin_shapefile(self):
        """Find built-in NOAA zones shapefile"""
        if self.config.US_STATES_PATH.exists():
            return str(self.config.US_STATES_PATH)
        return None


# ==================================================================================
# MAIN APPLICATION ENTRY POINT
# ==================================================================================

def main():
    """Main application entry point"""
    app = NOAAGridMinerGUI()
    app.run()


if __name__ == "__main__":
    main()
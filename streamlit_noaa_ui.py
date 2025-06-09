# streamlit_noaa_ui_alt.py - Alternative port version
import streamlit as st
from pathlib import Path
import os
import tempfile
import shutil
import logging
from typing import List, Optional, Dict, Any
import time
from download_noaa_grids import NOAAGrids, Config
import sys

# Set an alternative port via environment variable (before importing streamlit)
os.environ['STREAMLIT_SERVER_PORT'] = '8502'  # Try an alternative port

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def setup_page():
    """Configure the Streamlit page settings"""
    st.set_page_config(
        page_title="NOAA Atlas 14 Precipitation Grids",
        page_icon="🌧️",
        layout="wide",
        initial_sidebar_state="expanded"
    )
    
    st.title("NOAA Atlas 14 Grids Miner")
    st.markdown("""
    This tool downloads, processes, and mosaics NOAA Atlas 14 precipitation grids (partial duration series) for a given project area.
    Upload the required shapefiles, select your options, and click Process to begin.
    """)

    # Add an info box with the welcome message
    with st.expander("ℹ️ About this Tool", expanded=False):
        st.markdown("""
        **Key Features:**
        - ✅ Automated Grid Retrieval from NOAA servers
        - ✅ Smart Zone Detection for your project area
        - ✅ Grid Mosaicking across zone boundaries
        - ✅ 90% Confidence Intervals for 100-year events
        - ✅ Simple, user-friendly interface                    
        - ✅ Supports multiple recurrence intervals and durations
        """)



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

def get_user_inputs() -> Dict[str, Any]:
    """Collect and validate user inputs using Streamlit widgets"""
    st.header("Configuration Settings")
    
    with st.container():
        col1, col2 = st.columns(2)
        
        with col1:
            st.subheader("Base Directory")
            base_dir = st.text_input(
                "Enter the base directory where all data will be stored",
                help="e.g., D:/Projects/NOAA/Precipitation"
            )
            
            st.subheader("Shapefile Uploads")
            st.markdown("##### NOAA Atlas 14 Zones Shapefile")
            
            # Option to use built-in shapefile
            use_builtin_states = st.checkbox(
                "Use built-in NOAA Zones shapefile (US_States folder)",
                value=True,
                help=(
                    "Use the NOAA Atlas 14 zones shapefile included in the US_States folder. "
                    "NOAA Atlas 14 divides the United States and territories into zones, each corresponding to a published volume:\n\n"
                    "• Volume 1: Semiarid Southwest (sw)\n"
                    "• Volume 2: Ohio River Basin and Surrounding States (orb)\n"
                    "• Volume 3: Puerto Rico and the U.S. Virgin Islands (pr)\n"
                    "• Volume 4: Hawaiian Islands (hi)\n"
                    "• Volume 5: Selected Pacific Islands (see sub-regions)\n"
                    "• Volume 6: California (sw)\n"
                    "• Volume 7: Alaska (ak)\n"
                    "• Volume 8: Midwestern States (mw)\n"
                    "• Volume 9: Southeastern States (se)\n"
                    "• Volume 10: Northeastern States (ne)\n"
                    "• Volume 11: Texas (tx)\n"
                    "• Volume 12: Interior Northwest (inw)\n\n"
                    "Select this option to use the built-in shapefile for these NOAA Atlas 14 zones."
                )
            )
            
            states_files = None
            if not use_builtin_states:
                states_files = st.file_uploader(
                    "Upload ALL files for the NOAA zones shapefile (.shp, .shx, .dbf, .prj required)",
                    type=["shp", "shx", "dbf", "prj"], 
                    accept_multiple_files=True,
                    help="These files define the NOAA Atlas 14 zones"
                )
            
            st.markdown(
                "##### Project Area Shapefile",
                help="The uploaded shapefile should contain a single polygon feature representing your project area with an optional buffer. Do not upload a shapefile with multiple polygons."
            )
            
            # Option to use built-in shapefile
            use_builtin_project = st.checkbox(
                "Use built-in Project Area shapefile)",
                value=False,
                help=(
                    "Use the project area shapefile included in the Project_Area folder. "
                    "This is a sample shapefile provided for testing the app. "
                    "If you have a defined project area, please upload your own shapefile."
                )
            )
            
            prj_area_files = None
            if not use_builtin_project:
                prj_area_files = st.file_uploader(
                    "Upload ALL files for your project area shapefile (.shp, .shx, .dbf, and .prj required)",
                    type=["shp", "shx", "dbf", "prj"], 
                    accept_multiple_files=True,
                    help="These files define your project area"
                )
        
        with col2:
            st.subheader("Processing Options")
            
            # Recurrence Intervals
            st.markdown("##### Recurrence Intervals (Years)")
            interval_options = ["all"] + sorted(list(Config.VALID_EVENTS), key=int)
            selected_intervals = st.multiselect(
                "Select one or more recurrence intervals",
                options=interval_options,
                default=["all"],
                help="'all' will process all available intervals"
            )
            
            # Durations
            st.markdown("##### Durations")
            # Sort durations (minutes first, then hours)
            minutes = sorted([d for d in Config.VALID_DURATIONS if d.endswith('m')], key=lambda x: int(x[:-1]))
            hours = sorted([d for d in Config.VALID_DURATIONS if d.endswith('h')], key=lambda x: int(x[:-1]))
            duration_options = ["all"] + minutes + hours
            
            selected_durations = st.multiselect(
                "Select one or more durations",
                options=duration_options,
                default=["all"],
                help="'all' will process all available durations"
            )
            
            # Confidence Intervals
            st.markdown("##### Additional Options")
            ci_100yr = st.checkbox(
                "Include 100-Year Confidence Interval Grids",
                value=True,
                help="Generate 90% confidence interval grids for 100-year events"
            )
    
    return {
        "base_dir": base_dir,
        "use_builtin_states": use_builtin_states,
        "states_files": states_files,
        "use_builtin_project": use_builtin_project,
        "prj_area_files": prj_area_files,
        "events": selected_intervals,
        "durations": selected_durations,
        "ci_100yr": ci_100yr
    }

def find_builtin_shapefile(folder_name):
    """Find a shapefile in a built-in folder"""
    current_dir = os.path.dirname(os.path.abspath(__file__))
    folder_path = os.path.join(current_dir, folder_name)
    
    if not os.path.isdir(folder_path):
        return None
    
    # Find shapefile in folder
    shp_files = list(Path(folder_path).glob("*.shp"))
    if not shp_files:
        return None
        
    return str(shp_files[0])

def validate_inputs(inputs: Dict[str, Any]) -> Dict[str, Any]:
    """Validate user inputs and prepare for processing"""
    errors = []
    temp_paths = []
    states_shp_path = None
    prj_area_shp_path = None
    
    # Validate base directory
    if not inputs["base_dir"]:
        errors.append("Base directory is required")
    else:
        base_path = Path(inputs["base_dir"])
        if not base_path.exists():
            try:
                base_path.mkdir(parents=True, exist_ok=True)
            except Exception as e:
                errors.append(f"Cannot create base directory: {str(e)}")
    
    # Process NOAA Zones shapefile
    if inputs["use_builtin_states"]:
        states_shp_path = find_builtin_shapefile("US_States")
        if not states_shp_path:
            errors.append("Could not find .shp file in the US_States folder")
    elif not inputs["states_files"]:
        errors.append("NOAA Zones shapefile files are required")
    else:
        states_shp_path = copy_files_to_single_dir(inputs["states_files"], "noaa_zones")
        if not states_shp_path:
            errors.append("Missing .shp file in NOAA Zones shapefile upload")
        else:
            temp_paths.append(states_shp_path)
            
    # Process Project Area shapefile
    if inputs["use_builtin_project"]:
        prj_area_shp_path = find_builtin_shapefile("Project Area")
        if not prj_area_shp_path:
            errors.append("Could not find .shp file in the Project_Area folder")
    elif not inputs["prj_area_files"]:
        errors.append("Project Area shapefile files are required")
    else:
        prj_area_shp_path = copy_files_to_single_dir(inputs["prj_area_files"], "project_area")
        if not prj_area_shp_path:
            errors.append("Missing .shp file in Project Area shapefile upload")
        else:
            temp_paths.append(prj_area_shp_path)
    
    # Validate shapefile components if paths were created
    if states_shp_path and prj_area_shp_path:
        for shp_path, label in [(states_shp_path, "NOAA Zones"), (prj_area_shp_path, "Project Area")]:
            base = Path(shp_path).with_suffix('')
            for ext in ['.shp', '.shx', '.dbf']:
                if not base.with_suffix(ext).exists():
                    errors.append(f"Missing {ext} file for {label} shapefile")
    
    # Process events and durations
    if "all" in inputs["events"]:
        event_list = list(Config.VALID_EVENTS)
    else:
        event_list = inputs["events"]
        if not set(event_list).issubset(Config.VALID_EVENTS):
            errors.append(f"Invalid events. Valid options are: {', '.join(sorted(Config.VALID_EVENTS, key=int))}")
    
    if "all" in inputs["durations"]:
        dur_list = list(Config.VALID_DURATIONS)
    else:
        dur_list = inputs["durations"]
        if not set(dur_list).issubset(Config.VALID_DURATIONS):
            errors.append(f"Invalid durations. Valid options are: {', '.join(sorted(Config.VALID_DURATIONS))}")
    
    return {
        "valid": len(errors) == 0,
        "errors": errors,
        "base_dir": inputs["base_dir"] if "base_dir" in inputs else None,
        "states_shp_path": states_shp_path,
        "prj_area_shp_path": prj_area_shp_path,
        "event_list": event_list if "event_list" in locals() else None,
        "dur_list": dur_list if "dur_list" in locals() else None,
        "ci_100yr": inputs["ci_100yr"],
        "temp_paths": temp_paths
    }

def cleanup_temp_dirs(paths: List[str]) -> None:
    """Clean up temporary directories"""
    for path in paths:
        if path and Path(path).exists() and "temp" in str(Path(path).parent):
            try:
                shutil.rmtree(Path(path).parent)
                logger.info(f"Cleaned up temporary directory: {Path(path).parent}")
            except Exception as e:
                logger.warning(f"Failed to clean up {path}: {e}")

def process_noaa_grids(validated_inputs: Dict[str, Any], progress_bar) -> str:
    """Process NOAA grid data with progress reporting"""
    temp_paths = validated_inputs["temp_paths"]
    
    try:
        # Configure GDAL to allow restoring .shx files
        os.environ['SHAPE_RESTORE_SHX'] = 'YES'
        
        processor = NOAAGrids()
        progress_bar.progress(10, text="Initializing processing...")
        
        processor.process_grids(
            base_dir=validated_inputs["base_dir"],
            prj_area_shp_path=validated_inputs["prj_area_shp_path"],
            states_shp_path=validated_inputs["states_shp_path"],
            event_list=validated_inputs["event_list"],
            dur_list=validated_inputs["dur_list"],
            CI_100yr=validated_inputs["ci_100yr"]
        )
        
        progress_bar.progress(100, text="Processing complete!")
        return f"Processing completed successfully. Output location: {validated_inputs['base_dir']}"
    
    except Exception as e:
        logger.exception("Error in processing")
        return f"Error during processing: {str(e)}"
    
    finally:
        # Clean up temporary directories
        cleanup_temp_dirs(temp_paths)

def main():
    """Main application function"""
    setup_page()
    
    # Create sidebar with instructions
    with st.sidebar:
        st.header("Instructions")
        st.markdown("""
        ### Step 1: Setup
        - Enter a base directory for outputs
        - Use built-in shapefiles or upload your own
        
        ### Step 2: Configure
        - Select recurrence intervals
        - Select durations
        - Choose whether to include confidence intervals
        
        ### Step 3: Process
        - Click the Process button
        - Wait for processing to complete
        - Results will be saved to your base directory
        """)


        st.markdown("---")
        st.markdown("### References:")
        st.markdown("""
        1. [FEMA: 2D Watershed Modeling in HEC-RAS Recommended Practices](https://webapps.usgs.gov/infrm/pubs/211203_HUC8_2D_Watershed_Modeling_Recommendations.pdf)
        2. [Precipitation Frequency Estimates in GIS Compatible Format](https://hdsc.nws.noaa.gov/pfds/pfds_gis.html)
        """)
    
    # Get user inputs
    inputs = get_user_inputs()
    
    # Create a container for results
    results_container = st.container()
    
    # Process button
    col1, col2, col3 = st.columns([1, 1, 1])
    with col2:
        process_button = st.button("Process NOAA Grids", type="primary")
    
    # Handle processing
    if process_button:
        with results_container:
            st.subheader("Processing Results")
            
            # Validate inputs
            validated = validate_inputs(inputs)
            
            if not validated["valid"]:
                st.error("Please correct the following errors:")
                for error in validated["errors"]:
                    st.warning(error)
            else:
                progress_bar = st.progress(0, text="Starting processing...")
                
                # Show a spinner during processing
                with st.spinner("Processing NOAA grids. This may take some time..."):
                    start_time = time.time()
                    result = process_noaa_grids(validated, progress_bar)
                    elapsed_time = time.time() - start_time
                
                # Show result
                if "Error" in result:
                    st.error(result)
                else:
                    st.success(result)
                    
                    # Show elapsed time
                    hours, rem = divmod(elapsed_time, 3600)
                    minutes, seconds = divmod(rem, 60)
                    st.info(f"Processing completed in {int(hours)}h {int(minutes)}m {round(seconds, 2)}s")
                    
                    # Show output location
                    st.markdown(f"**Output Location:** `{validated['base_dir']}`")

if __name__ == "__main__":
    main()
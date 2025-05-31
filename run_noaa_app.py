# run_noaa_app_alt.py - Simple direct runner with elevated permissions
import os
import sys
import subprocess
import time

def run_as_admin():
    """Re-run the script with admin privileges if possible"""
    try:
        if sys.platform == 'win32':
            import ctypes
            if not ctypes.windll.shell32.IsUserAnAdmin():
                print("Attempting to run with administrator privileges...")
                ctypes.windll.shell32.ShellExecuteW(None, "runas", sys.executable, " ".join(sys.argv), None, 1)
                return True
    except Exception as e:
        print(f"Failed to elevate privileges: {e}")
    return False

def main():
    """Direct runner bypassing socket issues"""
    print("NOAA Atlas 14 Precipitation Grid Downloader - Alternative Runner")
    print("="*60)
    
    # Find python and app path
    current_dir = os.path.dirname(os.path.abspath(__file__))
    app_file = os.path.join(current_dir, "streamlit_noaa_ui.py")
    
    if not os.path.isfile(app_file):
        print(f"Error: Could not find {app_file}")
        print("Please make sure streamlit_noaa_ui.py is in the same directory as this script.")
        input("Press Enter to exit...")
        return
    
    # Try running directly with the current Python interpreter
    print("\nStarting Streamlit app with Python directly...")
    print(f"App path: {app_file}")
    print("Note: Using alternate port 8502 to avoid conflicts")
    print("\nThe app should open in your default web browser.")
    print("If it doesn't open automatically, look for a URL like http://localhost:8502")
    print("\nPress Ctrl+C to stop the application.\n")
    
    # Set environment variables
    os.environ['STREAMLIT_SERVER_PORT'] = '8502'  # Use alternate port
    os.environ['STREAMLIT_BROWSER_GATHER_USAGE_STATS'] = 'false'  # Disable stats
    
    try:
        # Direct import and run approach
        print("Running streamlit_noaa_ui.py directly...")
        
        # Change to the directory of the app file for proper path resolution
        original_dir = os.getcwd()
        os.chdir(current_dir)
        
        # Add the current directory to path
        if current_dir not in sys.path:
            sys.path.insert(0, current_dir)
        
        # Run the module directly
        exec(open(app_file).read())
        
    except KeyboardInterrupt:
        print("\nApplication stopped by user.")
    except Exception as e:
        print(f"\nError running directly: {e}")
        print("\nTrying alternative method with subprocess...")
        
        try:
            # Try to run with Python directly
            commands = [
                [sys.executable, "-m", "streamlit", "run", app_file, "--server.port=8502"],
                [sys.executable, app_file]
            ]
            
            for cmd in commands:
                try:
                    print(f"Running command: {' '.join(cmd)}")
                    subprocess.run(cmd)
                    return
                except Exception as sub_e:
                    print(f"Command failed: {sub_e}")
            
            # If we get here, all commands failed
            print("\nAll automatic methods failed.")
            print("\nPlease try running these commands manually in your terminal:")
            print(f"1. streamlit run {app_file} --server.port=8502")
            print(f"2. python -m streamlit run {app_file} --server.port=8502")
            print(f"3. python {app_file}")
            
            # Try admin launch as a last resort
            if sys.platform == 'win32':
                admin_choice = input("\nWould you like to try running with admin privileges? (y/n): ")
                if admin_choice.lower() in ['y', 'yes']:
                    # Will restart with admin privileges
                    if run_as_admin():
                        return
        
        except KeyboardInterrupt:
            print("\nOperation cancelled by user.")
    
    finally:
        # Cleanup/restore environment
        if 'original_dir' in locals():
            os.chdir(original_dir)
        
        input("\nPress Enter to exit...")

if __name__ == "__main__":
    main()
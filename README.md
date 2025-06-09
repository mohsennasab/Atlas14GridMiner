
# 🌧️ NOAA Atlas 14 Grids Miner

An automated tool for downloading, processing, and mosaicking NOAA Atlas 14 precipitation grids for hydrological analysis and flood modeling projects.

## 📋 Overview

This application automates the complex process of obtaining precipitation frequency data from NOAA Atlas 14, which is essential for hydrological modeling, flood risk assessment, and infrastructure design. The tool intelligently identifies relevant NOAA zones based on your project area and seamlessly combines data across zone boundaries.

## ✨ Key Features

- 🚀 **Automated Grid Retrieval**: Downloads precipitation grids directly from NOAA servers  
- 🗺️ **Smart Zone Detection**: Automatically identifies intersecting NOAA Atlas 14 zones for your project area  
- 🧩 **Grid Mosaicking**: Seamlessly combines grids across zone boundaries using maximum value method  
- 📊 **Confidence Intervals**: Generates 90% confidence interval grids for 100-year events  
- 🖥️ **Dual Interface**: Both web-based GUI and command-line interfaces available  
- ⚡ **Parallel Processing**: Multi-threaded downloads and processing for improved performance  
- 📁 **Organized Output**: Well-structured output folders with clear naming conventions  

## 🛠️ Installation

### Prerequisites

- Python 3.11+  
- Pixi package manager (recommended) or conda/pip  

### Using Pixi (Recommended)

```bash
git clone <repository-url>
cd NOAA-Atlas-14-Grids-Miner
pixi install
pixi shell
```

### Using Conda/Pip

```bash
conda create -n noaa-grids python=3.11
conda activate noaa-grids
pip install streamlit>=1.25.0 requests>=2.32.3 geopandas>=1.0.1 rasterio>=1.4.3 numpy>=2.2.4 tqdm>=4.67.1 scipy>=1.15.2 gdal>=3.10.2
```

## 🚀 Usage

### Web Interface (Recommended)

```bash
python run_noaa_app.py
```

Open your browser and navigate to `http://localhost:8502`

#### Configure settings:

- Set base directory for outputs  
- Upload project area shapefile (or use built-in sample)  
- Select recurrence intervals (1, 2, 5, 10, 25, 50, 100, 200, 500, 1000 years)  
- Choose durations (5m to 24h)  
- Enable/disable confidence intervals  

Click **"Process NOAA Grids"** and monitor progress

### Command Line Interface

```bash
python download_noaa_grids.py
```

Follow the interactive prompts to configure your processing parameters.

## 📂 Input Requirements

### Required Shapefiles

**Project Area Shapefile**: Defines your area of interest  
- Required: `.shp`, `.shx`, `.dbf`  
- Optional: `.prj` (recommended for proper CRS handling)  
- Will be automatically reprojected to NAD83 (EPSG:4269)  

**NOAA Atlas 14 Zones Shapefile**: Defines NOAA precipitation zones  
- Included in `US_States/` folder  
- Custom versions can be uploaded if needed  

## 🌎 NOAA Atlas 14 Zones Coverage

The tool supports all NOAA Atlas 14 volumes:

- Volume 1: Semiarid Southwest (sw)  
- Volume 2: Ohio River Basin and Surrounding States (orb)  
- Volume 3: Puerto Rico and the U.S. Virgin Islands (pr)  
- Volume 4: Hawaiian Islands (hi)  
- Volume 5: Selected Pacific Islands  
- Volume 6: California (sw)  
- Volume 7: Alaska (ak)  
- Volume 8: Midwestern States (mw)  
- Volume 9: Southeastern States (se)  
- Volume 10: Northeastern States (ne)  
- Volume 11: Texas (tx)  
- Volume 12: Interior Northwest (inw)  

## 📊 Output Structure

```
Base_Directory/
├── NOAA_grids/                    
│   ├── zone1_100yr_24h_a.asc     
│   └── ...
├── NOAA_grids_mosaic/             
│   ├── comb100yr24ha.asc          
│   ├── comb100yr24ha_plus.asc    
│   ├── comb100yr24ha_minus.asc    
│   └── ...
└── noaa_processing.log
```

### File Naming Convention

- `combXXyrYYa.asc`: Precipitation depth (XX = return period, YY = duration)  
- `combXXyrYYa_plus.asc`: Upper 84th percentile confidence interval  
- `combXXyrYYa_minus.asc`: Lower 16th percentile confidence interval  

## 🔧 Configuration Options

### Recurrence Intervals (Years)

1, 2, 5, 10, 25, 50, 100, 200, 500, 1000

### Durations

- Minutes: 5m, 10m, 15m, 30m  
- Hours: 1h, 2h, 3h, 6h, 12h, 24h  

### Processing Options

- Confidence Intervals: 90% confidence bands for 100-year events  
- Parallel Downloads: Configurable thread count for faster processing  
- Automatic Retry: Built-in retry mechanism for failed downloads  

## 🗂️ Project Structure

```
├── download_noaa_grids.py      
├── streamlit_noaa_ui.py        
├── run_noaa_app.py            
├── pixi.toml                  
├── .gitignore                 
├── US_States/                 
├── Project_Area/              
└── README.md                  
```

## 🔍 Troubleshooting

### Common Issues

**Encoding Error on Windows**  
- App will automatically fall back to subprocess method  
- App should still launch on `http://localhost:8502`  

**Missing Shapefile Components**  
- Ensure all required files (`.shp`, `.shx`, `.dbf`) are uploaded  
- `.prj` recommended for proper coordinate system handling  

**Download Failures**  
- Automatic retry is built-in  
- Check internet connection and NOAA server status  

**Memory Issues**  
- Process smaller areas or fewer parameters  
- Monitor system memory during processing  

### Getting Help

- Check processing log for detailed error info  
- Ensure dependencies are installed  
- Verify shapefile integrity and CRS  

## 🤝 Contributing

Contributions are welcome! Please:

- Follow existing code style and conventions  
- Add appropriate tests for new features  
- Update documentation as needed  
- Ensure all tests pass before submitting  

## 🔗 References

- FEMA: 2D Watershed Modeling in HEC-RAS Recommended Practices  
- NOAA: Precipitation Frequency Estimates in GIS Compatible Format  
- NOAA Atlas 14 Documentation  

## 📄 License

**Custom Open-Source License**  
Copyright (c) 2024 Mohsen Tahmasebi Nasab  

Permission is granted, free of charge, for personal, academic, or internal non-commercial use.  
Commercial use and redistribution (in part or full, modified or not) are not permitted without written permission.

### Disclaimer

The software is provided *as is*, without warranty of any kind. The author is not liable for any damages or claims arising from use.

---

*Built with ❤️ for the hydrology and water resources community*

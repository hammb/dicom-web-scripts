# DICOM to Zarr (Blosc) Converter

This project provides a Python script to convert DICOM series into Zarr arrays (using Blosc compression) and reconstruct them back into DICOM files.

## Features

- **DICOM to Zarr**: Converts a directory of DICOM files into a Zarr v3 array with Blosc compression (Zstd, bitshuffle).
- **Metadata Extraction**: Extracts DICOM tags and image metadata (origin, spacing, direction) into a separate JSON file.
- **Reconstruction**: Reconstructs DICOM files from the Zarr array and JSON metadata, verifying the round-trip process.

## Prerequisites

- Python 3.11+
- `pip` package manager

## Installation

1. Clone the repository (if applicable) or download the script.
2. Create and activate a Conda environment (optional but recommended):

   ```bash
   conda create -n dicom-web-scripts python=3.11
   conda activate dicom-web-scripts
   ```

3. Install the required dependencies:

   ```bash
   pip install -r requirements.txt
   ```

## Directory Structure

The script expects the following directory structure:

```
.
├── convert_to_blosc_and_back.py
├── requirements.txt
└── data/
    ├── raw/              # Place your input DICOM series folders here
    ├── converted/        # Output for Zarr arrays and JSON metadata
    └── reconstructed/    # Output for reconstructed DICOM files
```

## Usage

1. **Prepare Data**: Place your DICOM series folders inside `data/raw/`.
   - Example: `data/raw/patient1_scan/file1.dcm`, `data/raw/patient1_scan/file2.dcm`, etc.

2. **Run the Script**:

   ```bash
   python convert_to_blosc_and_back.py
   ```

3. **Check Results**:
   - **Converted Data**: Check `data/converted/` for `.zarr` directories and `.json` metadata files.
   - **Reconstructed Data**: Check `data/reconstructed/` for the reconstructed DICOM files.

## How It Works

1. **Loading**: The script scans `data/raw` for subdirectories. It uses `SimpleITK` to load the DICOM series from each folder.
2. **Conversion**:
   - The image data is converted to a NumPy array.
   - The array is saved to a Zarr store using the Zarr v3 format with Blosc compression (Zstd, level 1, bitshuffle).
   - Metadata (image geometry and DICOM tags) is saved to a JSON file.
3. **Reconstruction**:
   - The script reads the Zarr array and JSON metadata.
   - It reconstructs the SimpleITK image, restoring origin, spacing, and direction.
   - It writes the slices back as DICOM files to `data/reconstructed`, attempting to preserve the original filenames and tags.

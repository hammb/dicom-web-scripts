import json
import os
import shutil
import sys

import SimpleITK as sitk
import zarr
from numcodecs import Blosc

RAW_DIR = "data/raw"
CONVERTED_DIR = "data/converted"
RECONSTRUCTED_DIR = "data/reconstructed"


def save_metadata(image, reader, filenames, output_path):
    """Extracts and saves metadata from a SimpleITK image to a JSON file."""
    metadata = {
        "filenames": filenames,
        "origin": image.GetOrigin(),
        "spacing": image.GetSpacing(),
        "direction": image.GetDirection(),
        "size": image.GetSize(),
        "pixel_id": image.GetPixelID(),
        "pixel_id_type_as_string": image.GetPixelIDTypeAsString(),
    }

    # Extract DICOM tags for each slice
    slices_metadata = []
    depth = image.GetSize()[2]

    for i in range(depth):
        slice_tags = {}
        keys = reader.GetMetaDataKeys(i)
        for key in keys:
            slice_tags[key] = reader.GetMetaData(i, key)
        slices_metadata.append(slice_tags)

    metadata["slices_metadata"] = slices_metadata

    with open(output_path, "w") as f:
        json.dump(metadata, f, indent=4)


def load_metadata(input_path):
    """Loads metadata from a JSON file."""
    with open(input_path, "r") as f:
        return json.load(f)


def dicom_to_zarr(series_dir):
    series_id = os.path.basename(series_dir)
    print(f"Processing series: {series_id}")

    # --- 1. Load DICOM ---
    print("  Loading DICOM...")
    reader = sitk.ImageSeriesReader()
    dicom_names = reader.GetGDCMSeriesFileNames(series_dir)

    if not dicom_names:
        print(f"  No DICOM files found in {series_dir}")
        return None, None

    reader.SetFileNames(dicom_names)
    # Load the DICOM series
    # MetaDataDictionaryArrayUpdateOn is needed to access metadata for all slices
    reader.MetaDataDictionaryArrayUpdateOn()
    reader.LoadPrivateTagsOn()
    image = reader.Execute()

    # Get numpy array (z, y, x)
    arr = sitk.GetArrayFromImage(image)

    # --- 2. Save to Zarr and JSON ---
    print("  Converting to Zarr and JSON...")
    os.makedirs(CONVERTED_DIR, exist_ok=True)
    zarr_path = os.path.join(CONVERTED_DIR, f"{series_id}.zarr")
    json_path = os.path.join(CONVERTED_DIR, f"{series_id}.json")

    # Save array to Zarr
    if os.path.exists(zarr_path):
        shutil.rmtree(zarr_path)

    # Chunk by slice (1, height, width)
    chunks = (1, arr.shape[1], arr.shape[2])
    z = zarr.open(
        zarr_path,
        mode="w",
        zarr_format=3,
        shape=arr.shape,
        chunks=chunks,
        dtype=arr.dtype,
        codecs=[
            {
                "name": "bytes",
                "configuration": {
                    "endian": "little" if sys.byteorder == "little" else "big"
                },
            },
            {
                "name": "blosc",
                "configuration": {
                    "cname": "zstd",
                    "clevel": 1,
                    "shuffle": "bitshuffle",
                    "typesize": arr.itemsize,
                },
            },
        ],
    )
    z[:] = arr

    # Save metadata
    save_metadata(image, reader, dicom_names, json_path)

    print(f"  Saved to {zarr_path} and {json_path}")
    return zarr_path, json_path


def zarr_to_dicom(zarr_path, json_path, series_id):
    # --- 4. Load Zarr file and JSON ---
    print("  Loading back from Zarr...")
    # Load array
    arr_loaded = zarr.open(zarr_path, mode="r")[:]  # Read into memory as numpy array

    # Load metadata
    metadata = load_metadata(json_path)

    # --- 5. Reconstruct DICOM ---
    print("  Reconstructing DICOM...")
    reconstructed_image = sitk.GetImageFromArray(arr_loaded)
    reconstructed_image.SetOrigin(metadata["origin"])
    reconstructed_image.SetSpacing(metadata["spacing"])
    reconstructed_image.SetDirection(metadata["direction"])

    # Ensure the pixel type matches if possible, though GetImageFromArray infers it from numpy dtype
    # metadata["pixel_id"] could be used for verification

    recon_series_dir = os.path.join(RECONSTRUCTED_DIR, series_id)
    if os.path.exists(recon_series_dir):
        shutil.rmtree(recon_series_dir)
    os.makedirs(recon_series_dir, exist_ok=True)

    # Write slices
    writer = sitk.ImageFileWriter()
    writer.KeepOriginalImageUIDOn()

    filenames = metadata.get("filenames", [])

    # Try to detect extension from the first filename if available
    extension = ".dcm"
    if filenames:
        _, ext = os.path.splitext(filenames[0])
        extension = ext

    depth = arr_loaded.shape[0]
    slices_metadata = metadata.get("slices_metadata", [])

    for i in range(depth):
        # Extract slice (SimpleITK uses x, y, z indexing)
        slice_img = reconstructed_image[:, :, i]

        # Restore metadata tags to the slice
        # This is crucial for the file to be a valid DICOM
        if i < len(slices_metadata):
            slice_tags = slices_metadata[i]
            for k, v in slice_tags.items():
                # Skip tags that might conflict or are per-instance unique if we can't handle them
                # But for a simple reconstruction, copying the series-level tags is a good start.
                try:
                    slice_img.SetMetaData(k, str(v))
                except Exception:
                    pass

        # We need to ensure each slice has a unique SOP Instance UID if we want them to be valid
        # SimpleITK's ImageFileWriter might handle this if we don't provide one,
        # or we might need to generate it.
        # However, simply writing as .dcm usually works for basic viewing.

        if i < len(filenames):
            out_name = os.path.join(recon_series_dir, os.path.basename(filenames[i]))
        else:
            out_name = os.path.join(recon_series_dir, f"{i:04d}{extension}")

        writer.SetFileName(out_name)
        try:
            writer.Execute(slice_img)
        except Exception as e:
            print(f"    Error writing slice {i}: {e}")

    print(f"  Reconstructed to {recon_series_dir}")
    print("-" * 30)


def process_series(series_dir):
    series_id = os.path.basename(series_dir)
    zarr_path, json_path = dicom_to_zarr(series_dir)

    if zarr_path and json_path:
        zarr_to_dicom(zarr_path, json_path, series_id)


def main():
    # Ensure directories
    if not os.path.exists(RAW_DIR):
        print(f"Raw directory {RAW_DIR} does not exist.")
        return

    # Iterate over folders in raw
    # We look for directories inside data/raw
    entries = list(os.scandir(RAW_DIR))
    series_dirs = [f.path for f in entries if f.is_dir()]

    if not series_dirs:
        print(f"No series folders found in {RAW_DIR}")
        return

    for series_dir in series_dirs:
        process_series(series_dir)


if __name__ == "__main__":
    main()

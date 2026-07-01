"""
TRUSTLAYER — Dataset Downloader Utility
Team SOLARIS | CBI Hackathon 2026

Downloads the CMU Keystroke Dynamics Benchmark dataset and the Balabit Mouse
Dynamics Challenge dataset from their official repositories and configures them
in the project directory.

Usage:
    python scripts/download_datasets.py
"""

import os
import urllib.request
import zipfile
import shutil

# Configuration
DATASETS_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "datasets")

CMU_URL = "https://www.cs.cmu.edu/~keystroke/DSL-StrongPasswordData.csv"
BALABIT_URL = "https://github.com/balabit/Mouse-Dynamics-Challenge/archive/refs/heads/master.zip"

def download_file(url, dest_path):
    print(f"Downloading: {url} -> {dest_path}")
    headers = {"User-Agent": "Mozilla/5.0"}
    req = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(req) as response, open(dest_path, "wb") as out_file:
        shutil.copyfileobj(response, out_file)
    print("Download completed.")

def main():
    if not os.path.exists(DATASETS_DIR):
        os.makedirs(DATASETS_DIR)
        print(f"Created datasets directory: {DATASETS_DIR}")

    # 1. Download CMU Keystroke
    cmu_dest = os.path.join(DATASETS_DIR, "cmu_keystroke_benchmark.csv")
    if not os.path.exists(cmu_dest):
        try:
            download_file(CMU_URL, cmu_dest)
        except Exception as e:
            print(f"Error downloading CMU dataset: {e}")
    else:
        print("CMU Keystroke dataset already exists. Skipping.")

    # 2. Download and Extract Balabit Mouse
    balabit_zip = os.path.join(DATASETS_DIR, "balabit.zip")
    balabit_dest = os.path.join(DATASETS_DIR, "balabit")
    
    if not os.path.exists(balabit_dest):
        try:
            download_file(BALABIT_URL, balabit_zip)
            print("Extracting Balabit dataset...")
            with zipfile.ZipFile(balabit_zip, 'r') as zip_ref:
                zip_ref.extractall(DATASETS_DIR)
            
            # The zip extracts into a folder named "Mouse-Dynamics-Challenge-master"
            extracted_folder = os.path.join(DATASETS_DIR, "Mouse-Dynamics-Challenge-master")
            if os.path.exists(extracted_folder):
                os.rename(extracted_folder, balabit_dest)
                print(f"Successfully configured Balabit dataset in: {balabit_dest}")
            
            # Cleanup zip
            if os.path.exists(balabit_zip):
                os.remove(balabit_zip)
        except Exception as e:
            print(f"Error downloading/extracting Balabit dataset: {e}")
    else:
        print("Balabit Mouse dataset already exists. Skipping.")

    print("\nDataset configuration complete! You can now run 'python verify_datasets.py' or retraining scripts.")

if __name__ == "__main__":
    main()

import pydicom 
from pydicom import dcmread

import glob
import argparse
import os
import shutil
import sys
from pathlib import Path
import pandas as pd
import re
import subprocess
import json

class bcolors:
    HEADER = '\033[95m'
    OK = '\033[94m'
    INFO = '\033[96m'
    SUCCESS = '\033[92m'
    WARNING = '\033[93m'
    FAIL = '\033[91m'
    ENDC = '\033[0m'
    BOLD = '\033[1m'
    UNDERLINE = '\033[4m'

def dicom_dir_split(args):

    files = glob.glob(os.path.join(args.dir, '**'), recursive = True)

    series_description = {}
    series_files = {}
    patient_id = ''
    patient_age = ''


    for file in files:
        try:
            if Path(file).is_file():
                ds = dcmread(file)
                sn = ds['SeriesNumber'].value
                sd = ds['SeriesDescription'].value

                sn_sd = (sn, sd)

                if(patient_id == ''):
                    patient_id = ds['PatientID'].value

                if(patient_age == ''):
                    patient_age = ds['PatientAge'].value

                if sn_sd not in series_description:
                    series_description[sn_sd] = sd
                    series_files[sn_sd] = []

                series_files[sn_sd].append(file)
        except:
            print(bcolors.FAIL, "Not a dicom file:", file, bcolors.ENDC, file=sys.stderr)

    if args.skip_split:
        return series_description, series_files, {'patient_id': patient_id, 'patient_age': patient_age}

    if args.out_dcm is None:
        print(bcolors.FAIL, "Please set a valid output directory for the dicom split using --out_dcm flag", bcolors.ENDC, file=sys.stderr)
    out_dcm = os.path.join(args.out_dcm, os.path.basename(args.dir))

    print(bcolors.INFO, "Generating directories ...", bcolors.ENDC)

    for sn_sd in series_description:

        sn, sd = sn_sd

        out_sd = str(sn) + "_" + sd
        out_dir = os.path.join(out_dcm, out_sd)

        if not os.path.exists(out_dir):
            os.makedirs(out_dir)


    print(bcolors.INFO, "linking dicoms ...", bcolors.ENDC)
    for sn_sd in series_description:

        sn, sd = sn_sd

        sfs = series_files[sn_sd]

        for sf in sfs:

            out_sd = str(sn) + "_" + sd
            out_sf = os.path.join(out_dcm, out_sd, os.path.basename(sf))

            if os.path.splitext(out_sf)[1] == '':
                out_sf += ".dcm"

            try:
                
                sf = Path(sf).absolute()
                out_sf = Path(out_sf).absolute()

                print(bcolors.SUCCESS, "link:", sf, '->', out_sf, bcolors.ENDC)
                os.symlink(sf, out_sf)

            except:
                print(bcolors.FAIL, "Error linking file", sf, bcolors.ENDC, file=sys.stderr)

    print(bcolors.SUCCESS, "Dicom split done!", bcolors.ENDC)
    return series_description, series_files, {'patient_id': patient_id, 'patient_age': patient_age}

def main(args):


if __name__ == '__main__':


    parser = argparse.ArgumentParser(description='Split dicom directory by series number and series description')

    input_group = parser.add_argument_group('Input')

    input_group.add_argument('--skip_split', default=0, type=int, help='Skip dicom split')    

    input_dir_csv = input_group.add_mutually_exclusive_group(required=True)
    input_dir_csv.add_argument('--dir', type=str, help='Input directory with DICOM files')
    input_dir_csv.add_argument('--csv', default=None, type=str, help='NOT USED')

    output_group.add_argument('--out_dcm', help='Output directory for dicom split', type=str, default=None)        


    args = parser.parse_args()
    
    main(args)

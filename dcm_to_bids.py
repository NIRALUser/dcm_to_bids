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


    print(bcolors.INFO, "Copying dicoms ...", bcolors.ENDC)
    for sn_sd in series_description:

        sn, sd = sn_sd

        sfs = series_files[sn_sd]

        for sf in sfs:

            out_sd = str(sn) + "_" + sd
            out_sf = os.path.join(out_dcm, out_sd, os.path.basename(sf))

            if os.path.splitext(out_sf)[1] == '':
                out_sf += ".dcm"

            try:
                print(bcolors.SUCCESS, "copy:", sf, '->', out_sf, bcolors.ENDC)
                shutil.copy(sf, out_sf)
            except:
                print(bcolors.FAIL, "Error copying file", sf, bcolors.ENDC, file=sys.stderr)

    print(bcolors.SUCCESS, "Dicom split done!", bcolors.ENDC)
    return series_description, series_files, {'patient_id': patient_id, 'patient_age': patient_age}

def find_all_converted(args, series_description, bids_info, df_search, choices=['.nii.gz', '.nrrd']):

    groups = df_search.groupby('scan')

    series_converted = {}

    for scan, df_g in groups:

        out_bids_sub_age = os.path.join(args.out_bids, "sub-" + bids_info['bids_pid'], 'ses-' + bids_info['bids_age']) + os.path.sep
        out_bids_scan_dir = os.path.join(out_bids_sub_age, scan)

        if os.path.exists(out_bids_scan_dir):
            json_files = glob.glob(os.path.join(out_bids_scan_dir, '*.json'))

            for jsf in glob.glob(os.path.join(out_bids_scan_dir, '*.json')):
                sidecar_json = json.load(open(jsf))

                sn = sidecar_json["SeriesNumber"]
                sd = sidecar_json["SeriesDescription"]

                sn_sd = (sn, sd)

                img = jsf.replace('.json', args.out_ext)

                if(os.path.exists(img)):
                    series_converted[sn_sd] = img.replace(out_bids_sub_age, '')
                else:
                    print(bcolors.WARNING, "File not found when generating dictionary for tsv file", img, bcolors.ENDC)

    return series_converted


def convert(args, series_description, bids_info, df_search, choices=['.nii.gz', '.nrrd']):

    dcm2niix_e = "n" #.nii.gz by default
    dwiconvert_conversion_mode = "DicomToFSL"
    if args.out_ext == ".nrrd":
        dcm2niix_e = "y"
        dwiconvert_conversion_mode = "DicomToNrrd"

    if args.out_dcm is not None:
        out_dcm = os.path.join(args.out_dcm, os.path.basename(args.dir))
    else:
        out_dcm = args.dir

    # Of all the entries in the pattern_search_scans.csv file we group them by scan as these will all go to the same directory and we need to keep track of the runs. These can be for example T1/T2 going to anat folder or different types of DWI 6shell 76dir etc.
    groups = df_search.groupby('scan')

    series_converted = {}

    for scan, df_g in groups:

        for idx, g in df_g.iterrows():

            out_bids_scan_dir = os.path.join(args.out_bids, "sub-" + bids_info['bids_pid'], 'ses-' + bids_info['bids_age'], scan)

            # We start the counter for each run and iterate through the sorted series description by series number
            run_number = 1
            for sn_sd in sorted(series_description):

                sd = series_description[sn_sd]
                
                # if the series description matches the regex pattern we process this file using dcm2niix to create the output nii file and json side car
                if re.match(g['match'], sd, re.IGNORECASE):

                    if not os.path.exists(out_bids_scan_dir):
                        os.makedirs(out_bids_scan_dir)

                    sn = sn_sd[0]
                    out_sd = str(sn) + "_" + sd
                    dicom_dir = os.path.join(out_dcm, out_sd)

                    if args.use_dwi_convert and scan == "dwi":

                        out_dwi_convert = os.path.join(out_bids_scan_dir, out_sd + args.out_ext)

                        subprocess.run([args.dwi_convert, "--conversionMode", dwiconvert_conversion_mode, "-i", dicom_dir, "--useBMatrixGradientDirections", "-o", out_dwi_convert], stdout=sys.stdout, stderr=sys.stderr)

                        subprocess.run(["dcm2niix", "-b", "o", "-o", out_bids_scan_dir, dicom_dir], stdout=sys.stdout, stderr=sys.stderr)
                    else:
                        subprocess.run(["dcm2niix", "-e", dcm2niix_e,"-b", "y", "-o", out_bids_scan_dir, dicom_dir], stdout=sys.stdout, stderr=sys.stderr)

                    # We find ALL the output files based on the output series description and series number
                    # it includes .json .nii.gz .bvals .bvecs etc.
                    files = glob.glob(os.path.join(out_bids_scan_dir, '*{out_sd}*'.format(out_sd=out_sd)))

                    check_renames = {}

                    for file in files:

                        ext = os.path.splitext(file)[1]
                        if ext == ".gz":
                            ext = ".nii.gz"

                        bids_info_g = bids_info.copy()

                        bids_info_g['run_number'] = run_number                      
                        bids_info_g['ext'] = ext

                        rename_file = g['out_name'].format(**bids_info_g)

                        if sn_sd not in series_converted and ext in choices:
                            series_converted[sn_sd] = os.path.join(scan, rename_file)

                        if ext in check_renames:
                            rename_file += "_{num}".format(num=check_renames[ext])
                            print(bcolors.WARNING, "WARNING: It appears the conversion went wrong as there are more than 1 file with the same extension", bcolors.ENDC, file=sys.stderr)

                        # We proceed to rename the files based on the patterns

                        rename_file = os.path.join(out_bids_scan_dir, rename_file)
                        try:
                            print(bcolors.SUCCESS, "Renaming:", file, "->", rename_file, bcolors.ENDC)
                            os.rename(file, rename_file)
                        except:
                            print(bcolors.FAIL, "Error renaming file!", bcolors.ENDC, file=sys.stderr)



                        if not pd.isna(g["add_json"]) and ext == ".json":
                            add_json = json.loads(g["add_json"])
                            sidecar_json = json.load(open(rename_file))
                            sidecar_json.update(add_json)
                            json.dump(sidecar_json, open(rename_file, 'w'), indent=4, sort_keys=True)

                        if ext not in check_renames:
                            check_renames[ext] = 0

                        check_renames[ext] += 1

                    run_number+=1   

    return series_converted

def generate_tsv(args, series_files, series_converted, bids_info):
    print("Generating TSV ...")

    scans_df = []

    for sn_sd in sorted(series_converted):

        sf_dcm = dcmread(series_files[sn_sd][0])
        sf_converted = series_converted[sn_sd]

        acquisition_date = sf_dcm['AcquisitionDate']    
        acquisition_time = sf_dcm['AcquisitionTime']
        
        acquisition_date = '-'.join([acquisition_date[0:4], acquisition_date[4:6], acquisition_date[6:]])
        acquisition_time = ':'.join([acquisition_time[0:2], acquisition_time[2:4], acquisition_time[4:6]])

        acq_time = "{acquisition_date}T{acquisition_time}".format(**{'acquisition_date': acquisition_date, 'acquisition_time': acquisition_time})

        scans_df.append({'filename': sf_converted, 'acq_time': acq_time})


    out_bids_scans_acq_time = os.path.join(args.out_bids, "sub-" + bids_info['bids_pid'], 'ses-' + bids_info['bids_age'], "sub-" + bids_info['bids_pid'] + "_" + "ses-" + bids_info['bids_age'] + "_scans.tsv")

    scans_df = pd.DataFrame(scans_df)

    print(bcolors.INFO, "Writing:", out_bids_scans_acq_time, bcolors.ENDC)
    scans_df.to_csv(out_bids_scans_acq_time, index=False, sep='\t')

def insert_intended_for_fmap(bids_dir, bids_info):
    """Insert the IntendedFor field to JSON sidecart for fieldmap data"""

    fmap_path = "{bids_dir}/sub-{bids_pid}/ses-{bids_age}/fmap".format(**bids_info)
    func_path = "{bids_dir}/sub-{bids_pid}/ses-{bids_age}/func".format(**bids_info)
    dwi_path = "{bids_dir}/sub-{bids_pid}/ses-{bids_age}/dwi".format(**bids_info)

    nii_files = []
    json_files = []

    if os.path.exists(fmap_path):
        fmap_files = [os.path.join(fmap_path, f) for f in os.listdir(fmap_path)]
        json_files = [f for f in fmap_files if f.endswith(".json")]
        print(f"List of JSON files to amend {json_files}")

    if os.path.exists(func_path):               

        # makes list of the func files to add into the intended for field
        func_files = ["ses-{bids_age}/func/{file}".format(**bids_info, file=file) for file in os.listdir(func_path)]
        nii_files += [i for i in func_files if i.endswith(".nii.gz") and "sbref" not in i]                

    if os.path.exists(dwi_path):

        # makes list of the func files to add into the intended for field
        dwi_files = ["ses-{bids_age}/dwi/{file}".format(**bids_info, file=file) for file in os.listdir(dwi_path)]
        nii_files += [i for i in dwi_files if i.endswith(".nii.gz")]

    if len(nii_files) > 0 and len(json_files) > 0:

        print("List of NII files", nii_files)

        # Open the json files ('r' for read only) as a dictionary
        # Adds the Intended for key
        # Add the func files to the key value
        # The f.close is a duplication.
        # f can only be used inside the with "loop"
        # we open the file again to write only and
        # dump the dictionary to the files
        for file in json_files:
            os.chmod(file, 0o664)
            with open(file, "r") as f:
                print(f"Processing file {f}")
                data = json.load(f)
                data["IntendedFor"] = nii_files
                f.close
            with open(file, "w") as f:
                json.dump(data, f, indent=4, sort_keys=True)
                f.close
                print("Done with re-write")

def main(args, choices=['.nii.gz', '.nrrd']):

    # series_description = { series_number_1: 'series_description_1', series_number_2: 'series_description_2'} etc.
    args.dir = os.path.normpath(args.dir)
    series_description, series_files, patient_obj = dicom_dir_split(args)

    if args.csv_id is not None:
        df = pd.read_csv(args.csv_id)

        if 'age' in df.columns() and not args.use_dirname_as_id:
            query = 'pid == {patient_id} and age == {patient_age}'.format(**patient_obj)
        else:
            if args.use_dirname_as_id:
                patient_obj = {
                    'patient_id': os.path.basename(args.dir)
                }
            query = 'pid == {patient_id}'.format(**patient_obj)

        rows = pd.query(query)

        if(len(rows) > 1):
            print("WARNING! More than one entry found in csv_id file using query", query)

        bids_info = rows.reset_index().loc[0]
    else:
        bids_info = {'bids_pid': patient_obj['patient_id'], 'bids_age': patient_obj['patient_age']}

    if args.bids_pid and args.bids_age:
        bids_info = {'bids_pid': args.bids_pid, 'bids_age': args.bids_age}


    df_search = pd.read_csv(os.path.join(os.path.dirname(__file__), 'pattern_search_scans.csv'))

    if args.skip_convert == 0:
        series_converted = convert(args, series_description, bids_info, df_search, choices)

    if args.generate_tsv == 2:
        series_converted = find_all_converted(args, series_description, bids_info, df_search, choices)

    if args.generate_tsv > 0:
        generate_tsv(args, series_files, series_converted, bids_info)

    insert_intended_for_fmap(args.out_bids, bids_info)

if __name__ == '__main__':


    parser = argparse.ArgumentParser(description='Split dicom directory by series number and series description and then convert to bids')

    input_group = parser.add_argument_group('Input')

    input_dir_csv = input_group.add_mutually_exclusive_group(required=True)
    input_dir_csv.add_argument('--dir', type=str, help='Input directory with DICOM files')
    input_dir_csv.add_argument('--csv', default=None, type=str, help='Use this csv file to run dcm_to_bids for a whole dataset. The CSV must have columns "dir,bids_pid,bids_age". The dir column points to the directory with dicom files and bids_pid and bids_age are used to correct the id and age for the output.')


    input_group.add_argument('--skip_split', default=0, type=int, help='Skip dicom split')
    input_group.add_argument('--skip_convert', default=0, type=int, help='Skip convert')
    input_group.add_argument('--generate_tsv', default=1, type=int, help='Generate TSV output file. skip=0, default=1 (only converted ones in current run), find=2 (finds all available scans)')
    input_group.add_argument('--use_dwi_convert', default=0, type=int, help='Use DWIConvert executable instead of dcm2niix to convert the dwi')
    input_group.add_argument('--dwi_convert', default="DWIConvert", type=str, help='Executable name of DWIConvert')

    input_group_csv = parser.add_argument_group('Input CSV')
    input_group_csv.add_argument('--csv_id', default=None, type=str, help='Use this csv file to correct the id and age of the patient. This csv file must have column "pid" (required) and "age" (optional), it must also have columns for "bids_pid" (required) and "bids_age" (required). If this input is not provided, this convertion tool will use the patient id and age found in the dicom.')
    input_group_csv.add_argument('--use_dirname_as_id', default=0, type=int, help='Instead of using the id that exists in the dicom, it uses the directory name as matching key. The --csv_id must be provided')

    input_patient = parser.add_argument_group('Input patient info')

    input_patient.add_argument('--bids_pid', default=None, type=str, help='Input bids patient id. If used, it will override --csv_id and dicom\'s PatientID')
    input_patient.add_argument('--bids_age', default=None, type=str, help='Input bids age or session name. If used, it will override --csv_id and dicom\'s PatientAge')

    output_group = parser.add_argument_group('Output')
    output_group.add_argument('--out_dcm', help='Output directory for dicom split', type=str, default=None)
    output_group.add_argument('--out_bids', help='Output directory for bids convert', type=str, default='out_bids')
    input_group.add_argument('--out_ext', default=".nii.gz", choices=['.nii.gz', '.nrrd'], type=str, help='Output extension type')


    args = parser.parse_args()

    if args.csv:
        df = pd.read_csv(args.csv, converters={'bids_pid': str, 'bids_age': str})
        for idx, row in df.iterrows():
            args.dir = row['dir']
            args.bids_pid = row['bids_pid']
            args.bids_age = row['bids_age']
            print(bcolors.INFO, "Start split:", row, bcolors.ENDC)
            main(args)
    else:
        main(args, choices=['.nii.gz', '.nrrd'])

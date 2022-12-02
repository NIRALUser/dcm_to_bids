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

				if(patient_id == ''):
					patient_id = ds['PatientID'].value

				if(patient_age == ''):
					patient_age = ds['PatientAge'].value

				if sn not in series_description:
					series_description[sn] = sd
					series_files[sn] = []

				series_files[sn].append(file)
		except:
			print("Not a dicom file:", file, file=sys.stderr)

	out_dcm = os.path.join(args.out_dcm, os.path.basename(args.dir))

	if args.skip_split:
		return series_description, series_files, {'patient_id': patient_id, 'patient_age': patient_age}

	print("Generating directories ...")

	for sn in series_description:

		sd = series_description[sn]

		out_sd = str(sn) + "_" + sd + "_" + str(sn)
		out_dir = os.path.join(out_dcm, out_sd)

		if not os.path.exists(out_dir):
			os.makedirs(out_dir)


	print("Copying dicoms ...")
	for sn in series_description:

		sd = series_description[sn]

		out_dir = os.path.join(out_dcm, sd)

		sfs = series_files[sn]

		for sf in sfs:

			out_sd = str(sn) + "_" + sd + "_" + str(sn)
			out_sf = os.path.join(out_dcm, out_sd, os.path.basename(sf))

			if os.path.splitext(out_sf)[1] == '':
				out_sf += ".dcm"

			try:
				print("copy:", sf, '->', out_sf)
				shutil.copy(sf, out_sf)
			except:
				print("Error copying file", sf, file=sys.stderr)

	print("Dicom split done!")
	return series_description, series_files, {'patient_id': patient_id, 'patient_age': patient_age}


def convert(args, series_description, bids_info, df_search, choices=['.nii.gz', '.nrrd']):

	dcm2niix_e = "n" #.nii.gz by default
	dwiconvert_conversion_mode = "DicomToFSL"
	if args.out_ext == ".nrrd":
		dcm2niix_e = "y"
		dwiconvert_conversion_mode = "DicomToNrrd"

	out_dcm = os.path.join(args.out_dcm, os.path.basename(args.dir))

	# Of all the entries in the pattern_search_scans.csv file we group them by scan as these will all go to the same directory and we need to keep track of the runs. These can be for example T1/T2 going to anat folder or different types of DWI 6shell 76dir etc.
	groups = df_search.groupby('scan')

	series_converted = {}

	for scan, df_g in groups:

		for idx, g in df_g.iterrows():

			out_bids_scan_dir = os.path.join(args.out_bids, "sub-" + bids_info['bids_pid'], 'ses-' + bids_info['bids_age'], scan)

			# We start the counter for each run and iterate through the sorted series description by series number
			run_number = 1
			for sn in sorted(series_description):

				sd = series_description[sn]
				
				# if the series description matches the regex pattern we process this file using dcm2niix to create the output nii file and json side car
				if re.match(g['match'], sd, re.IGNORECASE):

					if not os.path.exists(out_bids_scan_dir):
						os.makedirs(out_bids_scan_dir)

					out_sd = str(sn) + "_" + sd + "_" + str(sn)
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

						if sn not in series_converted and ext in choices:
							series_converted[sn] = os.path.join(scan, rename_file)

						if ext in check_renames:
							rename_file += "_{num}".format(num=check_renames[ext])
							print("WARNING: It appears the conversion went wrong as there are more than 1 file with the same extension", file=sys.stderr)

						# We proceed to rename the files based on the patterns

						rename_file = os.path.join(out_bids_scan_dir, rename_file)
						try:
							print("Renaming:", file, "->", rename_file)
							os.rename(file, rename_file)
						except:
							print("Error renaming file!", file=sys.stderr)

						if ext not in check_renames:
							check_renames[ext] = 0

						check_renames[ext] += 1

					run_number+=1	

	return series_converted

def generate_tsv(args, series_files, series_converted, bids_info):
	print("Generating TSV ...")

	scans_df = []

	for sn in sorted(series_converted):

		sf_dcm = ds = dcmread(series_files[sn][0])
		sf_converted = series_converted[sn]

		acquisition_date = sf_dcm['AcquisitionDate']	
		acquisition_time = sf_dcm['AcquisitionTime']
		
		acquisition_date = '-'.join([acquisition_date[0:4], acquisition_date[4:6], acquisition_date[6:]])
		acquisition_time = ':'.join([acquisition_time[0:2], acquisition_time[2:4], acquisition_time[4:6]])

		acq_time = "{acquisition_date}T{acquisition_time}".format(**{'acquisition_date': acquisition_date, 'acquisition_time': acquisition_time})

		scans_df.append({'filename': sf_converted, 'acq_time': acq_time})


	out_bids_scans_acq_time = os.path.join(args.out_bids, "sub-" + bids_info['bids_pid'], 'ses-' + bids_info['bids_age'], "sub-" + bids_info['bids_pid'] + "_" + "ses-" + bids_info['bids_age'] + "_scans.tsv")

	scans_df = pd.DataFrame(scans_df)

	print("Writing:", out_bids_scans_acq_time)
	scans_df.to_csv(out_bids_scans_acq_time, index=False, sep='\t')

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

	series_converted = convert(args, series_description, bids_info, df_search, choices)

	generate_tsv(args, series_files, series_converted, bids_info)



if __name__ == '__main__':


    parser = argparse.ArgumentParser(description='Split dicom directory by series number and series description and then convert to bids')

    input_group = parser.add_argument_group('Input')

    input_group.add_argument('--dir', required=True, type=str, help='Input directory with DICOM files')
    input_group.add_argument('--skip_split', default=0, type=int, help='Skip dicom split')
    input_group.add_argument('--use_dwi_convert', default=0, type=int, help='Use DWIConvert executable instead of dcm2niix to convert the dwi')
    input_group.add_argument('--dwi_convert', default="DWIConvert", type=str, help='Executable name of DWIConvert')

    input_group_csv = parser.add_argument_group('Input CSV')
    input_group_csv.add_argument('--csv_id', default=None, type=str, help='Use this csv file to correct the id and age of the patient. This csv file must have column "pid" (required) and "age" (optional), it must also have columns for "bids_pid" (required) and "bids_age" (required). If this input is not provided, this convertion tool will use the patient id and age found in the dicom.')
    input_group_csv.add_argument('--use_dirname_as_id', default=0, type=int, help='Instead of using the id that exists in the dicom, it uses the directory name as matching key. The --csv_id must be provided')

    input_patient = parser.add_argument_group('Input patient info')

    input_patient.add_argument('--bids_pid', default=None, type=str, help='Input bids patient id. If used, it will override --csv_id and dicom\'s PatientID')
    input_patient.add_argument('--bids_age', default=None, type=str, help='Input bids age or session name. If used, it will override --csv_id and dicom\'s PatientAge')

    output_group = parser.add_argument_group('Output')
    output_group.add_argument('--out_dcm', help='Output directory for dicom split', type=str, default='out_dcm')
    output_group.add_argument('--out_bids', help='Output directory for bids convert', type=str, default='out_bids')
    input_group.add_argument('--out_ext', default=".nii.gz", choices=['.nii.gz', '.nrrd'], type=str, help='Output extension type')


    args = parser.parse_args()

    main(args, choices=['.nii.gz', '.nrrd'])

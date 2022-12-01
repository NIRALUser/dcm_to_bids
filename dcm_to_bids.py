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


def convert(args, series_description, bids_info, df_search):

	out_dcm = os.path.join(args.out_dcm, os.path.basename(args.dir))

	# Of all the entries in the pattern_search_scans.csv file we group them by scan as these will all go to the same directory and we need to keep track of the runs. These can be for example T1/T2 going to anat folder or different types of DWI 6shell 76dir etc.
	groups = df_search.groupby('scan')

	for scan, df_g in groups:

		for idx, g in df_g.iterrows():

			out_bids_scan_dir = os.path.join(args.out_bids, bids_info['bids_pid'], bids_info['bids_age'], scan)

			if not os.path.exists(out_bids_scan_dir):
				os.makedirs(out_bids_scan_dir)

			# We start the counter for each run and iterate through the sorted series description by series number
			run_number = 1
			for sn in sorted(series_description):

				sd = series_description[sn]
				
				# if the series description matches the regex pattern we process this file using dcm2niix to create the output nii file and json side car
				if re.match(g['match'], sd, re.IGNORECASE):

					out_sd = str(sn) + "_" + sd + "_" + str(sn)
					dicom_dir = os.path.join(out_dcm, out_sd)

					subprocess.run(["dcm2niix", "-b", "y", "-o", out_bids_scan_dir, dicom_dir], stdout=sys.stdout, stderr=sys.stderr)

					# We find ALL the output files based on the output series description and series number
					# it includes .json .nii.gz .bvals .bvecs etc.
					files = glob.glob(os.path.join(out_bids_scan_dir, '*{out_sd}*'.format(out_sd=out_sd)))

					check_renames = {}

					for file in files:

						ext = os.path.splitext(file)[1]

						bids_info_g = bids_info.copy()

						bids_info_g['run_number'] = run_number						
						bids_info_g['ext'] = ext

						rename_file = g['out_name'].format(**bids_info_g)

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


def main(args):

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

	df_search = pd.read_csv(os.path.join(os.path.dirname(__file__), 'pattern_search_scans.csv'))

	convert(args, series_description, bids_info, df_search)


if __name__ == '__main__':


    parser = argparse.ArgumentParser(description='Split dicom directory by series number and series description and then convert to bids')
    parser.add_argument('--dir', required=True, type=str, help='Input directory')
    parser.add_argument('--csv_id', default=None, type=str, help='Use this csv file to correct the id and age of the patient. This csv file must have column "pid" (required) and "age" (optional), it must also have columns for bids_pid (required) and bids_age (required). If this input is not provided, this convertion tool will use the patient id and age found in the dicom.')
    parser.add_argument('--use_dirname_as_id', default=0, type=int, help='Instead of using the id that exists in the dicom, it uses the directory name as matching key. The --csv_id must be provided')
    parser.add_argument('--skip_split', default=0, type=int, help='Skip dicom split')
    parser.add_argument('--out_dcm', help='Output directory for dicom split', type=str, default='out_dcm')
    parser.add_argument('--out_bids', help='Output directory for bids convert', type=str, default='out_bids')

    args = parser.parse_args()

    main(args)

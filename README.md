# dcm_to_bids

Converts a dicom directory to bids format. The covertion uses dcm2niix to convert from dicom to nii.gz format. As an option, it allows usage of [DWIConvert](https://github.com/BRAINSia/BRAINSTools) to process DWI data. 

## Installation

1. Clone this repository

```
git clone https://github.com/NIRALUser/dcm_to_bids.git & cd dcm_to_bids
```

2. Use the environment file provided to setup the dependencies. 

```
 conda env create -f dcm_to_bids.yml
```

3. Activate the environment

```
conda activate dcm_to_bids
```

## Usage

```
usage: dcm_to_bids.py [-h] --dir DIR [--skip_split SKIP_SPLIT]
                      [--use_dwi_convert USE_DWI_CONVERT]
                      [--dwi_convert DWI_CONVERT] [--csv_id CSV_ID]
                      [--use_dirname_as_id USE_DIRNAME_AS_ID]
                      [--out_dcm OUT_DCM] [--out_bids OUT_BIDS]
                      [--out_ext {.nii.gz,.nrrd}]

Split dicom directory by series number and series description and then convert
to bids

optional arguments:
  -h, --help            show this help message and exit

Input:
  --dir DIR             Input directory
  --skip_split SKIP_SPLIT
                        Skip dicom split
  --use_dwi_convert USE_DWI_CONVERT
                        Use DWIConvert executable instead of dcm2niix to
                        convert the dwi
  --dwi_convert DWI_CONVERT
                        Executable name of DWIConvert
  --out_ext {.nii.gz,.nrrd}
                        Output extension type

Input CSV:
  --csv_id CSV_ID       Use this csv file to correct the id and age of the
                        patient. This csv file must have column "pid"
                        (required) and "age" (optional), it must also have
                        columns for "bids_pid" (required) and "bids_age"
                        (required). If this input is not provided, this
                        convertion tool will use the patient id and age found
                        in the dicom.
  --use_dirname_as_id USE_DIRNAME_AS_ID
                        Instead of using the id that exists in the dicom, it
                        uses the directory name as matching key. The --csv_id
                        must be provided

Output:
  --out_dcm OUT_DCM     Output directory for dicom split
  --out_bids OUT_BIDS   Output directory for bids convert
```

## Example

To run the tool execute the dcm_to_bids.py
  
```
python dcm_to_bids/dcm_to_bids.py --dir input_dicom_directory --out_dcm output_dicom_directory --out_bids output_bids_directory
```

### Using a csv to keep track of the id and age of subjects

```
python dcm_to_bids/dcm_to_bids.py --dir input_dicom_directory --out_dcm output_dicom_directory --out_bids output_bids_directory --csv_id bids_ids_examples.csv
```

### Pattern matching to generate the bids outputs

The file pattern_search_scans.csv contains the type of scans that will be converted and a pattern matching scheme. 
It can be modified or new ones can be added to handle different inputs. 

### Example
```
scan,match,out_name
anat,.*t1w.*,{bids_pid}_ses-{bids_age}_run-{run_number:03d}_T1w{ext}
```

The scan column points to the output directory in the bids folder. The match column contains a regex pattern that will be match to find the different type of scans. In the example it will find all T1W images. The out_name column will be the output name and can be modified depending on the type of output scan to handle dwi, fmri etc. 

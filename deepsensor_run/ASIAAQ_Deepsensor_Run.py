###################################################################################################
# LOAD PACKAGES
# Basic packages:
import sys
import os
import logging
import time
import json
logging.captureWarnings(True)

# Data management & manipulation packages:
import numpy as np
import pandas as pd
import xarray as xr

# Deepsensor:
import deepsensor.torch
from deepsensor.data import DataProcessor
from deepsensor.data import TaskLoader
from deepsensor.model import ConvNP
from deepsensor.train import Trainer, set_gpu_default_device

print('Package loading complete')

# GPU Setup:
try:
    set_gpu_default_device()
    print('GPU setup complete')
except:
    pass


###################################################################################################
# FIXED SETTINGS
# input data folders
s_data_folder = "/discover/nobackup/cmalings/input/ASIA-AQ Experimentation"
s_data_folder_GCAS = "/discover/nobackup/cmalings/input/ASIA-AQ GCAS Simulation"
s_folder_base = "/discover/nobackup/cmalings/output/ASIA-AQ/deepsensor_working_data"

b_Retrain_Model = True
b_Repeat_Evaluation = True

unet_channels_settings = (32, 32, 32, 32, 32)
n_max_epoch = 100

###################################################################################################
# VARIABLE SETTINGS - Get From JSON

# get run name from input
s_name_for_model = sys.argv[1]
print(f'Running model: {s_name_for_model}')

# set working directory
processor_dir = f"/discover/nobackup/cmalings/output/ASIA-AQ/deepsensor_working_data/{s_name_for_model}/"
data_fpath = os.path.join(processor_dir,"tmp.nc")

# import settings from JSON
with open(os.path.join(processor_dir,s_name_for_model+'_settings.json'), 'r') as o_file:
    d_settings = json.load(o_file)

Consider_ground_monitors_as_input = d_settings['Ground Monitors Considered for Input']
Fraction_of_ground_monitors_to_train_on = d_settings['Ground Monitor Training Fraction']
Use_GEOSCF = d_settings['Use GEOS-CF']
Use_TROPOMI = d_settings['Use TROPOMI']
Use_GEMS = d_settings['Use GEMS']
Use_GCAS = d_settings['Use GCAS']
Use_LULC = d_settings['Use LULC']
Spatial_CV = d_settings['Spatial Cross-Validation']
n_fold_spatial_cv = d_settings['Number of Spatial Cross-Validation Folds']
i_fold_spatial_cv = d_settings['Spatial Cross-Validation Fold']
Temporal_CV = d_settings['Temporal Cross-Validation']
n_fold_temporal_cv = d_settings['Number of Temporal Cross-Validation Folds']
i_fold_temporal_cv = d_settings['Temporal Cross-Validation Fold']
Temporal_Month_Split = d_settings['Temporal Split By Month']
Train_in_March = d_settings['Training in March']

print('Loaded Settings:')
for s_key in d_settings.keys():
    print(f'{s_key} : {d_settings[s_key]} {type(d_settings[s_key])}')
print('-----SETUP COMPLETE-----')

###################################################################################################
# IMPORT DATA

# Load AirKorea Data
f_data_airkorea_raw = pd.read_csv(os.path.join(s_data_folder,'AirKorea_AsiaAQ_Seoul_station_h.csv'))

# Ensure DateTime Formatting:
f_data_airkorea_raw['time'] = pd.to_datetime(f_data_airkorea_raw['time'])

# Only retain data to be used here, and set the index to the proper sequence (time, lat, lon):
f_data_airkorea = f_data_airkorea_raw[['lat','lon','time','NO2']].set_index(['time','lat','lon'])

print(f'AirKorea Data Loaded: {len(f_data_airkorea)} records')

# Load GOES-CF Data
if Use_GEOSCF:
    a_data_GEOSCF_raw = xr.open_dataset(os.path.join(s_data_folder,'GEOS-CF_AsiaAQ_Seoul_Grid_025_h.nc'))
    
    # Only retain data to be used here, and set the dimensions to the proper sequence (time, lat, lon):
    a_data_GEOSCF = a_data_GEOSCF_raw[['no2',
                                       'tropcol_no2',
                                       'totcol_no2',
                                       'u2m',
                                       'v2m',
                                       'wndspd_2m',
                                       't2m',
                                       'q2m',
                                       'rh',
                                       'cldtt',
                                       'tprec',
                                       'troppb',
                                       'zl',
                                       'zpbl',
                                      ]].transpose('time','lat','lon')
    
    # Append data source to variable names:
    a_data_GEOSCF = a_data_GEOSCF.rename({s_var:'GEOS-CF_'+s_var for s_var in a_data_GEOSCF})

    print(f'GEOS-CF Data Loaded: {len(a_data_GEOSCF.time.values)} timestamps')

# Load TROPOMI Data
if Use_TROPOMI:
    a_data_TROPOMI_raw = xr.open_dataset(os.path.join(s_data_folder,'TROPOMI_AsiaAQ_Seoul_Regrid_005_h.nc'))
    
    # Only retain data to be used here, and set the dimensions to the proper sequence (time, lat, lon):
    a_data_TROPOMI = a_data_TROPOMI_raw[['no2','o3']].transpose('time','lat','lon')
    
    # Append data source to variable names:
    a_data_TROPOMI = a_data_TROPOMI.rename({s_var:'TROPOMI_'+s_var for s_var in a_data_TROPOMI})
    
    # Create Daily-aggregate TROPOMI Data:
    # Define "days" centered at nominal overpass time:
    v_days = np.arange(np.datetime64('2024-02-01T04:30:00'),np.datetime64('2024-03-31T23:59:59'),np.timedelta64(1,'D'))
    # Match each overpass with the nearest nominal day:
    v_day_assignments = [v_days[np.argmin(abs(v_days - t_time))] for t_time in a_data_TROPOMI.time.values]
    # Use coordinate grouping and averaging to create daily averages:
    a_data_TROPOMI_daily = a_data_TROPOMI.assign_coords({'date':('time',v_day_assignments)}).groupby('date').mean('time')
    # Rename variables and dimensions:
    a_data_TROPOMI_daily = a_data_TROPOMI_daily.rename({'date':'time'})
    a_data_TROPOMI_daily = a_data_TROPOMI_daily.rename({s_var:s_var.replace('TROPOMI_','TROPOMI_DAILY_') for s_var in a_data_TROPOMI})

    print(f'TROPOMI Data Loaded: {len(a_data_TROPOMI_daily.time.values)} days')

# Load GEMS
if Use_GEMS:
    a_data_GEMS_raw = xr.open_dataset(os.path.join(s_data_folder,'GEMS_AsiaAQ_Seoul_Regrid_008_h.nc'))
    
    # Only retain data to be used here, and set the dimensions to the proper sequence (time, lat, lon):
    a_data_GEMS = a_data_GEMS_raw[['ColumnAmountNO2Trop','ColumnAmountNO2']].transpose('time','lat','lon')
    
    # Append data source to variable names:
    a_data_GEMS = a_data_GEMS.rename({s_var:'GEMS_'+s_var for s_var in a_data_GEMS})

    print(f'GEMS Data Loaded: {len(a_data_GEMS.time.values)} hours')

# Load GCAS Data
if Use_GCAS:
    # Days with GCAS overflight:
    l_days_GCAS = [
                  '20240217',
                  '20240223',
                  '20240226',
                  '20240301',
                  '20240302',
                  '20240303',
                  '20240307',
                  '20240309'
                  ]
    
    # GCAS data variables to be used:
    l_GCAS_vars_to_keep = ['no2_vertical_column_below_aircraft','model_no2_vertical_column_below_aircraft']
    
    # Load and concatenate by time, and set the dimensions to the proper sequence (time, lat, lon):
    l_data_GCAS = [xr.open_dataset(os.path.join(s_data_folder_GCAS,f'GCAS_NO2_{s_day}_Seoul_Gridded_001_hourly.nc'))[l_GCAS_vars_to_keep] for s_day in l_days_GCAS]
    a_data_GCAS = xr.concat(l_data_GCAS,'time').transpose('time','lat','lon')
    
    # Append data source to variable names:
    a_data_GCAS = a_data_GCAS.rename({s_var:'GCAS_'+s_var for s_var in a_data_GCAS})

    print(f'GCAS Data Loaded: {len(a_data_GCAS.time.values)} hours')

# Load Land Use Dataset
if Use_LULC:
    a_data_LULC = xr.open_dataset(os.path.join(s_data_folder,'MCD12Q1.061_500m_aid0001.nc'))
    a_data_LULC = a_data_LULC[['LC_Type1']].mean('time').rename({'LC_Type1':'MCD12Q1_LC_Type1'}).sel(lat=slice(38,36),lon=slice(126,128))
    
    # Covert to categorical classes - THIS MAKES THE FILE TOO BIG
    if False:
        for i_class in np.unique(a_data_LULC['MCD12Q1_LC_Type1'].values):
            a_data_LULC['MCD12Q1_LC_Type1_Class'+str(int(i_class))] = xr.zeros_like(a_data_LULC['MCD12Q1_LC_Type1'])
            a_data_LULC['MCD12Q1_LC_Type1_Class'+str(int(i_class))] = a_data_LULC['MCD12Q1_LC_Type1_Class'+str(int(i_class))].where(a_data_LULC['MCD12Q1_LC_Type1'] != i_class,1)
    
    print('Land Use & Land Cover Data Loaded')

print('-----DATA LOADING COMPLETE-----')

###################################################################################################
# ALIGN DATA TO COMMON TIME

# Function to align times
def F_align_times(a_in,v_time,dt_tol = np.timedelta64(30,'m')):
    # Convert Data Frames to Xarray:
    if (type(a_in) == pd.DataFrame):
        b_frame = True
        a_in = a_in.to_xarray()
    else:
        b_frame = False
    # Use re-indexing with tolerance to get the nearest time in the sample:
    a_out = a_in.reindex(time=v_time,
                         method="nearest",
                         tolerance=dt_tol,
                         copy=False,
                         kwargs={'fill_value':'extrapolate'})
    # Convert back to dataframe if needed:
    if b_frame:
        a_out = a_out.to_dataframe().dropna(how='all')
    return a_out

# Target times: AirKorea Monitor Data
v_time = f_data_airkorea.reset_index()['time'].unique()

f_data_airkorea_aligned = F_align_times(f_data_airkorea,v_time)
if Use_GEOSCF:
    a_data_GEOSCF_aligned = F_align_times(a_data_GEOSCF,v_time) # 7MB
if Use_TROPOMI:
    a_data_TROPOMI_daily_aligned = F_align_times(a_data_TROPOMI_daily,v_time,dt_tol = np.timedelta64(12,'h')) # 37MB
if Use_GEMS:
    a_data_GEMS_aligned = F_align_times(a_data_GEMS,v_time) # 17MB
if Use_GCAS:
    a_data_GCAS_aligned = F_align_times(a_data_GCAS,v_time) # 925MB !!!

if Use_LULC:
    # Add time dimension to land use land cover dataset, include hour-of-day information - 41GB !!!!!
    a_data_AUX_aligned = a_data_LULC.expand_dims({'time':v_time}).transpose('time','lat','lon')
    a_data_AUX_aligned['Time_of_Day'] = xr.DataArray(pd.to_datetime(v_time).hour,dims=('time'),coords={'time':v_time}).expand_dims({'lat':a_data_AUX_aligned.lat.values,'lon':a_data_AUX_aligned.lon.values}).transpose('time','lat','lon')
else:
    a_data_AUX_aligned = xr.DataArray(pd.to_datetime(v_time).hour,name='Time_of_Day',dims=('time'),coords={'time':v_time}).expand_dims({'lat':np.arange(36,38.5,0.5),'lon':np.arange(126,128.5,0.5)}).transpose('time','lat','lon')

# Verify alignment
b_aligned = True
if len(v_time) != len(f_data_airkorea_aligned.reset_index()['time'].unique()):
    b_aligned = False
    print('Warning: AirKorea data are not temporally aligned.')
if Use_GEOSCF:
    if len(v_time) != len(a_data_GEOSCF_aligned.time.values):
        b_aligned = False
        print('Warning: GEOS-CF data are not temporally aligned.')
if Use_TROPOMI:        
    if len(v_time) != len(a_data_TROPOMI_daily_aligned.time.values):
        b_aligned = False
        print('Warning: TROPOMI data are not temporally aligned.')
if Use_GEMS:        
    if len(v_time) != len(a_data_GEMS_aligned.time.values):
        b_aligned = False
        print('Warning: GEMS data are not temporally aligned.')
if Use_GCAS:        
    if len(v_time) != len(a_data_GCAS_aligned.time.values):
        b_aligned = False
        print('Warning: GCAS data are not temporally aligned.')
if b_aligned:
    print('All data are aligned to common times.')

###################################################################################################
# SPLIT DATA FOR TRAINING AND TESTING

# Split Data by times:
if Temporal_CV:
    id_test = range(i_fold_temporal_cv,len(v_time),n_fold_temporal_cv)
    v_time_test = v_time[id_test]
    v_time_train = v_time[[index for index in range(0,len(v_time)) if index not in id_test]]
elif Temporal_Month_Split:
    if Train_in_March:
        v_time_train = v_time[v_time >= np.datetime64('2024-03-01T00:00:00')]
        v_time_test = v_time[v_time < np.datetime64('2024-03-01T00:00:00')]
    else:
        v_time_train = v_time[v_time < np.datetime64('2024-03-01T00:00:00')]
        v_time_test = v_time[v_time >= np.datetime64('2024-03-01T00:00:00')]
else:
    v_time_test = v_time
    v_time_train = v_time

# Split Site Data Spatially:
if Spatial_CV:
    # Assign site IDs to AirKorea data locations:
    f_data_airkorea_aligned_with_siteid = f_data_airkorea_aligned
    f_data_airkorea_aligned_with_siteid['siteID'] = f_data_airkorea_aligned_with_siteid.groupby(['lat', 'lon']).ngroup()
    # Divide by site IDs:
    v_test_siteID = range(i_fold_spatial_cv,max(f_data_airkorea_aligned_with_siteid['siteID'])+1,n_fold_spatial_cv)
    f_data_airkorea_aligned_test_sites = f_data_airkorea_aligned_with_siteid[f_data_airkorea_aligned_with_siteid['siteID'].isin(v_test_siteID)][['NO2']]
    f_data_airkorea_aligned_train_sites = f_data_airkorea_aligned_with_siteid[~(f_data_airkorea_aligned_with_siteid['siteID'].isin(v_test_siteID))][['NO2']]
else:
    f_data_airkorea_aligned_test_sites = f_data_airkorea_aligned
    f_data_airkorea_aligned_train_sites = f_data_airkorea_aligned

# Define Training and Testing Datasets:
v_datatypes = ['airkorea']
d_training = {'airkorea':F_align_times(f_data_airkorea_aligned_train_sites,v_time_train)}
d_testing = {'airkorea':F_align_times(f_data_airkorea_aligned_test_sites,v_time_test)}

if Consider_ground_monitors_as_input:
    # If ground monitors are to be used as inputs as well: 
    d_testing['airkorea_input'] = F_align_times(f_data_airkorea_aligned_train_sites,v_time_test)
    v_datatypes += ['airkorea_input']
if Use_GEOSCF:
    d_training['GEOSCF'] = F_align_times(a_data_GEOSCF_aligned,v_time_train)
    d_testing['GEOSCF'] = F_align_times(a_data_GEOSCF_aligned,v_time_test)
    v_datatypes += ['GEOSCF']
if Use_TROPOMI:
    d_training['TROPOMI'] = F_align_times(a_data_TROPOMI_daily_aligned,v_time_train)
    d_testing['TROPOMI'] = F_align_times(a_data_TROPOMI_daily_aligned,v_time_test)
    v_datatypes += ['TROPOMI']
if Use_GEMS:
    d_training['GEMS'] = F_align_times(a_data_GEMS_aligned,v_time_train)
    d_testing['GEMS'] = F_align_times(a_data_GEMS_aligned,v_time_test)
    v_datatypes += ['GEMS']
if Use_GCAS:
    d_training['GCAS'] = F_align_times(a_data_GCAS_aligned,v_time_train)
    d_testing['GCAS'] = F_align_times(a_data_GCAS_aligned,v_time_test)
    v_datatypes += ['GCAS']

print('Data Split Summary:')
print(f'  AirKorea: {len(d_training['airkorea'])} training samples from {len(d_training['airkorea'].groupby(['lat','lon']).mean())} sites, {len(d_testing['airkorea'])} testing samples from {len(d_testing['airkorea'].groupby(['lat','lon']).mean())} sites')
if Use_GEOSCF:
    print(f'  GEOS-CF:  {len(d_training['GEOSCF'].time)} training hours, {len(d_testing['GEOSCF'].time)} testing hours')
if Use_TROPOMI:
    print(f'  TROPOMI:  {str((~np.isnan(d_training['TROPOMI']['TROPOMI_DAILY_no2'].groupby('time.day').mean())).any(dim=['lat','lon']).sum().values)} days with training data, {str((~np.isnan(d_testing['TROPOMI']['TROPOMI_DAILY_no2'].groupby('time.day').mean())).any(dim=['lat','lon']).sum().values)} days with testing data')
if Use_GEMS:
    print(f'  GEMS:     {str((~np.isnan(d_training['GEMS']['GEMS_ColumnAmountNO2Trop'])).any(dim=['lat','lon']).sum().values)} hours with training data, {str((~np.isnan(d_testing['GEMS']['GEMS_ColumnAmountNO2Trop'])).any(dim=['lat','lon']).sum().values)} hours with testing data')
if Use_GCAS:
    print(f'  GCAS:     {str((~np.isnan(d_training['GCAS']['GCAS_no2_vertical_column_below_aircraft'])).any(dim=['lat','lon']).sum().values)} hours with training data, {str((~np.isnan(d_testing['GCAS']['GCAS_no2_vertical_column_below_aircraft'])).any(dim=['lat','lon']).sum().values)} hours with testing data')

###################################################################################################
# DATA PROCESSING

# Define Data Processor:
data_processor = DataProcessor(x1_name="lat", x2_name="lon")

# Condition the processor on the training data:
_ = data_processor(d_training['airkorea'], method='positive_semidefinite')
if Use_GEOSCF:
    _ = data_processor(d_training['GEOSCF'], method='mean_std')
if Use_TROPOMI:
    _ = data_processor(d_training['TROPOMI'], method='positive_semidefinite')
if Use_GEMS:
    _ = data_processor(d_training['GEMS'], method='positive_semidefinite')
if Use_GCAS:
    _ = data_processor(d_training['GCAS'], method='positive_semidefinite')
_ = data_processor(a_data_AUX_aligned,method='min_max')

# Process Training and Testing Data:
d_training_processed = {}
d_testing_processed = {}
for s_datatype in v_datatypes:
    try:
        d_training_processed[s_datatype] = data_processor(d_training[s_datatype])
    except:
        pass
    d_testing_processed[s_datatype] = data_processor(d_testing[s_datatype])
a_data_AUX_processed = data_processor(a_data_AUX_aligned,method='min_max')

# Save Data Processor:
data_processor.save(processor_dir)
print('-----DATA PROCESSING COMPLETE-----')

###################################################################################################
# DEFINE TASK LOADERS

# Define the task loaders for training and testing datasets:
l_training_context = []
l_testing_context = []
l_train_context_sampling = []
l_test_context_sampling = []

if Consider_ground_monitors_as_input:
    Training_Links = [(0,0)]
    Training_Target_Sampling = "split"
else:
    Training_Links = None
    Training_Target_Sampling = "all"

for s_type in v_datatypes:
    if (s_type == 'airkorea'):
        if Consider_ground_monitors_as_input:
            l_training_context += [d_training_processed['airkorea']]
            l_train_context_sampling += ["split"]
    elif (s_type == 'airkorea_input'):
        if Consider_ground_monitors_as_input:
            l_testing_context = [d_testing_processed['airkorea_input']]
            l_test_context_sampling += ["all"]
    else:
        l_training_context += [d_training_processed[s_type]]
        l_train_context_sampling += ["all"]
        l_testing_context += [d_testing_processed[s_type]]
        l_test_context_sampling += ["all"]

training_task_loader = TaskLoader(
    context=l_training_context,
    # aux_at_contexts=(0,a_data_LULC_processed),
    target=d_training_processed['airkorea'],
    aux_at_targets=a_data_AUX_processed,
    links=Training_Links
)

testing_task_loader = TaskLoader(
    context=l_testing_context,
    # aux_at_contexts=(0,a_data_LULC_processed),
    target=d_testing_processed['airkorea'],
    aux_at_targets=a_data_AUX_processed,
)

print('Task Loaders Created.')

###################################################################################################
# CREATE AND INITIALIZE MODEL

if b_Retrain_Model:
    model = ConvNP(data_processor, training_task_loader, unet_channels=unet_channels_settings)
    
    # Fix a bug: JSON is not able to encode numpy float32:
    model.config['encoder_scales'] = [float(number) for number in model.config['encoder_scales']]

    # Save the model
    model.save(processor_dir)

    print('ConvNP Model Created and Saved.')
else:
    model = ConvNP(data_processor, training_task_loader, processor_dir)
    print('ConvNP Model Loaded.')

###################################################################################################
# SET UP TRAINING

training_task_loader.load_dask()
testing_task_loader.load_dask()

# Define task Generators for training and testing:
def gen_training_tasks(dates, progress=True):
    tasks = []
    for date in dates:
        task = training_task_loader(date, context_sampling=l_train_context_sampling, target_sampling=Training_Target_Sampling, split_frac=Fraction_of_ground_monitors_to_train_on)
        tasks.append(task)
    return tasks

def gen_testing_tasks(dates, progress=True):
    tasks = []
    for date in dates:
        task = testing_task_loader(date, context_sampling=l_test_context_sampling, target_sampling="all")
        tasks.append(task)
    return tasks

# Generate Training and Testing Evaluation Tasks
train_tasks = gen_training_tasks(v_time_train)
test_tasks = gen_testing_tasks(v_time_test)

# Define an RMSE loss function for evalauting performance
def compute_model_rmse(model, val_tasks=test_tasks):
    errors = []
    target_var_ID = testing_task_loader.target_var_IDs[0][0]  # assume 1st target set and 1D
    for task in val_tasks:
        mean = data_processor.map_array(model.mean(task), target_var_ID, unnorm=True)
        true = data_processor.map_array(task["Y_t"][0], target_var_ID, unnorm=True)
        errors.extend(np.abs(mean - true))
    return np.sqrt(np.nanmean(np.concatenate(errors) ** 2)) # RMSE loss

if b_Retrain_Model:
    # Check number of model parameters
    _ = model(train_tasks[0])
    print(f"Model has {deepsensor.backend.nps.num_params(model.model):,} parameters")
    
    # test that the loss function computes:
    print('Loss funcion of untrained model: {}'.format(compute_model_rmse(model, val_tasks=train_tasks)))
else:
    print('Model is not going to be retrained.')
    print('Loss funcion of model: {}'.format(compute_model_rmse(model, val_tasks=train_tasks)))

print('-----MODEL SETUP COMPLETE-----')

###################################################################################################
# TRAIN MODEL

if b_Retrain_Model:
    losses = []
    val_rmses = []
    train_times = []
    
    val_rmse_best = np.inf
    trainer = Trainer(model, lr=5e-5)

    timer_start = time.time()
    for epoch in range(n_max_epoch):
        batch_losses = trainer(train_tasks[epoch%7:len(train_tasks):7]) # Use a subset (1/7) of the total training tasks in each epoch
        losses.append(np.mean(batch_losses))
        val_rmses.append(compute_model_rmse(model, val_tasks=train_tasks)) # evalaute model against full training dataset
        train_times.append((time.time()-timer_start)/60)
        if val_rmses[-1] < val_rmse_best:
            val_rmse_best = val_rmses[-1]
            # Fix a bug: JSON is not able to encode numpy float32:
            model.config['encoder_scales'] = [float(number) for number in model.config['encoder_scales']]
            model.save(processor_dir)
        print(f'Training epoch {epoch+1} of {n_max_epoch}, loss {val_rmse_best}, elapsed time {(time.time()-timer_start)/60} min')

    # save to CSV
    f_training_log = pd.DataFrame({'Epoch':np.arange(0,n_max_epoch),'Training Loss':losses,'Validation RMSE':val_rmses,'Training Time (minutes)':train_times})
    f_training_log.to_csv(os.path.join(processor_dir,'training_log.csv'))

else:
    print('Model was not retrained.')
    f_training_log = pd.read_csv(os.path.join(processor_dir,'training_log.csv'))

print('-----TRAINING COMPLETE-----')

###################################################################################################
# EVALAUTE MODEL ON TEST DATA

# Baseline 1: GEOS-CF Values at Coordinates
if Use_GEOSCF:
    def F_get_geoscf(a_data_geoscf,
                     time,
                     coords):
        a_geos_time = a_data_geoscf.sel(time=time)['GEOS-CF_no2']*1e9
        v_out = []
        for i_ndex in range(len(coords[0])):
            v_out += [a_geos_time.interp({'lat':coords[0][i_ndex],'lon':coords[1][i_ndex]}).values]
        return np.array(v_out)

# Baseline 2: Nearest Ground Monitor
def F_get_nearest(coords,true):
    v_out = []
    for i_ndex in range(len(coords[0])):
        sq_dist = ((coords[0] - coords[0][i_ndex])**2) + ((coords[1] - coords[1][i_ndex])**2)
        sq_dist[i_ndex] = np.nan
        id_nearest = np.nanargmin(sq_dist)
        v_out += [true[id_nearest]]
    return np.array(v_out)
def F_get_nearest_from_input(coords,coords_input,true_input):
    v_out = []
    for i_ndex in range(len(coords[0])):
        sq_dist = ((coords_input[0] - coords[0][i_ndex])**2) + ((coords_input[1] - coords[1][i_ndex])**2)
        id_nearest = np.nanargmin(sq_dist)
        v_out += [true_input[id_nearest]]
    return np.array(v_out)

# Apply model to validation tasks:
if b_Repeat_Evaluation:
    l_errors = []
    for val_task in test_tasks:
        time = val_task['time']
        target_var_ID = testing_task_loader.target_var_IDs[0][0]
        # mean = data_processor.map_array(model.mean(val_task), target_var_ID, unnorm=True)
        true = data_processor.map_array(val_task['Y_t'][0], target_var_ID, unnorm=True)[0]
        coords = data_processor.map_coord_array(val_task['X_t'][0], unnorm=True)
        pred = model.predict(val_task, X_t = coords)
        mean = pred[target_var_ID]['mean'].values
        std = pred[target_var_ID]['std'].values
        if Use_GEOSCF:
            geos = F_get_geoscf(a_data_GEOSCF_aligned,time,coords)
        if Consider_ground_monitors_as_input:
            coords_input = data_processor.map_coord_array(val_task['X_c'][0], unnorm=True)
            true_input = data_processor.map_array(val_task['Y_c'][0], 'NO2', unnorm=True)[0]
            near = F_get_nearest_from_input(coords,coords_input,true_input)
        else:
            near = F_get_nearest(coords,true)
        
        f_errors_task = pd.DataFrame({'time':np.array([time]*len(true)),
                                     'lat':coords[0],
                                     'lon':coords[1],
                                     'Truth':true,
                                     'Model':mean - true,
                                     'Model_Normalized':((mean - true)/std), 
                                     'Baseline_Nearest':near - true,
                                     })
        if Use_GEOSCF:
            f_errors_task['Baseline_GEOSCF'] = geos - true
        
        l_errors += [f_errors_task]
        print(f'Evalaution complete for {time}')
    
    f_errors = pd.concat(l_errors)

    # Save:
    f_errors.to_csv(os.path.join(processor_dir,'evaluation_errors.csv'),index=False)

    print('-----TESTING COMPLETE-----')

###################################################################################################

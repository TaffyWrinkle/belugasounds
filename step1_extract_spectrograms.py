#
# extract_spectrograms.py
#
# Load detection labels, extract audio for detection and non-detection regions,
# compute and save spectrograms.
#
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License.
#

#%% Imports

import pandas as pd
from datetime import datetime, timedelta
import glob
import os
import wave
import pylab
from matplotlib import pyplot
from joblib import Parallel, delayed
import multiprocessing
import gc
import random


#%% Step 1: import the labels

current_dir = "./Whale_Acoustics/"

data_dir = current_dir + "Data/"
labeled_data_dir = data_dir + "Labeled_Data/"
audio_dir = data_dir + "Raw_Audio/"
output_spectrogram_dir = data_dir + "Extracted_Spectrogram/"

if not os.path.exists(output_spectrogram_dir):
    os.makedirs(output_spectrogram_dir)

detector_labelled_data = pd.read_excel (labeled_data_dir + '_PG_WandM_Detector.xlsx')[['UTC', 'Species']].drop_duplicates()
detector_labelled_data['UTC'] =  detector_labelled_data['UTC'].astype('datetime64[s]')
detector_labelled_data = detector_labelled_data.drop_duplicates()
detector_labelled_data['Detection_TimeStamp'] = detector_labelled_data['UTC'].dt.strftime('%Y%m%d%H%M%S')
detector_labelled_data['Date'] = detector_labelled_data['UTC'].dt.strftime('%Y%m%d')

print(detector_labelled_data.shape)
#detector_labelled_data.Date.value_counts().sort_index()


#%% Step 2: match each labeled data segment to the corresponding audio file

audio_filenames = glob.glob(audio_dir + '*.wav')
audio_filenames = [os.path.basename(filename) for filename in audio_filenames]
audio_filenames_df = pd.DataFrame(audio_filenames, columns = ['audio_filename'])
audio_filenames_df['audio_start_TimeStamp'] = '20' + audio_filenames_df['audio_filename'].str.split(".").str[1]
audio_filenames_df['audio_end_TimeStamp'] = ''
for index, row in audio_filenames_df.iterrows():
    audio_start_TimeStamp = row['audio_start_TimeStamp']
    audio_end_time = datetime(int(audio_start_TimeStamp[0:4]), 
                              int(audio_start_TimeStamp[4:6]), 
                              int(audio_start_TimeStamp[6:8]), 
                              int(audio_start_TimeStamp[8:10]), 
                              int(audio_start_TimeStamp[10:12]),
                              int(audio_start_TimeStamp[12:14])) + timedelta(minutes = 5) 
    audio_end_TimeStamp = audio_end_time.strftime('%Y') + audio_end_time.strftime('%m') + audio_end_time.strftime('%d') + audio_end_time.strftime('%H')  + audio_end_time.strftime('%M') + audio_end_time.strftime('%S')
    audio_filenames_df.at[index,'audio_end_TimeStamp'] = audio_end_TimeStamp
    
audio_filenames_df['Date'] = audio_filenames_df['audio_start_TimeStamp'].str[:8]
audio_filenames_df.Date.value_counts().sort_index()

# Transform to dictionary with format {audio_filename: ['audio_start_TimeStamp', 'audio_end_TimeStamp', 'audio_start_date']}
audio_filenames_dict = audio_filenames_df.set_index('audio_filename').T.to_dict('list')

detector_labelled_data['audio_filename'] = ''
for index, row in detector_labelled_data.iterrows():
    Detection_TimeStamp = row['Detection_TimeStamp']
    matched_audio_filename = [k for k, v in audio_filenames_dict.items() if v[0] <= Detection_TimeStamp < v[1]]
    if len(matched_audio_filename) == 0:
        detector_labelled_data.at[index,'audio_filename'] = 'No Matched Audio File'
    elif len(matched_audio_filename) == 1:      
        detector_labelled_data.at[index,'audio_filename'] = matched_audio_filename[0]
    elif len(matched_audio_filename) >=2:      
        detector_labelled_data.at[index,'audio_filename'] = 'Multiple Matched Audio Files'  

print(detector_labelled_data.audio_filename.value_counts())   


#%% Step 3: extract spectrograms from detections

matched_detector_labelled_data = detector_labelled_data.loc[(~detector_labelled_data.audio_filename.str.contains('No Matched Audio File')) & (~detector_labelled_data.audio_filename.str.contains('Multiple Matched Audio Files'))].reset_index(drop=True)
print(matched_detector_labelled_data.shape)

matched_detector_labelled_data_B_F = matched_detector_labelled_data.loc[(matched_detector_labelled_data.Species == 'B') | (matched_detector_labelled_data.Species == 'F')].reset_index(drop=True)
print(matched_detector_labelled_data_B_F.shape)

spectrogram_seconds_duration = 2 

def get_wav_info(wav_file):
    wav = wave.open(wav_file, 'r')
    frames = wav.readframes(-1)
    sound_info = pylab.frombuffer(frames, 'int16')
    frame_rate = wav.getframerate()
    wav.close()
    return sound_info, frame_rate

def graph_spectrogram(wav_file, serialnumber, audio_begin_TimeStamp, start_second, Species):
    sound_info, frame_rate = get_wav_info(wav_file)
    pyplot.figure(num=None, figsize=(19, 12))
    pyplot.subplot(222)
    ax = pyplot.axes()
    ax.set_axis_off()
    pyplot.specgram(sound_info[frame_rate * start_second: frame_rate * (start_second+2)], Fs = frame_rate)
    pyplot.savefig(output_spectrogram_dir + serialnumber + '.' + audio_begin_TimeStamp + '_' + str(start_second)  + '_' + Species + '.png', bbox_inches='tight', transparent=True, pad_inches=0.0)
    pyplot.close()
    gc.collect()

def generate_spectrogram_B_F(i):
    Species = matched_detector_labelled_data_B_F.loc[i, 'Species']
    audio_filename = matched_detector_labelled_data_B_F.loc[i, 'audio_filename']
    serialnumber, audio_begin_TimeStamp = audio_filename.split('.')[0:2]
    Detection_TimeStamp = matched_detector_labelled_data_B_F.loc[i, 'Detection_TimeStamp']
    detection_start_timedelta = datetime(int(Detection_TimeStamp[0:4]), 
                 int(Detection_TimeStamp[4:6]), 
                 int(Detection_TimeStamp[6:8]),
                 int(Detection_TimeStamp[8:10]),
                 int(Detection_TimeStamp[10:12]),
                 int(Detection_TimeStamp[12:14])) - datetime(int('20' + audio_begin_TimeStamp[0:2]), 
                          int(audio_begin_TimeStamp[2:4]), 
                          int(audio_begin_TimeStamp[4:6]),
                          int(audio_begin_TimeStamp[6:8]), 
                          int(audio_begin_TimeStamp[8:10]),
                          int(audio_begin_TimeStamp[10:12]))
    detection_start_second = detection_start_timedelta.seconds
    return graph_spectrogram(audio_dir + audio_filename, serialnumber, audio_begin_TimeStamp, detection_start_second, Species)

num_cores = multiprocessing.cpu_count()
spectrograms_B_F = Parallel(n_jobs=num_cores)(delayed(generate_spectrogram_B_F)(i) for i in range(len(matched_detector_labelled_data_B_F)))


#%% Step 4: extract spectrograms from non-detection audio regions

sample_size = 2500
sound_detected_audio_filenames = detector_labelled_data.loc[~detector_labelled_data.audio_filename.str.contains('No Matched Audio File')].audio_filename.unique().tolist()
nosound_detected_audio_filenames = [filename for filename in audio_filenames if filename not in sound_detected_audio_filenames]
nosound_detected_audio_filenames_sample = random.sample(nosound_detected_audio_filenames, min(len(nosound_detected_audio_filenames), sample_size))

def generate_spectrogram_N(i):
    audio_filename = nosound_detected_audio_filenames_sample[i]
    Species = 'N'
    serialnumber, audio_begin_TimeStamp = audio_filename.split('.')[0:2]    
    # Each audio file is five minutes; sample the starting timestamp between second 0 - 299
    start_second = random.sample(range(0, 299), 1)[0]      
    return graph_spectrogram(audio_dir + audio_filename, serialnumber, audio_begin_TimeStamp, start_second, Species)

num_cores = multiprocessing.cpu_count()
spectrograms_N = Parallel(n_jobs=num_cores)(delayed(generate_spectrogram_N)(i) for i in range(len(nosound_detected_audio_filenames_sample)))
 

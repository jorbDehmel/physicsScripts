#!/usr/bin/python3

'''
This is a revision of my filter scripts wherein I attempt to
simplify them as much as possible while still being rigorous.
- Jordan Dehmel

From Dr. Boymelgreen

For each height:

Begin with Control ("0kHz")
    Calculate Average and STDEV from raw data
    Filter out any outliers that are greater than 2*STDEV
        (for the Brownian, less than 2*STDEV will often be
        negative I think)
    Recalculate Average +STDEV from the filtered data 
        (for reference, for top, I get average =0.014 and
        Average+2*STDEV=0.0178) For bottom, I get 0.09 and 0.14
        from the filtered data and 0.11 and 0.22 for the
        unfiltered data (I am not sure what the extra filter is
        between these two sets)

To calculate the mobility under applied field
    Filter out any data points that are less than
        Brownian+2STDEV
    Calculate AVERAGE+STDEV
    Remove outliers that are greater than AVERAGE+2*STDEV or
        less than AVERAGE-2*STDEV
    Recalculate AVERAGE+STDEV - that will be the data point for
        the frequency curve

I noted that for the top 1khz, there was only 1 "outlier" in 3
and in bottom 1kHz, there were none. I think that in general
this should be true if the tracked data is good quality.
'''

from typing import Union, List, Tuple, Optional
import sys
import numpy as np
from matplotlib import pyplot as plt
import pandas as pd
import reverser


# The variable to perform statistics on
to_capture: str = 'MEAN_STRAIGHT_LINE_SPEED'

# The files to load
filepaths: List[str] = ['/home/jorb/data/Report/Top/0khztrackssexport.csv',
                    '/home/jorb/data/Report/Top/1khztracks.csv',
                    '/home/jorb/data/Report/Bot/0khztracksexport.csv',
                    '/home/jorb/data/Report/Bot/1khztracks.csv']

# Frequencies
frequencies: List[float] = [0.0, 1000.0, 0.0, 1000.0]


def display_means(means: List[float], standard_deviations: List[float]) -> None:
    '''
    :param means: The mean (y) values to graph
    :param standard_deviations: The y error bars
    :param frequencies: The x values
    :return: None
    '''

    # Initialize pyplot
    plt.figure(figsize=(4.0, 4.0))

    # Write data points
    plt.scatter(y=means, x=frequencies)
    plt.errorbar(y=means, x=frequencies, yerr=standard_deviations)

    if frequencies[0] == 0.0:
        # Draw control line
        plt.hlines(frequencies[0], min(frequencies), max(frequencies))

    # Display
    plt.show()


def filter_single_file(filepath: str, is_brownian: bool,
                       brownian_mean: Union[float, None] = None,
                       brownian_std: Union[float, None] = None
                       ) -> Tuple[pd.DataFrame, int, int, float, float]:
    '''
    :param filepath: The file path to load from
    :param is_brownian: True if this is a 0khz file, False otherwise
    :return: A 5-tuple containing the filtered DataFrame, the number
            of tracks kept, the number of tracks filtered, the mean
            of the straight line speed, and the standard deviation of
            the straight line speed. Note: does NOT drop any useless
            columns.
    '''

    # Load file from filepath
    file: pd.DataFrame = pd.read_csv(filepath)

    # Drop labels
    file.drop(axis=0, inplace=True, labels=[0, 1, 2])

    # Make backup for latter scatterplotting
    file_backup: pd.DataFrame = file.copy(deep=True)

    speeds: List[float] = file[to_capture].astype(float).to_list()
    initial_num_rows: int = len(speeds)

    # Calculate mean and std
    mean: float = float(np.mean(speeds))
    std: float = float(np.std(speeds))

    num_rows_dropped: int = 0

    # If not brownian, do pre-filtering as mentioned above
    if not is_brownian:
        if brownian_mean is None or brownian_std is None:
            raise RuntimeError(
                'If a file is not Brownian, you must pass the Brownian values.')

        # Drop anything below 2 standard deviation above brownian
        threshold: float = brownian_mean + 2 * brownian_std
        for row in file.iterrows():

            # If below threshold (brownian_mean + 2 * brownian_std), drop row
            if float(row[1][to_capture]) < threshold:
                # Drop row
                file.drop(axis=0, inplace=True, labels=[row[0]])
                num_rows_dropped += 1

    # Internal filters. If this is a Brownian file, these are the only filters.
    for row in file.iterrows():

        # Filter if outlier as determined above
        if float(row[1][to_capture]) > mean + 2 * std:
            # Drop row
            file.drop(axis=0, inplace=True, labels=[row[0]])
            num_rows_dropped += 1

        # Filter if non-Brownian and below 2 standard deviations from mean
        elif not is_brownian and (float(row[1][to_capture]) < mean - 2 * std):
            # Drop row
            file.drop(axis=0, inplace=True, labels=[row[0]])
            num_rows_dropped += 1

    # Recalculate mean and std
    speeds = file[to_capture].astype(float).to_list()
    filtered_mean: float = float(np.mean(speeds))
    filtered_std: float = float(np.std(speeds))

    # Create scatterplot
    reverser.display_kept_lost_histogram(file_backup, file, filepath)

    # Return values as designated above
    return (file, initial_num_rows - num_rows_dropped,
            num_rows_dropped, filtered_mean, filtered_std)


def main() -> int:
    '''
    Main function
    '''

    # Initialize lists
    files: List[Optional[pd.DataFrame]] = [None for _ in range(len(filepaths))]

    rows_kept: List[int] = [-1 for _ in range(len(filepaths))]
    rows_dropped: List[int] = [-1 for _ in range(len(filepaths))]

    means: List[Optional[float]] = [None for _ in range(len(filepaths))]
    standard_deviations: List[Optional[float]] = [None for _ in range(len(filepaths))]

    # Iterate over list of files
    files[0], rows_kept[0], rows_dropped[0], means[0], standard_deviations[0] = filter_single_file(
        filepaths[0], True)
    print(f'Kept {rows_kept[0]} of {rows_kept[0] + rows_dropped[0]} on file {filepaths[0]}')

    for i, filepath in enumerate(filepaths):
        if i == 0:
            continue

        to_unpack = filter_single_file(
            filepath, False, means[0], standard_deviations[0])
        files[i], rows_kept[i], rows_dropped[i], means[i], standard_deviations[i] = to_unpack

        print(f'Kept {rows_kept[i]} of {rows_kept[i] + rows_dropped[i]} on file {filepath}')

    # display_means(means, standard_deviations, frequencies)

    # Construct minimal .csv output file, for simplicities sake
    # A thorough output file can be generated via filterer.py

    # Output .csv formatting:
    # FILEPATH,FREQUENCY,MEAN_STRAIGHT_LINE_SPEED,STRAIGHT_LINE_SPEED_STD,
    # INITIAL_TRACK_COUNT,FILTERED_TRACK_COUNT,

    headers: List[str] = ['FILEPATH',
                      'FREQUENCY',
                      'MEAN_STRAIGHT_LINE_SPEED',
                      'STRAIGHT_LINE_SPEED_STD',
                      'INITIAL_TRACK_COUNT',
                      'FILTERED_TRACK_COUNT']

    # Build raw python array
    array: List[List[Union[str, float, int, None]]] = []
    for i, _ in enumerate(filepaths):
        # Initialize row
        row: List[Union[str, float, int, None]] = [0.0 for _ in headers]

        # Build row
        row[0] = filepaths[i]
        row[1] = frequencies[i]
        row[2] = means[i]
        row[3] = standard_deviations[i]
        row[4] = rows_kept[i] + rows_dropped[i]
        row[5] = rows_kept[i]

        # Append a copy of the row to the array
        array.append(row[:])

    # Turn raw python array into DataFrame and save as .csv file
    csv: pd.DataFrame = pd.DataFrame(data=array, columns=headers)
    csv.to_csv('file_summary.csv')

    # Exit program without error
    return 0


if __name__ == '__main__':
    sys.exit(main())

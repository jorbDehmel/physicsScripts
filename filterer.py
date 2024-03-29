'''
This file is what you will use if you want "fancier" filtering
and utilities, like error handling and automatic file detection
given a folder.

Jordan Dehmel, 2023
jedehmel@mavs.coloradomesa.edu

Protocol overview from Dr. Boymelgreen

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

Refer to this list when modifying do_std_filter_flags
or do_iqr_filter_flags.

col_names = ['TRACK_DISPLACEMENT',
             'TRACK_MEAN_SPEED',
             'TRACK_MEDIAN_SPEED',
             'TRACK_MEAN_QUALITY',
             'TOTAL_DISTANCE_TRAVELED',
             'MEAN_STRAIGHT_LINE_SPEED',
             'LINEARITY_OF_FORWARD_PROGRESSION']
'''

# Import needed packages
import sys
from time import time
from typing import List, Tuple, Union, Optional, Any
from os import chdir, getcwd, sep
import pandas as pd
import matplotlib.pyplot as plt
from numpy import zeros, mean, std, percentile
import name_fixer

###############################################################################
# Begin settings; See docs/project_overview.pdf for a thorough explanation of
# each of these.
###############################################################################


# Put the folder you want to operate on into this string
folder: str = ''

# Flags for which -2 * STD filters to apply
# A False in the first position means it will not apply STD filters
# to the first item in col_names, in this case 'TRACK_DISPLACEMENT'.
# If it were True instead, it will do that filtering.
do_std_filter_flags: Union[List[bool], None] = None

# Flags for which -1.5 * IQR filters to apply
# This works just like above. If it is equal to None, it does none
# of these filters
do_iqr_filter_flags: Union[List[bool], None] = None

# If true, filters any particles whose quality (as measured by
# imagej) is below the given percentile
do_quality_percentile_filter: bool = False
quality_percentile_filter: float = 50.0

# Conversion from pixels/frame to um/s
conversion: float = 4 * 0.32

# Tends to work well
# Activates the brownian straight-line-speed threshold filter
# If active, removes any particle below Brownian mean
# straight-line-speed
do_speed_thresh: bool = True

# Determines how many standard deviations a particle must be
# above the Brownian mean in order to survive Brownian mean
# straight line speed thresholding (activated above)
brownian_multiplier: float = 0.0

# Just like do_speed_thresh, but for the displacement
do_displacement_thresh: bool = False

# Just like do_speed_thresh, but for the particle linearity
# (as measured by imagej)
do_linearity_thresh: bool = False

# For filtering tracks which are too short to be meaningful
# since error is higher on shorter tracks
# If active, filters out any tracks w/ less than duration_threshold
# frames.
do_duration_thresh: bool = True
duration_threshold: int = 65

# If not None, also save graphs and .csv files here
secondary_save_path: str = '/home/jorb/Programs/physicsScripts'

# If true, will only print warnings and errors
silent: bool = True

# If true, uses the given brownian speed fallback when no
# brownian file can be detected. This should not be an issue,
# so long as the regular expressions match the Brownian file.
do_speed_thresh_fallback: bool = False
brownian_speed_threshold_fallback: float = 0.042114570268546765

# Turns on or off extra graphs
do_filter_scatter_plots: bool = True
do_extra_filter_scatter_plots: bool = False

# If true, saves a histogram of filtered data points for each file
save_filtering_data: bool = False

###############################################################################
# End settings
###############################################################################

# Column names which will be kept from the original .csv file
col_names: List[str] = ['TRACK_DISPLACEMENT', 'TRACK_MEAN_SPEED',
                        'TRACK_MEDIAN_SPEED', 'TRACK_MEAN_QUALITY',
                        'TOTAL_DISTANCE_TRAVELED', 'MEAN_STRAIGHT_LINE_SPEED',
                        'LINEARITY_OF_FORWARD_PROGRESSION']

# Columns which didn't originally exist, but will exist in our output .csv
extra_columns: List[str] = ['INITIAL_TRACK_COUNT',
                            'FILTERED_TRACK_COUNT',
                            'STRAIGHT_LINE_SPEED_UM_PER_S']

# These are internally used; Do not change
brownian_speed_threshold: float = 0.0
brownian_displacement_threshold: float = 0.0
brownian_linearity_threshold: float = 0.0

# These are for internal use, do not change
filter_scatter_plots_data: List[List[List[Any]]] = []
save_num: int = 0
quality_threshold: Optional[float] = None

# These are regular expressions that power the automatic folder
# thing. Any naming scheme which matches these regular expressions
# is valid. If the naming scheme does not match, it is not detectable
# by this program.
patterns: List[str] = ['(((?<![0-9])0 ?khz|control).*track|t(0 ?khz|control))',
                       '((0.8 ?khz|800 ?hz).*track|t(0.8 ?khz|800 ?hz))',
                       '(1 ?khz.*track|t1 ?khz)',
                       '((?<![0-9])5 ?khz.*track|t5 ?khz)',
                       '(10 ?khz.*track|t10 ?khz)',
                       '(25 ?khz.*track|t25 ?khz)',
                       '(50 ?khz.*track|t50 ?khz)',
                       '(75 ?khz.*track|t75 ?khz)',
                       '(100 ?khz.*track|t100 ?khz)',
                       '(150 ?khz.*track|t150 ?khz)',
                       '(200 ?khz.*track|t200 ?khz)',
                       '(300 ?khz.*track|t300 ?khz)']

# If the above patterns cannot be matches, it will attempt these.
fallback_patterns: List[str] = ['((?<![0-9])0 ?khz|[cC]ontrol)',
                                '(0.8 ?khz|800 ?hz)',
                                '1 ?khz',
                                '(?<![0-9])5 ?khz',
                                '10 ?khz',
                                '25 ?khz',
                                '50 ?khz',
                                '75 ?khz',
                                '100 ?khz',
                                '150 ?khz',
                                '200 ?khz',
                                '300 ?khz']


def do_file(name: str,
            displacement_threshold: float = 0.0,
            speed_threshold: float = 0.0,
            linearity_threshold: float = 0.0,
            std_drop_flags: List[bool] = None,
            iqr_drop_flags: List[bool] = None,
            return_label: bool = False) -> ([float], [float]):
    '''
    Analyze a file with a given name, and return the results
    If speed_threshold is nonzero, any track with less speed will
    be filtered out. This is similar for the linearity and displacement
    thresholds. The std_drop_flags and iqr_drop_flags lists are
    arrays of booleans. If the ith item is True, that column
    will be filtered such that only items which remain are those
    which are above 2 STD/IQR below the mean for their column.
    Returns a tuple containing the output data followed by
    the standard deviations.
    '''

    global save_num
    save_num += 1

    csv: pd.DataFrame = pd.DataFrame()

    try:
        # Load file
        csv = pd.read_csv(name)
    except RuntimeError:
        print('Failed to open', name)
        return ([None for _ in col_names] + [None, None],
                [None for _ in col_names])

    # Drop useless data (columns)
    names_to_drop: List[str] = []
    for column_name in csv.columns:
        if column_name not in col_names and column_name != 'TRACK_DURATION':
            names_to_drop.append(column_name)

    csv.drop(axis=1, inplace=True, labels=names_to_drop)

    # Ensure the columns are in the correct order (VITAL)
    i: int = 0
    for item in csv.columns.to_list():
        if item != 'TRACK_DURATION':
            assert item == col_names[i]
            i += 1

    # Drop useless data (rows)
    csv.drop(axis=0, inplace=True, labels=[0, 1, 2])

    if save_filtering_data:
        plt.clf()
        plt.hist([float(row[1]['MEAN_STRAIGHT_LINE_SPEED'])
                 for row in csv.iterrows()], bins=30, color='r', label='PRE')

        m = mean([float(row[1]['MEAN_STRAIGHT_LINE_SPEED'])
                 for row in csv.iterrows()])
        s = std([float(row[1]['MEAN_STRAIGHT_LINE_SPEED'])
                for row in csv.iterrows()])
        plt.vlines([m - s, m, m + s], 0, 5, colors=['r'])

    # For keeping track of what was dropped
    dropped_row_indices = []

    # Used later
    initial_num_rows: int = len(csv)

    backup = csv.copy(deep=True)

    # Null filtering
    for row in csv.iterrows():
        if float(row[1]['TRACK_DURATION']) != float(row[1]['TRACK_DURATION']):
            csv.drop(axis=0, inplace=True, labels=[row[0]])

    # Do duration thresh here
    try:
        backup = csv.copy(deep=True)

        if do_duration_thresh:
            for row in csv.iterrows():
                # Must pass duration threshold
                if (float(row[1]['TRACK_DURATION']) < duration_threshold
                        or float(row[1]['TRACK_DURATION'])
                        != float(row[1]['TRACK_DURATION'])):
                    dropped_row_indices.append(
                        [row[0], row[1]['MEAN_STRAIGHT_LINE_SPEED'],
                         'DURATION_THRESHOLD'])
                    csv.drop(axis=0, inplace=True, labels=[row[0]])
                    continue

        if csv.shape[0] == 0:
            print('In file', name)
            print('Error! No items exceeded duration thresholding.')
            raise RuntimeError('Overfiltering Error')

    except RuntimeError as e:
        print(e)
        print('SEVERE WARNING! Reverting')
        csv = backup.copy(deep=True)

    # Now drop duration, it's not needed anymore
    csv.drop(axis=1, inplace=True, labels=['TRACK_DURATION'])
    assert csv.columns.to_list() == col_names

    # Recheck column order
    i: int = 0
    for item in csv.columns.to_list():
        assert item == col_names[i]
        i += 1

    try:
        # Do thresholding here
        if do_speed_thresh:
            for row in csv.iterrows():
                # Must meet mean straight line speed threshold
                if float(row[1]['MEAN_STRAIGHT_LINE_SPEED']) < speed_threshold:
                    dropped_row_indices.append(
                        [row[0], row[1]['MEAN_STRAIGHT_LINE_SPEED'],
                         'SPEED_THRESHOLD'])
                    csv.drop(axis=0, inplace=True, labels=[row[0]])
                    continue

        if csv.shape[0] == 0:
            print('In file', name)
            print('Error! No items exceeded brownian speed thresholding.')
            raise RuntimeError('Overfiltering Error')

    except RuntimeError as e:
        print(e)
        print('SEVERE WARNING! Reverting')
        csv = backup.copy(deep=True)

    try:
        backup = csv.copy(deep=True)

        if do_displacement_thresh:
            for row in csv.iterrows():
                # Must also meet displacement threshold
                if (float(row[1]['TRACK_DISPLACEMENT'])
                        < displacement_threshold):
                    dropped_row_indices.append(
                        [row[0], row[1]['MEAN_STRAIGHT_LINE_SPEED'],
                         'DISPLACEMENT_THRESHOLD'])
                    csv.drop(axis=0, inplace=True, labels=[row[0]])
                    continue

        if csv.shape[0] == 0:
            print('In file', name)
            print(
                'Error! No items exceeded brownian displacement thresholding.')
            raise RuntimeError('Overfiltering Error')

    except RuntimeError as e:
        print(e)
        print('SEVERE WARNING! Reverting')
        csv = backup.copy(deep=True)

    try:
        backup = csv.copy(deep=True)

        if do_linearity_thresh:
            for row in csv.iterrows():
                # Must pass linearity threshold
                if (float(row[1]['LINEARITY_OF_FORWARD_PROGRESSION'])
                        < linearity_threshold):
                    dropped_row_indices.append(
                        [row[0], row[1]['MEAN_STRAIGHT_LINE_SPEED'],
                         'LINEARITY_THRESHOLD'])
                    csv.drop(axis=0, inplace=True, labels=[row[0]])
                    continue

        if csv.shape[0] == 0:
            print('In file', name)
            print('Error! No items exceeded brownian linearity thresholding.')
            raise RuntimeError('Overfiltering Error')

    except RuntimeError as e:
        print(e)
        print('SEVERE WARNING! Reverting')
        csv = backup.copy(deep=True)

    try:
        backup = csv.copy(deep=True)

        if do_quality_percentile_filter:
            # Must pass quality threshold
            quality_percentile_threshold: float = percentile(
                csv['TRACK_MEAN_QUALITY'].astype(float),
                q=[quality_percentile_filter])[0]

            for row in csv.iterrows():
                if (float(row[1]['TRACK_MEAN_QUALITY'])
                        < quality_percentile_threshold):
                    dropped_row_indices.append(
                        [row[0], row[1]['MEAN_STRAIGHT_LINE_SPEED'],
                         'QUALITY_PERCENTILE'])
                    csv.drop(axis=0, inplace=True, labels=[row[0]])
                    continue

        if csv.shape[0] == 0:
            print('In file', name)
            print('Error! No items exceeded quality thresholding.')
            raise RuntimeError('Overfiltering Error')

    except RuntimeError as e:
        print(e)
        print('SEVERE WARNING! Reverting')
        csv = backup.copy(deep=True)

    try:
        backup = csv.copy(deep=True)

        # Do STD filtering if needed
        if std_drop_flags is not None:
            # Collect STD's for the requested items
            std_values: List[float] = [
                std(csv[col_name].astype(float)) if std_drop_flags[i] else 0.0
                for i, col_name in enumerate(csv.columns)]

            # Collect means
            mean_values: List[float] = [
                mean(csv[col_name].astype(float)) if std_drop_flags[i] else 0.0
                for i, col_name in enumerate(csv.columns)]

            # Iterate over rows, dropping if needed
            for row in csv.iterrows():
                raw_list: List[float] = row[1].astype(float).to_list()

                for i, _ in enumerate(raw_list):
                    if raw_list[i] < mean_values[i] - (2 * std_values[i]):
                        dropped_row_indices.append(
                            [row[0], row[1]['MEAN_STRAIGHT_LINE_SPEED'],
                             'INTERNAL_STD_FILTERING'])
                        csv.drop(axis=0, inplace=True, labels=[row[0]])
                        break

                    # Filter anything above, but ONLY if this is control
                    elif (speed_threshold == 0.0 and std_drop_flags[i]
                            and raw_list[i] > mean_values[i]
                            + (2 * std_values[i])):
                        dropped_row_indices.append(
                            [row[0], row[1]['MEAN_STRAIGHT_LINE_SPEED'],
                             'INTERNAL_STD_FILTERING'])
                        csv.drop(axis=0, inplace=True, labels=[row[0]])
                        break

        if csv.shape[0] == 0:
            print('In file', name)
            print('Error! No items survived brownian thresholding',
                  'and standard deviation filtering.')
            raise RuntimeError('Overfiltering Error')

    except RuntimeError as e:
        print(e)
        print('SEVERE WARNING! Reverting')
        csv = backup.copy(deep=True)

    try:
        backup = csv.copy(deep=True)

        # Do IQR filtering if needed
        if (iqr_drop_flags is not None
                and len(iqr_drop_flags) == len(csv.columns)):

            # Calculate IQR values
            iqr_values: List[float] = [0.0 for i in csv.columns]
            for i, col_name in enumerate(csv.columns):
                if iqr_drop_flags[i]:
                    q1, q3 = percentile(csv[col_name].astype(float), [25, 75])
                    iqr_values[i] = q3 - q1

            # Collect means
            mean_values: List[float] = [
                mean(csv[col_name].astype(float)) if iqr_drop_flags[i] else 0.0
                for col_name in csv.columns]

            # Iterate over rows, dropping if needed
            for row in csv.iterrows():
                raw_list: List[float] = row[1].astype(float).to_list()

                for i, _ in enumerate(raw_list):
                    if raw_list[i] < mean_values[i] - (1.5 * iqr_values[i]):
                        dropped_row_indices.append(
                            [row[0], row[1]['MEAN_STRAIGHT_LINE_SPEED'],
                             'INTERNAL_IQR_FILTERING'])
                        csv.drop(axis=0, inplace=True, labels=[row[0]])
                        break

                    # Filter anything above, but ONLY if this is control
                    elif (speed_threshold == 0.0 and iqr_drop_flags[i]
                            and raw_list[i] > mean_values[i]
                            + (1.5 * iqr_values[i])):
                        dropped_row_indices.append(
                            [row[0], row[1]['MEAN_STRAIGHT_LINE_SPEED'],
                             'INTERNAL_IQR_FILTERING'])
                        csv.drop(axis=0, inplace=True, labels=[row[0]])
                        break

        if csv.shape[0] == 0:
            print('In file', name)
            print(
                'Error! No items survived brownian thresholding, STD',
                'filtering, and IQR filtering.')
            raise RuntimeError('Overfiltering Error')

    except RuntimeError as e:
        print(e)
        print('SEVERE WARNING! Reverting')

        csv = backup.copy(deep=True)

    del backup

    csv.to_csv(name.replace('/', '_') + '.filtered.csv')

    # Compile output data from filtered inputs
    final_num_rows: int = len(csv)

    output_data: List[float] = [0.0 for _ in range(
        len(col_names) + len(extra_columns))]
    output_std: List[float] = [0.0 for _ in range(len(col_names))]

    # Calculate means and adjusted STD's
    for i, item in enumerate(col_names):
        output_data[i] = mean(csv[item].astype(float).to_list())
        output_std[i] = std(csv[item].astype(float).to_list())

    for i, _ in enumerate(output_data):
        if final_num_rows == 0:
            print('Warning! No tracks remain!')
            output_data[i] = None

    output_data[len(col_names)] = initial_num_rows
    output_data[len(col_names) + 1] = final_num_rows

    if output_data[5] is None:
        output_data[len(col_names) + 2] = None
    else:
        output_data[len(col_names) + 2] = output_data[5] * conversion

    # Output percent remaining
    if initial_num_rows != final_num_rows and not silent:
        print((name + ':')[-20:],
              'Filtered out', initial_num_rows -
              final_num_rows, 'tracks, leaving',
              final_num_rows, '(' +
              str(round(100 * final_num_rows / initial_num_rows, 3))
              + '% remain)')

    if save_filtering_data:
        plt.hist([float(row[1]['MEAN_STRAIGHT_LINE_SPEED'])
                 for row in csv.iterrows()], bins=30, alpha=0.5, color='b',
                 label='POST')
        plt.title('Pre V. Post Filter SLS w/ Means\n' + name)

        m = mean([float(row[1]['MEAN_STRAIGHT_LINE_SPEED'])
                 for row in csv.iterrows()])
        s = std([float(row[1]['MEAN_STRAIGHT_LINE_SPEED'])
                for row in csv.iterrows()])
        plt.vlines([m - s, m, m + s], 0, 5, colors=['b'])
        plt.vlines([brownian_speed_threshold], 0, 10, colors=['black'])

        lgd = plt.legend(bbox_to_anchor=(1.1, 1.05))

        plt.savefig(name.replace('/', '_') + str(save_num) + '.png',
                    bbox_extra_artists=(lgd,), bbox_inches='tight')

        if secondary_save_path is not None:
            plt.savefig(secondary_save_path + '/' + name.replace('/', '_')
                        + str(save_num) + '.png',
                        bbox_extra_artists=(lgd,), bbox_inches='tight')

        plt.close()

        dropped: pd.DataFrame = pd.DataFrame(dropped_row_indices, columns=[
                                             'CSV_TRACK_ROW_NUMBER',
                                             'MEAN_STRAIGHT_LINE_SPEED',
                                             'REASON'])
        dropped.to_csv(name.replace('/', '_') + str(save_num) + '.csv')
        dropped.to_csv(str(save_num) + '_dropped_tracks' + '.csv')

    if do_filter_scatter_plots:
        # Build an additional array w/ all the data, dropped or not.
        # Save the SLS for each track, as well as whether or not
        # it was dropped. Later we will assemble this into a
        # scatter plot

        # Build into a py array
        data: List[List[Any]] = []

        for item in csv.iterrows():
            data.append([item[0], item[1]['MEAN_STRAIGHT_LINE_SPEED'], False])

        for item in dropped_row_indices:
            data.append([item[0], item[1], True])

        # Append to global data for filter scatter plots
        filter_scatter_plots_data.append(data[:])

        plt.clf()

        plt.figure(figsize=(6, 4), dpi=500)
        plt.title(name[-60:])
        plt.xlabel('Track Original Index')
        plt.ylabel('Mean Straight Line Speed')

        # Brownian line
        if brownian_speed_threshold != 0.0:
            plt.plot([3] + [int(item[0]) for item in csv.iterrows()],
                     [brownian_speed_threshold] +
                     [brownian_speed_threshold for _ in csv.iterrows()],
                     c='black',
                     label='Brownian Mean + ' + str(brownian_multiplier)
                     + ' Standard Deviations')

        # Brownian mean + some amount of std explicit line
        else:
            value: float = output_data[5] + brownian_multiplier * output_std[5]

            plt.plot([3] + [int(item[0]) for item in csv.iterrows()],
                     [value] + [value for _ in csv.iterrows()],
                     c='black',
                     label='Mean + ' + str(brownian_multiplier)
                     + ' Standard Deviations')

        # Kept data
        plt.scatter([int(item[0]) for item in csv.iterrows()],
                    [float(item[1]['MEAN_STRAIGHT_LINE_SPEED'])
                     for item in csv.iterrows()],
                    c='b',
                    label='Kept')

        # Lost data
        plt.scatter([int(item[0]) for item in dropped_row_indices],
                    [float(item[1]) for item in dropped_row_indices],
                    c='r',
                    label='Lost')

        lgd = plt.legend(bbox_to_anchor=(1.1, 1.05), title=(
            'Kept ' + str(csv.shape[0]) + ', Lost '
            + str(len(dropped_row_indices))))

        if secondary_save_path is not None:
            plt.savefig(secondary_save_path + '/'
                        + name.replace('/', '_') +
                        str(save_num) + '_track_scatter.png')
        plt.savefig(name.replace('/', '_')
                    + str(save_num) + '_track_scatter.png',
                    bbox_extra_artists=(lgd,), bbox_inches='tight')

        plt.close()

    if return_label:
        label: str = ''

        if '800hz' in name or '0.8khz' in name:
            label = '800.0'
        elif '1khz' in name:
            label = '1000.0'
        elif '25khz' in name:
            label = '25000.0'
        elif '5khz' in name:
            label = '5000.0'
        elif '10khz' in name:
            label = '10000.0'
        elif '50khz' in name:
            label = '50000.0'
        elif '100khz' in name:
            label = '100000.0'
        elif '200khz' in name:
            label = '200000.0'

        elif '0khz' in name or 'control' in name:
            label = '0.0'

        return (output_data, output_std, label)
    else:
        return (output_data, output_std)


def graph_column_with_bars(table: pd.DataFrame,
                           bar_table: pd.DataFrame,
                           column_name: str,
                           bar_column_name: str,
                           file_name: (str | None) = None,
                           has_control: bool = False,
                           override_ticks: List[str] = None) -> bool:
    '''
    Create a column graph with bars.
    '''

    if (column_name not in table.columns
            or bar_column_name not in bar_table.columns):
        return False

    if file_name is None:
        file_name = column_name

    plt.clf()

    plt.rc('font', size=6)

    minus_bar: List[float] = [table[column_name][i]
                              - bar_table[bar_column_name][i]
                              for i in range(len(table[column_name]))]

    plus_bar: List[float] = [table[column_name][i]
                             + bar_table[bar_column_name][i]
                             for i in range(len(table[column_name]))]

    if has_control:
        brownian_bar: List[float] = [table[column_name][0]
                                     for _ in table[column_name]]
        plt.plot(brownian_bar)

    plt.plot(minus_bar)
    plt.plot(plus_bar)

    if override_ticks is not None:
        plt.plot(override_ticks, table[column_name])
    else:
        plt.plot(table[column_name])

    filter_status: str = ''

    # Create filter text
    if do_speed_thresh:
        filter_status += 'Speed-filtered '
    if do_displacement_thresh:
        filter_status += 'Displacement-filtered '
    if do_linearity_thresh:
        filter_status += 'Linearity-filtered '
    if do_quality_percentile_filter:
        filter_status += 'Quality-filtered '
    if do_quality_percentile_filter:
        filter_status += str(quality_percentile_filter) + \
            '-percentile-plus '
    if do_std_filter_flags is not None:
        filter_status += '2_STD_MIN-filtered '
    if do_iqr_filter_flags is not None:
        filter_status += '1.5_IQR_MIN-filtered '

    if filter_status == '':
        filter_status = 'Unfiltered '

    plt.title(name_fixer.get_cwd() + '\n' + filter_status + '\nMean '
              + column_name +
              'by Applied Frequency (Plus or Minus ' + bar_column_name + ')')

    plt.xlabel('Applied Frequency (Hertz)')
    plt.ylabel(column_name)

    plt.savefig(file_name)

    if secondary_save_path is not None:
        plt.savefig(secondary_save_path + '/' +
                    name_fixer.get_cwd() + '_' + file_name)

    return True


def main() -> int:
    '''
    This is what will be executed when the script is run;
    Everything above here is just meta stuff.
    '''

    global folder, brownian_speed_threshold, brownian_displacement_threshold
    global quality_threshold, brownian_linearity_threshold

    if folder == '' or folder is None:
        if len(sys.argv) != 1:
            if not silent:
                print('Changing folder from arguments...')

            chdir(sys.argv[1])

    else:
        chdir(folder)

    if not silent:
        print('Getting current folder...')

    folder = getcwd()

    if not silent:
        print('Analyzing input data at', folder)

    # Internal string representation of the frequencies
    names: List[str] = name_fixer.fix_names(patterns)
    has_control: bool = names[0] is not None

    # Drop any files which do not exist
    names = [name for name in names if name is not None]

    # Use fallback patterns if needed
    if len(names) == 0:
        if not silent:
            print(
                'Using fallback patterns; \
                This could lead to picking up spots files instead of tracks.')

        names: List[str] = name_fixer.fix_names(fallback_patterns)
        has_control: bool = names[0] is not None

        # Drop any files which do not exist
        names = [name for name in names if name is not None]

    # Exit if no names remain
    if len(names) == 0:
        print(folder)
        raise RuntimeError('No files could be found.')

    # Output array for data
    array = zeros(shape=(len(names), len(col_names) + len(extra_columns)))
    std_array = zeros(shape=(len(names), len(col_names)))

    # Analyze files
    for i, name in enumerate(names):
        if i == 0 and has_control:
            start: float = time()

            try:
                array[i], std_array[i] = do_file(folder + sep + name,
                                                 0.0, 0.0, 0.0,
                                                 do_std_filter_flags,
                                                 do_iqr_filter_flags)
            except RuntimeError:
                print("ERROR DURING COLLECTION OF FILE",
                      folder + sep + name)
                array[i] = [None for i in range(len(array[i]))]
                std_array[i] = [None for i in range(len(std_array[i]))]

            end: float = time()

            # Uses updated brownian standards:
            # In order to pass the filter, it must be more than 2 std from
            # brownian
            brownian_speed_threshold = array[0][5] + \
                brownian_multiplier * std_array[0][5]

            brownian_displacement_threshold = array[0][0]
            quality_threshold = array[0][3]
            brownian_linearity_threshold = array[0][6]

        else:
            start: float = time()

            array[i], std_array[i] = do_file(folder + sep + name,
                                             brownian_displacement_threshold,
                                             brownian_speed_threshold,
                                             brownian_linearity_threshold,
                                             do_std_filter_flags,
                                             do_iqr_filter_flags)

            end: float = time()

            if i == 0 and do_speed_thresh_fallback:
                brownian_speed_threshold = brownian_speed_threshold_fallback

        if not silent:
            print(name, 'took', round(end - start, 5), 'seconds.')

    if not silent:
        print('Generating output .csv file...')

    floated_names: List[str] = [
        str(name_fixer.path_to_hz(item)) for item in names]

    out_csv: pd.DataFrame = pd.DataFrame(array,
                                         columns=(
                                             col_names + extra_columns),
                                         index=floated_names)
    out_csv.to_csv('track_data_summary.csv')

    std_csv: pd.DataFrame = pd.DataFrame(std_array,
                                         columns=(
                                             [name + '_STD'
                                              for name in col_names]),
                                         index=floated_names)
    std_csv.to_csv('track_data_summary_stds.csv')

    if secondary_save_path is not None:
        out_csv.to_csv(secondary_save_path + '/' +
                       name_fixer.get_cwd() + 'track_data_summary.csv')
        std_csv.to_csv(secondary_save_path + '/' +
                       name_fixer.get_cwd() + 'track_data_summary_stds.csv')

    plt.clf()
    plt.rc('font', size=6)

    plt.title(name_fixer.get_cwd() +
              '\nInitial (Top) Vs. Final (Bottom) Track Counts')

    plt.plot(out_csv['INITIAL_TRACK_COUNT'])
    plt.plot(out_csv['FILTERED_TRACK_COUNT'])

    plt.savefig('TRACK_COUNT.png')
    if secondary_save_path is not None:
        plt.savefig(secondary_save_path + '/TRACK_COUNT.png')

    plt.close()

    if do_filter_scatter_plots:
        everything_labels: List[str] = [
            'FREQUENCY', 'ORIGINAL_POSITION', 'MEAN_STRAIGHT_LINE_SPEED',
            'WAS_FILTERED']
        everything = []

        only_kept_x = []
        only_kept_y = []

        only_lost_x = []
        only_lost_y = []

        for i, freq in enumerate(filter_scatter_plots_data):
            for item in freq:
                # item is a single track's info
                # = (name, sls, was_filtered)

                if not item[2]:
                    only_kept_x.append(floated_names[i])
                    only_kept_y.append(float(item[1]))
                else:
                    only_lost_x.append(floated_names[i])
                    only_lost_y.append(float(item[1]))

                everything.append(
                    [floated_names[i], item[0], item[1], item[2]])

        # Save as csv

        # Sort data such that its primary sort in frequency, and secondary is
        # track number. This is just aesthetic
        everything.sort(key=lambda i: float(i[0]) * 1000 + float(i[1]))

        csv: pd.DataFrame = pd.DataFrame(everything, columns=everything_labels)
        if secondary_save_path is not None:
            csv.to_csv(secondary_save_path + '/all_tracks.csv')
        csv.to_csv('all_tracks.csv')

        temp: List[str] = []
        for item in floated_names:
            if item not in temp:
                temp.append(item)
        floated_names = temp[:]

        del temp

        floated_names.sort(key=float)

        # Create actual scatter plot
        plt.clf()

        plt.figure(figsize=(6, 4), dpi=400)

        plt.xticks(ticks=[i for i in range(len(floated_names))],
                   labels=[i for i in floated_names],
                   rotation=45)

        values: List[Tuple[float, float]] = []
        for row in out_csv.iterrows():
            values.append((row[0], row[1]['MEAN_STRAIGHT_LINE_SPEED']))

        values.sort(key=lambda p: float(p[0]))

        plt.plot([value[0] for value in values], [value[1]
                 for value in values], label='Post-Filter Mean', alpha=0.5)

        plt.scatter(only_lost_x + only_kept_x,
                    only_lost_y + only_kept_y,
                    marker='.',
                    c='r',
                    sizes=[5 for _ in only_lost_x + only_kept_x],
                    alpha=0.5,
                    label='Original')

        plt.scatter(only_kept_x,
                    only_kept_y,
                    marker='^',
                    c='b',
                    sizes=[5 for _ in only_lost_x + only_kept_x],
                    alpha=0.5,
                    label='Post-Filter')

        plt.title(
            'Straight Line Speed By Applied Frequency\nRed = Original,'
            + 'Blue = Kept')
        plt.xlabel('Applied Frequency (Hz)')
        plt.ylabel('Mean Straight Line Speed (Pixels / Frame)')

        plt.legend(bbox_to_anchor=(1.1, 1.05), title=(
            'Kept ' + str(len(only_kept_x)) + ', Lost ' + str(
                len(only_lost_x))))

        if secondary_save_path is not None:
            plt.savefig(secondary_save_path + '/' +
                        name_fixer.get_cwd() + '_filter_scatter.png')
        plt.savefig(name_fixer.get_cwd() + '_filter_scatter.png')

        plt.close()

        if do_extra_filter_scatter_plots:
            # Other one
            plt.clf()

            plt.figure(figsize=(6, 4), dpi=400)

            plt.scatter(only_kept_x, only_kept_y, c=[
                        'b' for _ in only_kept_y], sizes=[
                            5 for _ in only_kept_x])

            plt.title(
                'Post-Filter Straight Line Speed By Applied Frequency\n\
                (Only tracks which WERE included in the final'
                + 'dataset appear here)')
            plt.xlabel('Applied Frequency (Hz)')
            plt.ylabel('Mean Straight Line Speed (Pixels / Frame)')

            if secondary_save_path is not None:
                plt.savefig(secondary_save_path + '/' +
                            name_fixer.get_cwd() + '_filtered_scatter.png')
            plt.savefig(name_fixer.get_cwd() + '_filtered_scatter.png')

            plt.close()

            # Other other one
            plt.clf()

            plt.figure(figsize=(6, 4), dpi=400)

            plt.scatter(only_lost_x, only_lost_y, c=[
                        'b' for _ in only_lost_y], sizes=[
                            5 for _ in only_lost_x])

            plt.title(
                'Filtered Out Straight Line Speed By Applied Frequency\n\
                (Only tracks which were NOT included in the final dataset'
                + 'appear here)')
            plt.xlabel('Applied Frequency (Hz)')
            plt.ylabel('Mean Straight Line Speed (Pixels / Frame)')

            if secondary_save_path is not None:
                plt.savefig(secondary_save_path + '/' +
                            name_fixer.get_cwd() + '_lost_scatter.png')
            plt.savefig(name_fixer.get_cwd() + '_lost_scatter.png')

            plt.close()

    if not silent:
        print('Done.')

    return 0


if __name__ == '__main__':
    sys.exit(main())

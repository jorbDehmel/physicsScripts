#!/usr/bin/python3

'''
Meta file for analysis of glycerol data
from Clark. Reuses generalized code from
other files.

Jordan Dehmel, 2023
jdehmel@outlook.com
'''

import os
import sys
import re
import numpy as np
import pandas as pd
from typing import *
from matplotlib import pyplot as plt

sys.path.insert(0, '/home/jorb/Programs/physicsScripts')

import name_fixer
import reverser

'''
Sections:

120 vs 240 um
Bottom Up vs Top Down
8, 12, 16, 20 v
SUBSECTION LABELS CHANGE BY SECTION

The files loaded here are ALREADY FILTERED
We just want to perform more analysis on
them.

FILTERING HAPPENS WITH OBSERVATIONAL BROWNIAN
SPEED THRESHOLD FALLBACK OF 0.042114570268546765
if nothing else is present.

size	solution	    min freq	max freq	midpoint
5	    1 X 10-4 M	    12	        17	        14.5
5	    5 X 10-5 M	    9	        12	        10.5
10	    1 X 10-4 M	    10	        15	        12.5
10	    5 X 10-5 M	    4	        7	        5.5

Part 2:
For a given frequency, voltage, and size, graph all z-positions
on one graph
'''

skip_permutations: bool = True
file_location: str = '/home/jorb/data_graphs'

# These filters are arranged in hierarchical order
main_folder_filter: str = ''

size_filters: [str] = ['120[_ ]?um', '240[_ ]?um']
directional_filters: [str] = ['[Tt]op[_ ]?[Dd]own', '[Bb]ottom[_ ]?[Uu]p']

voltage_filters: [str] = ['8[_ ][vV]',
                          '12[_ ][vV]', '16[_ ][vV]', '20[_ ][vV]']
z_position_filters: [str] = ['8940', '8960', '8965', '8990', '8980',
                             '8985', '9010', '9015', '9035', '9040',
                             '9060', '9080', '9090', '9115', '9140',
                             '9197', '9255', '9280', '9305', '9240',
                             '9265', '9290', '9315', '9340', '9180',
                             '9205', '9230', '9255', '9280',
                             'top-100', 'top-25', 'top-50', 'top-75', 'top-97', 'top_',
                             'bot+25', 'bot+50', 'bot_']

# This string must be in the filename in order to load it
final_file_qualifier: str = 'track_data_summary.csv'

save_number: int = 0

# This holds the brownian straight line speed
# for each filter. If brownian is not present in
# a set, it should be searched for here by climbing
# up the filter list until found.
brownian_values: [float] = []
brownian_stds: [float] = []

silent: bool = True


# Loads a list of lists of filters, and creates permutations of them.
# Returns a list of tuples. Each item is (name, matched_filter_set, data_file, std_file)
def load_all_filter_permutations(hierarchy: [[str]], current_filters: [str] = []) -> List[Tuple[str, str, List[str], pd.DataFrame, pd.DataFrame]]:

    if len(hierarchy) == 0:
        # Recursive base case
        name_array: [str] = name_fixer.find_all(current_filters[0])

        for filter in current_filters[1:]:
            temp: [str] = name_fixer.find_all(filter)

            name_array = [name for name in name_array if name in temp]

            if len(name_array) == 0:
                break

        name_array = [name for name in name_array if re.search(
            final_file_qualifier, name) is not None]

        # Build list of tuples
        out: List[Tuple[str, str, List[str], pd.DataFrame, pd.DataFrame]] = []

        for name in name_array:
            data_file: pd.DataFrame = pd.read_csv(name)
            std_file: pd.DataFrame = pd.read_csv(
                name.replace('.csv', '_stds.csv'))

            to_append: Tuple[str, str, List[str], pd.DataFrame, pd.DataFrame] = (
                name, name.replace('.csv', '_stds.csv'), current_filters[:], data_file, std_file)
            out.append(to_append)

        return out

    else:
        out: List[Tuple[str, str, List[str], pd.DataFrame, pd.DataFrame]] = []

        for filter in hierarchy[0]:
            result = load_all_filter_permutations(
                hierarchy[1:], current_filters + [filter])

            for item in result:
                out.append(item)

        return out


def z_pos_filter_to_float(what: str) -> float:
    try:
        out: float = float(what)
        return out
    except:
        if 'top' in what:
            if len(what) > 4:
                return 100.0 - float(what[4:])
            else:
                return 100.0
        elif 'bot' in what:
            if len(what) > 4:
                return float(what[4:])
            else:
                return 0.0


# Takes a list of filters and a dataset (generated by load_all_filter_permutations)
# and graphs all data which match the given filters on a single graph.
def graph_all_from_filter_list_and_dfs(filters: [str],
                                       data: List[Tuple[str, str, List[str], pd.DataFrame, pd.DataFrame]],
                                       where: [str],
                                       turning_point_lookup: List[Tuple[List[str], float]] = [],
                                       do_breakdown: bool = True) -> None:
    global save_number

    # Scrape all items in data which match the specified filters
    items_which_match: List[Tuple[str, str,
                                  List[str], pd.DataFrame, pd.DataFrame]] = []

    for item in data:
        did_match: bool = True

        for filter in filters:
            if filter not in item[2]:
                did_match = False
                break

        if did_match:
            items_which_match.append(item)

    if len(items_which_match) == 0:
        save_number += 1
        return

    ordered_data: [[float]] = []
    ordered_turning_points: [float] = []
    ordered_frequencies: [StopAsyncIteration] = []
    ordered_errors: [[float]] = []
    ordered_line_labels: [str] = []

    subtitle: str = 'From filter set: ' + \
        str(filters) + '\nPlus or minus 1 STD. Points without bars are interpolated.'
    axis_labels: Tuple[str, str] = (
        'Applied Frequency (Hz)', 'Mean Straight Line Speed (Pixels Per Frame)')
    save_paths: [str] = [path + str(save_number) + '.png' for path in where]
    save_number += 1

    # Build data arrays here for passing into graph_multiple_relative
    for item in items_which_match:
        # Ensure correct sort (prevents weird lines)
        item[3].sort_values('Unnamed: 0', inplace=True)
        item[4].sort_values('Unnamed: 0', inplace=True)

        # item[0] is file name
        ordered_line_labels.append(item[0][60:])

        # item[1] is std name
        # item[2] is filters which found it

        # item[3] is data
        ordered_data.append([row[1]['MEAN_STRAIGHT_LINE_SPEED']
                            for row in item[3].iterrows()])

        # item[4] is errors
        ordered_errors.append([row[1]['MEAN_STRAIGHT_LINE_SPEED_STD']
                              for row in item[4].iterrows()])

        # Attempt turning point lookup
        # If cannot be found, default to 12khz5
        match_index: int = -1
        for i, entry in enumerate(turning_point_lookup):
            if entry[0] == item[2]:
                match_index = i
                break

        if match_index != -1:
            ordered_turning_points.append(turning_point_lookup[match_index][1])

        else:
            if not silent:
                print(
                    'Warning! Crossover frequency could not be found. Falling back on 25khz5.')
            ordered_turning_points.append('25500.0')

        # Scrape frequencies, not necessarily including turning point
        current_frequencies: [str] = []
        for row in item[3].iterrows():
            freq: float = float(row[1][0])
            current_frequencies.append(str(freq))

        ordered_frequencies.append(current_frequencies[:])

        # Data fixing section below

        # If control was present, insert it into brownian list.
        # Otherwise, find more recent brownian and use it.
        if float(current_frequencies[0]) == 0.0:
            brownian_values.append(ordered_data[-1][0])
            brownian_stds.append(ordered_errors[-1][0])

        elif len(brownian_values) != 0 and len(brownian_stds) != 0:
            ordered_data[-1] = [np.mean(brownian_values)] + ordered_data[-1]
            ordered_errors[-1] = [np.max(brownian_stds)] + ordered_errors[-1]
            ordered_frequencies[-1] = ['0.0'] + ordered_frequencies[-1]

        else:
            if not silent:
                print('Warning! No Brownian value found or previously found.')

            ordered_data[-1] = [0.0] + ordered_data[-1]
            ordered_errors[-1] = [0.0] + ordered_errors[-1]
            ordered_frequencies[-1] = ['0.0'] + ordered_frequencies[-1]

            if '\nNon-Present Control' not in subtitle:
                subtitle += '\nNon-Present Control'

    reverser.graph_multiple_relative(
        data=ordered_data,
        turning_points=ordered_turning_points,
        labels=ordered_frequencies,
        save_paths=save_paths,
        axis_labels=axis_labels,
        line_labels=ordered_line_labels,
        subtitle=subtitle,
        errors=ordered_errors
    )

    reverser.save_multiple_relative(
        data=ordered_data,
        turning_points=ordered_turning_points,
        labels=ordered_frequencies,
        save_paths=[path.replace('.png', '.csv') for path in save_paths],
        line_labels=ordered_line_labels,
        errors=ordered_errors
    )

    if not do_breakdown:
        return

    # The output graph should have 1 line
    # The title should specify 'given X voltage, Y size, Z freq'
    # The x-axis should be z-position
    # The y-axis should be mean sls at that z-position

    # Each input file is a given z-position, and has all frequencies
    # For each input file
    # Sort input file frequencies into bins, 1 freq/bin
    # This will result in a set of bins
    # Also keep a separate set of bins for standard deviations
    # Each bin will have a data point for each z-position for its freq
    # We graph each bin separately

    # If there is only one item in the bin, skip graphing or csv-ing it

    # PROCESS:
    # Initialize bins, 1 per frequency. 1 set of bins for sls, 1 for std
    # Initialize list of z-pos (should be x-axis labels later)
    # Iterate over input files (each of which should be a z-pos)
    #       Iterate over bins
    #               If bin freq is in cur file, append to bin
    #               Else append null
    #               Do same for standard deviation

    frequency_bins: Dict[str, Tuple[str, float, float]] = {}

    for item in items_which_match:
        # Ensure correct sort by freq (prevents weird lines)
        item[3].sort_values('Unnamed: 0', inplace=True)
        item[4].sort_values('Unnamed: 0', inplace=True)

        real_rows_data: [] = [thing for thing in item[3].iterrows()]
        real_rows_std: [] = [thing for thing in item[4].iterrows()]

        for i in range(len(real_rows_data)):
            assert float(real_rows_data[i][1][0]) == float(
                real_rows_std[i][1][0])

            if str(real_rows_data[i][1][0]) in frequency_bins:
                frequency_bins[str(real_rows_data[i][1][0])].append(
                    (item[0], real_rows_data[i][1]['MEAN_STRAIGHT_LINE_SPEED'], real_rows_std[i][1]['MEAN_STRAIGHT_LINE_SPEED_STD']))
            else:
                frequency_bins[str(real_rows_data[i][1][0])] = [(
                    item[0], real_rows_data[i][1]['MEAN_STRAIGHT_LINE_SPEED'], real_rows_std[i][1]['MEAN_STRAIGHT_LINE_SPEED_STD'])]

    # Iterate over bins
    #       If len(bin) > 1:
    #           Build into array for csv
    #           Graph bin using labels
    #           Save csv

    for key in frequency_bins:
        if len(frequency_bins[key]) > 2 and len(frequency_bins[key]) < 10:

            # Each item in a bin is a tuple
            # This contains 'source path', sls, sls_std
            # Only depth should vary on this graph, everything else is constant

            # Build into array for csv
            array: [[float]] = []
            array = [[item[1], item[2]] for item in frequency_bins[key]]

            # Build into data frame from array
            csv: pd.DataFrame = pd.DataFrame(array,
                                             index=[t[0]
                                                    for t in frequency_bins[key]],
                                             columns=['MEAN_STRAIGHT_LINE_SPEED', 'MEAN_STRAIGHT_LINE_SPEED_STD'])

            # Save csv
            save_paths = [path + str(save_number - 1) +
                          '_by_z' for path in where]
            for path in save_paths:
                csv.to_csv(path + str(key) + '.csv')

            # Graph bin using labels
            # Each tuple should be one point
            # There should be one line on each graph

            # Sort depth labels
            frequency_bins[key].sort(key=lambda w: z_pos_filter_to_float(
                [r for r in z_position_filters if r in w[0]][0]))

            labels: [str] = [i[0] for i in frequency_bins[key]]

            for j, l in enumerate(labels):
                for r in z_position_filters:
                    if r in l:
                        labels[j] = r
                        break

            data: [float] = [i[1] for i in frequency_bins[key]]
            errors: [float] = [i[2] for i in frequency_bins[key]]

            plt.clf()

            plt.xticks(rotation=-45)
            plt.rc('font', size=8)
            plt.figure(figsize=(10, 10), dpi=200)

            plt.title('Mean Straight Line Speed by Depth\nPlus or Minus 1 Standard Deviation\n' +
                      str(filters) + ' ' + str(key) + 'hz')
            plt.xlabel('Z-Position')
            plt.ylabel('Mean Straight Line Speed (Pixels / Frame)')

            plt.plot(labels, data, label='Observed')
            plt.plot(labels, [np.mean(brownian_values)
                     for _ in data], label='Average Control')

            plt.errorbar(labels, data, errors)

            lgd = plt.legend(bbox_to_anchor=(1.1, 1.05))

            for path in save_paths:
                plt.savefig(path + str(key) + '.png',
                    bbox_extra_artists=(lgd,), bbox_inches='tight')

            plt.close()

    return


def yield_all_filter_permutations(hierarchy: [[str]], current_filters: [str] = []) -> [str]:
    if len(hierarchy) == 0:
        yield current_filters
        return

    else:
        for filter in hierarchy[0]:
            for item in yield_all_filter_permutations(hierarchy[1:], current_filters + [filter]):
                yield item

        return


if __name__ == '__main__':
    # Build turning point lookup table
    turning_point_lookup: List[Tuple[List[str], float]] = []

    os.chdir(file_location)
    hierarchy: [[str]] = [size_filters, directional_filters,
                          voltage_filters, z_position_filters]

    # Get all the files requested
    print('Loading files...')
    files: List[Tuple[str, str, List[str], pd.DataFrame,
                      pd.DataFrame]] = load_all_filter_permutations(hierarchy)

    print('Loaded', len(files), 'patterns, for a total of',
          len(files) * 2, 'files.')

    # Graph groups of files matching given filters
    print('Graphing selected files...')

    graph_all_from_filter_list_and_dfs(['120[_ ]?um', '12[_ ][vV]'],
                                       files,
                                       ['/home/jorb/Programs/physicsScripts/'],
                                       turning_point_lookup,
                                       True)

    if skip_permutations:
        print('Exiting due to skip_permutations')
        exit(0)

    print('Loading permutations...')
    perm_list = [[]]
    for perm in yield_all_filter_permutations(hierarchy):
        for i in range(1, len(perm) + 1):
            sub_perm = perm[:i]

            if sub_perm not in perm_list:
                perm_list.append(sub_perm[:])

    print('Graphing', len(perm_list), 'permutations...')

    # Graph every possible graph
    for perm in perm_list:
        if save_number % 10 == 0:
            print(save_number, 'of', len(perm_list))

        graph_all_from_filter_list_and_dfs(
            perm, files, ['/home/jorb/Programs/physicsScripts/perm/'], turning_point_lookup)

    try:
        print('Final mean Brownian:', np.mean(brownian_values),
              'w/ std', np.std(brownian_values))
        print('Final median Brownian:', np.median(brownian_values))
        print('Final mean Brownian STD:', np.mean(
            brownian_stds), 'w/ std', np.std(brownian_stds))
        print('Final median Brownian STD:', np.median(brownian_stds))
    except:
        print('Brownian values:', brownian_values)
        print('Brownian STDs:', brownian_stds)

    # Exit program
    exit(0)

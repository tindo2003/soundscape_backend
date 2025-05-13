import json
import pandas as pd
import os
from tqdm import tqdm
import argparse
import boto3

TRACKS_DF_FILENAME = "tracks_df.csv"
PLAYLISTS_DF_FILENAME = "playlists_df.csv"
PLAYLIST_TRACKS_DF_FILENAME = "playlist_tracks_df.csv"


playlists_df_list, tracks_df_list = [], []
track_uri_to_id = {}


def validate_dict(dictionary, expected_keys, expected_types):
    """
    Given a dictionary, test if it contains all the expected keys and
    with expected type of values

    Args:
        dictionary(dict): The dictionary to be tested
        expected_keys(tuple): The expected keys
        expected_types(tuple): The expected value types for each key
    Returns:
        tuple(bool, str): whether the test passed, the reason if failed
    """
    assert isinstance(dictionary, dict)

    for expected_key, expected_type in zip(expected_keys, expected_types):
        if expected_key not in dictionary:
            return False, f"{expected_key} not in dictionary"
        if not isinstance(dictionary[expected_key], expected_type):
            return False, f"dictionary[{expected_key}] is not a {expected_type}"

    return True, None


def validate_slice(slice):
    """
    Given a slice, test if it has data structure desribed in
    "Raw Data Structure.png"

    Args:
        slice(dict): a slice to be tested
    Returns:
        tuple(bool, str): whether the test passed, the reason if failed
    """

    if not isinstance(slice, dict):
        return False, "slice is not a dict"

    expected_keys = ("info", "playlists")
    expected_types = (dict, list)
    res = validate_dict(slice, expected_keys, expected_types)
    if res[0] is False:
        return res

    for playlist in slice["playlists"]:
        expected_keys = (
            "name",
            "collaborative",
            "pid",
            "modified_at",
            "num_tracks",
            "num_albums",
            "num_followers",
            "num_edits",
            "duration_ms",
            "num_artists",
            "tracks",
        )
        expected_types = (str, str, int, int, int, int, int, int, int, int, list)
        res = validate_dict(playlist, expected_keys, expected_types)
        if res[0] is False:
            return res

        for track in playlist["tracks"]:
            expected_keys = (
                "pos",
                "artist_name",
                "track_uri",
                "artist_uri",
                "track_name",
                "album_uri",
                "duration_ms",
                "album_name",
            )
            expected_types = (int, str, str, str, str, str, int, str)
            res = validate_dict(track, expected_keys, expected_types)
            if res[0] is False:
                return res

    return True, None


def process_slice(slice):
    """
    Given a slice with data structure described in "Raw Data Structure.png",
    modify this slice by
    1. Removing the "info" field
    2. Adding the attribute "slice"(originally in "info") to the slice
    3. In an entry of "playlists",
       convert "collaborative" from str to bool, and
       convert "duration_ms" from ms to secs(int)
    4. In an entry of "tracks" in an entry of "playlists",
       convert "duration_ms" from ms to secs(int)
    *Check "New Data Structure.png" for more details*
    Then, add all of the playlists and tracks into the dataframes

    Args:
        slice(dict): a slice to be processed
    Returns:
        None
    """
    assert isinstance(slice, dict)
    res = validate_slice(slice)
    assert res[0], res[1]

    # removing the info field and bringing "slice" toe the top level
    slice["slice"] = slice["info"]["slice"]
    slice.pop("info")

    for playlist in slice["playlists"]:
        # convert "collaborative" from str to bool for each playlist
        collab = playlist["collaborative"]
        playlist["collaborative"] = collab == "true"

        # convert "duration_ms" to "duration_s" for each playlist
        playlist["duration_s"] = playlist["duration_ms"] // 1000
        playlist.pop("duration_ms")

        for track in playlist["tracks"]:
            # convert "duration_ms" to "duration_s" for each track
            track["duration_s"] = track["duration_ms"] // 1000
            track.pop("duration_ms")

            # new track, append it to tracks_df
            if len(track_uri_to_id) == 0 or track["track_uri"] not in track_uri_to_id:
                track["track_id"] = len(track_uri_to_id)
                track_uri_to_id[track["track_uri"]] = track["track_id"]
                del track["pos"]
                tracks_df_list.append(track)

        # encode tracks to their ids
        ids = [track_uri_to_id[track["track_uri"]] for track in playlist["tracks"]]
        playlist["tracks"] = ids

        # most playlist doesn't have a description
        if "description" in playlist:
            del playlist["description"]
        # add the playlist to playlists_df
        playlists_df_list.append(playlist)


def pre_process_dataset(path, new_path):
    """
    Given the directory of the dataset, for each slice first modified it by
    the rules described in generate_new_slice.

    Then, generate 3 dataframes:
    playlists_df, tracks_df, and playlist_tracks_df

    playlists_df has the fields: pid, name, other metadata,
    and tracks which is a list containig the id of each track in the playlist.

    tracks_df has the fields: track_id, name, artist, and other metadata.

    playlist_tracks_df has the field: track_id and pid which could be used to
    tell which playlists contain a certain track.


    The generated dataframe will be saved in to the new_path directory with
    names "playlists_df.csv", "tracks_df.csv", and "playlist_track.csv".

    Args:
        path(str): Directory of the MPD dataset
        new_path(str): Directory of where to store the dataframes
    Returns:
        None
    """
    global playlists_df_list, tracks_df_list, track_uri_to_id
    assert isinstance(path, str)
    assert isinstance(new_path, str)

    s3 = boto3.client(
        "s3",
        aws_access_key_id="AKIAZ3MGMZFWEBCBTVXR",
        aws_secret_access_key="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",
        region_name="us-east-1",
    )

    # Specify the bucket name
    bucket_name = "soundscape-mpd-dataset"

    # List objects within the specified S3 bucket
    response = s3.list_objects_v2(Bucket=bucket_name)

    # Check if the bucket contains any objects
    if "Contents" in response:
        # Iterate over each object in the bucket
        files = response["Contents"]
        for obj in tqdm(files):
            key = obj["Key"]
            # Check if the object is a JSON file matching the desired pattern
            if key.startswith("mpd.slice.") and key.endswith(".json"):
                print(f"Processing file: {key}")
                # Retrieve the object
                s3_object = s3.get_object(Bucket=bucket_name, Key=key)
                # Read the object's content
                content = s3_object["Body"].read().decode("utf-8")
                # Load the JSON data
                mpd_slice = json.loads(content)
                # Process the JSON data
                process_slice(mpd_slice)
    else:
        print("No objects found in the bucket.")

    del track_uri_to_id
    # generate tracks_df and playlists_df
    if not os.path.isdir(new_path):
        os.makedirs(new_path)
    tracks_df = pd.DataFrame.from_dict(tracks_df_list)
    del tracks_df_list
    playlists_df = pd.DataFrame.from_dict(playlists_df_list)
    del playlists_df_list
    tracks_df.to_csv(os.sep.join((new_path, TRACKS_DF_FILENAME)), index=False)
    playlists_df.to_csv(os.sep.join((new_path, PLAYLISTS_DF_FILENAME)), index=False)

    # generate playlist_tracks_df
    playlist_tracks_df = pd.DataFrame(
        {
            "track_id": playlists_df["tracks"].explode(),
            "pid": playlists_df["pid"].repeat(playlists_df["tracks"].apply(len)),
        }
    )
    playlist_tracks_df.to_csv(
        os.sep.join((new_path, PLAYLIST_TRACKS_DF_FILENAME)), index=False
    )


def read_pre_processed_data(data_path):
    """Read the pre-processed MPD data into dataframes.

    Args:
        data_path (str): A path to the directory that contains the pre-processed
            MPD data CSVs.

    Returns:
        A tuple of three dataframes of the respective playlists data, tracks data,
        and playlists/tracks relations data.

    Raises:
        ValueError if data_path or any contained files does not exist or is invalid.
    """
    if not os.path.exists(data_path):
        raise ValueError(f"Data path {data_path} does not exist.")

    if not os.path.isdir(data_path):
        raise ValueError(f"Data path {data_path} must be a directory.")

    playlists_filename = os.path.join(data_path, PLAYLISTS_DF_FILENAME)
    tracks_filename = os.path.join(data_path, TRACKS_DF_FILENAME)
    playlists_tracks_filename = os.path.join(data_path, PLAYLIST_TRACKS_DF_FILENAME)

    if not os.path.isfile(playlists_filename):
        raise ValueError(f"Playlists filename {playlists_filename} must exist.")

    if not os.path.isfile(tracks_filename):
        raise ValueError(f"Playlists filename {tracks_filename} must exist.")

    if not os.path.isfile(playlists_tracks_filename):
        raise ValueError(f"Playlists filename {playlists_tracks_filename} must exist.")

    playlists_df = pd.read_csv(playlists_filename)
    tracks_df = pd.read_csv(tracks_filename)
    playlists_tracks_df = pd.read_csv(playlists_tracks_filename)

    return playlists_df, tracks_df, playlists_tracks_df


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("path", help="directory of the MPD dataset")
    parser.add_argument("new_path", help="directory of where to store the new dataset")
    args = parser.parse_args()
    pre_process_dataset(args.path, args.new_path)

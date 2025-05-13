from argparse import ArgumentParser
import sys
import pandas as pd
from tqdm import tqdm
import numpy as np

from recommendations.pre_processing import read_pre_processed_data
from recommendations.plots import save_bar_plot, save_audio_features_hist
from recommendations.utils import get_spotipy_client


def get_top_tracks_audio_features_cmp(
    topN_audio_df,
    sampleN_audio_df,
    N=1000
):
    """Get the audio features for the top tracks compared to a random sampling
    of tracks to compare distributions of audio characteristics.

    Args:
        top1000_audio_df (DataFrame): A DataFrame of the top 1000 tracks data.
        sample1000_audio_df (DataFrame): A DataFrame of 1000 randomly sampled tracks.
        N (int): The number of samples to compare distributions for.
    
    Returns:
        A DataFrame of the audio features for all of the top tracks and randomly
        sampled tracks combined together with appropriate labels.
    """
    # Join dataframes and label distributions for plotting
    topN_audio_df["label"] = f"top_{N}"
    sampleN_audio_df["label"] = f"sample_{N}"
    hist_df = pd.concat([topN_audio_df, sampleN_audio_df], ignore_index=True)
    return hist_df


def get_top_tracks_cmp(tracks_df, playlists_tracks_df):
    """Get the top tracks dataframes compared to a random sampling of tracks to
    compare distributions of audio characteristics.

    Args:
        tracks_df (DataFrame): A DataFrame of the unique tracks data.
        playlist_tracks_df (DataFrame): A DataFrame of the playlist and track id
            associations.
    
    Returns:
        The DataFrames of the the top tracks and randomly sampled tracks as a
        triplet pair.
    """
    # Get top 10000 and random sample of 10000 tracks
    top1000_tracks_df = get_most_common_tracks(tracks_df, playlists_tracks_df, n=1000)
    top1000_tracks_df = top1000_tracks_df.join(tracks_df, lsuffix="_left")
    sample1000_tracks_df = tracks_df.sample(1000)
    return top1000_tracks_df, sample1000_tracks_df


def get_top_artists_tracks_cmp(tracks_df, playlists_tracks_df):
    """Get the tracks of top artists dataframes compared to a random sampling of
    artist tracks to compare distributions of audio characteristics.

    Args:
        tracks_df (DataFrame): A DataFrame of the unique tracks data.
        playlist_tracks_df (DataFrame): A DataFrame of the playlist and track id
            associations.
    
    Returns:
        The DataFrames of the the top tracks and randomly sampled tracks as a
        tuple pair.
    """
    # Get top 10, top 10000, and random sample of 10000 tracks
    top100_artists_df = get_most_common_artists(tracks_df, playlists_tracks_df, n=100)
    top100_artists_df = top100_artists_df.join(tracks_df, on="artist_uri", lsuffix="_left")
    sample100_artists_df = tracks_df.sample(100)
    sample100_artists_df = sample100_artists_df.join(tracks_df, on="artist_uri", lsuffix="_left")
    return top100_artists_df, sample100_artists_df


def get_most_common_tracks(tracks_df, playlist_tracks_df, n=10, ascending=False):
    """Get the most included tracks across all playlists.

    Args:
        track_df (DataFrame): A DataFrame of the unique tracks data.
        playlist_tracks_df (DataFrame): A DataFrame of the playlist and track id
            associations.
        n (int): The number of tracks to include in the returning DataFrame.
        ascending (bool): Return the top N most common tracks or bottom N most common
            (rareset) tracks.

    Returns:
        A DataFrame of the most common tracks.
    """
    assert isinstance(tracks_df, pd.DataFrame)
    assert isinstance(playlist_tracks_df, pd.DataFrame)
    assert isinstance(n, int)
    assert n > 0
    df = get_unique_track_features(tracks_df, playlist_tracks_df)
    return df[["track_name", "track_uri", "count"]].sort_values("count", ascending=ascending)[:n]


def get_most_common_artists(tracks_df, playlist_tracks_df, n=10, ascending=False):
    """Get the artists that have the most unique inclusions across all playlists.

    A unique inclusion deduplicates an artist that has been added multiple
    times to a playlist via multiple different tracks.

    Args:
        track_df (DataFrame): A DataFrame of the unique tracks data.
        playlist_tracks_df (DataFrame): A DataFrame of the playlist and track id
            associations.
        n (int): The number of artists to include in the returning DataFrame.
        ascending (bool): Return the top N most common artists or bottom N most common
            (rareset) artists.

    Returns:
        A DataFrame of the most common artists.
    """
    assert isinstance(tracks_df, pd.DataFrame)
    assert isinstance(playlist_tracks_df, pd.DataFrame)
    assert isinstance(n, int)
    assert n > 0
    df = playlist_tracks_df.join(tracks_df.set_index("track_id")[["artist_uri", "artist_name"]], on="track_id")
    artists_df = df[["pid", "artist_uri", "artist_name"]].drop_duplicates()
    artists_df = artists_df.value_counts(["artist_uri", "artist_name"]).to_frame().reset_index()
    return artists_df[["artist_name", "artist_uri", "count"]].set_index("artist_name").sort_values("count", ascending=ascending)[:n]


def get_most_common_albums(tracks_df, playlist_tracks_df, n=10, ascending=False):
    """Get the albums that have the most unique inclusions across all playlists.

    A unique inclusion deduplicates an album that has been added multiple
    times to a playlist via multiple different tracks.

    Args:
        track_df (DataFrame): A DataFrame of the unique tracks data.
        playlist_tracks_df (DataFrame): A DataFrame of the playlist and track id
            associations.
        n (int): The number of albums to include in the returning DataFrame.
        ascending (bool): Return the top N most common albums or bottom N most common
            (rareset) albums.

    Returns:
        A DataFrame of the most common albums.
    """
    assert isinstance(tracks_df, pd.DataFrame)
    assert isinstance(playlist_tracks_df, pd.DataFrame)
    assert isinstance(n, int)
    assert n > 0
    df = playlist_tracks_df.join(tracks_df.set_index("track_id")[["album_uri", "album_name"]], on="track_id")
    artists_df = df[["pid", "album_uri", "album_name"]].drop_duplicates()
    artists_df = artists_df.value_counts(["album_uri", "album_name"]).to_frame().reset_index()
    return artists_df[["album_name", "album_uri", "count"]].set_index("album_name").sort_values("count", ascending=ascending)[:n]


def get_largest_albums(tracks_df, playlist_tracks_df, n=10):
    """Get the albums with the most amount of unique tracks.

    Args:
        track_df (DataFrame): A DataFrame of the unique tracks data.
        playlist_tracks_df (DataFrame): A DataFrame of the playlist and track id
            associations.
        n (int): The number of albums to include in the returning DataFrame.

    Returns:
        A DataFrame of the largest albums.
    """
    assert isinstance(tracks_df, pd.DataFrame)
    assert isinstance(playlist_tracks_df, pd.DataFrame)
    assert isinstance(n, int)
    assert n > 0
    df = get_unique_track_features(tracks_df, playlist_tracks_df)
    albums_df = df.value_counts(["album_uri", "album_name"]).to_frame().reset_index()
    return albums_df[["album_name", "count"]].set_index("album_name").sort_values("count", ascending=False)[:n]


def get_most_prolific_artists(tracks_df, playlist_tracks_df, n=10):
    """Get the artists that have generated the most number of unique tracks.

    Args:
        track_df (DataFrame): A DataFrame of the unique tracks data.
        playlist_tracks_df (DataFrame): A DataFrame of the playlist and track id
            associations.
        n (int): The number of artists to include in the returning DataFrame.

    Returns:
        A DataFrame of the most prolific artsits.
    """
    assert isinstance(tracks_df, pd.DataFrame)
    assert isinstance(playlist_tracks_df, pd.DataFrame)
    assert isinstance(n, int)
    assert n > 0
    df = get_unique_track_features(tracks_df, playlist_tracks_df)
    artists_df = df.value_counts(["artist_uri", "artist_name"]).to_frame().reset_index()
    return artists_df[["artist_name", "count"]].set_index("artist_name").sort_values("count", ascending=False)[:n]


def get_unique_track_features(tracks_df, playlist_tracks_df):
    """Get the common track features as a dataframe for further filtering that occur
    across all playlists.

    For example, the most common track feature would be the unique track that is 
    included the most number of times across all playlists (assuming no duplicates
    per playlist). From this we can also find the unique album feature and unique
    artist features.

    Note that the count column in the resulting dataframe is the number of appearances
    of a given track across all playlists.

    Args:
        track_df (DataFrame): A DataFrame of the unique tracks data.
        playlist_tracks_df (DataFrame): A DataFrame of the playlist and track id
            associations.

    Returns:
        A DataFrame of the common playlist track features across all playlists.
    """
    assert isinstance(tracks_df, pd.DataFrame)
    assert isinstance(playlist_tracks_df, pd.DataFrame)
    cols = ["track_name", "artist_name", "album_name", "track_uri", "artist_uri", "album_uri"]
    num_occurrences_df = playlist_tracks_df.value_counts("track_id").to_frame()
    return tracks_df[cols + ["track_id"]].join(num_occurrences_df, on="track_id")


def get_track_durations_stdev_distribution(tracks_df, playlist_tracks_df):
    """Get the distribution of the standard deviations of track durations in playlists.

    Args:
        track_df (DataFrame): A DataFrame of the unique tracks data.
        playlist_tracks_df (DataFrame): A DataFrame of the playlist and track id
            associations.
    Returns:
        list: A list of stdev of track durations where entry i corresponds to
            playlist with pid i.
    """
    assert isinstance(tracks_df, pd.DataFrame)
    assert isinstance(playlist_tracks_df, pd.DataFrame)

    tqdm.pandas()
    # cache the durations into a list for faster access
    track_duration_map = list(tracks_df.duration_s)

    # append track duration to playlist_tracks_df
    playlist_tracks_df['duration_s'] = playlist_tracks_df['track_id'].progress_apply(lambda x: track_duration_map[x])

    # caculate the standard deviation of duration_s in each playlist
    duration_s_stdevs = playlist_tracks_df.groupby('pid').progress_apply(lambda x: np.std(x.duration_s))

    # remove track duration column
    del playlist_tracks_df['duration_s']

    return duration_s_stdevs


def get_artist_diversity_distribution(tracks_df, playlist_tracks_df):
    """Get the distribution of the artist diversity in playlists.
    Artist diversity is defined as the number of unique artists divided by the number of tracks in a playlist.
    Artist diversity gives an insight of how diverse the artists are in a playlist,
    the closer to 1, the higher the diversity.

    Args:
        track_df (DataFrame): A DataFrame of the unique tracks data.
        playlist_tracks_df (DataFrame): A DataFrame of the playlist and track id
            associations.
    Returns:
        list: A list of artist diversity where entry i corresponds to
            playlist with pid i.
    """
    assert isinstance(tracks_df, pd.DataFrame)
    assert isinstance(playlist_tracks_df, pd.DataFrame)

    tqdm.pandas()
    # cache the durations into a list for faster access
    track_artist_map = list(tracks_df.artist_name)

    # append artist name to playlist_tracks_df
    playlist_tracks_df['artist_name'] = playlist_tracks_df['track_id'].progress_apply(lambda x: track_artist_map[x])

    # caculate the artist diversity of each playlist
    artist_diversity = playlist_tracks_df.groupby('pid').progress_apply(lambda x: x['artist_name'].nunique() / len(x['track_id']))

    # remove track artist name column
    del playlist_tracks_df['artist_name']

    return artist_diversity


def get_most_popular_one_hit_wonder(tracks_df, playlist_tracks_df, n=10):
    """
    Find artists with a low number of tracks but high popularity based on the number of inclusions across all playlists.

    Args:
        tracks_df (DataFrame): DataFrame of the unique tracks data.
        playlist_tracks_df (DataFrame): DataFrame of the playlist and track id associations.
        threshold_tracks (int): Threshold for the number of tracks below which an artist is considered to have a low track count.
        threshold_popularity (int): Threshold for the popularity based on the number of inclusions across all playlists.

    Returns:
        DataFrame: DataFrame of artists that meet the criteria.
    """
    assert isinstance(tracks_df, pd.DataFrame)
    assert isinstance(playlist_tracks_df, pd.DataFrame)
    assert isinstance(n, int)
    assert n > 0
    
    merged_df = pd.merge(playlist_tracks_df, tracks_df[['track_id', 'artist_name']], on='track_id')
    artist_track_counts = merged_df.groupby('artist_name')['track_id'].nunique().reset_index()
    artist_track_counts.columns = ['artist_name', 'track_count']
    artist_popularity = merged_df['artist_name'].value_counts().reset_index()
    artist_popularity.columns = ['artist_name', 'popularity']
    artist_stats = pd.merge(artist_track_counts, artist_popularity, on='artist_name')
    popular_one_hit_wonders = artist_stats[
        (artist_stats['track_count'] <= 1) & (artist_stats['popularity'] >= 1000)
    ]
    top_n_one_hit_wonders = popular_one_hit_wonders.sort_values(by='popularity', ascending=False).head(n)
    return top_n_one_hit_wonders


def get_popular_artist_cnt(tracks_df, playlist_tracks_df, n=100):
    """
    Find the number of top-n common artists in each playlist.

    Args:
        tracks_df (DataFrame): DataFrame of the unique tracks data.
        playlist_tracks_df (DataFrame): DataFrame of the playlist and track id associations.
        n(int): Top N most common artists would be considered as popular.

    Returns:
        pd.Series: A series of count of top-n common artists where each entry corresponds to a playlist.
    """
    assert isinstance(tracks_df, pd.DataFrame)
    assert isinstance(playlist_tracks_df, pd.DataFrame)
    assert isinstance(n, int)
    assert n > 0

    top_n_artists = get_most_common_artists(tracks_df, playlist_tracks_df, n)

    df = playlist_tracks_df.join(tracks_df.set_index("track_id")[["artist_name"]], on="track_id")

    def cnt(playlist):
        """Given a playlist, count the number of top-n artists in this playlist.

        Args:
            playlist (DataFrame): DataFrame of a playlist with artist names

        Returns:
            int: The number of top-n artists in this playlist.
        """
        assert isinstance(playlist, pd.DataFrame)

        ans = 0
        for artist in playlist.artist_name.unique():
            if artist in top_n_artists.index:
                ans += 1
        return ans

    # calculate the number of top 100 artists in a playlist
    top_n_artists_cnt = df.groupby('pid').progress_apply(lambda playlist: cnt(playlist))

    return top_n_artists_cnt


if __name__ == "__main__":
    parser = ArgumentParser()
    parser.add_argument(
        "input_data",
        type=str,
        help="Directory that contains the pre-processed MPD data.",
    )
    parser.add_argument(
        "-N",
        type=int,
        default=10,
        help="The top N ranked counts for each analysis feature to plot and save."
    )
    args = parser.parse_args(sys.argv[1:])
    N = args.N
    print("Reading pre processed data...")
    _, tracks_df, playlist_tracks_df = read_pre_processed_data(args.input_data)

    # Plot top N tracks
    print(f"Plotting top {N} most common tracks...")
    top_N_tracks = get_most_common_tracks(tracks_df, playlist_tracks_df, n=N)
    save_bar_plot(f"top{N}_tracks.png", top_N_tracks, x="track_name", y="count", title=f"Top {N} Most Common Tracks", orient="h")

    # Plot top N artists
    print(f"Plotting top {N} most common artists...")
    top_N_artists = get_most_common_artists(tracks_df, playlist_tracks_df, n=N)
    save_bar_plot(f"top{N}_artists.png", top_N_artists, x="artist_name", y="count", title=f"Top {N} Most Common Artists", orient="h")

    # Plot top N albums
    print(f"Plotting top {N} most common albums...")
    top_N_albums = get_most_common_albums(tracks_df, playlist_tracks_df, n=N)
    save_bar_plot(f"top{N}_albums.png", top_N_albums, x="album_name", y="count", title=f"Top {N} Most Common Albums", orient="h")

    # Plot top N prolific artists
    print(f"Plotting top {N} most prolific artists...")
    top_N_prolific_artists = get_most_prolific_artists(tracks_df, playlist_tracks_df, n=N)
    save_bar_plot(f"top{N}_prolific_artists.png", top_N_prolific_artists, x="artist_name", y="count", title=f"Top {N} Most Prolific Artists", orient="h")

    # Plot top N largest albums
    print(f"Plotting top {N} largest albums...")
    top_N_largest_albums = get_largest_albums(tracks_df, playlist_tracks_df, n=N)
    save_bar_plot(f"top{N}_largest_albums.png", top_N_largest_albums, x="album_name", y="count", title=f"Top {N} Largest Albums", orient="h")
    
    # Plot top N prolific artists with only one track
    print(f"Plotting top {N} most prolific artists...")
    top_N_prolific_one_hit = get_most_popular_one_hit_wonder(tracks_df, playlist_tracks_df, n=N)
    save_bar_plot(f"top{N}_prolific_one_hit.png", top_N_prolific_one_hit, x="artist_name", y="popularity", title=f"Top {N} Most Prolific Artists With Only One Track", orient="h")

    # Plot audio characteristic distributions
    top1000_audio_df = pd.read_csv("top1000_audio_features.csv")
    sample1000_audio_df = pd.read_csv("sample1000_audio_features.csv")
    hist_df = get_top_tracks_audio_features_cmp(top1000_audio_df, sample1000_audio_df)
    save_audio_features_hist("danceability_hist.png", hist_df, x="danceability", title="Danceability of Top 1000 vs. 1000 Random Tracks")
    save_audio_features_hist("energy_hist.png", hist_df, x="energy", title="Energy of Top 1000 vs. 1000 Random Tracks")
    save_audio_features_hist("loudness_hist.png", hist_df, x="loudness", title="Loudness of Top 1000 vs. 1000 Random Tracks")
    save_audio_features_hist("speechiness_hist.png", hist_df, x="speechiness", title="Speechiness of Top 1000 vs. 1000 Random Tracks")
    save_audio_features_hist("acousticness_hist.png", hist_df, x="acousticness", title="Acousticness of Top 1000 vs. 1000 Random Tracks")
    save_audio_features_hist("liveness_hist.png", hist_df, x="liveness", title="Liveness of Top 1000 vs. 1000 Random Tracks")
    save_audio_features_hist("valence_hist.png", hist_df, x="valence", title="Valence of Top 1000 vs. 1000 Random Tracks")
    save_audio_features_hist("tempo_hist.png", hist_df, x="tempo", title="Tempo of Top 1000 vs. 1000 Random Tracks")
    save_audio_features_hist("duration_ms.png", hist_df, x="duration_ms", title="Duration of Top 1000 vs. 1000 Random Tracks")

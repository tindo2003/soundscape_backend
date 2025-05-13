import pandas as pd
from sklearn.metrics.pairwise import cosine_similarity
from sklearn.preprocessing import StandardScaler
import faiss
import numpy as np
import os
from tqdm import tqdm

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "soundscape.settings")

import django

django.setup()

from recommendations.models import CosineSimilarity
from datetime import datetime
from django.db import transaction


# this is for pre-deprecated data
def load_data(csv_path: str):
    df = pd.read_csv(csv_path)
    df = df[df["id"].notna()]
    track_ids = df["id"].tolist()
    numerical_features = df[
        [
            "danceability",
            "energy",
            "key",
            "loudness",
            "speechiness",
            "acousticness",
            "instrumentalness",
            "liveness",
            "valence",
            "tempo",
            "duration_ms",
            "time_signature",
            "mode",
        ]
    ]
    scaler = StandardScaler()
    numerical_features = numerical_features.copy()
    numerical_features.fillna(numerical_features.mean(), inplace=True)
    normalized_features = scaler.fit_transform(numerical_features)
    normalized_features = normalized_features.copy(order="C")
    normalized_features = normalized_features.astype("float32")
    return track_ids, normalized_features


def calculate_top_k_similarity(data):
    index = faiss.IndexFlatIP(
        data.shape[1]
    )  # Inner product (equivalent to cosine similarity with normalized vectors)
    faiss.normalize_L2(data)  # Normalize for cosine similarity
    index.add(data)

    # Query the top 10 most similar items for all items
    D, I = index.search(data, k=10)
    return D, I


def save_similarities(D, I, track_ids):
    """
    Save cosine similarities into the database, optimized for speed.
    """
    start_time = datetime.now()

    # Prepare batch for bulk_create
    similarity_objects = []
    current_time = datetime.now()

    # Iterate over distances and indices
    for i, (distances, indices) in tqdm(
        enumerate(zip(D, I)), total=len(D), desc="Saving similarities"
    ):
        source_track_id = track_ids[i]  # Get the source track ID

        for distance, target_index in zip(distances, indices):
            if i == target_index:
                continue  # Skip self-similarity and below-threshold similarities

            target_track_id = track_ids[target_index]  # Get the target track ID

            # Prepare the object for bulk insertion
            similarity_objects.append(
                CosineSimilarity(
                    created=current_time,
                    source=source_track_id,
                    target=target_track_id,
                    similarity=float(distance),
                )
            )

    # Save in bulk
    with transaction.atomic():
        CosineSimilarity.objects.bulk_create(similarity_objects, batch_size=1000)

    print(
        f"Saved {len(similarity_objects)} similarity records in {datetime.now() - start_time} seconds"
    )


def main():
    cvs_path = "/Volumes/Extreme SSD/data/tracks_features.csv"
    CosineSimilarity.objects.all().delete()
    track_ids, data = load_data(cvs_path)
    D, I = calculate_top_k_similarity(data)
    save_similarities(D, I, track_ids)


if __name__ == "__main__":
    main()

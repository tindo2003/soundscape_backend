from users.models import UserTopTrack
from recommendations.models import CosineSimilarity
from django.db.models import Q


class ContentBasedRecs:
    def recommend_items(self, user_id, num=6):
        """
        Get recommendations for a user based on their top tracks.
        """
        # Get the user's top tracks
        active_user_items = (
            UserTopTrack.objects.filter(user_id=user_id)
            .values_list("track_id", flat=True)
            .distinct()
        )

        # Recommend items based on similarity
        return self.recommend_items_by_ratings(user_id, active_user_items, num)

    def recommend_items_by_ratings(self, user_id, active_user_items, num=6):
        """
        Recommend items based on cosine similarity scores.
        """
        # TODO: will do something different if we have user ratings for each song
        # Fetch top cosine similarity records
        sims = CosineSimilarity.objects.filter(
            Q(source__in=active_user_items) & ~Q(target__in=active_user_items)
        ).order_by("-similarity")[:num]

        # Build recommendations
        recs = {}
        for sim in sims:
            if sim.target not in recs:
                recs[sim.target] = {"similarity": sim.similarity, "source": sim.source}

        # Return top-N recommendations sorted by similarity
        return sorted(recs.items(), key=lambda x: -x[1]["similarity"])[:num]

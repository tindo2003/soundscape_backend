from django.urls import path, re_path

from .views import (
    RecommendationView,
    chart,
    recs_using_association_rules,
    recs_cb,
    recs_events,
    # RecommendationTracksView,
    # RecommendationArtistsView,
    # RecommendationAlbumsView,
    search_concerts,
)

app_name = "recommendations"

urlpatterns = [
    path("", RecommendationView.as_view(), name="recommendation"),
    re_path(r"^chart/", chart, name="chart"),
    re_path(
        r"^ar/(?P<user_id>\w+)/$",
        recs_using_association_rules,
        name="recs_using_association_rules",
    ),
    re_path(r"^cb/user/(?P<user_id>\w+)/$", recs_cb, name="recs_cb"),
    path("concerts_rec/", recs_events, name="recs_events"),
    # path(
    #     "recommendation/tracks/",
    #     RecommendationTracksView.as_view(),
    #     name="recommendation-tracks",
    # ),
    # path(
    #     "recommendation/artists/",
    #     RecommendationArtistsView.as_view(),
    #     name="recommendation-artists",
    # ),
    # path(
    #     "recommendation/albums/",
    #     RecommendationAlbumsView.as_view(),
    #     name="recommendation-albums",
    # ),
    path("concerts/search/", search_concerts, name="search_concerts"),
]

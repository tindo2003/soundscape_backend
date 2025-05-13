import tekore as tk
import os
from dotenv import load_dotenv
import requests

# import billboard

load_dotenv()
from users.models import User


lastfm_api_key = os.getenv("lastfm_api_key")
BASE_URL = "http://ws.audioscrobbler.com/2.0/"


class PopularityBasedRecs:
    @staticmethod
    def chart_top_tracks_by_country(spotify_id, limit=50):
        """
        Fetch the top tracks globally using Last.fm API.

        Parameters:
            limit (int): Number of top tracks to fetch (default is 10).

        Returns:
            list: A list of dictionaries containing track details.
        """
        # Checkout these links:
        # https://open.spotify.com/genre/section0JQ5DAzQHECxDlYNI6xD1h
        # https://open.spotify.com/genre/0JQ5DAudkNjCgYMM0TZXDr
        # https://github.com/guoguo12/billboard-charts
        country_to_playlist = {
            "VN": "37i9dQZEVXbKZyn1mKjmIl",
            "VE": "37i9dQZEVXbNvXzC8A6ysJ",
            "UY": "37i9dQZEVXbLJVn3eSzDgr",
            "GB": "37i9dQZEVXbMwmF30ppw50",
            "UA": "37i9dQZEVXbNcoJZ65xktI",
            "US": "37i9dQZEVXbLp5XoPON0wI",
            "AE": "37i9dQZEVXbIZQf3WEYSut",
            "TR": "37i9dQZEVXbJARRcHjHcAr",
            "TH": "37i9dQZEVXbJ7qiJCES5cj",
            "TW": "37i9dQZEVXbMVY2FDHm6NN",
            "CH": "37i9dQZEVXbKx6qX9uN66j",
            "SE": "37i9dQZEVXbKVvfnL1Us06",
            "ES": "37i9dQZEVXbJwoKy8qKpHG",
            "KR": "37i9dQZEVXbJZGli0rRP3r",
            "ZA": "37i9dQZEVXbJV3H3OfCN1z",
            "SK": "37i9dQZEVXbMwW10JmAnzE",
            "SG": "37i9dQZEVXbN66FupT0MuX",
            "SA": "37i9dQZEVXbO839WGRmpu1",
            "RO": "37i9dQZEVXbMeCoUmQDLUW",
            "PT": "37i9dQZEVXbJBafyanUiqT",
            "PL": "37i9dQZEVXbMZ5PAcNTDXd",
            "PI": "37i9dQZEVXbJVKdmjH0pON",
            "PE": "37i9dQZEVXbMGcjiWgg253",
            "PY": "37i9dQZEVXbOa9bIw7kKRV",
            "PA": "37i9dQZEVXbNSiWnkYnziz",
            "PK": "37i9dQZEVXbNy9tB5elXf1",
            "NO": "37i9dQZEVXbLWYFZ5CkSvr",
            "NG": "37i9dQZEVXbLw80jjcctV1",
            "NZ": "37i9dQZEVXbIWlLQoMVEFp",
            "NL": "37i9dQZEVXbK4BFAukDzj3",
            "MA": "37i9dQZEVXbNM8vS9cIqAG",
            "MX": "37i9dQZEVXbKUoIkUXteF6",
            "MY": "37i9dQZEVXbKcS4rq3mEhp",
            "LU": "37i9dQZEVXbJ9I5rNwuWjd",
            "LT": "37i9dQZEVXbMYxg0QVEswv",
            "LV": "37i9dQZEVXbJm5XJ9pVWM8",
            "KZ": "37i9dQZEVXbLeBcWrdps2V",
            "JP": "37i9dQZEVXbKqiTGXuCOsB",
            "IT": "37i9dQZEVXbJUPkgaWZcWG",
            "IL": "37i9dQZEVXbJ5J1TrbkAF9",
            "IE": "37i9dQZEVXbJIvhIOxXxdp",
            "ID": "37i9dQZEVXbIZK8aUquyx8",
            "IN": "37i9dQZEVXbMWDif5SCBJq",
            "IS": "37i9dQZEVXbNFK4e1Q7rTL",
            "HU": "37i9dQZEVXbMYsavqzfk6k",
            "HK": "37i9dQZEVXbMdvweCgpBAe",
            "HN": "37i9dQZEVXbMuaLyPOPOg7",
            "GT": "37i9dQZEVXbJHSzlHx2ZJU",
            "GR": "37i9dQZEVXbLfxwYMQnhFy",
            "DE": "37i9dQZEVXbK8BKKMArIyl",
            "FR": "37i9dQZEVXbKQ1ogMOyW9N",
            "FI": "37i9dQZEVXbJQ9kF73GOT2",
            "EE": "37i9dQZEVXbLnGyU4lLfIR",
            "SV": "37i9dQZEVXbKtVexUCYsK7",
            "EG": "37i9dQZEVXbMy2EcFg5F9m",
            "EC": "37i9dQZEVXbJPVQvqZqpcM",
            "DO": "37i9dQZEVXbMPoK06pe7d6",
            "DK": "37i9dQZEVXbMw2iUtFR5Eq",
            "CZ": "37i9dQZEVXbLKI6MPixefZ",
            "CY": "37i9dQZEVXbKVvIaSFCnNP",
            "CR": "37i9dQZEVXbNDIQm4XMct1",
            "CO": "37i9dQZEVXbL1Fl8vdBUba",
            "CL": "37i9dQZEVXbLJ0paT1JkgZ",
            "CA": "37i9dQZEVXbMda2apknTqH",
            "BG": "37i9dQZEVXbJQbYjwxrhPm",
            "BR": "37i9dQZEVXbKzoK95AbRy9",
            "BO": "37i9dQZEVXbJgjCMawPquO",
            "BE": "37i9dQZEVXbND4ZYa46PaA",
            "BY": "37i9dQZEVXbLRLeF2cVSaP",
            "AT": "37i9dQZEVXbM1EaZ0igDlz",
            "AU": "37i9dQZEVXbK4fwx2r07XW",
            "AR": "37i9dQZEVXbKPTKrnFPD0G",
            "global": "37i9dQZEVXbNG2KDcFcKOF",
        }
        try:
            user = User.objects.get(spotify_id=spotify_id)
            # Get the user's country code (assumes there's a country_code field in the User model)
            country_code = user.country

            if not country_code:
                return {"error": "User does not have a country code."}
            playlist_id = country_to_playlist.get(country_code)
            if not playlist_id:
                playlist_id = country_to_playlist.get("global")
            res = tk.Spotify(user.access_token).playlist_items(playlist_id)
            print(res.items)
        except User.DoesNotExist:
            return {"error": "User not found."}


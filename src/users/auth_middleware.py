# users/auth_middleware.py
from channels.middleware import BaseMiddleware
from channels.db import database_sync_to_async
from django.contrib.auth.models import AnonymousUser
from .models import SoundscapeUser, User as SpotifyUser
from .views import decrypt_session_token # Assuming decrypt_session_token is in users/utils.py
import time # For checking token expiration

# You might need to import your SessionPayload if decrypt_session_token returns it directly
# from somewhere import SessionPayload # If SessionPayload is defined elsewhere and returned by decrypt

@database_sync_to_async
def get_soundscape_user_from_custom_session(session_cookie_value: str):
    if not session_cookie_value:
        print("CustomAuth: No session cookie value provided.")
        return AnonymousUser()

    try:
        session_payload = decrypt_session_token(session_cookie_value)
    except Exception as e:
        print(f"CustomAuth: Error decrypting session token: {e}")
        return AnonymousUser()

    if not session_payload:
        print("CustomAuth: Decryption returned no payload.")
        return AnonymousUser()

    if not hasattr(session_payload, 'userid') or \
       not hasattr(session_payload, 'exp') or \
       not hasattr(session_payload, 'spotify_id'):
        print("CustomAuth: Invalid session payload structure (missing userid, exp, or spotify_id).")
        return AnonymousUser()

    if time.time() > session_payload.exp:
        print("CustomAuth: Session token expired.")
        return AnonymousUser()

    if not session_payload.spotify_id:
        print("CustomAuth: spotify_id missing in session payload.")
        return AnonymousUser()

    try:
        # 1. Find the SpotifyUser profile using spotify_id
        spotify_user_profile = SpotifyUser.objects.select_related('soundscape_user').get(
            spotify_id=session_payload.spotify_id
        )
        
        # 2. Access the related SoundscapeUser
        # The related name from User to SoundscapeUser is 'soundscape_user'
        # as defined in SoundscapeUser.profile's related_name.
        soundscape_user = spotify_user_profile.soundscape_user 
        
        if not soundscape_user:
            print(f"CustomAuth: SoundscapeUser not found for Spotify profile {spotify_user_profile.spotify_id}.")
            return AnonymousUser()

        # Now 'soundscape_user' is the instance of your main SoundscapeUser model
        print(f"CustomAuth: SoundscapeUser found: {soundscape_user.username} (ID: {soundscape_user.user_id})")
        return soundscape_user # Return the SoundscapeUser instance

    except SpotifyUser.DoesNotExist:
        print(f"CustomAuth: SpotifyUser profile with spotify_id {session_payload.spotify_id} not found.")
        return AnonymousUser()
    except SoundscapeUser.DoesNotExist: # Should be caught by the check above if relationship is proper
        print(f"CustomAuth: SoundscapeUser link broken for Spotify profile {session_payload.spotify_id}.")
        return AnonymousUser()
    except AttributeError: # If spotify_user_profile.soundscape_user doesn't exist (e.g. null foreign key)
        print(f"CustomAuth: SoundscapeUser not linked for Spotify profile {session_payload.spotify_id}.")
        return AnonymousUser()
    except Exception as e:
        print(f"CustomAuth: Error fetching user: {e}")
        return AnonymousUser()

class CustomCookieAuthMiddleware(BaseMiddleware):
    async def __call__(self, scope, receive, send):
        cookies = scope.get("cookies", {})
        session_cookie_value = cookies.get("session")

        if not session_cookie_value:
            headers = dict(scope.get("headers", []))
            cookie_header_bytes = headers.get(b"cookie")
            if cookie_header_bytes:
                cookie_header_str = cookie_header_bytes.decode('utf-8', errors='ignore')
                parsed_cookies = {
                    k.strip(): v.strip() 
                    for k, v in (item.split("=", 1) for item in cookie_header_str.split(";") if "=" in item)
                }
                session_cookie_value = parsed_cookies.get("session")
                if session_cookie_value:
                    print(f"CustomAuth: Session cookie found in headers: {session_cookie_value[:20]}...")
                else:
                    print("CustomAuth: 'session' cookie not found in parsed header string.")
            else:
                print("CustomAuth: No 'cookie' header found.")
        else:
            print(f"CustomAuth: Session cookie found in scope['cookies']: {session_cookie_value[:20]}...")

        if session_cookie_value:
            # This will now set scope['user'] to an instance of SoundscapeUser
            scope['user'] = await get_soundscape_user_from_custom_session(session_cookie_value)
        else:
            print("CustomAuth: No session cookie value to process. Setting AnonymousUser.")
            scope['user'] = AnonymousUser()
        
        auth_status = False
        user_display = "Anonymous"
        if scope['user'] and hasattr(scope['user'], 'is_authenticated'): # Django User/AnonymousUser
            auth_status = scope['user'].is_authenticated
            user_display = str(scope['user'])
        elif scope['user'] and isinstance(scope['user'], SoundscapeUser): # Your custom user
            auth_status = True # If it's a SoundscapeUser instance, consider it authenticated
            user_display = scope['user'].username

        print(f"CustomAuth: Middleware finished. User in scope: {user_display} (Authenticated: {auth_status})")
        
        return await super().__call__(scope, receive, send)

def CustomCookieAuthMiddlewareStack(inner):
    return CustomCookieAuthMiddleware(inner)

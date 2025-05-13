# users/consumers.py
import json
from channels.generic.websocket import AsyncWebsocketConsumer
from .models import SoundscapeUser # Ensure this is your main user model
from django.contrib.auth.models import AnonymousUser
from channels.db import database_sync_to_async
from .models import SoundscapeUser, Chat, Message


class NotificationConsumer(AsyncWebsocketConsumer):
    async def connect(self):
        # self.scope["user"] should now be an instance of SoundscapeUser or AnonymousUser
        self.user = self.scope.get("user") 
        
        user_display_for_log = "Anonymous"
        is_authenticated_for_log = False

        if self.user and not isinstance(self.user, AnonymousUser) and isinstance(self.user, SoundscapeUser):
            is_authenticated_for_log = True # If it's a SoundscapeUser, it's authenticated by our middleware
            user_display_for_log = self.user.username
        elif self.user and hasattr(self.user, 'is_authenticated'): # For standard AnonymousUser
            is_authenticated_for_log = self.user.is_authenticated
            user_display_for_log = str(self.user)


        print(f"Consumer Connect: User from scope: {user_display_for_log}")
        print(f"Consumer Connect: Is authenticated by middleware: {is_authenticated_for_log}")

        # Check if the user is a SoundscapeUser instance and authenticated
        if not (self.user and isinstance(self.user, SoundscapeUser) and is_authenticated_for_log):
            print("Consumer Connect: User not a valid SoundscapeUser or not authenticated. Closing connection.")
            await self.close()
            return

        # Now self.user is definitely a SoundscapeUser instance.
        # Use its primary key user_id (UUID) for the group name.
        self.room_group_name = f"notifications_{self.user.user_id}" 
        print(f"Consumer Connect: Joining room {self.room_group_name}")

        await self.channel_layer.group_add(
            self.room_group_name,
            self.channel_name
        )
        await self.accept()
        print(f"Consumer Connect: WebSocket accepted for user {self.user.username} (ID: {self.user.user_id})")

    async def disconnect(self, close_code):
        if hasattr(self, 'room_group_name') and self.room_group_name:
            print(f"Consumer Disconnect: Leaving room {self.room_group_name}")
            await self.channel_layer.group_discard(
                self.room_group_name,
                self.channel_name
            )
        else:
            print("Consumer Disconnect: No room group to leave or user was not set.")

    async def receive(self, text_data):
        user_identifier = "Unknown"
        if self.user and isinstance(self.user, SoundscapeUser):
            user_identifier = self.user.username
        print(f"Consumer Receive: Received message: {text_data} from user {user_identifier}")
        pass

    async def notification_message(self, event):
        user_identifier = "Unknown"
        if self.user and isinstance(self.user, SoundscapeUser):
            user_identifier = self.user.username
        print(f"Consumer notification_message: Sending event data to user {user_identifier}: {event['data']}")
        await self.send(text_data=json.dumps(event["data"]))



class ChatConsumer(AsyncWebsocketConsumer):
    async def connect(self):
        self.user = self.scope.get("user")
        
        if not (self.user and isinstance(self.user, SoundscapeUser)):
            await self.close()
            return

        # Get chat_id from URL
        self.chat_id = self.scope['url_route']['kwargs']['chat_id']
        self.room_group_name = f'chat_{self.chat_id}'

        # Join room group
        await self.channel_layer.group_add(
            self.room_group_name,
            self.channel_name
        )
        await self.accept()

    async def disconnect(self, close_code):
        # Leave room group
        await self.channel_layer.group_discard(
            self.room_group_name,
            self.channel_name
        )

    async def receive(self, text_data):
        try:
            data = json.loads(text_data)
            message = data.get('message')
            
            if not message:
                return

            # Save message to database
            chat = await database_sync_to_async(Chat.objects.get)(id=self.chat_id)
            message_obj = await database_sync_to_async(Message.objects.create)(
                chat=chat,
                sender=self.user,
                content=message
            )

            # Send message to room group
            await self.channel_layer.group_send(
                self.room_group_name,
                {
                    'type': 'chat_message',
                    'data': {
                        'id': message_obj.id,
                        'sender': {
                            'user_id': str(self.user.user_id),
                            'username': self.user.username,
                            'pfp': self.user.pfp
                        },
                        'content': message,
                        'created_at': message_obj.created_at.isoformat(),
                        'is_read': message_obj.is_read
                    }
                }
            )
        except Exception as e:
            print(f"Error in receive: {e}")

    async def chat_message(self, event):
        # Send message to WebSocket
        await self.send(text_data=json.dumps(event['data']))
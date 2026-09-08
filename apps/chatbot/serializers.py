from rest_framework import serializers
from apps.chatbot.models import Conversation, ChatMessage
from core.utils.public_input_validation import CHAT_MESSAGE_MAX_LENGTH, validate_long_text


class ChatMessageSerializer(serializers.ModelSerializer):
    class Meta:
        model = ChatMessage
        fields = ["id", "role", "content", "created_at"]


class ConversationSerializer(serializers.ModelSerializer):
    messages = ChatMessageSerializer(many=True, read_only=True)

    class Meta:
        model = Conversation
        fields = ["id", "title", "created_at", "updated_at", "messages"]


class ChatRequestSerializer(serializers.Serializer):
    message = serializers.CharField(
        max_length=CHAT_MESSAGE_MAX_LENGTH,
        trim_whitespace=True,
    )
    conversation_id = serializers.UUIDField(required=False)

    def validate_message(self, value):
        return validate_long_text(value, max_length=CHAT_MESSAGE_MAX_LENGTH)

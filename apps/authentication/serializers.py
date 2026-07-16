from django.contrib.auth.models import User
from rest_framework import serializers
from rest_framework_simplejwt.tokens import RefreshToken


class RegisterSerializer(serializers.ModelSerializer):
    password = serializers.CharField(write_only=True, min_length=8)

    class Meta:
        model = User
        fields = ('id', 'username', 'email', 'password')

    def create(self, validated_data):
        return User.objects.create_user(**validated_data)

    def to_representation(self, instance):
        refresh = RefreshToken.for_user(instance)

        return {
            'user': {
                'id': instance.id,
                'username': instance.username,
                'email': instance.email,
            },
            'tokens': {
                'refresh': str(refresh),
                'access': str(refresh.access_token),
            },
        }

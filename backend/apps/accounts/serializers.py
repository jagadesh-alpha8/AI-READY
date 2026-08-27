from django.contrib.auth import authenticate
from django.contrib.auth.password_validation import validate_password
from rest_framework import serializers

from .models import User


class UserSerializer(serializers.ModelSerializer):
    institution_id = serializers.PrimaryKeyRelatedField(source='institution', read_only=True)
    # Kept for the existing frontend (AuthContext/Navbar consume `user.name` directly);
    # first_name/last_name are the source of truth going forward.
    name = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = [
            'id', 'institution_id', 'username', 'name', 'first_name', 'last_name',
            'email', 'phone', 'role', 'department_name', 'is_active', 'is_staff',
            'date_joined', 'updated_at',
        ]
        read_only_fields = fields

    def get_name(self, obj):
        return obj.get_full_name()


class LoginResponseSerializer(serializers.Serializer):
    access_token = serializers.CharField()
    refresh_token = serializers.CharField()
    user = UserSerializer()


class LoginSerializer(serializers.Serializer):
    email = serializers.EmailField()
    password = serializers.CharField(write_only=True, trim_whitespace=False)

    def validate(self, attrs):
        user = authenticate(
            request=self.context.get('request'),
            username=attrs['email'],
            password=attrs['password'],
        )
        if user is None:
            raise serializers.ValidationError('Invalid login credentials')
        if not user.is_active:
            raise serializers.ValidationError('This account has been disabled')
        attrs['user'] = user
        return attrs


class LogoutSerializer(serializers.Serializer):
    refresh = serializers.CharField()


class ChangePasswordSerializer(serializers.Serializer):
    old_password = serializers.CharField(write_only=True, trim_whitespace=False)
    new_password = serializers.CharField(write_only=True, trim_whitespace=False)

    def validate_old_password(self, value):
        user = self.context['request'].user
        if not user.check_password(value):
            raise serializers.ValidationError('Current password is incorrect.')
        return value

    def validate_new_password(self, value):
        validate_password(value, user=self.context['request'].user)
        return value

    def save(self):
        user = self.context['request'].user
        user.set_password(self.validated_data['new_password'])
        user.save(update_fields=['password'])
        return user

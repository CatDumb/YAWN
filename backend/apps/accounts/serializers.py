from rest_framework import serializers

from apps.accounts.models import User


class OTPRequestSerializer(serializers.Serializer):
    email = serializers.EmailField()

    def validate_email(self, value):
        return value.strip().lower()


class OTPVerifySerializer(OTPRequestSerializer):
    challenge_id = serializers.UUIDField()
    code = serializers.RegexField(r"^\d{6}$")


class MembershipSerializer(serializers.Serializer):
    company_id = serializers.IntegerField(source="company.id")
    company = serializers.CharField(source="company.name")
    role = serializers.CharField()


class CurrentUserSerializer(serializers.ModelSerializer):
    memberships = MembershipSerializer(many=True, read_only=True)

    class Meta:
        model = User
        fields = ["id", "email", "first_name", "last_name", "memberships"]

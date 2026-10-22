from django.contrib.auth.forms import AdminUserCreationForm, UserChangeForm

from .models import User


class UserAdminCreationForm(AdminUserCreationForm[User]):
    class Meta:
        model = User
        fields = ("email",)


class UserAdminChangeForm(UserChangeForm[User]):
    class Meta:
        model = User
        fields = "__all__"

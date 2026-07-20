from django.contrib.auth.backends import ModelBackend
from django.contrib.auth import get_user_model


class EmailBackend(ModelBackend):
    def authenticate(self, username=None, password=None, **kwargs):
        if not username:
            return None
        UserModel = get_user_model()
        try:
            user = UserModel.objects.get(email__iexact=username)
        except UserModel.DoesNotExist:
            try:
                user = UserModel.objects.get(voter__sin__iexact=username)
            except (UserModel.DoesNotExist, UserModel.MultipleObjectsReturned):
                return None
        except UserModel.MultipleObjectsReturned:
            return None
        if user.check_password(password):
            return user
        return None

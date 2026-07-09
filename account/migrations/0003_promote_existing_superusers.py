from django.db import migrations


def promote_superusers_to_superadmin(apps, schema_editor):
    CustomUser = apps.get_model('account', 'CustomUser')
    CustomUser.objects.filter(is_superuser=True).update(user_type='0')


def reverse_promote(apps, schema_editor):
    CustomUser = apps.get_model('account', 'CustomUser')
    CustomUser.objects.filter(is_superuser=True, user_type='0').update(user_type='1')


class Migration(migrations.Migration):

    dependencies = [
        ('account', '0002_alter_customuser_user_type'),
    ]

    operations = [
        migrations.RunPython(promote_superusers_to_superadmin, reverse_promote),
    ]

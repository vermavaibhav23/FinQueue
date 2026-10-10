from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('jobs', '0005_idempotency_request'),
    ]

    operations = [
        migrations.DeleteModel(
            name='Transaction',
        ),
    ]

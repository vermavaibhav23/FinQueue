from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('jobs', '0002_transaction_and_more'),
    ]

    operations = [
        migrations.AlterField(
            model_name='job',
            name='job_type',
            field=models.CharField(
                choices=[
                    ('refund_processing', 'Refund Processing'),
                    ('webhook_delivery', 'Webhook Delivery'),
                    ('send_notification', 'Send Notification'),
                ],
                max_length=32,
            ),
        ),
    ]

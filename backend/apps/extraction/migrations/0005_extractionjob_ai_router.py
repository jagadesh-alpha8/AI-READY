from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('extraction', '0004_aiusage_source'),
    ]

    operations = [
        migrations.AddField(
            model_name='extractionjob',
            name='ai_router',
            field=models.CharField(blank=True, max_length=100),
        ),
    ]

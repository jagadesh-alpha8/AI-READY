# Generated for Onboarding Guide state persistence

import uuid
import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('accounts', '0003_consolidate_to_three_roles'),
        ('institutions', '0001_initial'),
        ('sprints', '0001_initial'),
    ]

    operations = [
        migrations.CreateModel(
            name='UserGuideState',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('skipped_steps', models.JSONField(blank=True, default=list)),
                ('is_dismissed', models.BooleanField(default=False)),
                ('dismissed_at', models.DateTimeField(blank=True, null=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('institution', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, related_name='guide_states', to='institutions.institution')),
                ('sprint', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, related_name='guide_states', to='sprints.sprint')),
                ('user', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='guide_states', to=settings.AUTH_USER_MODEL)),
            ],
            options={
                'ordering': ['-updated_at'],
                'indexes': [models.Index(fields=['user', 'institution', 'sprint'], name='accounts_us_user_id_4407b8_idx')],
            },
        ),
    ]


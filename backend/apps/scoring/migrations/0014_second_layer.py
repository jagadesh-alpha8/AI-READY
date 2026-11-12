import django.db.models.deletion
import uuid
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("scoring", "0013_depth_follow_up"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.AddField(
            model_name="depthresponse",
            name="parent",
            field=models.ForeignKey(
                blank=True,
                help_text="The response whose follow-up question this answers.",
                null=True,
                on_delete=django.db.models.deletion.CASCADE,
                related_name="follow_ups",
                to="scoring.depthresponse",
            ),
        ),
        migrations.AddField(
            model_name="depthresponse",
            name="status",
            field=models.CharField(
                choices=[("pending", "Waiting for a check"), ("checked", "Checked")],
                default="checked",
                max_length=10,
            ),
        ),
        migrations.AddField(
            model_name="depthresponse",
            name="windows",
            field=models.JSONField(
                blank=True, default=list, help_text="Passages the search found for the answer."
            ),
        ),
        migrations.AddField(
            model_name="depthresponse",
            name="support_check",
            field=models.JSONField(
                blank=True, default=dict, help_text="The answer checked against those passages."
            ),
        ),
        migrations.AddField(
            model_name="depthresponse",
            name="follow_up_text",
            field=models.TextField(
                blank=True, help_text="The one follow-up question the check asked, if any."
            ),
        ),
        migrations.CreateModel(
            name="AdditionalEvidence",
            fields=[
                (
                    "id",
                    models.UUIDField(
                        default=uuid.uuid4,
                        editable=False,
                        primary_key=True,
                        serialize=False,
                    ),
                ),
                ("run_ref", models.CharField(db_index=True, max_length=64)),
                ("document_ids", models.JSONField(default=list)),
                ("note", models.TextField(blank=True)),
                ("picked", models.JSONField(blank=True, default=list)),
                ("routing", models.JSONField(blank=True, default=dict)),
                ("windows", models.JSONField(blank=True, default=list)),
                (
                    "status",
                    models.CharField(
                        choices=[("pending", "Waiting for a check"), ("checked", "Checked")],
                        default="pending",
                        max_length=10,
                    ),
                ),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                (
                    "submitted_by",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="+",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={
                "ordering": ["run_ref", "created_at"],
            },
        ),
    ]

# Generated by Django 5.1.6 on 2025-04-02 08:57

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        ('accounts', '0024_business_timetowait'),
    ]

    operations = [
        migrations.CreateModel(
            name='RetellLLM',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('llm_id', models.CharField(max_length=255, unique=True)),
                ('model', models.CharField(max_length=255)),
                ('general_prompt', models.TextField(blank=True, null=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('business', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='retell_llms', to='accounts.business')),
            ],
        ),
        migrations.CreateModel(
            name='RetellAgent',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('agent_id', models.CharField(max_length=255, unique=True)),
                ('agent_name', models.CharField(max_length=255)),
                ('voice_id', models.CharField(max_length=255)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('business', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='retell_agents', to='accounts.business')),
                ('llm', models.ForeignKey(null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='agents', to='retell_agent.retellllm')),
            ],
        ),
    ]

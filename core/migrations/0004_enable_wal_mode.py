from django.db import migrations


def enable_wal_mode(apps, schema_editor):
    from django.db import connection

    with connection.cursor() as cursor:
        cursor.execute("PRAGMA journal_mode=WAL;")
        result = cursor.fetchone()
        if result:
            print(f"SQLite journal mode set to: {result[0]}")


class Migration(migrations.Migration):
    atomic = False

    dependencies = [
        ("core", "0003_add_langgraph_fields"),
    ]

    operations = [
        migrations.RunPython(enable_wal_mode, reverse_code=migrations.RunPython.noop),
    ]


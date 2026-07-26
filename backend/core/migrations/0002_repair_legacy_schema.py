from django.db import migrations


def repair_legacy_schema(apps, schema_editor):
    """Repair databases created before migrations were committed to source control.

    Earlier production images generated ``core.0001_initial`` at container start.
    The committed 0001 migration later reused that name with a newer model state,
    so Django considered the migration applied even though newer tables and columns
    were absent. This operation compares the historical model state with the actual
    database and creates only the missing tables, columns and automatic M2M tables.
    """

    connection = schema_editor.connection
    app_config = apps.get_app_config("core")

    def table_names():
        with connection.cursor() as cursor:
            return set(connection.introspection.table_names(cursor))

    def column_names(table):
        with connection.cursor() as cursor:
            return {
                column.name
                for column in connection.introspection.get_table_description(cursor, table)
            }

    existing_tables = table_names()

    for model in app_config.get_models(include_auto_created=False):
        options = model._meta
        if options.proxy or not options.managed:
            continue

        table = options.db_table
        if table not in existing_tables:
            schema_editor.create_model(model)
            existing_tables = table_names()
            continue

        existing_columns = column_names(table)
        for field in options.local_fields:
            if field.column and field.column not in existing_columns:
                schema_editor.add_field(model, field)
                existing_columns = column_names(table)

        for field in options.local_many_to_many:
            through = field.remote_field.through
            through_table = through._meta.db_table
            if through_table not in existing_tables:
                schema_editor.create_model(through)
                existing_tables = table_names()


def noop_reverse(apps, schema_editor):
    # The repair is intentionally irreversible: removing recovered production
    # columns or tables could destroy existing operational data.
    pass


class Migration(migrations.Migration):
    dependencies = [("core", "0001_initial")]

    operations = [migrations.RunPython(repair_legacy_schema, noop_reverse)]

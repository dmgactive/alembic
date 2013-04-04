import alembic
from alembic.operations import Operations
from alembic.migration import MigrationContext
from alembic import util
from contextlib import contextmanager

class EnvironmentContext(object):
    """Represent the state made available to an ``env.py`` script.

    :class:`.EnvironmentContext` is normally instantiated
    by the commands present in the :mod:`alembic.command`
    module.  From within an ``env.py`` script, the current
    :class:`.EnvironmentContext` is available via the
    ``alembic.context`` datamember.

    :class:`.EnvironmentContext` is also a Python context
    manager, that is, is intended to be used using the
    ``with:`` statement.  A typical use of :class:`.EnvironmentContext`::

        from alembic.config import Config
        from alembic.script import ScriptDirectory

        config = Config()
        config.set_main_option("script_location", "myapp:migrations")
        script = ScriptDirectory.from_config(config)

        def my_function(rev, context):
            '''do something with revision "rev", which
            will be the current database revision,
            and "context", which is the MigrationContext
            that the env.py will create'''

        with EnvironmentContext(
            config,
            script,
            fn = my_function,
            as_sql = False,
            starting_rev = 'base',
            destination_rev = 'head',
            tag = "sometag"
        ):
            script.run_env()

    The above script will invoke the ``env.py`` script
    within the migration environment.  If and when ``env.py``
    calls :meth:`.MigrationContext.run_migrations`, the
    ``my_function()`` function above will be called
    by the :class:`.MigrationContext`, given the context
    itself as well as the current revision in the database.

    .. note::

        For most API usages other than full blown
        invocation of migration scripts, the :class:`.MigrationContext`
        and :class:`.ScriptDirectory` objects can be created and
        used directly.  The :class:`.EnvironmentContext` object
        is *only* needed when you need to actually invoke the
        ``env.py`` module present in the migration environment.

    """

    _migration_context = None
    _default_opts = None

    config = None
    """An instance of :class:`.Config` representing the
    configuration file contents as well as other variables
    set programmatically within it."""

    script = None
    """An instance of :class:`.ScriptDirectory` which provides
    programmatic access to version files within the ``versions/``
    directory.

    """

    def __init__(self, config, script, **kw):
        """Construct a new :class:`.EnvironmentContext`.

        :param config: a :class:`.Config` instance.
        :param script: a :class:`.ScriptDirectory` instance.
        :param \**kw: keyword options that will be ultimately
         passed along to the :class:`.MigrationContext` when
         :meth:`.EnvironmentContext.configure` is called.

        """
        self.config = config
        self.script = script
        self.context_opts = kw
        if self._default_opts:
            self.context_opts.update(self._default_opts)

    def __enter__(self):
        """Establish a context which provides a
        :class:`.EnvironmentContext` object to
        env.py scripts.

        The :class:`.EnvironmentContext` will
        be made available as ``from alembic import context``.

        """
        alembic.context._install_proxy(self)
        return self

    def __exit__(self, *arg, **kw):
        alembic.context._remove_proxy()
        alembic.op._remove_proxy()

    def is_offline_mode(self):
        """Return True if the current migrations environment
        is running in "offline mode".

        This is ``True`` or ``False`` depending
        on the the ``--sql`` flag passed.

        This function does not require that the :class:`.MigrationContext`
        has been configured.

        """
        return self.context_opts.get('as_sql', False)

    def is_transactional_ddl(self):
        """Return True if the context is configured to expect a
        transactional DDL capable backend.

        This defaults to the type of database in use, and
        can be overridden by the ``transactional_ddl`` argument
        to :meth:`.configure`

        This function requires that a :class:`.MigrationContext`
        has first been made available via :meth:`.configure`.

        """
        return self.get_context().impl.transactional_ddl

    def requires_connection(self):
        return not self.is_offline_mode()

    def get_head_revision(self):
        """Return the hex identifier of the 'head' revision.

        This function does not require that the :class:`.MigrationContext`
        has been configured.

        """
        return self.script._as_rev_number("head")

    def get_starting_revision_argument(self):
        """Return the 'starting revision' argument,
        if the revision was passed using ``start:end``.

        This is only meaningful in "offline" mode.
        Returns ``None`` if no value is available
        or was configured.

        This function does not require that the :class:`.MigrationContext`
        has been configured.

        """
        if self._migration_context is not None:
            return self.script._as_rev_number(
                        self.get_context()._start_from_rev)
        elif 'starting_rev' in self.context_opts:
            return self.script._as_rev_number(
                        self.context_opts['starting_rev'])
        else:
            raise util.CommandError(
                        "No starting revision argument is available.")

    def get_revision_argument(self):
        """Get the 'destination' revision argument.

        This is typically the argument passed to the
        ``upgrade`` or ``downgrade`` command.

        If it was specified as ``head``, the actual
        version number is returned; if specified
        as ``base``, ``None`` is returned.

        This function does not require that the :class:`.MigrationContext`
        has been configured.

        """
        return self.script._as_rev_number(
                            self.context_opts['destination_rev'])

    def get_tag_argument(self):
        """Return the value passed for the ``--tag`` argument, if any.

        The ``--tag`` argument is not used directly by Alembic,
        but is available for custom ``env.py`` configurations that
        wish to use it; particularly for offline generation scripts
        that wish to generate tagged filenames.

        This function does not require that the :class:`.MigrationContext`
        has been configured.

        """
        return self.context_opts.get('tag', None)

    def configure(self,
            connection=None,
            url=None,
            dialect_name=None,
            transactional_ddl=None,
            output_buffer=None,
            output_encoding=None,
            starting_rev=None,
            tag=None,
            template_args=None,
            target_metadata=None,
            include_symbol=None,
            include_schemas=False,
            compare_type=False,
            compare_server_default=False,
            render_item=None,
            upgrade_token="upgrades",
            downgrade_token="downgrades",
            alembic_module_prefix="op.",
            sqlalchemy_module_prefix="sa.",
            **kw
        ):
        """Configure a :class:`.MigrationContext` within this
        :class:`.EnvironmentContext` which will provide database
        connectivity and other configuration to a series of
        migration scripts.

        Many methods on :class:`.EnvironmentContext` require that
        this method has been called in order to function, as they
        ultimately need to have database access or at least access
        to the dialect in use.  Those which do are documented as such.

        The important thing needed by :meth:`.configure` is a
        means to determine what kind of database dialect is in use.
        An actual connection to that database is needed only if
        the :class:`.MigrationContext` is to be used in
        "online" mode.

        If the :meth:`.is_offline_mode` function returns ``True``,
        then no connection is needed here.  Otherwise, the
        ``connection`` parameter should be present as an
        instance of :class:`sqlalchemy.engine.Connection`.

        This function is typically called from the ``env.py``
        script within a migration environment.  It can be called
        multiple times for an invocation.  The most recent
        :class:`~sqlalchemy.engine.Connection`
        for which it was called is the one that will be operated upon
        by the next call to :meth:`.run_migrations`.

        General parameters:

        :param connection: a :class:`~sqlalchemy.engine.Connection`
         to use
         for SQL execution in "online" mode.  When present, is also
         used to determine the type of dialect in use.
        :param url: a string database url, or a
         :class:`sqlalchemy.engine.url.URL` object.
         The type of dialect to be used will be derived from this if
         ``connection`` is not passed.
        :param dialect_name: string name of a dialect, such as
         "postgresql", "mssql", etc.
         The type of dialect to be used will be derived from this if
         ``connection`` and ``url`` are not passed.
        :param transactional_ddl: Force the usage of "transactional"
         DDL on or off;
         this otherwise defaults to whether or not the dialect in
         use supports it.
        :param output_buffer: a file-like object that will be used
         for textual output
         when the ``--sql`` option is used to generate SQL scripts.
         Defaults to
         ``sys.stdout`` if not passed here and also not present on
         the :class:`.Config`
         object.  The value here overrides that of the :class:`.Config`
         object.
        :param output_encoding: when using ``--sql`` to generate SQL
         scripts, apply this encoding to the string output.

         .. versionadded:: 0.5.0

        :param starting_rev: Override the "starting revision" argument
         when using ``--sql`` mode.
        :param tag: a string tag for usage by custom ``env.py`` scripts.
         Set via the ``--tag`` option, can be overridden here.
        :param template_args: dictionary of template arguments which
         will be added to the template argument environment when
         running the "revision" command.   Note that the script environment
         is only run within the "revision" command if the --autogenerate
         option is used, or if the option "revision_environment=true"
         is present in the alembic.ini file.  New in 0.3.3.
        :param version_table: The name of the Alembic version table.
         The default is ``'alembic_version'``.

        Parameters specific to the autogenerate feature, when
        ``alembic revision`` is run with the ``--autogenerate`` feature:

        :param target_metadata: a :class:`sqlalchemy.schema.MetaData`
         object that
         will be consulted during autogeneration.  The tables present
         will be compared against
         what is locally available on the target
         :class:`~sqlalchemy.engine.Connection`
         to produce candidate upgrade/downgrade operations.

        :param compare_type: Indicates type comparison behavior during
         an autogenerate
         operation.  Defaults to ``False`` which disables type
         comparison.  Set to
         ``True`` to turn on default type comparison, which has varied
         accuracy depending on backend.

         To customize type comparison behavior, a callable may be
         specified which
         can filter type comparisons during an autogenerate operation.
         The format of this callable is::

            def my_compare_type(context, inspected_column,
                        metadata_column, inspected_type, metadata_type):
                # return True if the types are different,
                # False if not, or None to allow the default implementation
                # to compare these types
                pass

         ``inspected_column`` is a dictionary structure as returned by
         :meth:`sqlalchemy.engine.reflection.Inspector.get_columns`, whereas
         ``metadata_column`` is a :class:`sqlalchemy.schema.Column` from
         the local model environment.

         A return value of ``None`` indicates to allow default type
         comparison to proceed.

        :param compare_server_default: Indicates server default comparison
         behavior during
         an autogenerate operation.  Defaults to ``False`` which disables
         server default
         comparison.  Set to  ``True`` to turn on server default comparison,
         which has
         varied accuracy depending on backend.

         To customize server default comparison behavior, a callable may
         be specified
         which can filter server default comparisons during an
         autogenerate operation.
         defaults during an autogenerate operation.   The format of this
         callable is::

            def my_compare_server_default(context, inspected_column,
                        metadata_column, inspected_default, metadata_default,
                        rendered_metadata_default):
                # return True if the defaults are different,
                # False if not, or None to allow the default implementation
                # to compare these defaults
                pass

         ``inspected_column`` is a dictionary structure as returned by
         :meth:`sqlalchemy.engine.reflection.Inspector.get_columns`, whereas
         ``metadata_column`` is a :class:`sqlalchemy.schema.Column` from
         the local model environment.

         A return value of ``None`` indicates to allow default server default
         comparison
         to proceed.  Note that some backends such as Postgresql actually
         execute
         the two defaults on the database side to compare for equivalence.

        :param include_symbol: A callable function which, given a table name
         and schema name (may be ``None``), returns ``True`` or ``False``, indicating
         if the given table should be considered in the autogenerate sweep.
         E.g.::

            def include_symbol(tablename, schema):
                return tablename not in ("skip_table_one", "skip_table_two")

            context.configure(
                # ...
                include_symbol = include_symbol
            )

         To limit autogenerate to a certain set of schemas when using the
         ``include_schemas`` option::

            def include_symbol(tablename, schema):
                return schema in (None, "schema1", "schema2")

            context.configure(
                # ...
                include_schemas = True,
                include_symbol = include_symbol
            )

         .. versionadded:: 0.3.6

         .. versionchanged:: 0.4.0  the ``include_symbol`` callable must now
            also accept a "schema" argument, which may be None.

        :param render_item: Callable that can be used to override how
         any schema item, i.e. column, constraint, type,
         etc., is rendered for autogenerate.  The callable receives a
         string describing the type of object, the object, and
         the autogen context.  If it returns False, the
         default rendering method will be used.  If it returns None,
         the item will not be rendered in the context of a Table
         construct, that is, can be used to skip columns or constraints
         within op.create_table()::

            def my_render_column(type_, col, autogen_context):
                if type_ == "column" and isinstance(col, MySpecialCol):
                    return repr(col)
                else:
                    return False

            context.configure(
                # ...
                render_item = my_render_column
            )

         Available values for the type string include: ``column``,
         ``primary_key``, ``foreign_key``, ``unique``, ``check``,
         ``type``, ``server_default``.

         .. versionadded:: 0.5.0

        :param upgrade_token: When autogenerate completes, the text of the
         candidate upgrade operations will be present in this template
         variable when ``script.py.mako`` is rendered.  Defaults to
         ``upgrades``.
        :param downgrade_token: When autogenerate completes, the text of the
         candidate downgrade operations will be present in this
         template variable when ``script.py.mako`` is rendered.  Defaults to
         ``downgrades``.

        :param alembic_module_prefix: When autogenerate refers to Alembic
         :mod:`alembic.operations` constructs, this prefix will be used
         (i.e. ``op.create_table``)  Defaults to "``op.``".
         Can be ``None`` to indicate no prefix.

        :param sqlalchemy_module_prefix: When autogenerate refers to
         SQLAlchemy
         :class:`~sqlalchemy.schema.Column` or type classes, this prefix
         will be used
         (i.e. ``sa.Column("somename", sa.Integer)``)  Defaults to "``sa.``".
         Can be ``None`` to indicate no prefix.
         Note that when dialect-specific types are rendered, autogenerate
         will render them using the dialect module name, i.e. ``mssql.BIT()``,
         ``postgresql.UUID()``.

        :param include_schemas: If True, autogenerate will scan across
         all schemas located by the SQLAlchemy
         :meth:`~sqlalchemy.engine.reflection.Inspector.get_schema_names`
         method, and include all differences in tables found across all
         those schemas.  When using this option, you may want to also
         use the ``include_symbol`` option to specify a callable which
         can filter the tables/schemas that get included.

         .. versionadded :: 0.4.0

        Parameters specific to individual backends:

        :param mssql_batch_separator: The "batch separator" which will
         be placed between each statement when generating offline SQL Server
         migrations.  Defaults to ``GO``.  Note this is in addition to the
         customary semicolon ``;`` at the end of each statement; SQL Server
         considers the "batch separator" to denote the end of an
         individual statement execution, and cannot group certain
         dependent operations in one step.
        :param oracle_batch_separator: The "batch separator" which will
         be placed between each statement when generating offline
         Oracle migrations.  Defaults to ``/``.  Oracle doesn't add a
         semicolon between statements like most other backends.

        """
        opts = self.context_opts
        if transactional_ddl is not None:
            opts["transactional_ddl"] = transactional_ddl
        if output_buffer is not None:
            opts["output_buffer"] = output_buffer
        elif self.config.output_buffer is not None:
            opts["output_buffer"] = self.config.output_buffer
        if output_encoding is not None:
            opts["output_encoding"] = output_encoding
        if starting_rev:
            opts['starting_rev'] = starting_rev
        if tag:
            opts['tag'] = tag
        if template_args and 'template_args' in opts:
            opts['template_args'].update(template_args)
        opts['target_metadata'] = target_metadata
        opts['include_symbol'] = include_symbol
        opts['include_schemas'] = include_schemas
        opts['upgrade_token'] = upgrade_token
        opts['downgrade_token'] = downgrade_token
        opts['sqlalchemy_module_prefix'] = sqlalchemy_module_prefix
        opts['alembic_module_prefix'] = alembic_module_prefix
        if render_item is not None:
            opts['render_item'] = render_item
        if compare_type is not None:
            opts['compare_type'] = compare_type
        if compare_server_default is not None:
            opts['compare_server_default'] = compare_server_default
        opts['script'] = self.script
        opts.update(kw)

        self._migration_context = MigrationContext.configure(
            connection=connection,
            url=url,
            dialect_name=dialect_name,
            opts=opts
        )

    def run_migrations(self, **kw):
        """Run migrations as determined by the current command line
        configuration
        as well as versioning information present (or not) in the current
        database connection (if one is present).

        The function accepts optional ``**kw`` arguments.   If these are
        passed, they are sent directly to the ``upgrade()`` and
        ``downgrade()``
        functions within each target revision file.   By modifying the
        ``script.py.mako`` file so that the ``upgrade()`` and ``downgrade()``
        functions accept arguments, parameters can be passed here so that
        contextual information, usually information to identify a particular
        database in use, can be passed from a custom ``env.py`` script
        to the migration functions.

        This function requires that a :class:`.MigrationContext` has
        first been made available via :meth:`.configure`.

        """
        with Operations.context(self._migration_context):
            self.get_context().run_migrations(**kw)

    def execute(self, sql, execution_options=None):
        """Execute the given SQL using the current change context.

        The behavior of :meth:`.execute` is the same
        as that of :meth:`.Operations.execute`.  Please see that
        function's documentation for full detail including
        caveats and limitations.

        This function requires that a :class:`.MigrationContext` has
        first been made available via :meth:`.configure`.

        """
        self.get_context().execute(sql,
                execution_options=execution_options)

    def static_output(self, text):
        """Emit text directly to the "offline" SQL stream.

        Typically this is for emitting comments that
        start with --.  The statement is not treated
        as a SQL execution, no ; or batch separator
        is added, etc.

        """
        self.get_context().impl.static_output(text)

    def begin_transaction(self):
        """Return a context manager that will
        enclose an operation within a "transaction",
        as defined by the environment's offline
        and transactional DDL settings.

        e.g.::

            with context.begin_transaction():
                context.run_migrations()

        :meth:`.begin_transaction` is intended to
        "do the right thing" regardless of
        calling context:

        * If :meth:`.is_transactional_ddl` is ``False``,
          returns a "do nothing" context manager
          which otherwise produces no transactional
          state or directives.
        * If :meth:`.is_offline_mode` is ``True``,
          returns a context manager that will
          invoke the :meth:`.DefaultImpl.emit_begin`
          and :meth:`.DefaultImpl.emit_commit`
          methods, which will produce the string
          directives ``BEGIN`` and ``COMMIT`` on
          the output stream, as rendered by the
          target backend (e.g. SQL Server would
          emit ``BEGIN TRANSACTION``).
        * Otherwise, calls :meth:`sqlalchemy.engine.Connection.begin`
          on the current online connection, which
          returns a :class:`sqlalchemy.engine.Transaction`
          object.  This object demarcates a real
          transaction and is itself a context manager,
          which will roll back if an exception
          is raised.

        Note that a custom ``env.py`` script which
        has more specific transactional needs can of course
        manipulate the :class:`~sqlalchemy.engine.Connection`
        directly to produce transactional state in "online"
        mode.

        """
        if not self.is_transactional_ddl():
            @contextmanager
            def do_nothing():
                yield
            return do_nothing()
        elif self.is_offline_mode():
            @contextmanager
            def begin_commit():
                self.get_context().impl.emit_begin()
                yield
                self.get_context().impl.emit_commit()
            return begin_commit()
        else:
            return self.get_bind().begin()

    def get_context(self):
        """Return the current :class:`.MigrationContext` object.

        If :meth:`.EnvironmentContext.configure` has not been
        called yet, raises an exception.

        """

        if self._migration_context is None:
            raise Exception("No context has been configured yet.")
        return self._migration_context

    def get_bind(self):
        """Return the current 'bind'.

        In "online" mode, this is the
        :class:`sqlalchemy.engine.Connection` currently being used
        to emit SQL to the database.

        This function requires that a :class:`.MigrationContext`
        has first been made available via :meth:`.configure`.

        """
        return self.get_context().bind

    def get_impl(self):
        return self.get_context().impl


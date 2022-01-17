
Using Pytest
============

So, you already have ``testcord`` installed, and can import it. However, setting up a client for every test is
a pain. The library is designed to work well with ``pytest`` (Thus the name), and it can make writing tests much
easier. In the following tutorial we'll show how to set it up.

Starting with Pytest
--------------------

``pytest`` can be installed through pip the same way ``testcord`` is. Once that's done, using it is as easy
as:

- Windows: ``py -m pytest``
- Linux: ``python3 -m pytest``

``pytest`` will detect any functions starting with 'test' in directories it searches, and run them. It also supports
a feature we will use heavily, called 'fixtures'. Fixtures are functions that do some common test setup, and
then can be used in tests to always perform that setup. They can also return an object that will be passed to
the test.

The final piece of this is ``pytest-asyncio``, a library for allowing ``pytest`` to run async tests. It is
automatically installed when you get ``testcord`` from pip, so you don't need to worry about installing it.

Putting all this together, we can rewrite our previous tests to look like this:

.. code:: python

    import pytest
    import discord.ext.test as testcord


    @pytest.fixture
    def bot(event_loop):
        bot = ... # However you create your bot, make sure to use loop=event_loop
        testcord.configure(bot)
        return bot


    @pytest.mark.asyncio
    async def test_ping(bot):
        await testcord.message("!ping")
        assert testcord.verify().message().contains().content("Ping:")


    @pytest.mark.asyncio
    async def test_foo(bot):
        await testcord.message("!hello")
        assert testcord.verify().message().content("Hello World!")

Much less writing the same code over and over again, and tests will be automatically run by pytest, then the results
output in a nice pretty format once it's done.

What is conftest.py?
--------------------

As you write tests, you may want to split them into multiple files. One file for testing this cog, another for
ensuring reactions work right. As it stands, you'll still need to copy your bot fixture into every file. To fix this,
you need to create a file named ``conftest.py`` at the root of where you're putting your tests. If you haven't already,
you should probably put them all in their own directory. Then you can put any fixtures you want in ``conftest.py``,
and pytest will let you use them in any other test file. ``pytest`` also recognizes certain function names with
special meanings, for example ``pytest_sessionfinish`` will be run after all tests are done if defined in your conftest.

An example ``conftest.py`` might look like this:

.. code:: python

    import pytest
    import discord.ext.test as testcord


    @pytest.fixture
    def bot(event_loop):
        bot = ... # However you create your bot, make sure to use loop=event_loop
        testcord.configure(bot)
        return bot


    def pytest_sessionfinish():
        # Clean up attachment files
        files = glob.glob('./testcord_*.dat')
        for path in files:
            try:
                os.remove(path)
            except Exception as e:
                print(f"Error while deleting file {path}: {e}")

With that, you should be ready to use ``testcord`` with your bot.

Troubleshooting
---------------

- I wrote a fixture, but I can't use the bot

Make sure your tests take a parameter with the exact same name as the fixture,
pytest runs them based on name, including capitalization.

- I get an instance of my bot, but it just gets stuck / doesn't do anything
  when I ``await``

Make sure you passed ``event_loop`` to your bot when creating it. Pytest-asyncio
does not necessarily use the default event loop, so your bot may not actually
be running.

--------------------

This is currently the end of the tutorials. Take a look at the `Runner Documentation`_ to see all the things you can
do with ``testcord``.

.. _Runner Documentation: ../modules/runner.html

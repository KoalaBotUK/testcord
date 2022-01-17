
Getting Started
===============

Welcome to ``testcord``, a python library for testing discord bots written using ``pycord``. This tutorial
will explain how to install ``testcord`` and set it up in your project, and write a simple test. If you already
know how to install libraries with pip, you probably want to skip to `Using Pytest`_.

Installing testcord
-------------------

To start with, you should install testcord with ``pip``. This will look a bit different, depending if you're
on Windows or Mac/Linux:

- Windows: ``py -m pip install testcord``
- Linux: ``python3 -m pip install testcord``

Using testcord
--------------

Once installed, you will need to import ``testcord`` before you can use it. As it is an extension to ``pycord``,
it goes into the ``pycord`` extensions module. So, the most basic usage of testcord would look like this:

.. code:: python

    import asyncio
    import discord.ext.test as testcord


    async def test_ping():
        bot = ...  # However you create your bot.
        testcord.configure(bot)
        await testcord.message("!ping")
        assert testcord.verify().message().contains().content("Ping:")


    async def test_foo():
        bot = ... # Same setup as above
        testcord.configure(bot)
        await testcord.message("!hello")
        assert testcord.verify().message().content("Hello World!")


    asyncio.run(test_ping())
    asyncio.run(test_foo())

If that looks like a lot of code just to run tests, don't worry, there's a better way! We can use pytest,
a popular Python testing library.

--------------------

**Next Tutorial**: `Using Pytest`_

.. _Using Pytest: ./using_pytest.html

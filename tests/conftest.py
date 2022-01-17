import glob
import os
import pytest
import discord
import discord.ext.commands as commands
import discord.ext.test as testcord


@pytest.fixture
def client(event_loop):
    c = discord.Client(loop=event_loop)
    testcord.configure(c)
    return c


@pytest.fixture
def bot(request, event_loop):
    intents = discord.Intents.default()
    intents.members = True
    b = commands.Bot("!", loop=event_loop, intents=intents)

    marks = request.function.pytestmark
    mark = None
    for mark in marks:
        if mark.name == "cogs":
            break

    if mark is not None:
        for extension in mark.args:
            b.load_extension("tests.internal." + extension)

    testcord.configure(b)
    return b


@pytest.fixture(autouse=True)
async def cleanup():
    yield
    await testcord.empty_queue()


def pytest_sessionfinish(session, exitstatus):
    """ Code to execute after all tests. """

    # dat files are created when using attachements
    print("\n-------------------------\nClean testcord_*.dat files")
    fileList = glob.glob('./testcord_*.dat')
    for filePath in fileList:
        try:
            os.remove(filePath)
        except Exception:
            print("Error while deleting file : ", filePath)
import discord
import pytest
import discord.ext.test as testcord


@pytest.mark.asyncio
async def test_verify_activity_matches(bot):
    fake_act = discord.Activity(name="Streaming",
                                url="http://mystreamingfeed.xyz",
                                type=discord.ActivityType.streaming)
    await bot.change_presence(activity=fake_act)
    assert testcord.verify().activity().matches(fake_act)

    other_act = discord.Activity(name="Playing Around", type=discord.ActivityType.playing)
    await bot.change_presence(activity=other_act)
    assert not testcord.verify().activity().matches(fake_act)


@pytest.mark.asyncio
async def test_verify_no_activity(bot):
    await bot.change_presence(activity=None)
    assert testcord.verify().activity().matches(None)

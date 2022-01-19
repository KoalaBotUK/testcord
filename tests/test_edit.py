
import pytest
import discord.ext.test as testcord


@pytest.mark.asyncio
async def test_edit(bot):
    guild = bot.guilds[0]
    channel = guild.channels[0]

    mes = await channel.send("Test Message")
    new_mes = await mes.edit(content="New Message")

    assert new_mes.content == "New Message"

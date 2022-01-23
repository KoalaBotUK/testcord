"""
    Module for 'server-side' state during testing. This module should contain
    methods for altering said server-side state, which then are responsible for triggering
    a ``parse_*`` call in the configured client state to inform the bot of the change.

    This setup matches discord's actual setup, where an HTTP call triggers a change on the server,
    which is then sent back to the bot as an event which is parsed and dispatched.
"""

from __future__ import annotations

import asyncio
import datetime
import logging
import pathlib
import re
from typing import (
    Any,
    Coroutine,
    Dict,
    NamedTuple,
    List,
    Optional,
    TYPE_CHECKING,
    TypeVar,
    Union,
    Pattern
)

import discord

from . import factories as facts, state as dstate, websocket, _types
from .http import FakeHttp

_log = logging.getLogger(__name__)

if TYPE_CHECKING:
    from discord.types.message import Attachment

    T = TypeVar('T')
    BE = TypeVar('BE', bound=BaseException)
    MU = TypeVar('MU', bound='MaybeUnlock')
    Response = Coroutine[Any, Any, T]


class BackendState(NamedTuple):
    """
        The testcord backend, with all the state it needs to hold to be able to pretend to be
        discord. Generally only used internally, but exposed through :py:func:`get_state`
    """
    messages: Dict[int, List[_types.JsonDict]]
    state: dstate.FakeState


log = logging.getLogger("discord.ext.tests")
_cur_config: Optional[BackendState] = None
_undefined = object()  # default value for when NoneType has special meaning


def get_state() -> dstate.FakeState:
    """
        Get the current backend state, or raise an error if it hasn't been configured

    :return: Current backend state
    """
    if _cur_config is None:
        raise ValueError("testcord backend not configured")
    return _cur_config.state


def make_guild(
        name: str,
        members: List[discord.Member] = None,
        channels: List[_types.AnyChannel] = None,
        roles: List[discord.Role] = None,
        owner: bool = False,
        id_num: int = -1,
) -> discord.Guild:
    """
        Add a new guild to the backend, triggering any relevant callbacks on the configured client

    :param name: Name of the guild
    :param members: Existing members of the guild or None
    :param channels: Existing channels in the guild or None
    :param roles: Existing roles in the guild or None
    :param owner: Whether the configured client owns the guild, default is false
    :param id_num: ID of the guild, or nothing to auto-generate
    :return: Newly created guild
    """
    if id_num == -1:
        id_num = facts.make_id()
    if roles is None:
        roles = [facts.make_role_dict("@everyone", id_num, position=0)]
    if channels is None:
        channels = []
    if members is None:
        members = []
    member_count = len(members) if len(members) != 0 else 1

    state = get_state()

    owner_id = state.user.id if owner else 0

    data = facts.make_guild_dict(
        name, owner_id, roles, id_num=id_num, member_count=member_count, members=members, channels=channels
    )

    state.parse_guild_create(data)

    return state._get_guild(id_num)


def update_guild(guild: discord.Guild, roles: List[discord.Role] = None) -> discord.Guild:
    """
        Update an existing guild with new information, triggers a guild update but not any individual item
        create/edit calls

    :param guild: Guild to be updated
    :param roles: New role list for the guild
    :return: Updated guild object
    """
    data = facts.dict_from_guild(guild)

    if roles is not None:
        data["roles"] = list(map(facts.dict_from_role, roles))

    state = get_state()
    state.parse_guild_update(data)

    return guild


def make_role(
        name: str,
        guild: discord.Guild,
        id_num: int = -1,
        colour: int = 0,
        color: Optional[int] = None,
        permissions: int = 104324161,
        hoist: bool = False,
        mentionable: bool = False,
) -> discord.Role:
    """
        Add a new role to the backend, triggering any relevant callbacks on the configured client

    :param name: Name of the new role
    :param guild: Guild role is being added to
    :param id_num: ID of the new role, or nothing to auto-generate
    :param colour: Color of the new role
    :param color: Alias for above
    :param permissions: Permissions for the new role
    :param hoist: Whether the new role is hoisted
    :param mentionable: Whether the new role is mentionable
    :return: Newly created role
    """
    r_dict = facts.make_role_dict(
        name, id_num=id_num, colour=colour, color=color, permissions=permissions, hoist=hoist, mentionable=mentionable
    )
    # r_dict["position"] = max(map(lambda x: x.position, guild._roles.values())) + 1
    r_dict["position"] = 1

    data = {
        "guild_id": guild.id,
        "role": r_dict
    }

    state = get_state()
    state.parse_guild_role_create(data)

    return guild.get_role(r_dict["id"])


def update_role(
        role: discord.Role,
        colour: Optional[int] = None,
        color: Optional[int] = None,
        permissions: Optional[int] = None,
        hoist: Optional[bool] = None,
        mentionable: Optional[bool] = None,
        name: Optional[str] = None,
) -> discord.Role:
    """
        Update an existing role with new data, triggering a role update event.
        Any value not passed/passed None will not update the existing value.

    :param role: Role to update
    :param colour: New color for the role
    :param color: Alias for above
    :param permissions: New permissions
    :param hoist: New hoist value
    :param mentionable: New mention value
    :param name: New name for the role
    :return: Role that was updated
    """
    data = {"guild_id": role.guild.id, "role": facts.dict_from_role(role)}
    if color is not None:
        colour = color
    if colour is not None:
        data["role"]["color"] = colour
    if permissions is not None:
        data["role"]["permissions"] = int(permissions)
        data["role"]["permissions_new"] = int(permissions)

    if hoist is not None:
        data["role"]["hoist"] = hoist
    if mentionable is not None:
        data["role"]["mentionable"] = mentionable
    if name is not None:
        data["role"]["name"] = name

    state = get_state()
    state.parse_guild_role_update(data)

    return role


def delete_role(role: discord.Role) -> None:
    """
        Remove a role from the backend, deleting it from the guild

    :param role: Role to delete
    """
    state = get_state()
    state.parse_guild_role_delete({"guild_id": role.guild.id, "role_id": role.id})


def make_text_channel(
        name: str,
        guild: discord.Guild,
        position: int = -1,
        id_num: int = -1,
        permission_overwrites: Optional[_types.JsonDict] = None,
        parent_id: Optional[int] = None,
) -> discord.TextChannel:
    if position == -1:
        position = len(guild.channels) + 1

    c_dict = facts.make_text_channel_dict(name, id_num, position=position, guild_id=guild.id,
                                          permission_overwrites=permission_overwrites, parent_id=parent_id)

    state = get_state()
    state.parse_channel_create(c_dict)

    return guild.get_channel(c_dict["id"])


def make_category_channel(
        name: str,
        guild: discord.Guild,
        position: int = -1,
        id_num: int = -1,
        permission_overwrites: Optional[_types.JsonDict] = None,
) -> discord.CategoryChannel:
    if position == -1:
        position = len(guild.categories) + 1
    c_dict = facts.make_category_channel_dict(name, id_num, position=position, guild_id=guild.id,
                                              permission_overwrites=permission_overwrites)
    state = get_state()
    state.parse_channel_create(c_dict)

    return guild.get_channel(c_dict["id"])


def delete_channel(channel: _types.AnyChannel) -> None:
    c_dict = facts.make_text_channel_dict(channel.name, id_num=channel.id, guild_id=channel.guild.id)

    state = get_state()
    state.parse_channel_delete(c_dict)


def update_text_channel(
        channel: discord.TextChannel,
        target: Union[discord.User, discord.Role],
        override: Optional[discord.PermissionOverwrite] = _undefined
) -> None:
    c_dict = facts.dict_from_channel(channel)
    if override is not _undefined:
        ovr = c_dict.get("permission_overwrites", [])
        existing = [o for o in ovr if o.get("id") == target.id]
        if existing:
            ovr.remove(existing[0])
        if override:
            ovr = ovr + [facts.dict_from_overwrite(target, override)]
        c_dict["permission_overwrites"] = ovr

    state = get_state()
    state.parse_channel_update(c_dict)


def make_user(username: str, discrim: Union[str, int], avatar: Optional[str] = None,
              id_num: int = -1) -> discord.User:
    if id_num == -1:
        id_num = facts.make_id()

    data = facts.make_user_dict(username, discrim, avatar, id_num)

    state = get_state()
    user = state.store_user(data)

    return user


def make_member(user: Union[discord.user.BaseUser, discord.abc.User], guild: discord.Guild,
                nick: Optional[str] = None,
                roles: Optional[List[discord.Role]] = None) -> discord.Member:
    if roles is None:
        roles = []
    roles = list(map(lambda x: x.id, roles))

    data = facts.make_member_dict(guild, user, roles, nick=nick)

    state = get_state()
    state.parse_guild_member_add(data)

    return guild.get_member(user.id)


def update_member(member: discord.Member, nick: Optional[str] = None,
                  roles: Optional[List[discord.Role]] = None) -> discord.Member:
    data = facts.dict_from_member(member)
    if nick is not None:
        data["nick"] = nick
    if roles is not None:
        data["roles"] = list(map(lambda x: x.id, roles))

    state = get_state()
    state.parse_guild_member_update(data)

    return member


def delete_member(member: discord.Member) -> None:
    out = facts.dict_from_member(member)
    state = get_state()
    state.parse_guild_member_remove(out)


def make_message(
        content: str,
        author: Union[discord.user.BaseUser, discord.abc.User],
        channel: _types.AnyChannel,
        tts: bool = False,
        embeds: Optional[List[discord.Embed]] = None,
        attachments: Optional[List[discord.Attachment]] = None,
        nonce: Optional[int] = None,
        id_num: int = -1,
) -> discord.Message:
    guild = channel.guild if hasattr(channel, "guild") else None
    guild_id = guild.id if guild else None

    mentions = find_user_mentions(content, guild)
    role_mentions = find_role_mentions(content, guild)
    channel_mentions = find_channel_mentions(content, guild)

    kwargs = {}
    if nonce is not None:
        kwargs["nonce"] = nonce

    data = facts.make_message_dict(
        channel, author, id_num, content=content, mentions=mentions, tts=tts, embeds=embeds, attachments=attachments,
        mention_roles=role_mentions, mention_channels=channel_mentions, guild_id=guild_id, **kwargs
    )

    state = get_state()
    state.parse_message_create(data)

    if channel.id not in _cur_config.messages:
        _cur_config.messages[channel.id] = []
    _cur_config.messages[channel.id].append(data)

    return state._get_message(data["id"])


MEMBER_MENTION: Pattern = re.compile(r"<@!?[0-9]{17,21}>", re.MULTILINE)
ROLE_MENTION: Pattern = re.compile(r"<@&([0-9]{17,21})>", re.MULTILINE)
CHANNEL_MENTION: Pattern = re.compile(r"<#[0-9]{17,21}>", re.MULTILINE)


def find_user_mentions(content: Optional[str], guild: Optional[discord.Guild]) -> List[
    discord.Member]:
    if guild is None or content is None:
        return []  # TODO: Check for dm user mentions
    matches = re.findall(MEMBER_MENTION, content)
    return [discord.utils.get(guild.members, id=int(re.search(r'\d+', match)[0])) for match in matches]  # noqa: E501


def find_role_mentions(content: Optional[str], guild: Optional[discord.Guild]) -> List[int]:
    if guild is None or content is None:
        return []
    matches = re.findall(ROLE_MENTION, content)
    return matches


def find_channel_mentions(content: Optional[str], guild: Optional[discord.Guild]) -> List[
    _types.AnyChannel]:
    if guild is None or content is None:
        return []
    matches = re.findall(CHANNEL_MENTION, content)
    return [discord.utils.get(guild.channels, mention=match) for match in matches]


def delete_message(message: discord.Message) -> None:
    data = {
        "id": message.id,
        "channel_id": message.channel.id
    }
    if message.guild is not None:
        data["guild_id"] = message.guild.id

    state = get_state()
    state.parse_message_delete(data)

    messages = _cur_config.messages[message.channel.id]
    index = next(i for i, v in enumerate(messages) if v["id"] == message.id)
    del _cur_config.messages[message.channel.id][index]


def make_attachment(filename: pathlib.Path, name: Optional[str] = None, id_num: int = -1) -> discord.Attachment:
    if name is None:
        name = str(filename.name)
    if not filename.is_file():
        raise ValueError("Attachment must be a real file")
    size = filename.stat().st_size
    file_uri = filename.absolute().as_uri()
    return discord.Attachment(
        state=get_state(),
        data=facts.make_attachment_dict(name, size, file_uri, file_uri, id_num)
    )


def add_reaction(message: discord.Message, user: Union[discord.user.BaseUser, discord.abc.User],
                 emoji: str) -> None:
    if ":" in emoji:
        temp = emoji.split(":")
        emoji = {
            "id": temp[0],
            "name": temp[1]
        }
    else:
        emoji = {
            "id": None,
            "name": emoji
        }

    data = {
        "message_id": message.id,
        "channel_id": message.channel.id,
        "user_id": user.id,
        "emoji": emoji
    }
    if message.guild:
        data["guild_id"] = message.guild.id
    # when reactions are added by something other than the bot client, we want the user to end up in the payload.
    if isinstance(user, discord.Member):
        data["member"] = facts.dict_from_member(user)

    state = get_state()
    state.parse_message_reaction_add(data)

    messages = _cur_config.messages[message.channel.id]
    message_data = next(filter(lambda x: x["id"] == message.id, messages), None)
    if message_data is not None:
        if "reactions" not in message_data:
            message_data["reactions"] = []

        react: Optional[_types.JsonDict] = None
        for react in message_data["reactions"]:
            if react["emoji"]["id"] == emoji["id"] and react["emoji"]["name"] == emoji["name"]:
                break

        if react is None:
            react = {"count": 0, "me": False, "emoji": emoji}
            message_data["reactions"].append(react)

        react["count"] += 1
        if user.id == state.user.id:
            react["me"] = True


def remove_reaction(message: discord.Message, user: discord.user.BaseUser, emoji: str) -> None:
    if ":" in emoji:
        temp = emoji.split(":")
        emoji = {
            "id": temp[0],
            "name": temp[1]
        }
    else:
        emoji = {
            "id": None,
            "name": emoji
        }

    data = {
        "message_id": message.id,
        "channel_id": message.channel.id,
        "user_id": user.id,
        "emoji": emoji
    }
    if message.guild:
        data["guild_id"] = message.guild.id

    state = get_state()
    state.parse_message_reaction_remove(data)

    messages = _cur_config.messages[message.channel.id]
    message_data = next(filter(lambda x: x["id"] == message.id, messages), None)
    if message_data is not None:
        if "reactions" not in message_data:
            message_data["reactions"] = []

        react: Optional[_types.JsonDict] = None
        for react in message_data["reactions"]:
            if react["emoji"]["id"] == emoji["id"] and react["emoji"]["name"] == emoji["name"]:
                break
        if react is None:
            return

        react["count"] -= 1
        if user.id == state.user.id:
            react["me"] = False

        if react["count"] == 0:
            message_data["reactions"].remove(react)


def clear_reactions(message: discord.Message):
    data = {
        "message_id": message.id,
        "channel_id": message.channel.id
    }
    if message.guild:
        data["guild_id"] = message.guild.id

    state = get_state()
    state.parse_message_reaction_remove_all(data)

    messages = _cur_config.messages[message.channel.id]
    message_data = next(filter(lambda x: x["id"] == message.id, messages), None)
    if message_data is not None:
        message_data["reactions"] = []


def pin_message(channel_id: int, message_id: int):
    data = {
        "channel_id": channel_id,
        "last_pin_timestamp": datetime.datetime.now().isoformat(),
    }
    state = get_state()
    state.parse_channel_pins_update(data)


def unpin_message(channel_id: int, message_id: int):
    data = {
        "channel_id": channel_id,
        "last_pin_timestamp": None,
    }
    state = get_state()
    state.parse_channel_pins_update(data)


def configure(client: Optional[discord.Client], *, use_dummy: bool = False) -> None:
    """
        Configure the backend, optionally with the provided client

    :param client: Client to use, or None
    :param use_dummy: Whether to use a dummy if client param is None, or error
    """
    global _cur_config, _messages

    if client is None and use_dummy:
        log.info("None passed to backend configuration, dummy client will be used")
        client = discord.Client()

    if not isinstance(client, discord.Client):
        raise TypeError("Runner client must be an instance of discord.Client")

    loop = asyncio.get_event_loop()

    if client.http is not None:
        loop.create_task(client.http.close())

    http = FakeHttp(loop=loop)
    client.http = http

    ws = websocket.FakeWebSocket(None, loop=loop)
    client.ws = ws

    test_state = dstate.FakeState(client, http=http, loop=loop)
    http.state = test_state

    client._connection = test_state

    _cur_config = BackendState({}, test_state)

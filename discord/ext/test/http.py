from __future__ import annotations

import asyncio
import logging
import pathlib
import sys
import urllib.parse
import urllib.request
from typing import (
    Any,
    ClassVar,
    Coroutine,
    Dict,
    List,
    Optional,
    Sequence,
    TYPE_CHECKING,
    Tuple,
    TypeVar
)

import discord
import discord.http as dhttp
from discord.errors import Forbidden, NotFound

from . import backend as back
from . import factories as facts, state as dstate, callbacks, _types
from .errors import TestOperationNotImplemented
from ._types import FakeRequest

_log = logging.getLogger(__name__)

if TYPE_CHECKING:
    from discord.file import File
    from discord.enums import (
        AuditLogAction,
        InteractionResponseType,
    )

    from discord.types import (
        audit_log,
        channel,
        components,
        emoji,
        embed,
        guild,
        integration,
        interactions,
        invite,
        member,
        message,
        template,
        role,
        user,
        webhook,
        channel,
        widget,
        threads,
        sticker,
        welcome_screen,
        scheduled_events,
    )
    from discord.types.snowflake import Snowflake, SnowflakeList

    T = TypeVar('T')
    BE = TypeVar('BE', bound=BaseException)
    MU = TypeVar('MU', bound='MaybeUnlock')
    Response = Coroutine[Any, Any, T]


def _get_higher_locs(num: int) -> Dict[str, Any]:
    """
        Get the local variables from higher in the call-stack. Should only be used in FakeHttp for
        retrieving information not passed to it by its caller.

    :param num: How many calls up to retrieve from
    :return: The local variables of that call, as a dictionary
    """
    frame = sys._getframe(num + 1)
    locs = frame.f_locals
    del frame
    return locs


class FakeHttp(dhttp.HTTPClient):
    """
        A mock implementation of an ``HTTPClient``. Instead of actually sending requests to discord, it triggers
        a runner callback and calls the ``testcord`` backend to update any necessary state and trigger any necessary
        fake messages to the client.
    """
    fileno: ClassVar[int] = 0
    state: dstate.FakeState

    def __init__(self, loop: asyncio.AbstractEventLoop = None) -> None:
        if loop is None:
            loop = asyncio.get_event_loop()

        super().__init__(connector=None, loop=loop)

    async def request(self, *args: Any, **kwargs: Any) -> Any:
        """
            Overloaded to raise a NotImplemented error informing the user that the requested operation
            isn't yet supported by ``testcord``. To fix this, the method call that triggered this error should be
            overloaded below to instead trigger a callback and call the appropriate backend function.

        :param args: Arguments provided to the request
        :param kwargs: Keyword arguments provided to the request
        """
        route: dhttp.Route = args[0]
        raise NotImplementedError(
            f"Operation occured that isn't captured by the tests framework. This is testcord's fault, please report"
            f"an issue on github. Debug Info: {route.method} {route.url} with {kwargs}"
        )

    async def get_from_cdn(self, url: str) -> bytes:
        parsed_url = urllib.parse.urlparse(url)
        path = urllib.request.url2pathname(parsed_url.path)
        with open(path, 'rb') as fd:
            return fd.read()

    # Message management

    async def start_private_message(self, user_id: int) -> _types.JsonDict:
        locs = _get_higher_locs(1)
        user = locs.get("self", None)

        await callbacks.dispatch_event("start_private_message", user)

        return facts.make_dm_channel_dict(user)

    async def send_message(
        self,
        channel_id: Snowflake,
        content: Optional[str],
        *,
        tts: bool = False,
        embed: Optional[embed.Embed] = None,
        embeds: Optional[List[embed.Embed]] = None,
        nonce: Optional[str] = None,
        allowed_mentions: Optional[message.AllowedMentions] = None,
        message_reference: Optional[message.MessageReference] = None,
        stickers: Optional[List[sticker.StickerItem]] = None,
        components: Optional[List[components.Component]] = None,) -> _types.JsonDict:
        locs = _get_higher_locs(1)
        channel = locs.get("channel", None)

        user = self.state.user
        if hasattr(channel, "guild"):
            perm = channel.permissions_for(channel.guild.get_member(user.id))
        else:
            perm = channel.permissions_for(user)
        if not (perm.send_messages or perm.administrator):
            raise Forbidden(FakeRequest(403, "missing send_messages"), "send_messages")

        if embed:
            embeds = [embed]

        message = back.make_message(
            channel=channel, author=self.state.user, content=content, tts=tts, embeds=embeds, nonce=nonce
        )

        await callbacks.dispatch_event("send_message", message)

        return facts.dict_from_message(message)

    async def send_typing(self, channel_id: Snowflake) -> None:
        locs = _get_higher_locs(1)
        channel = locs.get("channel", None)

        await callbacks.dispatch_event("send_typing", channel)

    async def send_files(
        self,
        channel_id: Snowflake,
        *,
        files: Sequence[File],
        content: Optional[str] = None,
        tts: bool = False,
        embed: Optional[embed.Embed] = None,
        embeds: Optional[List[embed.Embed]] = None,
        nonce: Optional[str] = None,
        allowed_mentions: Optional[message.AllowedMentions] = None,
        message_reference: Optional[message.MessageReference] = None,
        stickers: Optional[List[sticker.StickerItem]] = None,
        components: Optional[List[components.Component]] = None,
    ) -> _types.JsonDict:
        # allowed_mentions is being ignored.  It must be a keyword argument but I'm not yet certain what to use it for
        locs = _get_higher_locs(1)
        channel = locs.get("channel", None)

        attachments = []
        for file in files:
            path = pathlib.Path(f"./testcord_{self.fileno}.dat")
            self.fileno += 1
            if file.fp.seekable():
                file.fp.seek(0)
            with open(path, "wb") as nfile:
                nfile.write(file.fp.read())
            attachments.append((path, file.filename))
        attachments = list(map(lambda x: back.make_attachment(*x), attachments))

        if embed:
            embeds = [discord.Embed.from_dict(embed)]

        message = back.make_message(
            channel=channel, author=self.state.user, attachments=attachments, content=content, tts=tts, embeds=embeds,
            nonce=nonce
        )

        await callbacks.dispatch_event("send_message", message)

        return facts.dict_from_message(message)

    def edit_files(
        self,
        channel_id: Snowflake,
        message_id: Snowflake,
        files: Sequence[File],
        **fields,
    ) -> Response[message.Message]:
        raise TestOperationNotImplemented(self.edit_files.__name__)

    async def delete_message(
        self, channel_id: Snowflake, message_id: Snowflake, *, reason: Optional[str] = None
    ) -> None:
        locs = _get_higher_locs(1)
        message = locs.get("self", None)

        await callbacks.dispatch_event("delete_message", message.channel, message, reason=reason)

        back.delete_message(message)

    def delete_messages(
        self, channel_id: Snowflake, message_ids: SnowflakeList, *, reason: Optional[str] = None
    ) -> None:
        raise TestOperationNotImplemented(self.delete_messages.__name__)

    async def edit_message(self, channel_id: Snowflake, message_id: Snowflake, **fields: Any
                           ) -> _types.JsonDict:
        locs = _get_higher_locs(1)
        message = locs.get("self", None)

        await callbacks.dispatch_event("edit_message", message.channel, message, fields)

        out = facts.dict_from_message(message)
        out.update(fields)
        return out

    async def add_reaction(self, channel_id: Snowflake, message_id: Snowflake, emoji: str) -> None:
        locs = _get_higher_locs(1)
        message = locs.get("self")
        # normally only the connected user can add a reaction, but for testing purposes we want to be able to force
        # the call from a specific user.
        user = locs.get("member", self.state.user)

        emoji = emoji  # TODO: Turn this back into class?

        await callbacks.dispatch_event("add_reaction", message, emoji)

        back.add_reaction(message, user, emoji)

    async def remove_reaction(
        self, channel_id: Snowflake, message_id: Snowflake, emoji: str, member_id: Snowflake
    ) -> None:
        locs = _get_higher_locs(1)
        message = locs.get("self")
        member = locs.get("member")

        await callbacks.dispatch_event("remove_reaction", message, emoji, member)

        back.remove_reaction(message, member, emoji)

    async def remove_own_reaction(self, channel_id: Snowflake, message_id: Snowflake, emoji: str) -> None:
        locs = _get_higher_locs(1)
        message = locs.get("self")
        member = locs.get("member")

        await callbacks.dispatch_event("remove_own_reaction", message, emoji, member)

        back.remove_reaction(message, self.state.user, emoji)

    def get_reaction_users(
        self,
        channel_id: Snowflake,
        message_id: Snowflake,
        emoji: str,
        limit: int,
        after: Optional[Snowflake] = None,
    ) -> Response[List[user.User]]:
        raise TestOperationNotImplemented(self.get_reaction_users.__name__)

    async def clear_reactions(self, channel_id: Snowflake, message_id: Snowflake) -> None:
        locs = _get_higher_locs(1)
        message = locs.get("self")
        back.clear_reactions(message)

    def clear_single_reaction(self, channel_id: Snowflake, message_id: Snowflake, emoji: str) -> Response[None]:
        raise TestOperationNotImplemented(self.clear_single_reaction.__name__)

    async def get_message(self, channel_id: Snowflake, message_id: Snowflake) -> _types.JsonDict:
        locs = _get_higher_locs(1)
        channel = locs.get("self")

        await callbacks.dispatch_event("get_message", channel, message_id)

        messages = back._cur_config.messages[channel_id]
        find = next(filter(lambda m: m["id"] == message_id, messages), None)
        if find is None:
            raise NotFound(FakeRequest(404, "Not Found"), "Unknown Message")
        return find

    async def get_channel(self, channel_id: Snowflake) -> _types.JsonDict:
        await callbacks.dispatch_event("get_channel", channel_id)

        find = None
        for guild in back._cur_config.state.guilds:
            for channel in guild.channels:
                if channel.id == channel_id:
                    find = facts.dict_from_channel(channel)
        if find is None:
            raise NotFound(FakeRequest(404, "Not Found"), "Unknown Channel")
        return find

    async def logs_from(
        self,
        channel_id: Snowflake,
        limit: int,
        before: Optional[Snowflake] = None,
        after: Optional[Snowflake] = None,
        around: Optional[Snowflake] = None,
    ) -> List[_types.JsonDict]:
        locs = _get_higher_locs(1)
        his = locs.get("self", None)
        channel = his.channel

        await callbacks.dispatch_event("logs_from", channel, limit, before=None, after=None, around=None)

        messages = back._cur_config.messages[channel_id]
        if after is not None:
            start = next(i for i, v in enumerate(messages) if v["id"] == after)
            return messages[start:start + limit]
        elif around is not None:
            start = next(i for i, v in enumerate(messages) if v["id"] == around)
            return messages[start - limit // 2:start + limit // 2]
        else:
            if before is None:
                start = len(messages)
            else:
                start = next(i for i, v in enumerate(messages) if v["id"] == before)
            return messages[start - limit:start]

    async def pin_message(self, channel_id: Snowflake, message_id: Snowflake, reason: Optional[str] = None) -> None:
        back.pin_message(channel_id, message_id)

    async def unpin_message(self, channel_id: Snowflake, message_id: Snowflake, reason: Optional[str] = None) -> None:
        back.unpin_message(channel_id, message_id)

    def pins_from(self, channel_id: Snowflake) -> Response[List[message.Message]]:
        raise TestOperationNotImplemented(self.pins_from.__name__)

    async def kick(self, user_id: Snowflake, guild_id: Snowflake, reason: Optional[str] = None) -> None:
        locs = _get_higher_locs(1)
        guild = locs.get("self", None)
        member = locs.get("user", None)

        await callbacks.dispatch_event("kick", guild, member, reason=reason)

        back.delete_member(member)

    async def ban(
        self,
        user_id: Snowflake,
        guild_id: Snowflake,
        delete_message_days: int = 1,
        reason: Optional[str] = None,
    ) -> None:
        locs = _get_higher_locs(1)
        guild = locs.get("self", None)
        member = locs.get("user", None)

        await callbacks.dispatch_event("ban", guild, member, delete_message_days, reason=reason)

        back.delete_member(member)

    def unban(self, user_id: Snowflake, guild_id: Snowflake, *, reason: Optional[str] = None) -> Response[None]:
        raise TestOperationNotImplemented(self.unban.__name__)

    def edit_profile(self, payload: Dict[str, Any]) -> Response[user.User]:
        raise TestOperationNotImplemented(self.edit_profile.__name__)

    async def change_my_nickname(
        self,
        guild_id: Snowflake,
        nickname: str,
        *,
        reason: Optional[str] = None,
    ) -> _types.JsonDict:
        locs = _get_higher_locs(1)
        me = locs.get("self", None)

        me.nick = nickname

        await callbacks.dispatch_event("change_nickname", nickname, me, reason=reason)

        return {"nick": nickname}

    def change_nickname(
        self,
        guild_id: Snowflake,
        user_id: Snowflake,
        nickname: str,
        *,
        reason: Optional[str] = None,
    ) -> Response[member.Member]:
        raise TestOperationNotImplemented(self.change_nickname.__name__)

    def edit_my_voice_state(self, guild_id: Snowflake, payload: Dict[str, Any]) -> Response[None]:
        raise TestOperationNotImplemented(self.edit_my_voice_state.__name__)

    def edit_voice_state(self, guild_id: Snowflake, user_id: Snowflake, payload: Dict[str, Any]) -> Response[None]:
        raise TestOperationNotImplemented(self.edit_voice_state.__name__)

    async def edit_member(
        self,
        guild_id: Snowflake,
        user_id: Snowflake,
        *,
        reason: Optional[str] = None,
        **fields: Any,
    ) -> None:
        locs = _get_higher_locs(1)
        member = locs.get("self", None)

        await callbacks.dispatch_event("edit_member", fields, member, reason=reason)

    def edit_channel(
        self,
        channel_id: Snowflake,
        *,
        reason: Optional[str] = None,
        **options: Any,
    ) -> Response[channel.Channel]:
        raise TestOperationNotImplemented(self.edit_channel.__name__)

    def bulk_channel_update(
        self,
        guild_id: Snowflake,
        data: List[guild.ChannelPositionUpdate],
        *,
        reason: Optional[str] = None,
    ) -> Response[None]:
        raise TestOperationNotImplemented(self.bulk_channel_update.__name__)

    def create_channel(
        self,
        guild_id: Snowflake,
        channel_type: channel.ChannelType,
        *,
        reason: Optional[str] = None,
        **options: Any,
    ) -> _types.JsonDict:
        locs = _get_higher_locs(1)
        guild = locs.get("self", None)
        name = locs.get("name", None)
        perms = options.get("permission_overwrites", None)
        parent_id = options.get("parent_id", None)

        if channel_type == discord.ChannelType.text.value:
            channel = back.make_text_channel(name, guild, permission_overwrites=perms, parent_id=parent_id)
        elif channel_type == discord.ChannelType.category.value:
            channel = back.make_category_channel(name, guild, permission_overwrites=perms)
        else:
            raise NotImplementedError(
                "Operation occurred that isn't captured by the tests framework. This is testcord's fault, please report"
                "an issue on github. Debug Info: only TextChannels and CategoryChannels are currently supported."
            )
        return facts.dict_from_channel(channel)

    async def delete_channel(
        self,
        channel_id: Snowflake,
        *,
        reason: Optional[str] = None,
    ) -> None:
        locs = _get_higher_locs(1)
        channel = locs.get("self", None)
        if channel.type.value == discord.ChannelType.text.value:
            back.delete_channel(channel)
        if channel.type.value == discord.ChannelType.category.value:
            for sub_channel in channel.text_channels:
                back.delete_channel(sub_channel)
            back.delete_channel(channel)

    def start_thread_with_message(
        self,
        channel_id: Snowflake,
        message_id: Snowflake,
        *,
        name: str,
        auto_archive_duration: threads.ThreadArchiveDuration,
        reason: Optional[str] = None,
    ) -> Response[threads.Thread]:
        raise TestOperationNotImplemented(self.start_thread_with_message.__name__)

    def start_thread_without_message(
        self,
        channel_id: Snowflake,
        *,
        name: str,
        auto_archive_duration: threads.ThreadArchiveDuration,
        type: threads.ThreadType,
        invitable: bool = True,
        reason: Optional[str] = None,
    ) -> Response[threads.Thread]:
        raise TestOperationNotImplemented(self.start_thread_without_message.__name__)

    def join_thread(self, channel_id: Snowflake) -> Response[None]:
        raise TestOperationNotImplemented(self.join_thread.__name__)

    def add_user_to_thread(self, channel_id: Snowflake, user_id: Snowflake) -> Response[None]:
        raise TestOperationNotImplemented(self.add_user_to_thread.__name__)

    def leave_thread(self, channel_id: Snowflake) -> Response[None]:
        raise TestOperationNotImplemented(self.leave_thread.__name__)

    def remove_user_from_thread(self, channel_id: Snowflake, user_id: Snowflake) -> Response[None]:
        raise TestOperationNotImplemented(self.remove_user_from_thread.__name__)

    def get_public_archived_threads(
        self, channel_id: Snowflake, before: Optional[Snowflake] = None, limit: int = 50
    ) -> Response[threads.ThreadPaginationPayload]:
        raise TestOperationNotImplemented(self.get_public_archived_threads.__name__)

    def get_private_archived_threads(
        self, channel_id: Snowflake, before: Optional[Snowflake] = None, limit: int = 50
    ) -> Response[threads.ThreadPaginationPayload]:
        raise TestOperationNotImplemented(self.get_private_archived_threads.__name__)

    def get_joined_private_archived_threads(
        self, channel_id: Snowflake, before: Optional[Snowflake] = None, limit: int = 50
    ) -> Response[threads.ThreadPaginationPayload]:
        raise TestOperationNotImplemented(self.get_joined_private_archived_threads.__name__)

    def get_active_threads(self, guild_id: Snowflake) -> Response[threads.ThreadPaginationPayload]:
        raise TestOperationNotImplemented(self.get_active_threads.__name__)

    def get_thread_members(self, channel_id: Snowflake) -> Response[List[threads.ThreadMember]]:
        raise TestOperationNotImplemented(self.get_thread_members.__name__)

    # Webhook management

    def create_webhook(
        self,
        channel_id: Snowflake,
        *,
        name: str,
        avatar: Optional[bytes] = None,
        reason: Optional[str] = None,
    ) -> Response[webhook.Webhook]:
        raise TestOperationNotImplemented(self.create_webhook.__name__)

    def channel_webhooks(self, channel_id: Snowflake) -> Response[List[webhook.Webhook]]:
        raise TestOperationNotImplemented(self.channel_webhooks.__name__)

    def guild_webhooks(self, guild_id: Snowflake) -> Response[List[webhook.Webhook]]:
        raise TestOperationNotImplemented(self.guild_webhooks.__name__)

    def get_webhook(self, webhook_id: Snowflake) -> Response[webhook.Webhook]:
        raise TestOperationNotImplemented(self.get_webhook.__name__)

    def follow_webhook(
        self,
        channel_id: Snowflake,
        webhook_channel_id: Snowflake,
        reason: Optional[str] = None,
    ) -> Response[None]:
        raise TestOperationNotImplemented(self.follow_webhook.__name__)

    # Guild management

    async def get_guilds(
        self,
        limit: int,
        before: Optional[Snowflake] = None,
        after: Optional[Snowflake] = None,
    ) -> list[dict]:
        await callbacks.dispatch_event("get_guilds", limit, before=None, after=None)
        guilds = back.get_state().guilds  # List[]

        guilds_new = [{
            'id': guild.id,
            'name': guild.name,
            'icon': guild.icon,
            'splash': guild.splash,
            'owner_id': guild.owner_id,
            'region': guild.region,
            'afk_channel_id': guild.afk_channel.id if guild.afk_channel else None,
            'afk_timeout': guild.afk_timeout,
            'verification_level': guild.verification_level,
            'default_message_notifications': guild.default_notifications.value,
            'explicit_content_filter': guild.explicit_content_filter,
            'roles': list(map(facts.dict_from_role, guild.roles)),
            'emojis': list(map(facts.dict_from_emoji, guild.emojis)),
            'features': guild.features,
            'mfa_level': guild.mfa_level,
            'application_id': None,
            'system_channel_id': guild.system_channel.id if guild.system_channel else None,
            'owner': guild.owner_id == back.get_state().user.id
        } for guild in guilds]

        if not limit:
            limit = 100
        if after is not None:
            start = next(i for i, v in enumerate(guilds) if v.id == after)
            return guilds_new[start:start + limit]
        else:
            if before is None:
                start = int(len(guilds) / 2)
            else:
                start = next(i for i, v in enumerate(guilds) if v.id == before)
            return guilds_new[start - limit: start]

    def leave_guild(self, guild_id: Snowflake) -> Response[None]:
        raise TestOperationNotImplemented(self.leave_guild.__name__)

    async def get_guild(self, guild_id: Snowflake, *, with_counts = True) -> _types.JsonDict:
        locs = _get_higher_locs(1)
        client = locs.get("self", None)
        guild = discord.utils.get(client.guilds, id=guild_id)
        return facts.dict_from_guild(guild)

    def delete_guild(self, guild_id: Snowflake) -> Response[None]:
        raise TestOperationNotImplemented(self.delete_guild.__name__)

    def create_guild(self, name: str, region: str, icon: Optional[str]) -> Response[guild.Guild]:
        raise TestOperationNotImplemented(self.create_guild.__name__)

    def edit_guild(self, guild_id: Snowflake, *, reason: Optional[str] = None, **fields: Any) -> Response[guild.Guild]:
        raise TestOperationNotImplemented(self.edit_guild.__name__)

    def get_template(self, code: str) -> Response[template.Template]:
        raise TestOperationNotImplemented(self.get_template.__name__)

    def guild_templates(self, guild_id: Snowflake) -> Response[List[template.Template]]:
        raise TestOperationNotImplemented(self.guild_templates.__name__)

    def create_template(self, guild_id: Snowflake, payload: template.CreateTemplate) -> Response[template.Template]:
        raise TestOperationNotImplemented(self.create_template.__name__)

    def sync_template(self, guild_id: Snowflake, code: str) -> Response[template.Template]:
        raise TestOperationNotImplemented(self.sync_template.__name__)

    def edit_template(self, guild_id: Snowflake, code: str, payload) -> Response[template.Template]:
        raise TestOperationNotImplemented(self.edit_template.__name__)

    def delete_template(self, guild_id: Snowflake, code: str) -> Response[None]:
        raise TestOperationNotImplemented(self.delete_template.__name__)

    def create_from_template(self, code: str, name: str, region: str, icon: Optional[str]) -> Response[guild.Guild]:
        raise TestOperationNotImplemented(self.create_from_template.__name__)

    def get_bans(self, guild_id: Snowflake) -> Response[List[guild.Ban]]:
        raise TestOperationNotImplemented(self.get_bans.__name__)

    def get_ban(self, user_id: Snowflake, guild_id: Snowflake) -> Response[guild.Ban]:
        raise TestOperationNotImplemented(self.get_ban.__name__)

    def get_vanity_code(self, guild_id: Snowflake) -> Response[invite.VanityInvite]:
        raise TestOperationNotImplemented(self.get_vanity_code.__name__)

    def change_vanity_code(self, guild_id: Snowflake, code: str, *, reason: Optional[str] = None) -> Response[None]:
        raise TestOperationNotImplemented(self.change_vanity_code.__name__)

    def get_all_guild_channels(self, guild_id: Snowflake) -> Response[List[guild.GuildChannel]]:
        raise TestOperationNotImplemented(self.get_all_guild_channels.__name__)

    def get_members(
        self, guild_id: Snowflake, limit: int, after: Optional[Snowflake]
    ) -> Response[List[member.MemberWithUser]]:
        raise TestOperationNotImplemented(self.get_members.__name__)

    async def get_member(self, guild_id: int, member_id: int) -> _types.JsonDict:
        locs = _get_higher_locs(1)
        guild = locs.get("self", None)
        member = discord.utils.get(guild.members, id=member_id)

        return facts.dict_from_member(member)

    def prune_members(
            self,
            guild_id: Snowflake,
            days: int,
            compute_prune_count: bool,
            roles: List[str],
            *,
            reason: Optional[str] = None,
    ) -> Response[guild.GuildPrune]:
        raise TestOperationNotImplemented(self.prune_members.__name__)

    def estimate_pruned_members(
        self,
        guild_id: Snowflake,
        days: int,
        roles: List[str],
    ) -> Response[guild.GuildPrune]:
        raise TestOperationNotImplemented(self.estimate_pruned_members.__name__)

    def get_sticker(self, sticker_id: Snowflake) -> Response[sticker.Sticker]:
        raise TestOperationNotImplemented(self.get_sticker.__name__)

    def list_premium_sticker_packs(self) -> Response[sticker.ListPremiumStickerPacks]:
        raise TestOperationNotImplemented(self.list_premium_sticker_packs.__name__)

    def get_all_guild_stickers(self, guild_id: Snowflake) -> Response[List[sticker.GuildSticker]]:
        raise TestOperationNotImplemented(self.get_all_guild_stickers.__name__)

    def get_guild_sticker(self, guild_id: Snowflake, sticker_id: Snowflake) -> Response[sticker.GuildSticker]:
        raise TestOperationNotImplemented(self.get_guild_sticker.__name__)

    def create_guild_sticker(
        self, guild_id: Snowflake, payload: sticker.CreateGuildSticker, file: File, reason: str
    ) -> Response[sticker.GuildSticker]:
        raise TestOperationNotImplemented(self.create_guild_sticker.__name__)

    def modify_guild_sticker(
        self, guild_id: Snowflake, sticker_id: Snowflake, payload: sticker.EditGuildSticker, reason: Optional[str],
    ) -> Response[sticker.GuildSticker]:
        raise TestOperationNotImplemented(self.modify_guild_sticker.__name__)

    def delete_guild_sticker(self, guild_id: Snowflake, sticker_id: Snowflake, reason: Optional[str]) -> Response[None]:
        raise TestOperationNotImplemented(self.delete_guild_sticker.__name__)

    def get_all_custom_emojis(self, guild_id: Snowflake) -> Response[List[emoji.Emoji]]:
        raise TestOperationNotImplemented(self.get_all_custom_emojis.__name__)

    def get_custom_emoji(self, guild_id: Snowflake, emoji_id: Snowflake) -> Response[emoji.Emoji]:
        raise TestOperationNotImplemented(self.get_custom_emoji.__name__)

    def create_custom_emoji(
        self,
        guild_id: Snowflake,
        name: str,
        image: bytes,
        *,
        roles: Optional[SnowflakeList] = None,
        reason: Optional[str] = None,
    ) -> Response[emoji.Emoji]:
        raise TestOperationNotImplemented(self.create_custom_emoji.__name__)

    def delete_custom_emoji(
        self,
        guild_id: Snowflake,
        emoji_id: Snowflake,
        *,
        reason: Optional[str] = None,
    ) -> Response[None]:
        raise TestOperationNotImplemented(self.delete_custom_emoji.__name__)

    def edit_custom_emoji(
        self,
        guild_id: Snowflake,
        emoji_id: Snowflake,
        *,
        payload: Dict[str, Any],
        reason: Optional[str] = None,
    ) -> Response[emoji.Emoji]:
        raise TestOperationNotImplemented(self.edit_custom_emoji.__name__)

    def get_all_integrations(self, guild_id: Snowflake) -> Response[List[integration.Integration]]:
        raise TestOperationNotImplemented(self.get_all_integrations.__name__)

    def create_integration(self, guild_id: Snowflake, type: integration.IntegrationType, id: int) -> Response[None]:
        raise TestOperationNotImplemented(self.create_integration.__name__)

    def edit_integration(self, guild_id: Snowflake, integration_id: Snowflake, **payload: Any) -> Response[None]:
        raise TestOperationNotImplemented(self.edit_integration.__name__)

    def sync_integration(self, guild_id: Snowflake, integration_id: Snowflake) -> Response[None]:
        raise TestOperationNotImplemented(self.sync_integration.__name__)

    def delete_integration(
        self, guild_id: Snowflake, integration_id: Snowflake, *, reason: Optional[str] = None
    ) -> Response[None]:
        raise TestOperationNotImplemented(self.delete_integration.__name__)

    def get_audit_logs(
        self,
        guild_id: Snowflake,
        limit: int = 100,
        before: Optional[Snowflake] = None,
        after: Optional[Snowflake] = None,
        user_id: Optional[Snowflake] = None,
        action_type: Optional[AuditLogAction] = None,
    ) -> Response[audit_log.AuditLog]:
        raise TestOperationNotImplemented(self.get_audit_logs.__name__)

    def get_widget(self, guild_id: Snowflake) -> Response[widget.Widget]:
        raise TestOperationNotImplemented(self.get_widget.__name__)

    def edit_widget(self, guild_id: Snowflake, payload) -> Response[widget.WidgetSettings]:
        raise TestOperationNotImplemented(self.edit_widget.__name__)

    # Invite management

    def create_invite(
        self,
        channel_id: Snowflake,
        *,
        reason: Optional[str] = None,
        max_age: int = 0,
        max_uses: int = 0,
        temporary: bool = False,
        unique: bool = True,
        target_type: Optional[invite.InviteTargetType] = None,
        target_user_id: Optional[Snowflake] = None,
        target_application_id: Optional[Snowflake] = None,
    ) -> Response[invite.Invite]:
        raise TestOperationNotImplemented(self.create_invite.__name__)

    def get_invite(
        self, invite_id: str, *, with_counts: bool = True, with_expiration: bool = True, guild_scheduled_event_id: Optional[int] = None
    ) -> Response[invite.Invite]:
        raise TestOperationNotImplemented(self.get_invite.__name__)

    def invites_from(self, guild_id: Snowflake) -> Response[List[invite.Invite]]:
        raise TestOperationNotImplemented(self.invites_from.__name__)

    def invites_from_channel(self, channel_id: Snowflake) -> Response[List[invite.Invite]]:
        raise TestOperationNotImplemented(self.invites_from_channel.__name__)

    def delete_invite(self, invite_id: str, *, reason: Optional[str] = None) -> Response[None]:
        raise TestOperationNotImplemented(self.delete_invite.__name__)

    # Role management

    def get_roles(self, guild_id: Snowflake) -> Response[List[role.Role]]:
        raise TestOperationNotImplemented(self.get_roles.__name__)

    async def edit_role(
        self, guild_id: Snowflake, role_id: Snowflake, *, reason: Optional[str] = None, **fields: Any
    ) -> _types.JsonDict:
        locs = _get_higher_locs(1)
        role = locs.get("self")
        guild = role.guild

        await callbacks.dispatch_event("edit_role", guild, role, fields, reason=reason)

        back.update_role(role, **fields)
        return facts.dict_from_role(role)

    async def delete_role(self, guild_id: Snowflake, role_id: Snowflake, *, reason: Optional[str] = None) -> None:
        locs = _get_higher_locs(1)
        role = locs.get("self")
        guild = role.guild

        await callbacks.dispatch_event("delete_role", guild, role, reason=reason)

        back.delete_role(role)

    def replace_roles(
        self,
        user_id: Snowflake,
        guild_id: Snowflake,
        role_ids: List[int],
        *,
        reason: Optional[str] = None,
    ) -> Response[member.MemberWithUser]:
        raise TestOperationNotImplemented(self.replace_roles.__name__)

    async def create_role(self, guild_id: Snowflake, *, reason: Optional[str] = None, **fields: Any) -> _types.JsonDict:
        locs = _get_higher_locs(1)
        guild = locs.get("self", None)
        role = back.make_role(guild=guild, **fields, )

        await callbacks.dispatch_event("create_role", guild, role, reason=reason)

        return facts.dict_from_role(role)

    async def move_role_position(
        self,
        guild_id: Snowflake,
        positions: List[guild.RolePositionUpdate],
        *,
        reason: Optional[str] = None,
    ) -> None:
        locs = _get_higher_locs(1)
        role = locs.get("self", None)
        guild = role.guild

        await callbacks.dispatch_event("move_role", guild, role, positions, reason=reason)

        for pair in positions:
            guild._roles[pair["id"]].position = pair["position"]

    async def add_role(
        self, guild_id: Snowflake, user_id: Snowflake, role_id: Snowflake, *, reason: Optional[str] = None
    ) -> None:
        locs = _get_higher_locs(1)
        member = locs.get("self", None)
        role = locs.get("role", None)

        await callbacks.dispatch_event("add_role", member, role, reason=reason)

        roles = [role] + [x for x in member.roles if x.id != member.guild.id]
        back.update_member(member, roles=roles)

    async def remove_role(
        self, guild_id: Snowflake, user_id: Snowflake, role_id: Snowflake, *, reason: Optional[str] = None
    ) -> None:
        locs = _get_higher_locs(1)
        member = locs.get("self", None)
        role = locs.get("role", None)

        await callbacks.dispatch_event("remove_role", member, role, reason=reason)

        roles = [x for x in member.roles if x != role and x.id != member.guild.id]
        back.update_member(member, roles=roles)

    async def edit_channel_permissions(
        self,
        channel_id: Snowflake,
        target: Snowflake,
        allow: Snowflake,
        deny: Snowflake,
        type: channel.OverwriteType,
        *,
        reason: Optional[str] = None,
    ) -> None:
        locs = _get_higher_locs(1)
        channel: discord.TextChannel = locs.get("self", None)
        targeted = locs.get("target", None)

        user = self.state.user
        perm: discord.Permissions = channel.permissions_for(channel.guild.get_member(user.id))
        if not (perm.administrator or perm.manage_permissions):
            raise Forbidden(FakeRequest(403, "missing manage_roles"), "manage_roles")

        ovr = discord.PermissionOverwrite.from_pair(discord.Permissions(allow), discord.Permissions(deny))
        back.update_text_channel(channel, targeted, ovr)

    async def delete_channel_permissions(
        self, channel_id: Snowflake, target: channel.OverwriteType, *, reason: Optional[str] = None
    ) -> None:
        locs = _get_higher_locs(1)
        channel: discord.TextChannel = locs.get("self", None)
        target = locs.get("target", None)

        user = self.state.user
        perm: discord.Permissions = channel.permissions_for(channel.guild.get_member(user.id))
        if not (perm.administrator or perm.manage_permissions):
            raise Forbidden(FakeRequest(403, "missing manage_roles"), "manage_roles")

        back.update_text_channel(channel, target, None)

    # Welcome Screen

    def get_welcome_screen(self, guild_id: Snowflake) -> Response[welcome_screen.WelcomeScreen]:
        raise TestOperationNotImplemented(self.get_welcome_screen.__name__)

    def edit_welcome_screen(self, guild_id: Snowflake, payload: Any, *, reason: Optional[str] = None) -> Response[welcome_screen.WelcomeScreen]:
        raise TestOperationNotImplemented(self.edit_welcome_screen.__name__)

    # Voice management

    def move_member(
        self,
        user_id: Snowflake,
        guild_id: Snowflake,
        channel_id: Snowflake,
        *,
        reason: Optional[str] = None,
    ) -> Response[member.MemberWithUser]:
        raise TestOperationNotImplemented(self.move_member.__name__)

    # Stage instance management

    def get_stage_instance(self, channel_id: Snowflake) -> Response[channel.StageInstance]:
        raise TestOperationNotImplemented(self.get_stage_instance.__name__)

    def create_stage_instance(self, *, reason: Optional[str], **payload: Any) -> Response[channel.StageInstance]:
        raise TestOperationNotImplemented(self.create_stage_instance.__name__)

    def edit_stage_instance(self, channel_id: Snowflake, *, reason: Optional[str] = None, **payload: Any) -> Response[None]:
        raise TestOperationNotImplemented(self.edit_stage_instance.__name__)

    def delete_stage_instance(self, channel_id: Snowflake, *, reason: Optional[str] = None) -> Response[None]:
        raise TestOperationNotImplemented(self.delete_stage_instance.__name__)

    # Guild scheduled events management

    def get_scheduled_events(self, guild_id: Snowflake, with_user_count: bool = True) -> Response[List[scheduled_events.ScheduledEvent]]:
        raise TestOperationNotImplemented(self.get_scheduled_events.__name__)

    def get_scheduled_event(self, guild_id: Snowflake, event_id: Snowflake, with_user_count: bool = True) -> Response[scheduled_events.ScheduledEvent]:
        raise TestOperationNotImplemented(self.get_scheduled_event.__name__)

    def create_scheduled_event(self, guild_id: Snowflake, reason: Optional[str] = None, **payload: Any) -> Response[scheduled_events.ScheduledEvent]:
        raise TestOperationNotImplemented(self.create_scheduled_event.__name__)

    def delete_scheduled_event(self, guild_id: Snowflake, event_id: Snowflake) -> Response[None]:
        raise TestOperationNotImplemented(self.delete_scheduled_event.__name__)

    def edit_scheduled_event(self, guild_id: Snowflake, event_id: Snowflake, reason: Optional[str] = None, **payload: Any) -> Response[scheduled_events.ScheduledEvent]:
        raise TestOperationNotImplemented(self.edit_scheduled_event.__name__)

    def get_scheduled_event_users(
        self,
        guild_id: Snowflake,
        event_id: Snowflake,
        limit: int,
        with_member: bool = False,
        before: Snowflake = None,
        after: Snowflake = None
    ) -> Response[List[scheduled_events.ScheduledEventSubscriber]]:
        raise TestOperationNotImplemented(self.get_scheduled_event_users.__name__)

    # Application commands (global)

    def get_global_commands(self, application_id: Snowflake) -> Response[List[interactions.ApplicationCommand]]:
        raise TestOperationNotImplemented(self.get_global_commands.__name__)

    def get_global_command(
        self, application_id: Snowflake, command_id: Snowflake
    ) -> Response[interactions.ApplicationCommand]:
        raise TestOperationNotImplemented(self.get_global_command.__name__)

    def upsert_global_command(self, application_id: Snowflake, payload) -> Response[interactions.ApplicationCommand]:
        raise TestOperationNotImplemented(self.upsert_global_command.__name__)

    def edit_global_command(
        self,
        application_id: Snowflake,
        command_id: Snowflake,
        payload: interactions.EditApplicationCommand,
    ) -> Response[interactions.ApplicationCommand]:
        raise TestOperationNotImplemented(self.edit_global_command.__name__)

    def delete_global_command(self, application_id: Snowflake, command_id: Snowflake) -> Response[None]:
        raise TestOperationNotImplemented(self.delete_global_command.__name__)

    def bulk_upsert_global_commands(
        self, application_id: Snowflake, payload
    ) -> Response[List[interactions.ApplicationCommand]]:
        raise TestOperationNotImplemented(self.bulk_upsert_global_commands.__name__)

    # Application commands (guild)

    def get_guild_commands(
        self, application_id: Snowflake, guild_id: Snowflake
    ) -> Response[List[interactions.ApplicationCommand]]:
        raise TestOperationNotImplemented(self.get_guild_commands.__name__)

    def get_guild_command(
        self,
        application_id: Snowflake,
        guild_id: Snowflake,
        command_id: Snowflake,
    ) -> Response[interactions.ApplicationCommand]:
        raise TestOperationNotImplemented(self.get_guild_command.__name__)

    def upsert_guild_command(
        self,
        application_id: Snowflake,
        guild_id: Snowflake,
        payload: interactions.EditApplicationCommand,
    ) -> Response[interactions.ApplicationCommand]:
        raise TestOperationNotImplemented(self.upsert_guild_command.__name__)

    def edit_guild_command(
        self,
        application_id: Snowflake,
        guild_id: Snowflake,
        command_id: Snowflake,
        payload: interactions.EditApplicationCommand,
    ) -> Response[interactions.ApplicationCommand]:
        raise TestOperationNotImplemented(self.edit_guild_command.__name__)

    def delete_guild_command(
        self,
        application_id: Snowflake,
        guild_id: Snowflake,
        command_id: Snowflake,
    ) -> Response[None]:
        raise TestOperationNotImplemented(self.delete_guild_command.__name__)

    def bulk_upsert_guild_commands(
        self,
        application_id: Snowflake,
        guild_id: Snowflake,
        payload: List[interactions.EditApplicationCommand],
    ) -> Response[List[interactions.ApplicationCommand]]:
        raise TestOperationNotImplemented(self.bulk_upsert_guild_commands.__name__)

    def bulk_upsert_command_permissions(
        self,
        application_id: Snowflake,
        guild_id: Snowflake,
        payload: List[interactions.EditApplicationCommand],
    ) -> Response[List[interactions.ApplicationCommand]]:
        raise TestOperationNotImplemented(self.bulk_upsert_command_permissions.__name__)

    # Interaction responses

    def _edit_webhook_helper(
        self,
        route: dhttp.Route,
        file: Optional[File] = None,
        content: Optional[str] = None,
        embeds: Optional[List[embed.Embed]] = None,
        allowed_mentions: Optional[message.AllowedMentions] = None,
    ):
        raise TestOperationNotImplemented(self._edit_webhook_helper.__name__)

    def create_interaction_response(
        self,
        interaction_id: Snowflake,
        token: str,
        *,
        type: InteractionResponseType,
        data: Optional[interactions.InteractionApplicationCommandCallbackData] = None,
    ) -> Response[None]:
        raise TestOperationNotImplemented(self.create_interaction_response.__name__)

    def get_original_interaction_response(
        self,
        application_id: Snowflake,
        token: str,
    ) -> Response[message.Message]:
        raise TestOperationNotImplemented(self.get_original_interaction_response.__name__)

    def edit_original_interaction_response(
        self,
        application_id: Snowflake,
        token: str,
        file: Optional[File] = None,
        content: Optional[str] = None,
        embeds: Optional[List[embed.Embed]] = None,
        allowed_mentions: Optional[message.AllowedMentions] = None,
    ) -> Response[message.Message]:
        raise TestOperationNotImplemented(self.edit_original_interaction_response.__name__)

    def delete_original_interaction_response(self, application_id: Snowflake, token: str) -> Response[None]:
        raise TestOperationNotImplemented(self.delete_original_interaction_response.__name__)

    def create_followup_message(
        self,
        application_id: Snowflake,
        token: str,
        files: List[File] = [],
        content: Optional[str] = None,
        tts: bool = False,
        embeds: Optional[List[embed.Embed]] = None,
        allowed_mentions: Optional[message.AllowedMentions] = None,
    ) -> Response[message.Message]:
        raise TestOperationNotImplemented(self.create_followup_message.__name__)

    def edit_followup_message(
        self,
        application_id: Snowflake,
        token: str,
        message_id: Snowflake,
        file: Optional[File] = None,
        content: Optional[str] = None,
        embeds: Optional[List[embed.Embed]] = None,
        allowed_mentions: Optional[message.AllowedMentions] = None,
    ) -> Response[message.Message]:
        raise TestOperationNotImplemented(self.edit_followup_message.__name__)

    def delete_followup_message(self, application_id: Snowflake, token: str, message_id: Snowflake) -> Response[None]:
        raise TestOperationNotImplemented(self.delete_followup_message.__name__)

    def get_guild_application_command_permissions(
        self,
        application_id: Snowflake,
        guild_id: Snowflake,
    ) -> Response[List[interactions.GuildApplicationCommandPermissions]]:
        raise TestOperationNotImplemented(self.delete_followup_message.__name__)

    def get_application_command_permissions(
        self,
        application_id: Snowflake,
        guild_id: Snowflake,
        command_id: Snowflake,
    ) -> Response[interactions.GuildApplicationCommandPermissions]:
        raise TestOperationNotImplemented(self.get_application_command_permissions.__name__)

    def edit_application_command_permissions(
        self,
        application_id: Snowflake,
        guild_id: Snowflake,
        command_id: Snowflake,
        payload: interactions.BaseGuildApplicationCommandPermissions,
    ) -> Response[None]:
        raise TestOperationNotImplemented(self.edit_application_command_permissions.__name__)

    def bulk_edit_guild_application_command_permissions(
        self,
        application_id: Snowflake,
        guild_id: Snowflake,
        payload: List[interactions.PartialGuildApplicationCommandPermissions],
    ) -> Response[None]:
        raise TestOperationNotImplemented(self.bulk_edit_guild_application_command_permissions.__name__)

    # Misc

    async def application_info(self) -> _types.JsonDict:
        # TODO: make these values configurable
        user = self.state.user
        data = {
            "id": user.id,
            "name": user.name,
            "icon": user.avatar,
            "description": "A test discord application",
            "rpc_origins": None,
            "bot_public": True,
            "bot_require_code_grant": False,
            "owner": facts.make_user_dict("TestOwner", "0001", None),
            "summary": None,
            "verify_key": None
        }

        appinfo = discord.AppInfo(self.state, data)
        await callbacks.dispatch_event("app_info", appinfo)

        return data

    async def get_gateway(self, *, encoding: str = 'json', zlib: bool = True) -> str:
        raise TestOperationNotImplemented(self.get_gateway.__name__)


    async def get_bot_gateway(self, *, encoding: str = 'json', zlib: bool = True) -> Tuple[int, str]:
        raise TestOperationNotImplemented(self.get_bot_gateway.__name__)

    async def get_user(self, user_id: int) -> _types.JsonDict:
        locs = _get_higher_locs(1)
        client = locs.get("self", None)
        guild = client.guilds[0]
        member = discord.utils.get(guild.members, id=user_id)
        return facts.dict_from_user(member._user)

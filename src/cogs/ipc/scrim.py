from __future__ import annotations
import typing

if typing.TYPE_CHECKING:
    from core import Quotient

from .base import IpcCog
from models import Guild, Scrim, Timer
from discord.ext import ipc
import discord
from constants import IST
from datetime import datetime, timedelta


class ScrimIpc(IpcCog):
    def __init__(self, bot: Quotient):
        self.bot = bot

    @ipc.server.route()
    async def create_new_scrim(self, payload):
        data = payload.data

        guild = self.bot.get_guild(int(data.get("guild_id")))
        if not guild:
            return self.deny_request("Quotient have been removed from the server.")

        if not (await Guild.get(guild_id=guild.id)).private_ch:
            return self.deny_request(
                "You haven't done Quotient setup in your server yet, kindly run qsetup command once and try again."
            )

        perms = guild.me.guild_permissions
        if not all((perms.manage_channels, perms.manage_roles)):
            return self.deny_request("Quotient needs manage_channels and manage_roles permission in the server.")

        scrim = Scrim(guild_id=guild.id, host_id=int(data.get("host_id")), name=data.get("name"))

        registration_channel = self.bot.get_channel(int(data.get("registration_channel_id")))
        if not registration_channel:
            return self.deny_request(
                "Quotient cannot see registration channel , Make sure it has appropriate permissions."
            )

        perms = registration_channel.permissions_for(guild.me)
        if not all(
            (perms.send_messages, perms.manage_messages, perms.manage_channels, perms.add_reactions, perms.embed_links)
        ):
            return self.deny_request("Quotient do not have required permissions in the registration channel.")

        if await Scrim.filter(registration_channel_id=registration_channel.id):
            return self.deny_request("The registration channel you selected is already assigned to another scrim.")

        scrim.registration_channel_id = registration_channel.id

        slotlist_channel = self.bot.get_channel(int(data.get("slotlist_channel_id")))
        if not slotlist_channel:
            return self.deny_request(
                "Quotient cannot see slotlist channel , Can you make sure it has appropriate permissions?"
            )

        perms = slotlist_channel.permissions_for(guild.me)
        if not all(
            (perms.send_messages, perms.manage_messages, perms.manage_channels, perms.add_reactions, perms.embed_links)
        ):
            return self.deny_request("Quotient do not have required permissions in the Slotlist channel.")

        scrim.slotlist_channel_id = slotlist_channel.id

        role = guild.get_role(int(data.get("role_id")))

        _list = [
            k
            for k, v in dict(role.permissions).items()
            if v is True and k in ("manage_channels", "manage_guild", "manage_messages", "manage_roles", "administrator")
        ]
        if _list:
            return self.deny_request("Success role contains some moderation permissions, kindly remove them first.")

        scrim.role_id = role.id

        epoch = datetime(1970, 1, 1)

        scrim.required_mentions = data.get("required_mentions")
        scrim.total_slots = data.get("total_slots")
        scrim.open_time = IST.localize(epoch + timedelta(hours=5, minutes=30, milliseconds=data.get("open_time")))

        await scrim.save()
        await self.bot.reminders.create_timer(scrim.open_time, "scrim_open", scrim_id=scrim.id)

        reason = "Created for scrims management."

        scrims_mod = discord.utils.get(guild.roles, name="scrims-mod")

        if scrims_mod is None:
            scrims_mod = await guild.create_role(name="scrims-mod", color=0x00FFB3, reason=reason)

        overwrite = registration_channel.overwrites_for(guild.default_role)
        overwrite.update(read_messages=True, send_messages=True, read_message_history=True)
        await registration_channel.set_permissions(scrims_mod, overwrite=overwrite)

        scrims_log_channel = discord.utils.get(guild.text_channels, name="quotient-scrims-logs")

        if scrims_log_channel is None:
            overwrites = {
                guild.default_role: discord.PermissionOverwrite(read_messages=False),
                guild.me: discord.PermissionOverwrite(read_messages=True),
                scrims_mod: discord.PermissionOverwrite(read_messages=True),
            }
            scrims_log_channel = await guild.create_text_channel(
                name="quotient-scrims-logs",
                overwrites=overwrites,
                reason=reason,
            )

            # Sending Message to scrims-log-channel
            note = await scrims_log_channel.send(
                embed=discord.Embed(
                    description=f"If events related to scrims i.e opening registrations or adding roles, "
                    f"etc are triggered, then they will be logged in this channel. "
                    f"Also I have created {scrims_mod.mention}, you can give that role to your "
                    f"scrims-moderators. User with {scrims_mod.mention} can also send messages in "
                    f"registration channels and they won't be considered as scrims-registration.\n\n"
                    f"`Note`: **Do not rename this channel.**",
                    color=discord.Color(self.bot.color),
                )
            )
            await note.pin()

        return self.positive

    @ipc.server.route()
    async def edit_scrim(self, payload):
        data = payload.data

        guild = self.bot.get_guild(int(data.get("guild_id")))

        if not guild:
            return self.not_guild

        scrim = await Scrim.get_or_none(id=int(data.get("id")))

        if not scrim:
            return self.deny_request("Either this scrim was deleted or Quotient was removed from the server.")

        _dict = {
            "name": data.get("name"),
            "required_mentions": int(data.get("required_mentions")),
            "start_from": int(data.get("start_from")),
            "total_slots": int(data.get("total_slots")),
            "autoslotlist": data.get("autoslotlist"),
            "multiregister": data.get("multiregister"),
            "autodelete_rejects": data.get("autodelete_rejects"),
            "teamname_compulsion": data.get("teamname_compulsion"),
            "no_duplicate_name": data.get("no_duplicate_name"),
            "show_time_elapsed": data.get("show_time_elapsed"),
            "open_message": data.get("open_message"),
            "close_message": data.get("close_message"),
            "autodelete_extras": data.get("autodelete_extras"),
        }

        registration_channel_id = int(data.get("registration_channel_id"))
        if not scrim.registration_channel_id == registration_channel_id:
            registration_channel = self.bot.get_channel(int(payload.data.get("registration_channel_id")))

            if not registration_channel:
                return self.deny_request(
                    "Quotient cannot see registration channel , Make sure it has appropriate permissions."
                )

            perms = registration_channel.permissions_for(guild.me)
            if not all(
                (
                    perms.send_messages,
                    perms.manage_messages,
                    perms.manage_channels,
                    perms.add_reactions,
                    perms.embed_links,
                )
            ):
                return self.deny_request("Quotient do not have required permissions in the registration channel.")

            if await Scrim.filter(registration_channel_id=registration_channel.id):
                return self.deny_request("The registration channel you selected is already assigned to another scrim.")

            _dict["registration_channel_id"] = registration_channel.id

        slotlist_channel_id = int(data.get("slotlist_channel_id"))
        if not scrim.slotlist_channel_id == slotlist_channel_id:
            slotlist_channel = self.bot.get_channel(int(payload.data.get("slotlist_channel_id")))
            if not slotlist_channel:
                return await self.deny_request(
                    payload, "Quotient cannot see slotlist channel , Can you make sure it has appropriate permissions?"
                )

            perms = slotlist_channel.permissions_for(guild.me)
            if not all(
                (
                    perms.send_messages,
                    perms.manage_messages,
                    perms.manage_channels,
                    perms.add_reactions,
                    perms.embed_links,
                )
            ):
                return await self.deny_request(
                    payload, "Quotient do not have required permissions in the Slotlist channel."
                )

            _dict["slotlist_channel_id"] = slotlist_channel_id

        role_id = int(data.get("role_id"))
        if not scrim.role_id == role_id:
            role = guild.get_role(int(payload.data.get("role_id")))

            _list = [
                k
                for k, v in dict(role.permissions).items()
                if v is True
                and k in ("manage_channels", "manage_guild", "manage_messages", "manage_roles", "administrator")
            ]
            if _list:
                return await self.deny_request(
                    payload, "Success role contains some moderation permissions, kindly remove them first."
                )

            _dict["role_id"] = role.id

        ping_role_id = data.get("ping_role_id")
        if ping_role_id and int(ping_role_id) != scrim.ping_role_id:
            _dict["ping_role_id"] = int(ping_role_id)

        _dict["open_role_id"] = int(data.get("open_role_id"))

        epoch = datetime(1970, 1, 1)

        open_time = IST.localize(epoch + timedelta(hours=5, minutes=30, milliseconds=int(data.get("open_time"))))

        _dict["open_time"] = open_time

        if data.get("autoclean_time"):
            autoclean_time = IST.localize(
                epoch + timedelta(hours=5, minutes=30, milliseconds=int(data.get("autoclean_time")))
            )
            if datetime.now(tz=IST) > autoclean_time:
                autoclean_time = autoclean_time + timedelta(hours=24)

            _dict["autoclean_time"] = autoclean_time
            await Timer.filter(
                extra={"args": [], "kwargs": {"scrim_id": int(data.get("id"))}}, event="autoclean"
            ).delete()

            await self.bot.reminders.create_timer(autoclean_time, "autoclean", scrim_id=int(data.get("id")))

        await Scrim.filter(id=int(data.get("id"))).update(**_dict)
        await self.bot.db.execute(
            """UPDATE public."sm.scrims" SET autoclean = $1 , open_days = $2 WHERE id = $3""",
            data.get("autoclean"),
            data.get("open_days"),
            int(data.get("id")),
        )
        await Timer.filter(extra={"args": [], "kwargs": {"scrim_id": int(data.get("id"))}}, event="scrim_open").delete()

        await self.bot.reminders.create_timer(open_time, "scrim_open", scrim_id=int(data.get("id")))

        return self.positive

    @ipc.server.route()
    async def delete_scrim(self, payload):
        await Scrim.filter(pk=int(payload.scrim_id)).delete()
        return self.positive
